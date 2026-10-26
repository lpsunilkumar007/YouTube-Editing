"""Shorts / Reels v3: vertical layouts WITHOUT circular camera overlays (circles are for long-form only).

Layouts (1080x1920, 30 fps; pictures from the ORIGINAL recordings, approved HDR->SDR; audio = final mix of the span):
  B  full-frame presenter : 9:16 crop of the original camera, face centred, head and shoulders room, never stretched
  A  split screen          : desktop full width on top (content-fitted, padded not stretched), caption band, presenter
                             as a full-width rectangle below (face in the upper part of the rectangle, clear of the UI)
  C  desktop focus         : zoom into the region being worked on (the ink drawn in that span + nearby content),
                             presenter hidden, captions below the desktop
Automatic plan: hook (first sentence) and conclusion (last sentence) -> B; while a slide is shown -> A; sub-spans where
the presenter writes for >= 3 s -> C; every switch is placed in a measured pause; parts shorter than 3 s are merged.
Captions: Hinglish SRT cues of the span, glossary terms highlighted in lime; position per layout, never over the face
or the desktop, above the Shorts/Reels interface zone (bottom ~23 %, right 190 px)."""
import json, os, re
import numpy as np
from . import media, render as R
from .shorts_v2 import content_crop, _esc

W, H, FPS = 1080, 1920, 30
G = {"A": {"desk": (0, 0, 1080, 900), "cap_band": (900, 1040), "face": (0, 1040, 1080, 880)},
     "C": {"desk": (0, 110, 1080, 1260), "cap_band": (1385, 1480)},
     "B": {"cap_bottom": 1470}}
NAVY = "0x0C1525"

# ---------------------------------------------------------------- planning
def pauses(env, a, b, thr=-50, min_len=0.12):
    i0, i1 = int(a * 100), int(b * 100); q = env[i0:i1] < thr; out, s = [], None
    for i, v in enumerate(q):
        if v and s is None: s = i
        if (not v or i == len(q) - 1) and s is not None:
            if (i - s) / 100 >= min_len: out.append(((i0 + s) / 100, (i0 + i) / 100))
            s = None
    return out

def ink_runs(desktop, D0, D1, offset, min_px=6, max_frac=0.45, slide_w=1890, min_len=2.5):
    """Concentrated writing (zoom candidates), in face time: consecutive 0.5 s windows with new red ink whose COMBINED
    bounding box stays within max_frac of the slide width. Ink spread across the slide (circling items of a diagram)
    is not a zoom candidate: the whole diagram matters there, so the split view is kept."""
    fr = media.frames(desktop, D0, D1 - D0, 480, 270, 10.0, pix="rgb24").astype(np.int16)
    red = (fr[..., 0] > 150) & (fr[..., 1] < 90) & (fr[..., 2] < 100); wins = []
    for k in range(0, len(red) - 5, 5):
        new = red[k + 5] & ~red[k]; ys, xs = np.nonzero(new)
        if len(xs) >= min_px: wins.append((D0 + k / 10 - offset, D0 + (k + 5) / 10 - offset, xs.min() * 4, xs.max() * 4))
    runs = []
    for t0, t1, x0, x1 in wins:
        if runs and t0 - runs[-1][1] <= 1.0 and max(x1, runs[-1][3]) - min(x0, runs[-1][2]) <= max_frac * slide_w:
            r = runs[-1]; runs[-1] = (r[0], t1, min(x0, r[2]), max(x1, r[3]))
        else:
            runs.append((t0, t1, x0, x1))
    return [(round(a, 2), round(b, 2)) for a, b, *_ in runs if b - a >= min_len]

def plan(F0, F1, sentence_starts, env, ink, slide_visible=True, min_part=3.0):
    """sentence_starts: face times of transcript lines in [F0, F1]. Returns [(f0, f1, layout)]."""
    P = pauses(env, F0, F1)
    def snap(t):                          # centre of the nearest pause (switches only in pauses)
        c = min(P, key=lambda p: abs((p[0] + p[1]) / 2 - t), default=None)
        return (c[0] + c[1]) / 2 if c and abs((c[0] + c[1]) / 2 - t) < 1.2 else t
    starts = sorted(s for s in sentence_starts if F0 + 2.5 < s < F1 - 2.5)
    hook_end = snap(starts[0]) if starts else F0 + min(6, (F1 - F0) / 3)
    concl = snap(starts[-1]) if len(starts) > 1 else F1
    parts = [(F0, hook_end, "B")]
    t = hook_end
    runs = [(max(a, hook_end), min(b, concl)) for a, b in ink]          # one zoom per Short (the longest writing run):
    ink = sorted(r for r in runs if r[1] - r[0] >= 3.0)                # no A/C ping-pong, no unnecessary switches
    ink = [max(ink, key=lambda r: r[1] - r[0])] if ink else []
    for a, b in ink:                                    # writing for >= 3 s inside the middle -> desktop focus
        a, b = max(a, hook_end), min(b, concl)
        if b - a < 3.0 or not slide_visible: continue
        a, b = snap(a - 0.5), snap(b + 0.5)
        if a - t >= min_part: parts.append((t, a, "A"))
        else: a = t                                     # too short for its own part: the zoom starts where we are
        parts.append((a, b, "C")); t = b
    if concl - t >= min_part: parts.append((t, concl, "A" if slide_visible else "B"))
    elif parts: parts[-1] = (parts[-1][0], concl, parts[-1][2])
    if F1 - concl > 0.5: parts.append((concl, F1, "B"))
    merged = []
    for p in parts:
        if merged and (p[2] == merged[-1][2] or p[1] - p[0] < min_part): merged[-1] = (merged[-1][0], p[1], merged[-1][2])
        else: merged.append(p)
    return [(round(a, 3), round(b, 3), l) for a, b, l in merged]

# ---------------------------------------------------------------- captions
def _ass(cues, path, layout, glossary_terms, band_bottom=None, style="line"):
    if layout == "A": mv, al = H - (band_bottom or G["A"]["cap_band"][1]) + (8 if style == "line" else 30), 2
    elif layout == "C": mv, al = H - G["C"]["cap_band"][1], 2
    else: mv, al = H - G["B"]["cap_bottom"], 2
    st = (f"Style: Cap,Poppins SemiBold,52,&H00FFFFFF,&H00FFFFFF,&H00000000,&H40251510,0,0,0,0,100,100,0,0,3,14,0,{al},70,190,{mv},1\n\n"
          if style == "line" else      # chunk: 2-4 words, bold white, black outline + soft shadow, no box, centred clear of the UI
          f"Style: Cap,Poppins Black,68,&H00FFFFFF,&H00FFFFFF,&H00000000,&H90000000,0,0,0,0,100,100,0,0,1,5,3,{al},190,190,{mv},1\n\n")
    head = (f"[Script Info]\nScriptType: v4.00+\nPlayResX: {W}\nPlayResY: {H}\n\n[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
            "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
            + st + "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
    rx = re.compile(r"(?<![\w#.])(" + "|".join(re.escape(t) for t in sorted(glossary_terms, key=len, reverse=True)) + r")(?![\w#])", re.I) if glossary_terms else None
    ts = lambda t: f"{int(t // 3600)}:{int(t // 60 % 60):02d}:{max(0, t) % 60:05.2f}"
    with open(path, "w", encoding="utf-8") as f:
        f.write(head)
        for a, b, t in cues:
            txt = t.replace("\n", r"\N")
            if rx: txt = rx.sub(lambda m: r"{\c&H35E6A3&}" + m.group(1) + r"{\c&HFFFFFF&}", txt)    # lime #A3E635 (ASS is BGR)
            f.write(f"Dialogue: 0,{ts(max(0, a))},{ts(b)},Cap,,0,0,0,,{txt}\n")

def chunk_cues(cues, env_at, max_words=4, max_chars=22):
    """Split caption lines into 2-4 word chunks (the reviewed text, never re-transcribed). Chunk times are proportional
    to characters and each boundary snaps to the quietest 10 ms of narration within +-0.2 s (env_at(edit_t) -> dB)."""
    out = []
    for a, b, t in cues:
        words = t.replace("\n", " ").split(); groups, g = [], []
        for w in words:
            if g and (len(g) >= max_words or len(" ".join(g + [w])) > max_chars): groups.append(g); g = []
            g.append(w)
        if g: groups.append(g)
        if len(groups) > 1 and len(groups[-1]) == 1 and len(" ".join(groups[-2] + groups[-1])) <= max_chars + 6:
            last = groups.pop(); groups[-1] += last           # no orphan single word at the end of a line
        n = [len(" ".join(x)) + 1 for x in groups]; cum = np.cumsum([0] + n) / sum(n); bnd = [a + c * (b - a) for c in cum]
        for k in range(1, len(bnd) - 1):
            cand = np.arange(max(bnd[k - 1] + 0.25, bnd[k] - 0.2), min(bnd[k + 1] - 0.25, bnd[k] + 0.2), 0.01)
            if len(cand): bnd[k] = float(cand[np.argmin([env_at(x) for x in cand])])
        out += [(bnd[k], bnd[k + 1], " ".join(x)) for k, x in enumerate(groups)]
    return out

def tighten(F0, F1, env, max_gap=0.25, min_pause=0.35, thr=-50):
    """Pause cores to remove (face time): every measured pause >= min_pause keeps max_gap/2 of room tone on each side,
    so cuts sit only inside measured pauses and never inside a word."""
    return [(a + max_gap / 2, b - max_gap / 2) for a, b in pauses(env, F0, F1, thr, min_pause) if b - a >= min_pause and a > F0 + 0.05 and b < F1 - 0.05]

# ---------------------------------------------------------------- picture
def _face_center(ft, f0, f1):
    m = (ft[:, 0] >= f0) & (ft[:, 0] <= f1) & ~np.isnan(ft[:, 1]) if ft is not None else None
    if m is None or not m.any(): return 960, 420, 250
    return float(np.median(ft[m, 1])), float(np.median(ft[m, 2])), float(np.median(ft[m, 3]))

def _pl(cfg, pipeline, w, h, crop):
    x, y, cw, ch = [int(v) // 2 * 2 for v in crop]
    if pipeline == "libplacebo":
        return f"libplacebo={cfg['color']['libplacebo']}:w={w}:h={h}:crop_x={x}:crop_y={y}:crop_w={cw}:crop_h={ch}:downscaler=ewa_lanczos:format=yuv420p"
    return f"crop={cw}:{ch}:{x}:{y},scale={w}:{h}:flags=lanczos"

def presenter_crop(ft, f0, f1, aspect, face_y=0.40, size=3.2):
    """Crop (source px) with the given aspect (w/h): head-and-shoulders room = size x face width tall, face at face_y."""
    cx, cy, fw = _face_center(ft, f0, f1); ch = min(1080, size * fw); cw = ch * aspect
    if cw > 1920: cw = 1920; ch = cw / aspect
    x = min(max(0, cx - cw / 2), 1920 - cw); y = min(max(0, cy - face_y * ch), 1080 - ch)
    return [x, y, cw, ch]

def focus_crop(desktop, D0, D1, area, aspect, min_w=700):
    """Desktop-focus region: ink drawn in [D0, D1] (+ margin), widened to the target aspect, >= min_w source px."""
    fr = media.frames(desktop, D0, max(0.6, D1 - D0), 480, 270, 5.0, pix="rgb24").astype(np.int16)
    red = (fr[..., 0] > 150) & (fr[..., 1] < 90) & (fr[..., 2] < 100); new = red.any(0) & ~red[0]
    ys, xs = np.nonzero(new)
    if len(xs) < 20: return None
    k = 4                                                                    # robust box: ignore isolated specks (cursor/noise)
    x0, x1 = np.percentile(xs, 2) * k - 60, (np.percentile(xs, 98) + 1) * k + 60
    y0, y1 = np.percentile(ys, 2) * k - 60, (np.percentile(ys, 98) + 1) * k + 60
    keep = (xs * k >= x0) & (xs * k <= x1) & (ys * k >= y0) & (ys * k <= y1); xs, ys = xs[keep], ys[keep]
    w, h = x1 - x0, y1 - y0; w, h = (w, w / aspect) if w / h > aspect else (h * aspect, h)
    w = max(w, min_w); h = w / aspect
    sx0, sy0, sx1, sy1 = area; w = min(w, sx1 - sx0); h = min(h, sy1 - sy0)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    X0 = min(max(sx0, cx - w / 2), sx1 - w); Y0 = min(max(sy0, cy - h / 2), sy1 - h)
    # snap the vertical edges to clean cut columns (between cards / diagram columns; a thin text line may be crossed):
    # narrowest [L, R] with all new ink inside and width >= min_w -> cards are never sliced, zoom stays as tight as possible
    bg = np.median(fr[0, ::6, ::6].reshape(-1, 3), 0); content = (np.abs(fr[-1] - bg).max(-1) > 40)
    band = content[int(Y0 / k):int(np.ceil((Y0 + h) / k))]; col = band.mean(0)
    cut = col <= np.percentile(col, 25) + 0.01
    ink_l, ink_r = xs.min() * k, (xs.max() + 1) * k
    Ls = [c * k for c in range(len(col)) if cut[c] and sx0 <= c * k <= ink_l]
    Rs = [c * k for c in range(len(col)) if cut[c] and ink_r <= c * k <= sx1]
    pairs = [(L_, R_) for L_ in Ls for R_ in Rs if R_ - L_ >= min_w and (R_ - L_) / aspect <= sy1 - sy0 + 1e-6] or             [(L_, R_) for L_ in Ls for R_ in Rs if R_ - L_ >= min_w]
    if pairs:
        L_, R_ = min(pairs, key=lambda p: p[1] - p[0]); w = R_ - L_; X0 = L_
        h = min(w / aspect, sy1 - sy0); Y0 = min(max(sy0, cy - h / 2), sy1 - h)
    # text lines sliced by the side edges (e.g. a long heading) near the top/bottom of the crop: trim them off when
    # >= 90 % of the new ink stays inside (the crop gets shorter and is padded, never stretched)
    lc, rc = int(X0 / k), int((X0 + w) / k) - 1; nr = content.shape[0]
    def cross(r):
        row = content[r]; return (lc > 0 and row[lc] and row[lc - 1]) or (rc < len(row) - 1 and row[rc] and row[rc + 1])
    sl = np.array([any(cross(q) for q in range(max(0, r - 1), min(nr, r + 2))) for r in range(nr)])   # gaps in glyphs bridged
    ink_in = lambda a_, b_: ((ys >= a_) & (ys < b_)).mean()
    r0, r1 = int(Y0 / k), min(nr, int(np.ceil((Y0 + h) / k)))
    q = r0
    while q < r0 + (r1 - r0) // 4 and not sl[q]: q += 1           # a sliced line in the top quarter ...
    if q < r0 + (r1 - r0) // 4:
        while q < r1 and sl[q:q + 5].any(): q += 1                  # through the whole sliced line
        e = q
        while q < min(r1, e + 4) and content[q, lc:rc + 1].any(): q += 1    # the rest of that line (descenders), max 16 px
        if ink_in(q, r1) >= 0.85: Y0, h = q * k, Y0 + h - q * k; r0 = q   # ... is cut off above
        else:                                                    # the ink is on that line: show the whole line instead
            t_ = r0
            while t_ > max(int(sy0 / k), r0 - 12) and content[t_ - 1, lc:rc + 1].any(): t_ -= 1
            Y1 = max(sy0, t_ * k - 12)
            if Y1 < Y0 and ink_in(int(Y1 / k), int((Y1 + h) / k)) >= 0.95: Y0 = Y1; r0, r1 = int(Y0 / k), min(nr, int(np.ceil((Y0 + h) / k)))
    q = r1 - 1
    while q > r1 - 1 - (r1 - r0) // 4 and not sl[q]: q -= 1       # same at the bottom
    if q > r1 - 1 - (r1 - r0) // 4:
        while q > r0 and sl[max(0, q - 4):q + 1].any(): q -= 1
        e = q
        while q > max(r0, e - 4) and content[q, lc:rc + 1].any(): q -= 1
        if ink_in(r0, q + 1) >= 0.85: h = (q + 1) * k - Y0
    return [X0, Y0, w, h]

def _fit(crop, box_w, box_h):
    """Scale a crop into a box preserving aspect ratio (pad, never stretch) -> (scaled w, h, x pad, y pad)."""
    s = min(box_w / crop[2], box_h / crop[3]); w, h = int(crop[2] * s) // 2 * 2, int(crop[3] * s) // 2 * 2
    return w, h, (box_w - w) // 2, (box_h - h) // 2

def clip_problems(F0, F1, words, segments, env=None, thr=-50.0):
    """A Short must start and end between words and should not jump across a cut in the lecture (removed content cannot
    come back, but the jump shows). An edge is mid-word when a transcribed word spans it AND the narration level there
    says the presenter is speaking (ASR word ends are approximate; a measured pause wins). words: [(start, end, ...)]
    face time; env: speech level per 10 ms. -> (refuse [], warn [])."""
    def speaking(e, side):                       # the 50 ms the Short would cut off: before its start, after its end
        k = int(e * 100); seg = env[max(0, k - 5):k + 1] if side < 0 else env[k:k + 6]
        return env is None or (len(seg) and seg.max() > thr)
    refuse = [f"{'start' if e == F0 else 'end'} {e:.2f} s falls inside the word '{str(w[2]).strip()}' ({w[0]:.2f}-{w[1]:.2f} s): "
              "move it to the pause before or after" for e, side in ((F0, -1), (F1, 1)) for w in words
              if w[0] + 0.03 < e < min(w[1], w[0] + 1.2) - 0.03 and speaking(e, side)]
    warn = [f"jumps across the lecture's cut at {a['face_out']:.2f} -> {b['face_in']:.2f} s"
            for a, b in zip(segments, segments[1:]) if b["face_in"] - a["face_out"] > 0.05 and F0 < a["face_out"] and b["face_in"] < F1]
    return refuse, warn

def pieces_of(parts, segments=None, cut_out=()):
    """[(face_a, face_b, layout, part_f0, part_f1)]: the parts minus the lecture's own cuts (so the final's audio stays in
    sync) and minus tightened pause cores. Crops are computed on the whole part, so a jump cut keeps its framing."""
    pieces = []
    for f0, f1, lay in parts:
        spans = [(max(f0, g["face_in"]), min(f1, g["face_in"] + g["frames"] / FPS)) for g in segments] if segments else [(f0, f1)]
        for c0, c1 in cut_out:
            spans = [q for a, b in spans for q in ([(a, b)] if c1 <= a or c0 >= b else [(a, c0), (c1, b)])]
        pieces += [(a, b, lay, f0, f1) for a, b in spans if b - a > 0.5 / FPS]
    return pieces

def render(cfg, final, cues, parts, offset, ft, pipeline, out, glossary_terms, edit_time, area=(0, 0, 1890, 1080), counter_box=None, segments=None,
           cut_out=(), audio_wav=None, cap_style="line", crops=None):
    """parts [(f0, f1, layout)] in face time; edit_time(F) maps to the final edit (audio source).
    crops: guided split shots {(f0, f1): {"desk": crop, "parent": (p0, p1)}} (shorts_focus): the desktop crop of that A
    shot; split proportions and the presenter crop come from the parent A part, so only the desktop reframes."""
    d = os.path.join(os.path.dirname(out), "_v3"); os.makedirs(d, exist_ok=True); hw = ["-init_hw_device", "vulkan"] if pipeline == "libplacebo" else []
    face, desk = cfg["sources"]["face_camera"], cfg["sources"]["desktop_recording"]; files, info = [], []
    wc = R.wide_crop(face); src = lambda c: c                              # face crops below are in 1920x1080 frame space
    if wc:                                                                 # wider source (e.g. 2864x1322): frame space = its
        fs = wc[3] / 1080; sw = 2 * wc[0] + wc[2]                           # centre 16:9 window, mapped uniformly (no stretch)
        if ft is not None:
            ft = ft.copy(); ft[:, 1] = (ft[:, 1] * sw / 1920 - wc[0]) / fs; ft[:, 3] = ft[:, 3] * sw / 1920 / fs
        src = lambda c: [wc[0] + c[0] * fs, c[1] * fs, c[2] * fs, c[3] * fs]
    e0 = edit_time(parts[0][0]); pieces = pieces_of(parts, segments, cut_out)
    for k, (f0, f1, lay, P0, P1) in enumerate(pieces):
        T = round((f1 - f0) * FPS) / FPS; po = os.path.join(d, f"p{k}.mp4"); ass = po.replace(".mp4", ".ass")
        ea = edit_time(f0) - e0; _ass([(a - e0 - ea, b - e0 - ea, t) for a, b, t in cues if b - e0 > ea and a - e0 < ea + T], ass, lay, glossary_terms, style=cap_style)
        base = ["ffmpeg", "-v", "error", "-y", *hw, "-ss", f"{f0:.4f}", "-t", f"{T:.4f}", "-i", face]
        if lay == "B":
            cx, cy, fw = _face_center(ft, P0, P1); cw = 608; x = min(max(0, cx - cw / 2), 1920 - cw)
            fc = f"[0:v]fps={FPS},{_pl(cfg, pipeline, W, H, src([x, 0, cw, 1080]))},setsar=1,subtitles='{_esc(ass)}'[v]"; cmd = base
            info.append({"part": k, "layout": "B full-frame presenter", "face_crop": [int(x), 0, cw, 1080], "upscale": round(H / 1080, 2)})
        else:
            D0 = f0 + offset
            gs = (crops or {}).get((P0, P1))
            if lay == "A" and gs:                                                          # guided split: fixed 1080x900 desktop
                bx, by, bw, bh = G["A"]["desk"]; dc = gs["desk"]; band = 130; pres = (0, bh + band, 1080, H - bh - band)
                _ass([(a - e0 - ea, b - e0 - ea, t) for a, b, t in cues if b - e0 > ea and a - e0 < ea + T], ass, lay, glossary_terms, bh + band, cap_style)
            elif lay == "A":
                bx, by, bw, bh = G["A"]["desk"]; dc = content_crop(desk, P0 + offset, P1 + offset, area, counter_box, aspect=bw / bh, min_w=900)
                fit_h = int(min(bh, max(0.55 * 1480, bw * dc[3] / dc[2])) // 2 * 2)       # dynamic split (usable height 1480)
                bh = fit_h; band = 130; pres = (0, bh + band, 1080, H - bh - band)
                _ass([(a - e0 - ea, b - e0 - ea, t) for a, b, t in cues if b - e0 > ea and a - e0 < ea + T], ass, lay, glossary_terms, bh + band, cap_style)
            else:
                bx, by, bw, bh = G["C"]["desk"]; dc = gs["desk"] if gs else focus_crop(desk, P0 + offset, P1 + offset, area, bw / bh) or content_crop(desk, P0 + offset, P1 + offset, area, counter_box, aspect=bw / bh, min_w=700)
            w, h, px, py = _fit(dc, bw, bh); x, y, cw, ch = [int(v) // 2 * 2 for v in dc]
            fc = (f"color=c={NAVY}:s={W}x{H}:r={FPS}:d={T:.4f},format=yuv420p[bg];"
                  f"[1:v]fps={FPS},crop={cw}:{ch}:{x}:{y},scale={w}:{h}:flags=lanczos,setsar=1[dk];[bg][dk]overlay={bx + px}:{by + py}[s1];")
            if lay == "A":
                fx, fy, fw_, fh_ = pres; pc = presenter_crop(ft, *(gs["parent"] if gs else (P0, P1)), fw_ / fh_, face_y=0.30)
                fc += f"[0:v]fps={FPS},{_pl(cfg, pipeline, fw_, fh_, src(pc))},setsar=1[pr];[s1][pr]overlay={fx}:{fy}[s2];[s2]subtitles='{_esc(ass)}'[v]"
                info.append({"part": k, "layout": "A guided split" if gs else "A split", "src": [P0, P1], "desktop_crop": [x, y, cw, ch], "desktop_scale": round(w / cw, 3), "presenter_crop": [int(v) for v in pc]})
            else:
                fc += f"[s1]subtitles='{_esc(ass)}'[v]"
                info.append({"part": k, "layout": "C desktop focus", "src": [P0, P1], "desktop_crop": [x, y, cw, ch], "desktop_scale": round(w / cw, 3)})
            cmd = base + ["-ss", f"{D0:.4f}", "-t", f"{T:.4f}", "-i", desk]
        cmd += ["-filter_complex", fc, "-map", "[v]", "-t", f"{T:.4f}", "-r", str(FPS), *cfg["output"]["x264"][:6], "-pix_fmt", "yuv420p",
                "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", "-color_range", "tv", "-an", po]
        media.run(cmd); files.append(po)
    lst = out + ".txt"; open(lst, "w").writelines(f"file '{os.path.abspath(p)}'\n" for p in files)
    dur = sum(round((p[1] - p[0]) * FPS) / FPS for p in pieces)
    aud = ["-i", audio_wav] if audio_wav else ["-ss", f"{e0:.4f}", "-t", f"{dur:.4f}", "-i", final]   # own mix, or the lecture's audio
    media.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, *aud,
               "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-t", f"{dur:.4f}", "-movflags", "+faststart", out])
    os.remove(lst)
    for p in files: os.remove(p)
    if media.decode_errors(out): raise RuntimeError(f"{out}: decode errors")
    return info
