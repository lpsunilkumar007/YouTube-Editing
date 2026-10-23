"""Stage 'captions': cleaned transcript -> caption cues on the FINAL edit timeline -> SRT (+ optional styled ASS).

Never invents text: cue text is the transcript text, only (a) glossary spelling normalisation on whole words and
(b) removal of editorial markers. Lines flagged 'translation' ((meaning) = English rendering of Hindi speech) or that are
only '[unclear…]' are NOT captioned; they are listed in captions_review.md for manual transcription. 'reconstructed' (≈)
lines are captioned but listed for a listen-check. Manual corrections: edit captions_edit.json and rerun (it wins)."""
import json, os, re
import numpy as np

# ---------------------------------------------------------------- text
def load_glossary(path):
    g = json.load(open(path, encoding="utf-8"))
    return [(canon, re.compile(r"(?<![\w#.])(?:" + "|".join(vs) + r")(?![\w#])", re.I)) for canon, vs in g.items()
            if not canon.startswith("_")]

def normalise(text, glossary):
    text = re.sub(r"\[unclear[^\]]*\]", "…", text)            # keep the gap visible, never guess words
    text = text.replace("≈", "").replace("[", "").replace("]", "")
    for canon, rx in glossary:
        text = rx.sub(canon, text)
    return re.sub(r"\s+", " ", text).strip(" ,")

def split_cues(text, maxc=42, lines=2):
    """Split one transcript line into cue texts at sentence/clause boundaries, each <= lines*maxc chars, wrapped."""
    limit = maxc * lines - 8                                   # slack so every cue can wrap into <= maxc lines
    parts = [p.strip() for p in re.split(r"(?<=[.?!])\s+|(?<=,)\s+(?=\S{3,})", text) if p.strip()]
    cues, cur = [], ""
    for p in parts:
        cand = f"{cur} {p}".strip()
        if len(cand) <= limit: cur = cand; continue
        if cur: cues.append(cur)
        if len(p) > limit:                                      # long clause: balanced parts split at spaces
            k = -(-len(p) // limit); words = p.split(" "); target = len(p) / k; part = ""
            for w in words:
                if part and len(part) + 1 + len(w) > target + 6 and len(cues) < 10_000:
                    cues.append(part); part = w
                else: part = f"{part} {w}".strip()
            p = part
        cur = p
    if cur: cues.append(cur)
    return [wrap(c, maxc) for c in cues]

def wrap(text, maxc):
    """Two balanced lines, breaking at the space that best balances them (each <= maxc when possible)."""
    if len(text) <= maxc: return text
    sp = [i for i, ch in enumerate(text) if ch == " "]
    if not sp: return text
    ok = [i for i in sp if i <= maxc and len(text) - i - 1 <= maxc]
    i = min(ok or sp, key=lambda i: abs(i - (len(text) - i - 1)))
    return text[:i] + "\n" + text[i + 1:]

# ---------------------------------------------------------------- timing
def speech_runs(env, start, end, thr=-50.0, step=0.01):
    """Speech intervals (face time) inside [start, end] from the 10 ms speech map."""
    i0, i1 = int(start / step), min(len(env), int(end / step)); q = env[i0:i1] > thr; out, s = [], None
    for i, v in enumerate(q):
        if v and s is None: s = i
        if (not v or i == len(q) - 1) and s is not None:
            out.append((start + s * step, start + i * step)); s = None
    return out

def time_line(text_cues, start, end, env=None):
    """Distribute a line's cues over its speech (character-proportional), start/end snapped to measured speech."""
    if env is not None:
        runs = [r for r in speech_runs(env, start, end) if r[1] - r[0] > 0.05]
        if runs: start, end = runs[0][0], runs[-1][1]
    n = [max(1, len(c.replace("\n", " "))) for c in text_cues]; tot = sum(n); out, t = [], start
    for c, k in zip(text_cues, n):
        d = (end - start) * k / tot; out.append([t, t + d, c]); t += d
    return out

def to_edit(cues, edl):
    """Map face-time cues onto the final edit: segments [{face_in, face_out, edit_start}]. Parts in removed footage
    are dropped; a cue spanning a cut is split at the cut (text kept on the larger part)."""
    out = []
    for a, b, text in cues:
        pieces = []
        for s in edl:
            lo, hi = max(a, s["face_in"]), min(b, s["face_out"])
            if hi - lo > 0.05: pieces.append((s["edit_start"] + lo - s["face_in"], s["edit_start"] + hi - s["face_in"]))
        if not pieces: continue
        merged = [list(pieces[0])]
        for p in pieces[1:]:
            if p[0] - merged[-1][1] < 0.05: merged[-1][1] = p[1]       # contiguous segments (same take)
            else: merged.append(list(p))
        big = max(merged, key=lambda p: p[1] - p[0]); out.append([big[0], big[1], text])
    return out

def merge_short(cues, cfg):
    """Cues shorter than min_duration_s are merged into a neighbour when the joined text still fits two lines."""
    c = cfg["captions"]; limit = c["max_chars_per_line"] * c["max_lines"]; out = []
    for a, b, t in cues:
        t = " ".join(t.split())
        if out and (b - a < c["min_duration_s"] or out[-1][1] - out[-1][0] < c["min_duration_s"]) and a - out[-1][1] < 0.3                 and len(out[-1][2]) + 1 + len(t) <= limit and b - out[-1][0] <= c["max_duration_s"]:
            out[-1] = [out[-1][0], b, out[-1][2] + " " + t]
        else:
            out.append([a, b, t])
    return [[a, b, wrap(t, c["max_chars_per_line"])] for a, b, t in out]

def enforce(cues, cfg):
    c = cfg["captions"]; out = []
    cues = merge_short([[a, b, t.replace("\n", " ")] for a, b, t in cues], cfg)
    for i, (a, b, t) in enumerate(cues):
        nxt = cues[i + 1][0] if i + 1 < len(cues) else b + 10
        b = min(max(b, a + c["min_duration_s"]), a + c["max_duration_s"], nxt - c["min_gap_s"])
        if b - a >= 0.3: out.append([round(a, 3), round(b, 3), t])
    return out

# ---------------------------------------------------------------- output
def _ts(t):
    ms = int(round(t * 1000)); return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"

def write_srt(cues, path):
    with open(path, "w", encoding="utf-8") as f:
        for i, (a, b, t) in enumerate(cues, 1):
            f.write(f"{i}\n{_ts(a)} --> {_ts(b)}\n{t}\n\n")

def write_ass(cues, path, cfg):
    """Optional styled captions (Segoe UI Semibold, white on translucent navy, above the chip band)."""
    W, H = cfg["output"]["resolution"]; pal = cfg["graphics"]["palette"]
    navy = pal["canvas"].lstrip("#"); bgr = navy[4:6] + navy[2:4] + navy[0:2]
    head = (f"[Script Info]\nScriptType: v4.00+\nPlayResX: {W}\nPlayResY: {H}\n\n[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, "
            "StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
            f"Style: Cap,Segoe UI Semibold,{int(40 * H / 1080)},&H00FFFFFF,&H00FFFFFF,&H00000000,&H28{bgr},0,0,0,0,100,100,0,0,3,10,0,2,"
            f"{int(80 * W / 1920)},{int(460 * W / 1920)},{int(120 * H / 1080)},1\n\n[Events]\n"
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
    ts = lambda t: f"{int(t // 3600)}:{int(t // 60 % 60):02d}:{t % 60:05.2f}"
    with open(path, "w", encoding="utf-8") as f:
        f.write(head)
        for a, b, t in cues: f.write(f"Dialogue: 0,{ts(a)},{ts(b)},Cap,,0,0,0,,{t.replace(chr(10), r'\N')}\n")

def build(cfg, transcript_lines, edl, env=None, step=0.01):
    gl = load_glossary(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), cfg["captions"]["glossary"]))
    out_dir = cfg["paths"]["transcripts"]; os.makedirs(out_dir, exist_ok=True)
    edit_path = os.path.join(out_dir, "captions_edit.json")
    manual = json.load(open(edit_path, encoding="utf-8")) if os.path.exists(edit_path) else None
    review, cues = [], []
    lines = transcript_lines
    for i, ln in enumerate(lines):
        end = lines[i + 1]["face"] if i + 1 < len(lines) else ln["face"] + 6
        txt = normalise(ln["text"], gl)
        if "translation" in ln["flags"] or re.fullmatch(r"[….\s]*", txt):
            review.append((ln["face"], "NOT captioned (" + ("English rendering, not the spoken words" if "translation" in ln["flags"] else "unclear") + ")", ln["text"])); continue
        if ln["flags"] & {"reconstructed", "unclear"}:
            review.append((ln["face"], "captioned, listen-check (" + ", ".join(sorted(ln["flags"])) + ")", ln["text"]))
        cues += time_line(split_cues(txt, cfg["captions"]["max_chars_per_line"], cfg["captions"]["max_lines"]), ln["face"], end, env)
    edit_cues = enforce(to_edit(cues, edl), cfg)
    if manual:                                                       # user corrections win (same order/timing editable)
        edit_cues = [[c["start"], c["end"], c["text"]] for c in manual["cues"]]
    else:
        json.dump({"_help": "Edit text/timing here and rerun captions; this file then overrides the automatic cues.",
                   "cues": [{"start": a, "end": b, "text": t} for a, b, t in edit_cues]},
                  open(os.path.join(out_dir, "captions_edit.template.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    srt = os.path.join(out_dir, f"{cfg['project']['lesson_id']}_hinglish.srt"); write_srt(edit_cues, srt)
    if cfg["captions"]["styled_burn_in"] or "ass" in cfg["captions"]["format"]:
        write_ass(edit_cues, srt.replace(".srt", ".ass"), cfg)
    with open(os.path.join(cfg["paths"]["reports"], "captions_review.md"), "w", encoding="utf-8") as f:
        f.write(f"# Caption review: {cfg['project']['lecture_topic']}\n\n{len(edit_cues)} cues written to `{os.path.basename(srt)}`.\n"
                f"Lines below need a human check (face-camera time).\n\n| face time | status | transcript line |\n|---|---|---|\n")
        for F, st, t in review: f.write(f"| {int(F // 60)}:{F % 60:05.2f} | {st} | {t} |\n")
    return srt, edit_cues, review
