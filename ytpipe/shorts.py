"""Shorts / Reels: candidate finder (report for approval) and vertical 1080x1920 renderer (gate 'shorts').

Candidates come from the final edit's transcript (no re-transcription). A window starts at a line that opens a topic
(question, definition, example, chapter start), runs 20-60 s, ends on a line that ends a sentence, and is scored for
standalone value. Lines starting with a connective ("to", "aur", "phir", "so", "then", "waise hi"...) depend on earlier
context and are penalised; windows with '(meaning)' or '[unclear]' lines are rejected. Up to shorts.max_candidates are
proposed; fewer if the content does not support them.

Vertical layout (safe areas for Shorts/Reels UI: right 180 px column of buttons, bottom ~22 % caption/handle area,
top ~10 % header): hook text y 140-300, desktop panel (content region of the slide, reframed, never a centre crop)
y 330-1010, face circle 470 px centred at y 1270, burned-in captions y 1530-1640 inside x 60-900. Face-only clips use a
9:16 face crop centred on the median face position."""
import json, os, re
import numpy as np
from . import media, render

CONNECTIVES = ("to ", "aur ", "phir ", "so ", "then ", "waise hi", "and ", "but ", "par ", "toh ", "uske baad", "isliye")
OPENERS = re.compile(r"\?|kya hai|kya hota|kya cheez|kaise|kyon|why |what |how |example|let us suppose", re.I)
FILLER = re.compile(r"^(≈\s*)?(theek hai( ji)?|okay|ok|haan|right)\??\.?$", re.I)          # not hooks
BACKREF = re.compile(r"jaise maine|maine pehle|as i said|pehle bhi|upar bataya|example diya tha", re.I)  # needs earlier context

def edit_lines(lines, edl):
    out = []
    for ln in lines:
        for s in edl:
            if s["face_in"] - 1e-6 <= ln["face"] < s["face_out"]:
                out.append(dict(ln, t=s["edit_start"] + ln["face"] - s["face_in"])); break
    return out

def candidates(cfg, lines, edl, glossary_terms, chapters=()):
    L = edit_lines(lines, edl); dmin, dmax = cfg["shorts"]["duration_s"]; out = []
    chap_t = [a for a, _ in chapters]
    for i, ln in enumerate(L):
        low = ln["text"].lower().lstrip("≈ ")
        if FILLER.match(ln["text"].strip()) or (i > 0 and not re.search(r"[.?!]\s*$", L[i - 1]["text"])): continue  # sentence starts only
        opener = bool(OPENERS.search(ln["text"])) or any(abs(ln["t"] - c) < 1.0 for c in chap_t)
        if low.startswith(CONNECTIVES) and not opener: continue
        for j in range(i + 1, len(L)):
            end_t = L[j + 1]["t"] if j + 1 < len(L) else L[j]["t"] + 4
            dur = end_t - ln["t"]
            if dur > cfg["shorts"]["allow_up_to_s"]: break
            if dur < dmin or not re.search(r"[.?!]\s*$", L[j]["text"]): continue
            win = L[i:j + 1]
            if any(f in w["flags"] for w in win for f in ("translation",)) or sum("unclear" in w["flags"] for w in win) > 0: break
            text = " ".join(w["text"] for w in win).lower()
            terms = sorted({t for t in glossary_terms if re.search(r"(?<!\w)" + re.escape(t.lower()) + r"(?!\w)", text)})
            crosses = sum(ln["t"] + 1.0 < c < end_t - 1.0 for c in chap_t)          # spills into the next topic
            score = 2 * opener + len(terms) * 0.6 + ("example" in text) * 1.0 - 1.5 * low.startswith(CONNECTIVES) \
                    - 2.0 * bool(BACKREF.search(ln["text"])) - 1.5 * crosses - max(0, dur - dmax) / 15
            out.append({"start": round(ln["t"], 2), "end": round(end_t - 0.15, 2), "duration": round(end_t - 0.15 - ln["t"], 1),
                        "hook": ln["text"], "terms": terms, "score": round(score, 2), "lines": [w["text"] for w in win],
                        "standalone": not low.startswith(CONNECTIVES)})
            if dur >= dmax: break
    out.sort(key=lambda c: -c["score"]); picked = []
    for c in out:
        if c["score"] < 2.0: continue                                  # not strong enough: never filled to a quota
        if all(c["end"] <= p["start"] or c["start"] >= p["end"] for p in picked): picked.append(c)
        if len(picked) == cfg["shorts"]["max_candidates"]: break
    for c in picked:
        segs = [s for s in edl if s["edit_start"] < c["end"] and s["edit_start"] + s["frames"] / 30 > c["start"]]
        c["layout"] = ("split: desktop on top, presenter rectangle below (no circle: long-form only)" if any(s["layout"] != "A" for s in segs)
                       else "full-frame presenter (9:16 face crop)")
    return sorted(picked, key=lambda c: c["start"])

def report(cfg, cands, chapters, path):
    fmt = lambda t: f"{int(t // 60)}:{t % 60:04.1f}"
    def chap(t):
        prev = [n for a, n in chapters if a <= t]; return prev[-1] if prev else ""
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# Shorts / Reels candidate report: {cfg['project']['lecture_topic']}\n\n"
                f"Status: **awaiting your approval** (nothing rendered). {len(cands)} candidate(s); fewer than "
                f"{cfg['shorts']['max_candidates']} means the lecture does not support more strong standalone clips.\n\n")
        for k, c in enumerate(cands, 1):
            f.write(f"## {k}. {c.get('title', '(title to write)')}\n\n"
                    f"- **Final-video time:** {fmt(c['start'])} – {fmt(c['end'])} ({c['duration']} s)\n- **Topic:** {chap(c['start'])}\n"
                    f"- **Opening hook (spoken):** \"{c['hook']}\"\n- **Teaching value:** {c.get('value', ', '.join(c['terms']) or '-')}\n"
                    f"- **Works on its own:** {'yes' if c['standalone'] else 'needs context'}{(' — ' + c['note']) if c.get('note') else ''}\n"
                    f"- **Recommended vertical layout:** {c['layout']}\n- **Score:** {c['score']}\n\n")

def vertical_cmd(cfg, src_final, cues, c, out, face_box=None, desk_box=None, title=""):
    """Render from the FINAL video (already synced, graded, edited): desktop region and face circle are re-framed out of
    the 1920x1080 edit (card + circle positions from the geometry), captions burned from the SRT cues of that span."""
    W, H = cfg["shorts"]["size"]; fps = cfg["shorts"]["fps"]; t0, t1 = c["start"], c["end"]; T = t1 - t0
    ass = out.replace(".mp4", ".ass"); _ass(cfg, [(a - t0, b - t0, x) for a, b, x in cues if b > t0 and a < t1], ass, title)
    pal = cfg["graphics"]["palette"]["canvas"].lstrip("#")
    if desk_box:                                                       # x, y, w, h in the final 1920x1080 frame
        dx, dy, dw, dh = desk_box; pw = 1000; ph = min(680, int(dh * pw / dw)); cx, cy, d = face_box
        fc = (f"color=c=0x{pal}:s={W}x{H}:r={fps}:d={T:.3f}[bg];"
              f"[0:v]crop={dw}:{dh}:{dx}:{dy},scale={pw}:{ph}:flags=lanczos,setsar=1[dk];"
              f"[0:v]crop={d}:{d}:{cx}:{cy},scale=470:470:flags=lanczos,format=yuva444p[fc];"
              f"[fc][1:v]alphamerge[fcm];[bg][dk]overlay={(W - pw) // 2}:{330 + (680 - ph) // 2}[v1];[v1][fcm]overlay={(W - 470) // 2}:{1270 - 235}[v2];"
              f"[v2]subtitles='{_esc(ass)}'[v]")
        mask = ["-loop", "1", "-t", f"{T:.3f}", "-i", _circle_png(out)]
    else:
        fx = face_box[0] if face_box else 656; cw = 608
        fc = f"[0:v]crop={cw}:1080:{fx}:0,scale={W}:{H}:flags=lanczos,setsar=1[f];[f]subtitles='{_esc(ass)}'[v]"; mask = []
    return ["ffmpeg", "-v", "error", "-y", "-ss", f"{t0:.3f}", "-t", f"{T:.3f}", "-i", src_final, *mask, "-filter_complex", fc,
            "-map", "[v]", "-map", "0:a", "-r", str(fps), *cfg["output"]["x264"][:6], "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart", out]

def _esc(p):
    return p.replace("\\", "/").replace(":", "\\:")

def _circle_png(out):
    from PIL import Image, ImageDraw
    p = os.path.join(os.path.dirname(out), "circle470.png")
    if not os.path.exists(p):
        m = Image.new("L", (470 * 8, 470 * 8), 0); ImageDraw.Draw(m).ellipse([0, 0, 470 * 8 - 1, 470 * 8 - 1], fill=255)
        m.resize((470, 470), Image.LANCZOS).save(p)
    return p

def _ass(cfg, cues, path, title):
    W, H = cfg["shorts"]["size"]
    head = (f"[Script Info]\nScriptType: v4.00+\nPlayResX: {W}\nPlayResY: {H}\n\n[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
            "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
            "Style: Cap,Poppins SemiBold,52,&H00FFFFFF,&H00FFFFFF,&H00000000,&H50271810,0,0,0,0,100,100,0,0,3,14,0,2,60,180,290,1\n"
            "Style: Hook,Poppins Black,64,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,8,60,180,150,1\n\n"
            "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
    ts = lambda t: f"{int(t // 3600)}:{int(t // 60 % 60):02d}:{max(0, t) % 60:05.2f}"
    with open(path, "w", encoding="utf-8") as f:
        f.write(head)
        if title: f.write(f"Dialogue: 1,{ts(0)},{ts(3.5)},Hook,,0,0,0,,{title}\n")
        for a, b, t in cues: f.write(f"Dialogue: 0,{ts(max(0, a))},{ts(b)},Cap,,0,0,0,,{t.replace(chr(10), r'\N')}\n")

def render_short(cfg, src_final, cues, c, out, geometry=None, edl=None, face_track=None):
    """Vertical clip from the final edit. Each part follows the layout of the main edit at that moment (slide shot ->
    desktop panel + face circle; face shot -> 9:16 face crop centred on the measured face); parts are concatenated as
    video only and the audio is muxed once from the continuous span (no seams in the narration)."""
    os.makedirs(os.path.dirname(out), exist_ok=True)
    parts = []
    spans = [(c["start"], c["end"], "B" if c["layout"].startswith("desktop") else "A")]
    if edl:
        spans = []
        for x in edl:
            a, b = max(c["start"], x["edit_start"]), min(c["end"], x["edit_start"] + x["frames"] / 30)
            if b - a > 0.02:
                if spans and spans[-1][2] == x["layout"] and abs(spans[-1][1] - a) < 1e-3: spans[-1] = (spans[-1][0], b, x["layout"])
                else: spans.append((a, b, x["layout"]))
    for k, (a, b, lay) in enumerate(spans):
        sub = dict(c, start=a, end=b); po = out.replace(".mp4", f"_part{k}.mp4")
        sub_cues = cues
        if lay != "A" and geometry:
            cx, cy, cw, ch = geometry["card"]; kx, ky, kd = geometry["camera"]
            above = [cx, cy, cw, ky - cy - 8]; left = [cx, cy, kx - cx - 8, ch]
            desk = [v // 2 * 2 for v in (c.get("desk_box") or max(above, left, key=lambda q: q[2] * q[3]))]
            cmd = vertical_cmd(cfg, src_final, sub_cues, sub, po, geometry["camera"], desk, c.get("hook_text", "") if k == 0 else "")
        else:
            fx = 656
            if face_track is not None and edl:
                seg = next(x for x in edl if x["edit_start"] <= a + 0.01 < x["edit_start"] + x["frames"] / 30)
                F0 = seg["face_in"] + a - seg["edit_start"]; F1 = F0 + (b - a)
                m = (face_track[:, 0] >= F0) & (face_track[:, 0] <= F1) & ~np.isnan(face_track[:, 1])
                if m.any(): fx = int(min(max(0, np.median(face_track[m, 1]) - 304), 1920 - 608)) // 2 * 2
            cmd = vertical_cmd(cfg, src_final, sub_cues, sub, po, [fx, 0, 608], None, c.get("hook_text", "") if k == 0 else "")
        j = cmd.index("0:a"); del cmd[j - 1:j + 1]                                 # video only for parts
        cmd = [x for x in cmd if x not in ("-c:a", "aac", "-b:a", "192k")]
        media.run(cmd); parts.append(po)
    lst = out + ".txt"
    with open(lst, "w") as f: f.writelines(f"file '{os.path.abspath(p)}'\n" for p in parts)
    media.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-ss", f"{c['start']:.3f}", "-t", f"{c['end'] - c['start']:.3f}",
               "-i", src_final, "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", out])
    for p_ in parts: os.remove(p_)
    os.remove(lst)
    if media.decode_errors(out): raise RuntimeError(f"{out}: decode errors")
    return out
