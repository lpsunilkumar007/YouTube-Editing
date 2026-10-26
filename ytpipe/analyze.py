"""Stage 'analyze': per-lecture measurements that were hand-made for Lesson 01. All cached in analysis/.

slide_area   : columns/rows that stay near-black across sampled desktop frames are bars -> content box.
slide_changes: large, sustained frame differences inside the slide area (not ink: red pixels are excluded).
counter      : a small region in the bottom-right quarter whose pixels change exactly at slide changes and are static
               in between -> box (or None). Used to hide/redraw the burned-in counter.
ink          : red-pen pixel growth (onsets with bbox) at 10 fps.
content_mask : per-slide union of text+ink pixels (worst case) for camera/zoom clearance checks.
speech       : 10 ms speech map of the narration (pauses, for cut placement).
face_track   : face centre/size every 0.5 s (OpenCV Haar) -> fixed crop per take."""
import json, os
import numpy as np
from . import media

AW, AH = 480, 270          # analysis resolution for the desktop (16:9)

def _red(f):
    return (f[..., 0] > 150) & (f[..., 1] < 90) & (f[..., 2] < 100)

def sample_desktop(path, dur, fps=2.0):
    return media.frames(path, 0, dur, AW, AH, fps, pix="rgb24")

def slide_area(fr, thr=12):
    """Bounding box (full-res px) of everything that is ever brighter than near-black."""
    lum = fr.max(axis=(0, 3)) if fr.ndim == 4 else fr.max(axis=0)
    cols = np.nonzero((lum > thr).mean(0) > 0.02)[0]; rows = np.nonzero((lum > thr).mean(1) > 0.02)[0]
    if not len(cols) or not len(rows):
        return None
    s = 1920 / AW
    # bars are contiguous from the frame edge; keep the inner region between them
    x0, x1 = int(cols[0] * s), int((cols[-1] + 1) * s); y0, y1 = int(rows[0] * s), int((rows[-1] + 1) * s)
    # snap to the frame edge when within one analysis pixel (no real bar)
    x0 = 0 if x0 <= s else x0; y0 = 0 if y0 <= s else y0
    x1 = 1920 if 1920 - x1 <= s else x1; y1 = 1080 if 1080 - y1 <= s else y1
    return [x0, y0, x1, y1]

def slide_changes(fr, fps, area, min_frac=0.008, settle=1.0):
    """Times where >= min_frac of the slide area changes (ignoring red ink) and the new state persists `settle` s.
    0.8 % sits well above pen/cursor noise (<= 0.1 % measured) and below a minimal slide build (1.7 % on the fixture)."""
    s = AW / 1920; x0, y0, x1, y1 = [int(round(v * s)) for v in area]
    g = fr[:, y0:y1, x0:x1].astype(np.int16); red = _red(fr[:, y0:y1, x0:x1])
    d = (np.abs(np.diff(g, axis=0)).max(-1) > 40) & ~red[1:] & ~red[:-1]
    frac = d.reshape(len(d), -1).mean(1)
    out, k = [], 0
    while k < len(frac):
        if frac[k] >= min_frac:
            j = k + int(settle * fps)
            if j >= len(g) or np.abs(g[min(j, len(g) - 1)] - g[k + 1]).max(-1).mean() < 8:
                out.append(round((k + 1) / fps, 2)); k += int(settle * fps); continue
        k += 1
    return out

def blank_spans(fr, fps, area, thr=12, frac=0.9, gap=2.0):
    """Desktop times [start, end] where the slide area is (almost) all black: PowerPoint's 'End of slide show' screen
    or a black slide. Measured: 99.8 % of the area dark on those frames, at most 4 % on the dark-themed slides.
    Spans closer than `gap` s merge."""
    s = AW / 1920; x0, y0, x1, y1 = [int(round(v * s)) for v in area]
    dark = (fr[:, y0:y1, x0:x1].max(-1) < thr).reshape(len(fr), -1).mean(1)
    out = []
    for i in np.nonzero(dark >= frac)[0]:
        t = i / fps
        if out and t - out[-1][1] <= gap: out[-1][1] = round(t + 1 / fps, 2)
        else: out.append([round(t, 2), round(t + 1 / fps, 2)])
    return out

def counter_box(path, dur, changes, area, n_off=24, thr=30):
    """Full-resolution check of the bottom-right quarter of the slide: pixels that change across every slide change
    (frame 0.5 s before vs 0.5 s after) but stay static between changes (n_off pairs 0.5 s apart, away from changes)."""
    if len(changes) < 2:
        return None
    x0, y0, x1, y1 = area; cx, cy = (x0 + x1) // 2 // 2 * 2, (y0 + y1) // 2 // 2 * 2; w, h = (x1 - cx) // 2 * 2, (y1 - cy) // 2 * 2
    crop = f"crop={w}:{h}:{cx}:{cy}"
    def pair(t):
        f = media.frames(path, max(0, t - 0.5), 1.0, w, h, 2.0, vf_pre=crop).astype(np.int16)
        return np.abs(f[-1] - f[0]) > thr if len(f) >= 2 else np.zeros((h, w), bool)
    at = np.mean([pair(t) for t in changes], 0)
    quiet = [t for t in np.linspace(1, dur - 1, n_off * 3) if all(abs(t - c) > 1.5 for c in changes)][:n_off]
    off = np.mean([pair(t) for t in quiet], 0) if quiet else np.zeros_like(at)
    cand = (at > 0.5) & (off < 0.05)
    ys, xs = np.nonzero(cand)
    if len(xs) < 4:
        return None
    bx = [cx + int(xs.min()) - 4, cy + int(ys.min()) - 4, cx + int(xs.max()) + 5, cy + int(ys.max()) + 5]
    if (bx[2] - bx[0]) * (bx[3] - bx[1]) > 0.01 * 1920 * 1080:                 # too big to be a counter
        return None
    return bx

def ink_events(path, dur, fps=10.0, min_px=4, merge_gap=0.4):
    fr = media.frames(path, 0, dur, AW, AH, fps, pix="rgb24"); r = _red(fr)
    grow = (r[1:] & ~r[:-1]).sum((1, 2)); ev, on = [], None
    for k, n in enumerate(grow):
        if n >= min_px and on is None: on = k
        if (n < min_px or k == len(grow) - 1) and on is not None:
            m = (r[k + 1] & ~r[on]); ys, xs = np.nonzero(m); s = 1920 / AW
            if len(xs): ev.append({"start": round((on + 1) / fps, 2), "end": round((k + 1) / fps, 2),
                                   "bbox": [int(xs.min() * s), int(ys.min() * s), int((xs.max() + 1) * s), int((ys.max() + 1) * s)]})
            on = None
    merged = []                                       # one stroke = growth runs separated by < merge_gap
    for e in ev:
        if merged and e["start"] - merged[-1]["end"] < merge_gap:
            m = merged[-1]; m["end"] = e["end"]
            m["bbox"] = [min(m["bbox"][0], e["bbox"][0]), min(m["bbox"][1], e["bbox"][1]),
                         max(m["bbox"][2], e["bbox"][2]), max(m["bbox"][3], e["bbox"][3])]
        else:
            merged.append(dict(e))
    return merged

def content_masks(fr, fps, changes, dur):
    """Per slide (between changes): union of non-background pixels (worst case) at analysis resolution."""
    edges = [0.0] + list(changes) + [dur]; masks = []
    for a, b in zip(edges, edges[1:]):
        seg = fr[int(a * fps): max(int(a * fps) + 1, int(b * fps))]
        bg = np.median(seg[:, ::8, ::8].reshape(-1, 3), 0)
        masks.append((np.abs(seg.astype(np.int16) - bg).max(-1) > 40).any(0))
    return masks

def speech_map(path, channel=0, step=0.01, win=0.02):
    """10 ms RMS (dBFS) of the narration channel, plus speech/pause runs at editing.speech_threshold_dbfs."""
    x = media.audio(path, sr=16000, channel=channel)
    hop, w = int(step * 16000), int(win * 16000)
    c = np.concatenate([[0], np.cumsum(x.astype(np.float64) ** 2)]); idx = np.arange(0, len(x) - w, hop)
    return 10 * np.log10((c[idx + w] - c[idx]) / w + 1e-12)

def pauses(env, thr=-50.0, min_len=0.25, step=0.01):
    q = env < thr; out, s = [], None
    for i, v in enumerate(q):
        if v and s is None: s = i
        if (not v or i == len(q) - 1) and s is not None:
            if (i - s) * step >= min_len: out.append((round(s * step, 2), round(i * step, 2)))
            s = None
    return out

def face_track(path, dur, every=0.5, w=960, h=540, vf_pre=""):
    import cv2
    cas = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    fr = media.frames(path, 0, dur, w, h, 1 / every, vf_pre=vf_pre); s = 1920 / w; out = []
    for k, g in enumerate(fr):
        f = cas.detectMultiScale(g, 1.1, 5, minSize=(40, 40))
        if len(f):
            x, y, fw, fh = max(f, key=lambda r: r[2] * r[3]); out.append([k * every, (x + fw / 2) * s, (y + fh / 2) * s, fw * s])
        else:
            out.append([k * every, np.nan, np.nan, np.nan])
    return np.array(out)

def run(cfg, meta, steps=("desktop", "speech", "face")):
    A = cfg["paths"]["analysis"]; os.makedirs(A, exist_ok=True); res = {}
    desk = cfg["sources"]["desktop_recording"]; ddur = meta["desktop_recording"]["duration"]
    from concurrent.futures import ThreadPoolExecutor
    pool = ThreadPoolExecutor(2)                      # face and speech decode while the desktop is analysed
    face = pool.submit(face_track, cfg["sources"]["face_camera"], meta["face_camera"]["duration"]) if "face" in steps else None
    speech = pool.submit(speech_map, cfg["sources"]["face_camera"], 0) if "speech" in steps else None
    try:
        if "desktop" in steps:
            fr = sample_desktop(desk, ddur, 2.0)
            area = slide_area(fr) if cfg["layout"]["slide_area"] == "auto" else cfg["layout"]["slide_area"]
            ch = slide_changes(fr, 2.0, area)
            cb = counter_box(desk, ddur, ch, area) if cfg["layout"]["counter"] == "auto" else cfg["layout"]["counter"]
            masks = content_masks(fr, 2.0, ch, ddur)
            np.savez_compressed(os.path.join(A, "content_masks.npz"), *masks)
            res.update(slide_area=area, slide_changes=ch, counter_box=cb, ink=ink_events(desk, ddur), blank_spans=blank_spans(fr, 2.0, area)); del fr
        if "speech" in steps:
            env = speech.result()
            np.save(os.path.join(A, "speech_env.npy"), env.astype(np.float32))
            res["pauses"] = pauses(env, cfg["editing"]["speech_threshold_dbfs"])
        if "face" in steps:
            np.save(os.path.join(A, "face_track.npy"), face.result())
    finally:
        pool.shutdown(wait=False, cancel_futures=True)   # a failed step does not leave queued decodes behind
    old = {}
    p = os.path.join(A, "analysis.json")
    if os.path.exists(p): old = json.load(open(p, encoding="utf-8"))
    old.update(res)
    with open(p, "w", encoding="utf-8") as f: json.dump(old, f, indent=1)
    return old
