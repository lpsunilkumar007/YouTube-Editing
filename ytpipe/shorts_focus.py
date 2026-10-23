"""Guided split screen (Shorts v4, approved 2026-10-22): the desktop half of layout A follows what is being explained.

For every narration line of an A part, the region being explained is found on the ORIGINAL desktop frame from
  1. the new pen ink drawn while the line is spoken (strongest signal: you point at it), and
  2. slide text that the line names (Windows' built-in offline OCR of the frame; English words of the Hinglish line,
     e.g. "hardware", "touch", "operating system" -> the HARDWARE / "parts you can touch" block).
The desktop is then cropped to that region plus context, at a readable scale (>= ~0.83x instead of ~0.6x for the
whole slide). Nothing is generated: crops of the recorded desktop only.
Shot rules: a reframe is a hard cut placed in a measured pause (on a tightened jump cut when one is near), shots are
>= min_shot s, neighbouring lines with the same region share a shot, a line naming nothing keeps the current framing,
and regions too wide for a readable crop fall back to the whole-content overview. The presenter rectangle and the
split proportions stay fixed for the whole part, so only the desktop reframes."""
import json, os, re, subprocess
import cv2
import numpy as np
from . import media

PS1 = os.path.join(os.path.dirname(__file__), "ocr_win.ps1")
STOP = set("the a an is are to of and or for in on at it as be by we our you your can cannot not this that with from what "
           "set use one two more each other they them their its has have does did will just so then than very here there "
           "ek hai hain ho ki ke ka ko se ye wo jo kya hum log main mera".split())

def ocr(desktop, times, cache):
    """OCR of desktop frames at the given desktop times (cached per time). Returns {t: [line, ...]}."""
    db = json.load(open(cache, encoding="utf-8")) if os.path.exists(cache) else {}
    todo = [t for t in times if f"{t:.2f}" not in db]
    if todo:
        d = os.path.join(os.path.dirname(cache), "_ocr"); os.makedirs(d, exist_ok=True); imgs = []
        for t in todo:
            p = os.path.join(d, f"d{t:.2f}.png"); imgs.append(p)
            media.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", desktop, "-frames:v", "1", p])
        out = os.path.join(d, "ocr.json")
        subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", PS1, out, *imgs], check=True, capture_output=True)
        for t, r in zip(todo, json.load(open(out, encoding="utf-8-sig"))): db[f"{t:.2f}"] = r["lines"]
        for p in imgs: os.remove(p)
        json.dump(db, open(cache, "w", encoding="utf-8"), ensure_ascii=False)
    return {t: db[f"{t:.2f}"] for t in times}

def blocks(lines, area, header=290, footer=1000):
    """Group OCR lines into blocks (a heading with its sub-lines, a card, a paragraph). The slide title/subtitle band
    and the footer are ignored: the title is context, not the thing being explained."""
    L = []
    for l in lines:
        ws = l["words"]; x0 = min(w["x"] for w in ws); y0 = min(w["y"] for w in ws)
        x1 = max(w["x"] + w["w"] for w in ws); y1 = max(w["y"] + w["h"] for w in ws)
        if y1 < header or y0 > footer or x0 >= area[2]: continue
        L.append({"box": [x0, y0, x1, y1], "words": [(w["t"], w["h"]) for w in ws], "h": y1 - y0})
    B = []
    for l in sorted(L, key=lambda q: q["box"][1]):
        for b in B:
            bx = b["box"]; lx = l["box"]; gap = lx[1] - bx[3]
            if -0.5 * l["h"] <= gap <= 1.2 * max(l["h"], b["lh"]) and min(bx[2], lx[2]) - max(bx[0], lx[0]) > 0.3 * min(bx[2] - bx[0], lx[2] - lx[0]):
                b["box"] = [min(bx[0], lx[0]), min(bx[1], lx[1]), max(bx[2], lx[2]), max(bx[3], lx[3])]; b["words"] += l["words"]; b["lh"] = l["h"]; break
        else:
            B.append({"box": list(l["box"]), "words": list(l["words"]), "lh": l["h"]})
    return B

def _norm(w):
    return re.sub(r"[^a-z0-9]", "", w.lower())

def _union(bs):
    return [min(b[0] for b in bs), min(b[1] for b in bs), max(b[2] for b in bs), max(b[3] for b in bs)]

def match(text, B, fits=lambda box: True, weak=()):
    """Region named by the narration line. Content words (>= 3 letters, prefix-tolerant: part/parts) are matched
    against the blocks; blocks are grouped in rows (a diagram row, two columns side by side) and a row scores the sum,
    per spoken word, of the tallest matching glyphs (headings beat body text). Best row -> its matched blocks; when they
    are too wide for a readable crop, the best single block. None when nothing is named. Words of the slide title
    (weak) are the slide's topic, said throughout, and count 0.3."""
    said = {_norm(w) for w in text.split()} - STOP
    said = [w for w in said if len(w) >= 3]
    def hit(w):
        w = _norm(w)
        return next((s for s in said if w == s or (min(len(w), len(s)) >= 4 and (w.startswith(s) or s.startswith(w)))), None) if len(w) >= 3 and w not in STOP else None
    sc = []
    for b in B:
        h = {}
        for w, wh in b["words"]:
            s = hit(w)
            if s: h[s] = max(h.get(s, 0), wh * (0.3 if s in weak else 1))
        sc.append(h)
    rows = []
    for i in sorted(range(len(B)), key=lambda i: B[i]["box"][1]):
        if not sc[i]: continue
        bx = B[i]["box"]; r = next((r for r in rows if min(r["box"][3], bx[3]) - max(r["box"][1], bx[1]) > 0.3 * min(r["box"][3] - r["box"][1], bx[3] - bx[1])), None)
        if r: r["idx"].append(i); r["box"] = _union([r["box"], bx])
        else: rows.append({"idx": [i], "box": list(bx)})
    if not rows or (all(set(sc[i]) <= set(weak) for r in rows for i in r["idx"])       # title words alone are weak evidence,
                    and max(len(set().union(*[sc[i] for i in r["idx"]])) for r in rows) < 2): return None   # unless 2+ of them name one row
    def score(idx):
        h = {}
        for i in idx:
            for s, wh in sc[i].items(): h[s] = max(h.get(s, 0), wh)
        return sum(h.values())
    best = max(rows, key=lambda r: score(r["idx"])); u = _union([B[i]["box"] for i in best["idx"]])
    return u if fits(u) else B[max(best["idx"], key=lambda i: (score([i]), -B[i]["box"][0]))]["box"]

def ink_box(desktop, D0, D1, min_px=40):
    """Robust box (desktop px) of the new red ink drawn in [D0, D1], or None."""
    fr = media.frames(desktop, D0, max(0.6, D1 - D0), 480, 270, 4.0, pix="rgb24").astype(np.int16)
    red = (fr[..., 0] > 150) & (fr[..., 1] < 90) & (fr[..., 2] < 100); new = red.any(0) & ~red[0]
    ys, xs = np.nonzero(new)
    if len(xs) < min_px: return None
    k = 4; return [np.percentile(xs, 1) * k, np.percentile(ys, 1) * k, (np.percentile(xs, 99) + 1) * k, (np.percentile(ys, 99) + 1) * k]

def sliced(crop, boxes, tol=4):
    """Text lines [x0, y0, x1, y1] that a crop [x, y, w, h] cuts through (partly inside, partly outside)."""
    X, Y, w, h = crop
    return [q for q in boxes if q[2] > X + tol and q[0] < X + w - tol and q[3] > Y + tol and q[1] < Y + h - tol
            and not (q[0] >= X - tol and q[2] <= X + w + tol and q[1] >= Y - tol and q[3] <= Y + h + tol)]

def _even(c, area):
    """Crop to even pixels, rounded outward (never shaved into a text line), inside the area."""
    x0 = max(area[0], int(c[0]) // 2 * 2); y0 = max(area[1], int(c[1]) // 2 * 2)
    x1 = min(area[2], -(-int(np.ceil(c[0] + c[2])) // 2) * 2); y1 = min(area[3], -(-int(np.ceil(c[1] + c[3])) // 2) * 2)
    return [x0, y0, (x1 - x0) // 2 * 2, (y1 - y0) // 2 * 2]

def best_frame(must, area, out_w, out_h, cap, boxes, pad=(16, 12)):
    """Most readable crop [x, y, w, h] that contains `must` and cuts no text line at an edge (user, 2026-10-22: wider
    crops rather than clipped words). Edges are tried in every gap between text lines. Score: the displayed scale
    min(out_w / w, out_h / h) (at most `cap`, never zoomed further) times the square root of the share of the output box
    it fills (a thin strip in a tall box wastes the screen), then the larger area (more context).
    The crop may be narrower or shorter than the output aspect (it is then padded, never stretched). None if no crop
    can avoid cutting a line."""
    sx0, sy0, sx1, sy1 = area; m0, m1, m2, m3 = must
    if m0 < sx0 - 1 or m2 > sx1 + 1: return None
    m0, m1, m2, m3 = max(m0, sx0), max(m1, sy0), min(m2, sx1), min(m3, sy1)
    Q = np.array([[max(q[0], sx0), max(q[1], sy0), min(q[2], sx1), min(q[3], sy1)] for q in boxes if q[2] > sx0 and q[0] < sx1 and q[3] > sy0 and q[1] < sy1] or np.zeros((0, 4)), float)
    px, py = pad
    Ls = sorted({sx0, m0} | {v for v in np.r_[Q[:, 2] + px, Q[:, 0] - px] if sx0 <= v <= m0})
    Rs = sorted({sx1, m2} | {v for v in np.r_[Q[:, 0] - px, Q[:, 2] + px] if m2 <= v <= sx1})
    Ts = sorted({sy0, m1} | {v for v in np.r_[Q[:, 3] + py, Q[:, 1] - py] if sy0 <= v <= m1})
    Bs = sorted({sy1, m3} | {v for v in np.r_[Q[:, 1] - py, Q[:, 3] + py] if m3 <= v <= sy1})
    L, R = np.array(Ls)[:, None, None], np.array(Rs)[None, :, None]; best, key = None, None
    for T in Ts:
        for B_ in Bs:
            h = B_ - T; w = R - L                                  # (nL, nR, 1)
            if len(Q):
                x0, y0, x1, y1 = Q[:, 0], Q[:, 1], Q[:, 2], Q[:, 3]
                hit = (x1 > L + 2) & (x0 < R - 2) & (y1 > T + 2) & (y0 < B_ - 2)   # stricter than sliced(): safe after rounding outward
                inside = (x0 >= L - 4) & (x1 <= R + 4) & (y0 >= T - 4) & (y1 <= B_ + 4)
                ok = ~(hit & ~inside).any(-1)
            else: ok = np.ones(w.shape[:2], bool)
            sc = np.minimum(out_w / w[..., 0], out_h / h)
            ok &= sc <= cap + 1e-6                                 # never zoom past the cap
            fill = w[..., 0] * h * sc ** 2 / (out_w * out_h)          # share of the output box the crop covers
            for i, j in zip(*np.nonzero(ok)):
                k = (round(float(sc[i, j] * fill[i, j] ** 0.5), 2), float(w[i, j, 0] * h))
                if key is None or k > key: key, best = k, [Ls[i], T, Rs[j] - Ls[i], h]
    return best

def crop_for(roi, area, aspect, min_w=900, margin=70, boxes=(), title=290):
    """Readable crop (source px, given aspect) around a region of interest; None when the region is too wide.
    boxes: text-line boxes [x0, y0, x1, y1] of the slide. No word is ever cut at an edge: best_frame picks the most
    readable crop (at most min_w wide at the output scale) whose edges lie between text lines, then it is widened to the
    output aspect where that cuts nothing. title: kept for callers (no special case now)."""
    sx0, sy0, sx1, sy1 = area; max_w = min(sx1 - sx0, (sy1 - sy0) * aspect)
    x0, y0, x1, y1 = roi[0] - margin, roi[1] - margin, roi[2] + margin, roi[3] + margin
    if max(min_w, x1 - x0, (y1 - y0) * aspect) > max_w + 1: return None
    ow, oh = 1080.0, 1080.0 / aspect; cap = ow / min_w
    C = [best_frame([max(roi[0] - m, sx0), max(roi[1] - m, sy0), min(roi[2] + m, sx1), min(roi[3] + m, sy1)], area, ow, oh, cap, boxes)
         for m in (margin, margin / 2, 0)]                         # a smaller margin only when it keeps the text clearly larger
    C = [c for c in C if c]
    if not C: return None
    sc = lambda c: min(ow / c[2], oh / c[3]) * (c[2] * c[3] * min(ow / c[2], oh / c[3]) ** 2 / (ow * oh)) ** 0.5; top = max(sc(c) for c in C); c = next(c for c in C if sc(c) >= 0.9 * top)
    X, Y, w, h = c; W = max(w, h * aspect, min_w); H = W / aspect
    if W <= max_w + 1:                                             # fill the output aspect (context) when nothing is cut
        cx, cy = X + w / 2, Y + h / 2; g = [min(max(sx0, cx - W / 2), sx1 - W), min(max(sy0, cy - H / 2), sy1 - H), W, H]
        if g[0] <= X + 1 and g[1] <= Y + 1 and g[0] + W >= X + w - 1 and g[1] + H >= Y + h - 1 and not sliced(g, boxes): X, Y, w, h = g
    return _even([X, Y, w, h], area)

def unclip(crop, area, aspect, boxes, min_w=700, must=None):
    """An existing crop (overview, desktop focus) changed so that no text line is cut at its edges. Kept inside: `must`
    (e.g. the pen writing of a desktop focus) or else the crop's inner part (60 px in from each edge); the zoom never
    exceeds the original's."""
    if not crop or not boxes or not sliced(crop, boxes): return crop
    X, Y, w, h = crop; ow, oh = 1080.0, 1080.0 / aspect; cap = min(ow / w, oh / h)
    c = None
    if must:
        m = [max(must[0], X), max(must[1], Y), min(must[2], X + w), min(must[3], Y + h)]
        c = next((c for c in (best_frame([m[0] - g, m[1] - g, m[2] + g, m[3] + g], area, ow, oh, cap, boxes) for g in (40, 0)) if c), None)
    c = c or best_frame([X + 60, Y + 60, X + w - 60, Y + h - 60], area, ow, oh, cap, boxes)
    return _even(c, area) if c else crop

def glyph_boxes(desktop, t, area, gap=31):
    """Printed text on the desktop frame at time t, found from the pixels (not OCR): every non-background, non-pen
    pixel, letters joined into words and words into lines (gaps < `gap` px). Catches text OCR misses (under pen ink,
    partly read titles). Thin rules and dividers are skipped. Boxes [x0, y0, x1, y1] inside the slide area."""
    f = media.frames(desktop, t, 0.05, 1920, 1080, 30, pix="rgb24")[0].astype(np.int16)
    bg = np.median(f[::8, ::8].reshape(-1, 3), 0)
    pen = cv2.dilate(((f[..., 0] - np.maximum(f[..., 1], f[..., 2])) > 30).astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
    m = ((np.abs(f - bg).max(-1) > 50) & ~pen).astype(np.uint8)
    m[:, area[2]:] = 0; m[:, :area[0]] = 0; m[:area[1]] = 0; m[area[3]:] = 0
    for k in ((81, 1), (1, 161)):                                  # rules / dividers are not text (a long thin run of pixels)
        m &= ~cv2.morphologyEx(m, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, k)).astype(bool)
    n, _, st, _ = cv2.connectedComponentsWithStats(cv2.dilate(m, cv2.getStructuringElement(cv2.MORPH_RECT, (gap, 5))))
    return [[int(x) + gap // 2 - 10, int(y), int(x + w) - gap // 2 + 10, int(y + h)] for x, y, w, h, _ in st[1:]   # +10 px: letter edges under the pen
            if h >= 10 and not (w > 400 and h < 14)]

def text_boxes(desktop, times, cache, area):
    """Text-line boxes at the given desktop times: OCR lines plus pixel-found lines (glyph_boxes)."""
    fr = ocr(desktop, times, cache)
    return [q for lines in fr.values() for q in line_boxes(lines)] + [q for t in times for q in glyph_boxes(desktop, t, area)]

def line_boxes(lines):
    return [[min(w["x"] for w in l["words"]), min(w["y"] for w in l["words"]), max(w["x"] + w["w"] for w in l["words"]), max(w["y"] + w["h"] for w in l["words"])] for l in lines]

def _iou(a, b):
    ix = max(0, min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])); iy = max(0, min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1]))
    return ix * iy / (a[2] * a[3] + b[2] * b[3] - ix * iy)

def title_words(lines, header=290):
    return {_norm(w["t"]) for l in lines for w in l["words"] if 90 < w["y"] + w["h"] < header}

def guided(f0, f1, line_starts, texts, desktop, offset, area, aspect, pauses, overview, cache, min_shot=4.0, log=None):
    """Shots of one A part: [(s0, s1, crop)] in face time. line_starts/texts: narration lines (face time, any range);
    pauses: [(a, b)] measured pauses (face time); overview: the whole-content crop (context: used for the opening line
    when it names nothing, and for regions too wide to read)."""
    starts = [f0] + [s for s in line_starts if f0 + 0.3 < s < f1 - 0.3]; ends = starts[1:] + [f1]
    txt = [next((t for s_, t in reversed(list(zip(line_starts, texts))) if s_ <= s + 0.31), "") for s in starts]   # line spoken at s
    fr = ocr(desktop, [round(f0 + offset + 0.2, 2), round(f1 + offset - 0.2, 2)], cache)
    B = [b for lines in fr.values() for b in blocks(lines, area)]; weak = set().union(*[title_words(l) for l in fr.values()])
    LB = text_boxes(desktop, list(fr), cache, area)
    fits = lambda u: crop_for(u, area, aspect) is not None; overview = unclip(overview, area, aspect, LB, 900)
    rows, R = [], {}                                               # R: crop -> the region of interest it frames
    for s, e, t in zip(starts, ends, txt):
        ink = ink_box(desktop, s + offset, e + offset); m = match(t, B, fits, weak)
        roi = (_union([ink, m]) if fits(_union([ink, m])) else ink) if ink and m else (ink or m)   # pen and words disagree: the pen wins
        c = (crop_for(roi, area, aspect, boxes=LB) or overview) if roi else None
        if c and c is not overview: R[tuple(c)] = roi
        rows.append([s, e, c])
        if log is not None: log.append({"t": [round(s, 2), round(e, 2)], "text": t, "ink": ink and [int(v) for v in ink], "words": m, "crop": rows[-1][2]})
    for i in range(len(rows)):                                     # naming nothing: the opening shows the overview, later lines keep the framing
        if rows[i][2] is None: rows[i][2] = rows[i - 1][2] if i else overview
    def join(c1, c2):                                              # one framing for both: their union when barely wider
        if c1 == c2: return c1
        r1, r2 = R.get(tuple(c1)), R.get(tuple(c2))
        if r1 and r2:                                              # both regions of interest in one readable crop
            u = crop_for(_union([r1, r2]), area, aspect, boxes=LB)
            if u and u[2] <= 1.15 * max(c1[2], c2[2]): R[tuple(u)] = _union([r1, r2]); return u
        u = crop_for(_union([[c[0], c[1], c[0] + c[2], c[1] + c[3]] for c in (c1, c2)]), area, aspect, margin=0, boxes=LB)
        return u if u and u[2] <= 1.08 * max(c1[2], c2[2]) else None
    shots = []
    for s, e, c in rows:                                           # same region -> same shot
        if shots and (shots[-1][2] == c or _iou(shots[-1][2], c) >= 0.55):   # union if barely wider, else the longer-held framing
            shots[-1][2] = join(shots[-1][2], c) or (shots[-1][2] if shots[-1][1] - shots[-1][0] >= e - s else c); shots[-1][1] = e
        else: shots.append([s, e, c])
    for k in range(len(shots) - 1, 0, -1):                         # reframes only in measured pauses (prefer >= 0.35 s ones)
        s = shots[k][0]; lo, hi = max(shots[k - 1][0] + 1.0, s - 1.5), min(shots[k][1] - 1.0, s + 1.0)
        P = [p for p in pauses if lo <= (p[0] + p[1]) / 2 <= hi]
        if P:
            p = min(P, key=lambda p: (p[1] - p[0] < 0.35, abs((p[0] + p[1]) / 2 - s))); shots[k][0] = shots[k - 1][1] = (p[0] + p[1]) / 2
        else:                                                      # no pause near: no reframe
            shots[k - 1] = [shots[k - 1][0], shots[k][1], join(shots[k - 1][2], shots[k][2]) or max(shots[k - 1:k + 1], key=lambda q: q[1] - q[0])[2]]; del shots[k]
    while len(shots) > 1 and min(b - a for a, b, _ in shots) < min_shot:   # short shots join a neighbour
        i = min(range(len(shots)), key=lambda j: shots[j][1] - shots[j][0])
        j = i - 1 if i == len(shots) - 1 or (i > 0 and shots[i - 1][1] - shots[i - 1][0] >= shots[i + 1][1] - shots[i + 1][0]) else i + 1
        a, b = min(i, j), max(i, j); shots[a:b + 1] = [[shots[a][0], shots[b][1], join(shots[a][2], shots[b][2]) or shots[j][2]]]
    out = []
    for s, e, c in shots:
        if out and out[-1][2] == c: out[-1][1] = e
        else: out.append([s, e, c])
    return [(round(a, 3), round(b, 3), c) for a, b, c in out]
