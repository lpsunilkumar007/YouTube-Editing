"""Stage 'metadata': YouTube publishing text for the FINAL edit.

Deterministic here: chapters (face-time markers -> final-edit times via the EDL, validated against YouTube's rules:
first at 0:00, >= 3 chapters, each >= 10 s, ascending), tags (<= 500 chars), hashtags, verbatim credits from
config/credits.json, link placeholders ({{...}}) for anything not supplied, and a content brief (per-chapter transcript)
from which titles/description prose are written. Creative text lives in metadata/description_input.json (written by
Claude from the brief, reviewed by the user) and is validated: no URLs except configured links/credits, no unresolved
placeholders unless declared, title lengths, chapter list identical to youtube_chapters.txt."""
import json, os, re

def edit_time(F, edl):
    for s in edl:
        if s["face_in"] - 1e-6 <= F <= s["face_out"] + 1e-6:
            return s["edit_start"] + F - s["face_in"]
    raise ValueError(f"face time {F} is not in the final edit")

def fmt(t):
    t = int(t); h, m, s = t // 3600, t // 60 % 60, t % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"

def chapters(markers, edl, duration):
    """markers: [(face_time, title)] -> [(edit_seconds, title)] with the first forced to 0:00; raises on rule violations."""
    ch = sorted((edit_time(F, edl), t) for F, t in markers)
    ch[0] = (0.0, ch[0][1])
    errs = []
    if len(ch) < 3: errs.append("YouTube needs >= 3 chapters")
    for (a, t), (b, _) in zip(ch, ch[1:] + [(duration, None)]):
        if b - a < 10: errs.append(f"chapter '{t}' shorter than 10 s")
    if [fmt(a) for a, _ in ch] != sorted({fmt(a) for a, _ in ch}, key=lambda x: [int(p) for p in x.split(":")]):
        errs.append("chapter times not strictly ascending")
    if errs: raise ValueError("; ".join(errs))
    return ch

def content_brief(lines, edl, ch, out_md):
    """Per chapter: the transcript text that is IN the final edit (cut lines excluded) -> basis for all prose."""
    with open(out_md, "w", encoding="utf-8") as f:
        f.write("# Content brief (source for titles, description, thumbnails and Shorts; from the final edit)\n\n")
        bounds = [a for a, _ in ch] + [1e9]
        for k, (a, t) in enumerate(ch):
            f.write(f"## {fmt(a)} {t}\n\n")
            for ln in lines:
                try: e = edit_time(ln["face"], edl)
                except ValueError: continue
                if bounds[k] <= e < bounds[k + 1]:
                    f.write(f"- [{fmt(e)}] {ln['text']}{'  ⟨' + ','.join(sorted(ln['flags'])) + '⟩' if ln['flags'] else ''}\n")
            f.write("\n")

def tags_line(tags, limit=500):
    out, n = [], 0
    for t in dict.fromkeys(x.strip() for x in tags if x.strip()):
        add = len(t) + (2 if " " in t else 0) + (1 if out else 0)        # YouTube counts quotes around multi-word tags
        if n + add > limit: break
        out.append(t); n += add
    return out

def credits_block(cfg, ids):
    cr = json.load(open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), cfg["youtube"]["credits"]), encoding="utf-8"))
    return "\n\n".join(cr[i]["attribution"] for i in ids), [cr[i] for i in ids]

URL = re.compile(r"https?://\S+")

def seo(cfg, inp, desc, ch, tags, today=None):
    """Title/description rules from the research (youtube.seo): satisfaction over clicks (no clickbait, promise only what
    the video delivers), the searched phrase early in the title and the description's first lines, a title that is not
    cut off on phones, enough description context, tag variants, YouTube's chapter rules, no lesson numbers, and a dated
    research note with sources for every video (inp["research"]: {date, sources, search_phrases})."""
    import datetime
    S = cfg["youtube"]["seo"]; p = []; r = inp.get("research") or {}
    rec = inp["titles"][inp["recommended"] - 1]["title"]; norm = lambda s: re.sub(r"[^a-z0-9%]+", " ", s.lower()).strip()
    phrases = [norm(x) for x in r.get("search_phrases", [])]
    if not r: p.append("no 'research' in description_input.json: research titles/search phrases for this video first (date, sources, search_phrases)")
    else:
        if len(r.get("sources", [])) < S["min_sources"]: p.append(f"research: cite at least {S['min_sources']} sources")
        if not phrases: p.append("research: list the search_phrases viewers use")
        try:
            age = ((today or datetime.date.today()) - datetime.date.fromisoformat(r.get("date", ""))).days
            if age > S["research_max_age_days"]: p.append(f"research is {age} days old: refresh it")
        except ValueError: p.append("research: date must be YYYY-MM-DD")
    if len(rec) > S["title_mobile_chars"]: p.append(f"recommended title is {len(rec)} chars: over {S['title_mobile_chars']} it is cut off on phones")
    if phrases and not any(norm(rec).find(ph) != -1 and norm(rec).find(ph) <= S["phrase_within_chars"] for ph in phrases):
        p.append("recommended title does not start with a researched search phrase")
    if phrases and not any(ph in norm(inp["intro"][:200]) for ph in phrases): p.append("description intro does not use a researched search phrase")
    for x in [t["title"] for t in inp["titles"]] + [desc, inp["pinned_comment"]]:
        if re.search(r"\blesson\s*0*\d+\b", x, re.I): p.append(f"lesson number in viewer-facing text: {x[:60]}")
        bait = [w for w in S["clickbait"] if w in x.lower()]
        if bait: p.append(f"clickbait wording {bait}: {x[:60]}")
    for t in inp["titles"]:
        caps = [w for w in re.findall(r"[A-Za-z]{5,}", t["title"]) if w.isupper()]
        if caps: p.append(f"all-caps words read as clickbait: {caps} in {t['title']}")
    words = len(re.findall(r"\w+", desc.split("**Music**")[0]))
    if words < S["description_min_words"]: p.append(f"description has {words} words (aim for {S['description_min_words']}+ for context)")
    lo, hi = S["tags_range"]
    if not lo <= len(tags) <= hi: p.append(f"{len(tags)} tags (aim for {lo}-{hi}, incl. spelling variants)")
    if len(ch) < 3 or ch[0][0] != 0 or any(b[0] - a[0] < 10 for a, b in zip(ch, ch[1:])):
        p.append("chapters must start at 0:00, be at least 3 and each at least 10 s (YouTube Help)")
    return p

def build(cfg, ch, inp):
    """inp = description_input.json content. Writes youtube_description.md, youtube_chapters.txt, youtube_tags.txt,
    youtube_hashtags.txt, pinned_comment.md, youtube_titles.md into metadata/. Returns (paths, problems)."""
    M = cfg["paths"]["metadata"]; os.makedirs(M, exist_ok=True); probs = []
    chap = "\n".join(f"{fmt(a)} {t}" for a, t in ch)
    music_ids = [cfg["audio"]["music"]["credit_id"]] if cfg["audio"]["music"]["enabled"] else []
    cred_text, cred = credits_block(cfg, music_ids + inp.get("extra_credit_ids", []))
    tags = tags_line(inp["tags"], cfg["youtube"]["tags_max_chars"])
    hashtags = [h if h.startswith("#") else "#" + h for h in inp["hashtags"]][: cfg["youtube"]["hashtags_max"]]
    links = cfg["youtube"]["links"]
    res = "\n".join(f"- {r['label']}: {links.get(r['link'], r['link'])}" for r in inp.get("resources", []))
    desc = "\n\n".join(x for x in [
        inp["intro"], "**What you will learn**\n" + "\n".join(f"- {x}" for x in inp["learn"]),
        "**Concepts covered**\n" + "\n".join(f"- {x}" for x in inp["concepts"]),
        "**Examples in this video**\n" + "\n".join(f"- {x}" for x in inp["examples"]),
        "**Chapters**\n" + chap,
        ("**Prerequisites**\n" + inp["prerequisites"]) if inp.get("prerequisites") else "",
        ("**Resources**\n" + res) if res else "",
        inp["cta"], " ".join(hashtags),
        "**Music**\n" + cred_text + "\n\n(Attribution is required by the licence; it does not guarantee that no Content ID claim will appear.)" if cred_text else ""] if x)
    files = {"youtube_description.md": desc + "\n", "youtube_chapters.txt": chap + "\n", "youtube_tags.txt": ", ".join(tags) + "\n",
             "youtube_hashtags.txt": " ".join(hashtags) + "\n", "pinned_comment.md": inp["pinned_comment"] + "\n"}
    t = inp["titles"]; maxc = cfg["youtube"]["max_title_chars"]
    files["youtube_titles.md"] = ("# YouTube title options\n\n| # | Angle | Title | Characters |\n|---|---|---|---|\n" +
        "".join(f"| {i} | {x['angle']} | {x['title'].replace('|', chr(92) + '|')} | {len(x['title'])} |\n" for i, x in enumerate(t, 1)) +
        f"\n**Recommended:** {t[inp['recommended'] - 1]['title']}\n\n{inp['recommendation_reason']}\n\n"
        + ("**Research** (" + inp["research"].get("date", "") + "): search phrases " + ", ".join(inp["research"].get("search_phrases", [])) +
           "\n\nSources:\n" + "\n".join(f"- {u}" for u in inp["research"].get("sources", [])) + "\n\n" if inp.get("research") else "") +
        "No search-volume or ranking claims are made: no keyword data was available.\n")
    # ---- validation
    allowed = {v for v in links.values()} | {c["license_url"] for c in cred} | set(inp.get("allowed_urls", []))
    for name, txt in files.items():
        ok = allowed | (set((inp.get("research") or {}).get("sources", [])) if name == "youtube_titles.md" else set())  # research notes
        for u in URL.findall(txt):
            if u.rstrip(").,") not in ok: probs.append(f"{name}: URL not from config/credits: {u}")
        for ph in set(re.findall(r"\{\{[A-Z_]+\}\}", txt)): probs.append(f"{name}: placeholder to fill: {ph}")
    for x in t:
        if len(x["title"]) > maxc: probs.append(f"title over {maxc} chars: {x['title']}")
    if len(t) != cfg["youtube"]["title_options"]: probs.append(f"expected {cfg['youtube']['title_options']} titles")
    if cred_text and cred_text not in desc: probs.append("credit text not verbatim in description")
    if len(desc) > 5000: probs.append(f"description {len(desc)} chars > YouTube limit 5000")
    probs += seo(cfg, inp, desc, ch, tags)
    for name, txt in files.items():
        with open(os.path.join(M, name), "w", encoding="utf-8") as f: f.write(txt)
    return [os.path.join(M, n) for n in files], probs

# ---------------------------------------------------------------- short-form (only for APPROVED clips)
LIMITS = {"shorts_title": 100, "shorts_description": 5000, "reel_caption": 2200, "hashtags": 5}

def short_meta(cfg, clip, inp, music_sections=()):
    """clip: approved candidate (final-video start/end). inp: {title, description, reel_caption, hashtags, cover_t,
    pinned_comment?} written from the clip's own transcript lines. Music credit is added only if the clip overlaps a
    music section of the final mix."""
    probs = []
    if len(inp["title"]) > LIMITS["shorts_title"]: probs.append("Shorts title over 100 characters")
    if len(inp["reel_caption"]) > LIMITS["reel_caption"]: probs.append("Reel caption over 2200 characters")
    tags = [h if h.startswith("#") else "#" + h for h in inp["hashtags"]][:LIMITS["hashtags"]]
    if not (clip["start"] <= inp["cover_t"] <= clip["end"]): probs.append("cover frame outside the clip")
    uses_music = any(a < clip["end"] and b > clip["start"] for a, b, *_ in music_sections)
    credit = credits_block(cfg, [cfg["audio"]["music"]["credit_id"]])[0] if uses_music else ""
    for k in ("title", "description", "reel_caption"):
        if URL.search(inp[k]) or re.search(r"\{\{[A-Z_]+\}\}", inp[k]): probs.append(f"{k}: contains a link/placeholder to check")
    md = (f"# {inp['title']}\n\n**Clip:** {fmt(clip['start'])}–{fmt(clip['end'])} of the final video ({clip['duration']} s)\n\n"
          f"## YouTube Shorts\n**Title:** {inp['title']}\n\n**Description:**\n{inp['description']}\n\n{' '.join(tags)}\n"
          + (f"\n{credit}\n" if credit else "") +
          f"\n## Instagram Reel\n**Caption:**\n{inp['reel_caption']}\n\n{' '.join(tags)}\n" + (f"\nMusic: {credit.splitlines()[0]}\n" if credit else "") +
          f"\n## Cover frame\nFinal-video time {fmt(inp['cover_t'])} ({inp.get('cover_note', '')})\n"
          + (f"\n## Pinned comment\n{inp['pinned_comment']}\n" if inp.get("pinned_comment") else ""))
    d = os.path.join(cfg["paths"]["metadata"], "shorts"); os.makedirs(d, exist_ok=True)
    path = os.path.join(d, re.sub(r"[^a-z0-9]+", "_", inp["title"].lower())[:50] + ".md"); open(path, "w", encoding="utf-8").write(md)
    return path, probs
