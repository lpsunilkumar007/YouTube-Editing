"""Stage 'timeline': a PROPOSAL (for user approval) of keep segments and layouts, from measured data only.

keeps   : narration span split at pauses longer than editing.max_dead_air_s; each cut keeps 0.35 s of room tone per side
          (inside the measured pause), boundaries snapped to the output frame grid.
restarts: consecutive transcript lines whose first words repeat (possible false start / retake) are FLAGGED, never removed.
layouts : B while a slide is shown and the presenter writes or the slide changed recently; A for the opening sentence(s),
          the closing and long stretches without desktop activity; switches only at pauses, min shot length 4 s;
          A->B switches are placed just after a slide change when one falls in the pause (hides the change).
zooms   : candidates only (ink concentrated in a small area), each must pass layout clearance checks before use.
chips/elements/music: empty slots; filled from the transcript (Claude) and approved with the timeline."""
import json, os, re
import numpy as np

def snap(t, fps):
    return round(t * fps) / fps

def keeps(pauses, speech_start, speech_end, max_dead=1.5, keep_side=0.35, fps=30, protect=()):
    """protect: face-time intervals that are never cut (pen writing: a silence while the presenter writes is not dead
    air, and cutting it would make the ink jump)."""
    out, a = [], max(0.0, speech_start - 0.3)
    for p0, p1 in pauses:
        if p0 <= a or p1 >= speech_end: continue
        if any(q0 < p1 and q1 > p0 for q0, q1 in protect): continue
        if p1 - p0 > max_dead:
            out.append((snap(a, fps), snap(p0 + keep_side, fps))); a = p1 - keep_side
    out.append((snap(a, fps), snap(speech_end + 0.3, fps)))
    return [(x, y) for x, y in out if y - x > 0.5]

def remove(keep_list, removals, fps=30):
    """Content cuts (retakes, spoken 'cut this' instructions): face-time ranges [(a, b, ...)] taken out of the keep list.
    a and b already carry room tone (see retakes.detect), so the joint lands in a pause on both sides."""
    out = []
    for x, y in keep_list:
        parts = [(x, y)]
        for r in removals:
            a, b = r[0], r[1]; parts = [q for p0, p1 in parts for q in ((p0, min(p1, a)), (max(p0, b), p1)) if q[1] - q[0] > 0]
        out += [(snap(p0, fps), snap(p1, fps)) for p0, p1 in parts]
    return [(x, y) for x, y in out if y - x > 0.5]

def cutaways(segments, removals, ink, pauses, fps=30, min_s=1.5, max_s=4.0):
    """A content cut that removes pen writing would make the ink jump on the slide. The slide shot after such a cut
    starts on the presenter (layout A) until the first pause >= 0.3 s after min_s (at most max_s), so the ink changes
    off screen. Returns the new segment list and the face times of the cut-aways."""
    out, done = [], []
    for s in segments:
        r = next((r for r in removals if abs(s["face_in"] - r[1]) < 0.05 and any(r[0] < e["start"] < r[1] or r[0] < e["end"] < r[1] for e in ink)), None)
        if r and s["layout"] != "A":
            t = next((round((p0 + p1) / 2, 2) for p0, p1 in pauses if p1 - p0 >= 0.3 and s["face_in"] + min_s <= (p0 + p1) / 2 <= s["face_in"] + max_s), s["face_in"] + max_s / 2)
            t = snap(min(t, s["face_out"]), fps); out += [dict(s, layout="A", face_out=t), dict(s, face_in=t)]; done.append(s["face_in"]); continue
        out.append(s)
    return [s for s in out if s["face_out"] - s["face_in"] > 0.01], done

def widen_blanks(blanks, slide_changes, near=2.0, fps=2.0):
    """Clicking past the last slide often flashes other slides around the blank ('End of slide show'). Extend each blank
    span (desktop time) over slide changes within `near` s of it: back to just before the first change (changes are
    detected on the first frame of the new state, sampled at `fps`), forward to the last change."""
    out = []
    for b0, b1 in blanks:
        while True:
            pre = [c for c in slide_changes if b0 - near <= c <= b0 and c - 1 / fps < b0]
            post = [c for c in slide_changes if b1 < c <= b1 + near]
            n0, n1 = min([c - 1 / fps for c in pre] + [b0]), max(post + [b1])
            if (n0, n1) == (b0, b1): break
            b0, b1 = n0, n1
        out.append([round(b0, 2), round(b1, 2)])
    return out

def cover_blanks(shots, blanks, pauses, fps=30, look_s=6.0, min_piece=1.0):
    """A slide shot must never show a blank desktop ('End of slide show', a black slide). Around each blank span (face
    time) the shot goes to the presenter (A): from the last pause before it to the first pause after it, within look_s,
    else 0.3 s outside the blank. Slide pieces shorter than min_piece join the presenter part."""
    for b0, b1 in blanks:
        out = []
        for s in shots:
            if s["layout"] == "A" or s["face_out"] <= b0 or s["face_in"] >= b1: out.append(s); continue
            mids = [(p0 + p1) / 2 for p0, p1 in pauses]
            c0 = max([m for m in mids if max(s["face_in"], b0 - look_s) <= m <= b0] or [max(s["face_in"], b0 - 0.3)])
            c1 = min([m for m in mids if b1 <= m <= min(s["face_out"], b1 + look_s)] or [min(s["face_out"], b1 + 0.3)])
            c0, c1 = snap(c0, fps), snap(c1, fps)
            if c0 - s["face_in"] < min_piece: c0 = s["face_in"]
            if s["face_out"] - c1 < min_piece: c1 = s["face_out"]
            out += [dict(s, face_out=c0), dict(s, layout="A", face_in=c0, face_out=c1), dict(s, face_in=c1)]
        shots = [s for s in out if s["face_out"] - s["face_in"] > 0.01]
    merged = []
    for s in shots:
        if merged and merged[-1]["layout"] == s["layout"] == "A" and abs(merged[-1]["face_out"] - s["face_in"]) < 1e-6: merged[-1] = dict(merged[-1], face_out=s["face_out"])
        else: merged.append(s)
    return merged

def restarts(lines, n=2):
    flags = []
    for a, b in zip(lines, lines[1:]):
        wa = re.findall(r"\w+", a["text"].lower())[:n]; wb = re.findall(r"\w+", b["text"].lower())[:n]
        if wa and wa == wb and b["face"] - a["face"] < 6: flags.append({"face": a["face"], "text": a["text"], "next": b["text"]})
    return flags

def layouts(keep_list, pauses, slide_changes_face, ink_face, opening_s=12.0, quiet_s=25.0, min_shot=4.0):
    """Per keep, split into A/B shots at pauses. Activity = ink or slide change within the last quiet_s seconds."""
    act = sorted(list(slide_changes_face) + [e["start"] for e in ink_face])
    def active(t): return any(t - quiet_s <= x <= t + 2 for x in act)
    shots = []
    for a, b in keep_list:
        cuts = [a] + [(p0 + p1) / 2 for p0, p1 in pauses if a + min_shot < (p0 + p1) / 2 < b - min_shot] + [b]
        for x, y in zip(cuts, cuts[1:]):
            lay = "A" if (x < keep_list[0][0] + opening_s or not active((x + y) / 2)) else "B"
            if shots and shots[-1]["layout"] == lay and abs(shots[-1]["face_out"] - x) < 1e-6: shots[-1]["face_out"] = y
            else: shots.append({"layout": lay, "face_in": x, "face_out": y})
    if shots: shots[-1]["layout"] = "A" if shots[-1]["face_out"] - shots[-1]["face_in"] < 20 else shots[-1]["layout"]
    merged = []                                     # absorb shots shorter than min_shot into the previous one
    for s in shots:
        if merged and s["face_out"] - s["face_in"] < min_shot and abs(merged[-1]["face_out"] - s["face_in"]) < 1e-6:
            merged[-1]["face_out"] = s["face_out"]
        else: merged.append(s)
    return merged

def zoom_candidates(shots, ink_face, area, min_ink=3):
    out = []
    for i, s in enumerate(shots):
        ev = [e for e in ink_face if s["face_in"] <= e["start"] < s["face_out"]]
        if s["layout"] != "B" or len(ev) < min_ink: continue
        x0 = min(e["bbox"][0] for e in ev); y0 = min(e["bbox"][1] for e in ev); x1 = max(e["bbox"][2] for e in ev); y1 = max(e["bbox"][3] for e in ev)
        if (x1 - x0) < 0.6 * area[2]: out.append({"shot": i, "ink_bbox": [x0, y0, x1, y1], "status": "candidate: run clearance check"})
    return out

def voice_onset(env, t, loud, back=5.0, gap=0.3, step=0.01):
    """The recognizer can miss the first words (lesson05: 'Hello programmers…' from 6.6 s, first word heard at 9.45 s).
    Walk back from t while the narration stays loud (gaps up to `gap` s), at most `back` s: the edit starts at the voice."""
    k = int(t / step); stop = max(0, int((t - back) / step)); quiet = 0; first = k
    while k > stop:
        k -= 1
        if env[k] > loud: first, quiet = k, 0
        else:
            quiet += 1
            if quiet * step > gap: break
    return round(min(t, first * step - 0.15), 2)

def propose(cfg, analysis, lines, offset, out_json, removals=()):
    fps = cfg["output"]["fps"]; pauses = [tuple(p) for p in analysis["pauses"]]
    env = np.load(os.path.join(cfg["paths"]["analysis"], "speech_env.npy")); sp = np.nonzero(env > cfg["editing"]["speech_threshold_dbfs"])[0]
    start, end = sp[0] * 0.01, sp[-1] * 0.01
    wj = os.path.join(cfg["paths"]["transcripts"], "words.json")              # spoken words beat the level map (room noise)
    if os.path.exists(wj):
        ws = [w for s in json.load(open(wj, encoding="utf-8"))["segments"] for w in s.get("words", []) if w[1] - w[0] >= 0.06]
        if ws: start, end = max(start, ws[0][0]), min(end, ws[-1][1])
    start = voice_onset(env, start, cfg["editing"]["speech_threshold_dbfs"] + 15)
    sc = [t - offset for t in analysis["slide_changes"]]
    ink = [dict(e, start=e["start"] - offset, end=e["end"] - offset) for e in analysis["ink"]]
    writing = [(e["start"] - 0.3, e["end"] + 0.3) for e in ink if start < e["start"] < end]
    kl = remove(keeps(pauses, start, end, cfg["editing"]["max_dead_air_s"], 0.35, fps, writing), removals, fps)
    shots = layouts(kl, pauses, sc, ink)
    for s in shots:
        s["face_in"], s["face_out"] = snap(s["face_in"], fps), snap(s["face_out"], fps)
    shots, _ = cutaways(shots, removals, ink, pauses, fps)
    blanks = widen_blanks(analysis.get("blank_spans", []), analysis["slide_changes"])
    shots = cover_blanks(shots, [(a - offset, b - offset) for a, b in blanks], pauses, fps)
    area = analysis["slide_area"]
    plan = {"status": "PROPOSAL - review, edit and approve (python -m ytpipe approve timeline)", "offset_s": offset,
            "keeps": kl, "segments": shots, "zoom_candidates": zoom_candidates(shots, ink, [area[0], area[1], area[2] - area[0], area[3] - area[1]]),
            "restart_flags": restarts(lines), "removed_dead_air_s": round(sum(p1 - p0 - 0.7 for p0, p1 in pauses if p1 - p0 > cfg["editing"]["max_dead_air_s"] and start < p0 and p1 < end), 2),
            "content_cuts": [dict(r[2], face_in=r[0], face_out=r[1]) if len(r) > 2 else {"face_in": r[0], "face_out": r[1]} for r in removals],
            "chips": [], "elements": [], "music_sections": "auto: intro, chapter joints, outro", "chapters": []}
    os.makedirs(os.path.dirname(out_json), exist_ok=True); json.dump(plan, open(out_json, "w"), indent=1)
    return plan
