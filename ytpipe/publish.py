"""Publishing package: collects the deliverables of a lecture into <lesson>/publishing_package/ (copies, never moves)
with an index that states which approvals were given and which QA checks actually ran (from reports/qa_*.json)."""
import glob, json, os, re, shutil, time
from . import state

def _count(v):
    """Findings in a QA result: lists count their items, dicts are searched (a 'findings' key wins), strings count as 1."""
    if isinstance(v, list): return len(v)
    if isinstance(v, dict): return _count(v["findings"]) if "findings" in v else sum(_count(x) for x in v.values())
    return 1 if isinstance(v, str) and v else 0

def _thumbnails(cfg, st):
    """The approved thumbnail (note 'file:<name>.png' or 'option_N') if there is one, else every current option (v2 first, v1 fallback)."""
    P = cfg["paths"]; note = st["approvals"].get("thumbnail", {}).get("note", "")
    f = re.search(r"file:(\S+\.png)", note)
    if f and os.path.exists(os.path.join(P["thumbnails"], f.group(1))): return [os.path.join(P["thumbnails"], f.group(1))]
    opts = sorted(glob.glob(os.path.join(P["thumbnails"], "thumbnail_premium_v2_*.png"))) or         sorted(glob.glob(os.path.join(P["thumbnails"], "thumbnail_option_*.png")))
    m = re.search(r"option_(\d+)", st["approvals"].get("thumbnail", {}).get("note", ""))
    chosen = [f for f in opts if m and re.search(rf"_{m.group(1)}\.png$", f)]
    return chosen or opts

def _shorts(d):
    """One file per Short: the approved v4 render (shorts/v4/short_NN.mp4) when present, else short_NN.mp4. Retired variants
    (_v2 circle, _music/_v4 previews) are excluded."""
    pick = {}
    for f in sorted(glob.glob(os.path.join(d, "short_*.mp4"))) + sorted(glob.glob(os.path.join(d, "v4", "short_*.mp4"))):
        m = re.search(r"short_(\d+)\.mp4$", f)
        if m: pick[m.group(1)] = f
    return [pick[k] for k in sorted(pick)]

def _blog(d):
    """Blog files for the package: the article files, the screenshots the article uses (paths kept, so its image links
    work), and the WordPress dry run and outreach list when they exist."""
    top = sorted(f for f in glob.glob(os.path.join(d, "*")) if os.path.isfile(f))
    used = sorted({m for f in top if f.endswith(".md") for m in re.findall(r"\]\((screens/[^)\s]+)\)", open(f, encoding="utf-8").read())})
    return top + [os.path.join(d, u) for u in used if os.path.exists(os.path.join(d, u))] + \
           [os.path.join(d, "wordpress", f) for f in ("dry_run.md", "outreach.md") if os.path.exists(os.path.join(d, "wordpress", f))]

def _fact_status(P):
    f = os.path.join(P["reports"], "fact_check.md")
    if not os.path.exists(f): return "- **not done**: run `python -m ytpipe factcheck` (claims must be verified before publishing)"
    m = re.search(r"Result: \*\*(.+?)\*\*", open(f, encoding="utf-8").read())
    return f"- {m.group(1) if m else 'unknown'} (reports/fact_check.md)"

def _sync_status(P):
    """How the offset was established: pen/word anchors are the only proof on a silent desktop recording."""
    p = os.path.join(P["analysis"], "sync.json")
    if not os.path.exists(p): return "- not run"
    r = json.load(open(p, encoding="utf-8"))["result"]
    if r["status"] != "ok": return f"- **NOT verified**: {r['offset_s']} s, {r['method']} ({r.get('reason', '')})"
    if r["method"].startswith("pen/word anchors") or "cross-correlation" in r["method"]: return f"- verified: {r['offset_s']} s, {r['method']}"
    return f"- confirmed by you, not measured: {r['offset_s']} s, {r['method']}"

def build(cfg, final_video=None):
    P = cfg["paths"]; out = os.path.join(P["root"], "publishing_package"); os.makedirs(out, exist_ok=True); st = state.load(cfg)
    items = {"full video": [final_video] if final_video else [], "captions": glob.glob(os.path.join(P["transcripts"], "*.srt")),
             "thumbnails": _thumbnails(cfg, st),
             "youtube metadata": [os.path.join(P["metadata"], f) for f in ("youtube_titles.md", "youtube_description.md", "youtube_chapters.txt",
                                  "youtube_tags.txt", "youtube_hashtags.txt", "pinned_comment.md") if os.path.exists(os.path.join(P["metadata"], f))],
             "shorts": _shorts(P["shorts"])
                       + sorted(glob.glob(os.path.join(P["shorts"], "*.md"))),
             "shorts metadata": sorted(glob.glob(os.path.join(P["metadata"], "shorts", "*.md")) + glob.glob(os.path.join(P["shorts"], "metadata", "*.md"))),
             "blog": _blog(os.path.join(P["root"], "blog")),
             "reports": sorted(glob.glob(os.path.join(P["reports"], "*.md")))}
    qa = {os.path.basename(f)[3:-5]: json.load(open(f, encoding="utf-8")) for f in glob.glob(os.path.join(P["reports"], "qa_*.json"))}
    lines = [f"# Publishing package: {cfg['project']['lecture_topic']}", "", f"Built {time.strftime('%Y-%m-%d %H:%M')}. Files are copies.", "",
             "## Approvals", ""] + [f"- {g}: {'**approved** ' + st['approvals'][g]['at'] if g in st['approvals'] else 'not approved'}" for g in state.GATES] + \
            ["", "## Fact check", "", _fact_status(P)] + \
            ["", "## Camera/desktop sync", "", _sync_status(P)] + \
            ["", "## QA checks that ran", ""] + ([f"- {k}: {_count(v)} finding(s)" for k, v in qa.items()] or ["- none recorded"]) + \
            ["", "## Contents", ""]
    for k, fs in items.items():
        lines.append(f"**{k}:** " + (", ".join(os.path.basename(f) for f in fs) if fs else "_missing_"))
        sub = os.path.join(out, k.replace(" ", "_")); shutil.rmtree(sub, ignore_errors=True); os.makedirs(sub)   # copies only: no stale files
        for f in fs:
            dst = os.path.join(sub, os.path.relpath(f, os.path.join(P["root"], "blog")) if k == "blog" else os.path.basename(f))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            if f.lower().endswith(".mp4"):
                lines.append(f"  (video not copied, location: `{f}`)"); continue
            shutil.copy2(f, dst)
    open(os.path.join(out, "INDEX.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    upload_copy(cfg, items, os.path.join(out, "UPLOAD_COPY.txt"))
    return out

def _plain(md):
    """Markdown -> text for YouTube/Instagram boxes: '**Heading**' becomes '*Heading*' (YouTube bold); escapes removed."""
    return re.sub(r"\*\*(.+?)\*\*", r"*\1*", md).replace("\\|", "|").strip()

def upload_copy(cfg, items, path):
    """One plain-text file with everything to paste on upload: title, description (chapters + credits included), tags,
    hashtags, pinned comment, files to attach, and per Short the title, description, Reel caption and cover time."""
    M = cfg["paths"]["metadata"]; rd = lambda f: open(os.path.join(M, f), encoding="utf-8").read() if os.path.exists(os.path.join(M, f)) else ""
    bar = "=" * 72; out = [f"UPLOAD COPY: {cfg['project']['lecture_topic']}", f"Built {time.strftime('%Y-%m-%d %H:%M')} from the validated metadata. Paste each block as is.", ""]
    titles = rd("youtube_titles.md"); rec = re.search(r"\*\*Recommended:\*\* (.+)", titles)
    alts = re.findall(r"^\| \d+ \| [^|]+ \| (.+?) \| \d+ \|$", titles, re.M)
    files = [f"Video:      {f}" for f in items["full video"]] + [f"Thumbnail:  {f}" for f in items["thumbnails"][:1]] + \
            [f"Captions:   {f}  (upload as a subtitle file)" for f in items["captions"]]
    out += [bar, "YOUTUBE: LONG VIDEO", bar, "", "FILES TO ATTACH", *files, "", "TITLE", rec.group(1) if rec else "", "",
            "OTHER TITLE OPTIONS", *[f"- {_plain(t)}" for t in alts if not rec or _plain(t) != rec.group(1)], "",
            "DESCRIPTION (chapters and music credit included)", "-" * 40, _plain(rd("youtube_description.md")), "-" * 40, "",
            "TAGS", rd("youtube_tags.txt").strip(), "", "PINNED COMMENT (post it, then pin it)", rd("pinned_comment.md").strip(), ""]
    for f in items["shorts metadata"]:
        md = open(f, encoding="utf-8").read(); sec = lambda h: (re.search(rf"## {h}\n(.*?)(?=\n## |\Z)", md, re.S) or [None, ""])[1]
        yt, ig, cov = sec("YouTube Shorts"), sec("Instagram Reel"), sec("Cover frame")
        t = re.search(r"\*\*Title:\*\* (.+)", yt); d = re.search(r"\*\*Description:\*\*\n(.*)", yt, re.S); c = re.search(r"\*\*Caption:\*\*\n(.*)", ig, re.S)
        out += [bar, f"SHORT: {t.group(1) if t else os.path.basename(f)}", bar, "", "YOUTUBE SHORTS TITLE", t.group(1) if t else "", "",
                "YOUTUBE SHORTS DESCRIPTION (music credit included)", "-" * 40, d.group(1).strip() if d else "", "-" * 40, "",
                "INSTAGRAM REEL CAPTION", "-" * 40, c.group(1).strip() if c else "", "-" * 40, "", "COVER FRAME", cov.strip(), ""]
    if items["shorts"]:
        out += ["SHORT VIDEO FILES (in order)", *[f"- {f}" for f in items["shorts"] if f.endswith(".mp4")], ""]
    if items.get("blog"):
        out += [bar, "BLOG POST", bar, "", "Files: " + ", ".join(os.path.basename(f) for f in items["blog"]),
                "Open the .html in a browser, select the article, paste it into Medium or your site's editor; SEO fields are in SEO.txt.",
                "WordPress: python -m ytpipe wp-publish (dry run: wordpress/dry_run.md), approve its payload hash, then --send for a DRAFT.",
                "Backlink ideas to work through by hand: wordpress/outreach.md.", ""]
    out += [bar, "BEFORE YOU PUBLISH: go through PUBLISHING_CHECKLIST.md. Keep every music credit: CC BY requires it.", bar]
    open(path, "w", encoding="utf-8").write("\n".join(out) + "\n")
