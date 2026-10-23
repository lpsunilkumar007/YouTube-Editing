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

def build(cfg, final_video=None):
    P = cfg["paths"]; out = os.path.join(P["root"], "publishing_package"); os.makedirs(out, exist_ok=True); st = state.load(cfg)
    items = {"full video": [final_video] if final_video else [], "captions": glob.glob(os.path.join(P["transcripts"], "*.srt")),
             "thumbnails": _thumbnails(cfg, st),
             "youtube metadata": [os.path.join(P["metadata"], f) for f in ("youtube_titles.md", "youtube_description.md", "youtube_chapters.txt",
                                  "youtube_tags.txt", "youtube_hashtags.txt", "pinned_comment.md") if os.path.exists(os.path.join(P["metadata"], f))],
             "shorts": _shorts(P["shorts"])
                       + sorted(glob.glob(os.path.join(P["shorts"], "*.md"))),
             "shorts metadata": sorted(glob.glob(os.path.join(P["metadata"], "shorts", "*.md")) + glob.glob(os.path.join(P["shorts"], "metadata", "*.md"))),
             "reports": sorted(glob.glob(os.path.join(P["reports"], "*.md")))}
    qa = {os.path.basename(f)[3:-5]: json.load(open(f, encoding="utf-8")) for f in glob.glob(os.path.join(P["reports"], "qa_*.json"))}
    lines = [f"# Publishing package: {cfg['project']['lecture_topic']}", "", f"Built {time.strftime('%Y-%m-%d %H:%M')}. Files are copies.", "",
             "## Approvals", ""] + [f"- {g}: {'**approved** ' + st['approvals'][g]['at'] if g in st['approvals'] else 'not approved'}" for g in state.GATES] + \
            ["", "## QA checks that ran", ""] + ([f"- {k}: {_count(v)} finding(s)" for k, v in qa.items()] or ["- none recorded"]) + \
            ["", "## Contents", ""]
    for k, fs in items.items():
        lines.append(f"**{k}:** " + (", ".join(os.path.basename(f) for f in fs) if fs else "_missing_"))
        sub = os.path.join(out, k.replace(" ", "_")); os.makedirs(sub, exist_ok=True)
        for f in fs:
            dst = os.path.join(sub, os.path.basename(f))
            if f.lower().endswith(".mp4"):
                lines.append(f"  (video not copied, location: `{f}`)"); continue
            shutil.copy2(f, dst)
    open(os.path.join(out, "INDEX.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    return out
