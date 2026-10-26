"""Stage 'factcheck': every factual claim in the lecture is checked before anything is published (user rule, 2026-10-26:
"we should not post wrong content"). Runs after the transcript is cleaned and BEFORE metadata, blog and WordPress, which
refuse to run until it passes.

1. brief   reports/fact_check_brief.md: every claim-like line of transcripts/transcript.txt (numbers, %, =, definitions,
           "always/only/means", glossary terms) with an id and its time in the final video.
2. verdict metadata/fact_check.json, written by Claude after checking each claim against reliable sources:
           {"checked": "YYYY-MM-DD", "claims": [{"id", "verdict": correct|imprecise|wrong|opinion, "source", "note",
            "action": none|cut|note|keep_flagged}]}
           - wrong     needs a source and a fix: "cut" (an applied cut in timelines/content_cuts.json covers its time)
                       or "note" (a correction written into the description / pinned comment: field "correction")
           - imprecise needs a note; it is never repeated in written copy (description, blog, Shorts)
           - correct   technical claims carry a source where one exists; opinion = the presenter's view or an example
           A wrong claim that is cut from the video no longer appears in the brief (cut lines are not published); record it
           anyway with id "r1", "r2"… and its "text", so the report shows the correction.
3. check   every claim in the brief has a verdict and every error has its fix -> reports/fact_check.md, problems []."""
import json, os, re

CUES = re.compile(r"\d|%|=|\b(is|are|means?|called|always|never|only|every|sirf|har|matlab|hota hai|hoti hai|hote hain|"
                  r"kehte hain|bolte hain|deta hai|dega|degi|equal|divisible|remainder)\b", re.I)
VERDICTS = ("correct", "imprecise", "wrong", "opinion")

def claims(lines, glossary=(), final_time=None):
    """Claim-like lines -> [{id, face, final, text}]. Removed (—cut—) lines are already excluded by transcript.parse."""
    g = [t.lower() for t in glossary if len(t) > 2]
    out = []
    for l in lines:
        t = l["text"]
        if len(t.split()) < 3 or not (CUES.search(t) or any(x in t.lower() for x in g)): continue
        out.append({"id": f"c{len(out) + 1:03d}", "face": round(l["face"], 2), "final": final_time(l["face"]) if final_time else None, "text": t})
    return out

def brief(cl, path, title):
    mm = lambda t: "--" if t is None else f"{int(t // 60)}:{t % 60:04.1f}"
    L = [f"# Fact-check brief: {title}", "", f"{len(cl)} claim-like lines. Check each against a reliable source (official docs,",
         "standard references) and record a verdict in metadata/fact_check.json (format: ytpipe/factcheck.py).", "",
         "| id | final video | claim |", "|---|---|---|"] + [f"| {c['id']} | {mm(c['final'])} | {c['text'].replace('|', '/')} |" for c in cl]
    open(path, "w", encoding="utf-8").write("\n".join(L) + "\n")
    return path

def check(cl, fc, cuts=()):
    """-> problems ([] = pass)."""
    if not fc: return ["no metadata/fact_check.json: check the claims in reports/fact_check_brief.md first"]
    v = {c["id"]: c for c in fc.get("claims", [])}; p = []
    for c in cl:
        x = v.get(c["id"])
        if not x: p.append(f"{c['id']} has no verdict: {c['text'][:70]}"); continue
        if x.get("verdict") not in VERDICTS: p.append(f"{c['id']}: verdict must be one of {VERDICTS}")
        if x.get("verdict") == "wrong":
            if not x.get("source"): p.append(f"{c['id']}: a wrong claim needs a source")
            if x.get("action") == "cut":
                if not any(k.get("apply") and k["face_in"] - 0.5 <= c["face"] <= k["face_out"] + 0.5 for k in cuts):
                    p.append(f"{c['id']}: marked 'cut' but no applied cut covers {c['face']} s (timelines/content_cuts.json)")
            elif x.get("action") == "note":
                if not x.get("correction"): p.append(f"{c['id']}: 'note' needs the correction text")
            else: p.append(f"{c['id']}: a wrong claim needs action 'cut' or 'note'")
        if x.get("verdict") == "imprecise" and not x.get("note"): p.append(f"{c['id']}: an imprecise claim needs a note")
    return p

def report(cl, fc, problems, path, title):
    v = {c["id"]: c for c in (fc or {}).get("claims", [])}
    L = [f"# Fact check: {title}", "", f"Checked {fc.get('checked', '?') if fc else '(not yet)'}. Result: **{'PASS' if not problems else 'NOT PASSED'}**.", ""]
    ids = {c["id"] for c in cl}                                    # claims removed in the edit are recorded too (id "r…", text)
    flagged = [c for c in cl if v.get(c["id"], {}).get("verdict") in ("wrong", "imprecise")] + \
              [{"id": x["id"], "text": x.get("text", "")} for x in (fc or {}).get("claims", []) if x["id"] not in ids]
    L += ["## Corrections and flags", ""] + ([f"- **{c['id']} ({v[c['id']]['verdict']}, action {v[c['id']].get('action', 'none')})**: {c['text']}  \n"
          f"  {v[c['id']].get('note', '')} {('Correction: ' + v[c['id']]['correction']) if v[c['id']].get('correction') else ''} "
          f"{('Source: ' + v[c['id']]['source']) if v[c['id']].get('source') else ''}" for c in flagged] or ["- none"])
    L += ["", "## All claims", "", "| id | verdict | claim | source |", "|---|---|---|---|"] + \
         [f"| {c['id']} | {v.get(c['id'], {}).get('verdict', '—')} | {c['text'].replace('|', '/')[:90]} | {v.get(c['id'], {}).get('source', '')} |" for c in cl]
    if problems: L += ["", "## Problems", ""] + [f"- {x}" for x in problems]
    open(path, "w", encoding="utf-8").write("\n".join(L) + "\n")
    return path

def run(cfg, lines, glossary, final_time, title):
    """Writes the brief (always) and, when metadata/fact_check.json exists, the report. -> (claims, problems)."""
    P = cfg["paths"]; cl = claims(lines, glossary, final_time)
    brief(cl, os.path.join(P["reports"], "fact_check_brief.md"), title)
    fj = os.path.join(P["metadata"], "fact_check.json"); fc = json.load(open(fj, encoding="utf-8")) if os.path.exists(fj) else None
    cj = os.path.join(P["timelines"], "content_cuts.json"); cuts = json.load(open(cj, encoding="utf-8")) if os.path.exists(cj) else []
    probs = check(cl, fc, cuts)
    if fc: report(cl, fc, probs, os.path.join(P["reports"], "fact_check.md"), title)
    return cl, probs
