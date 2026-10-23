"""Stage 'sync': offset L with desktop_time = face_time + L, estimated per lecture (never assumed).

1. metadata  : face capture clock (Apple creationdate / creation_time) vs desktop end clock (file mtime - duration).
               Coarse (clocks, finalisation delay): +-2.5 s. Always computed, used as the search prior.
2. audio_xcorr: only if BOTH files carry real audio. Coarse envelope cross-correlation over the whole overlap, then
               refined at 16 kHz in windows at start / middle / end -> offset, drift (ppm), confidence (peak/sidelobe).
3. manual    : sync.manual_offset_s (set by the user after checking the anchors this stage lists).
If the best available estimate is less certain than sync.max_uncertainty_s, status = "needs_input": the pipeline stops
and the report lists slide-change / ink anchors to confirm by eye (as done for Lesson 01, which had silent OBS audio)."""
import datetime as dt, json, os
import numpy as np
from scipy.signal import fftconvolve
from . import media

def _parse_time(s):
    if not s: return None
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None

def metadata_estimate(meta):
    f, d = meta["face_camera"], meta["desktop_recording"]
    fs = _parse_time(f.get("apple_creationdate")) or _parse_time(f.get("creation_time"))
    if fs is None:
        return None
    d_start = d["mtime"] - d["duration"] - 2.0          # OBS finalises the file ~1.5-3 s after the last frame
    return {"offset_s": round(fs - d_start, 2), "uncertainty_s": 2.5,
            "basis": "face creation clock vs desktop file mtime - duration (+2 s finalisation)"}

def _envelope(x, sr, hop):
    n = len(x) // hop
    return np.sqrt((x[:n * hop].reshape(n, hop) ** 2).mean(1))

def xcorr_lag(a, b):
    """lag (samples) such that b[t] ~ a[t - lag]; plus peak/sidelobe confidence."""
    a = (a - a.mean()) / (a.std() + 1e-9); b = (b - b.mean()) / (b.std() + 1e-9)
    c = fftconvolve(b, a[::-1], mode="full"); k = int(np.argmax(c)); lag = k - (len(a) - 1)
    side = np.delete(c, slice(max(0, k - 50), k + 50)); conf = float(c[k] / (np.abs(side).max() + 1e-9))
    return lag, conf

def audio_estimate(face, desk, prior=None, win_s=30.0):
    """Coarse: 100 Hz RMS envelopes over everything. Fine: 16 kHz windows at start/middle/end of the overlap."""
    sr_c, hop = 8000, 80
    fa = media.audio(face, sr=sr_c); da = media.audio(desk, sr=sr_c)
    lag, conf = xcorr_lag(_envelope(fa, sr_c, hop), _envelope(da, sr_c, hop))
    L0 = lag * hop / sr_c                                   # desktop = face + L0
    if conf < 2.0:
        return {"status": "weak", "offset_s": L0, "confidence": round(conf, 2)}
    fdur = len(fa) / sr_c; ddur = len(da) / sr_c
    lo, hi = max(0.0, -L0), min(fdur, ddur - L0)            # overlap in face time
    pts = []
    for c in np.linspace(lo + win_s, hi - win_s, 3) if hi - lo > 3 * win_s else [(lo + hi) / 2]:
        f0 = max(lo, c - win_s / 2)
        a = media.audio(face, ss=f0, t=win_s, sr=16000)
        b = media.audio(desk, ss=f0 + L0 - 1.0, t=win_s + 2.0, sr=16000)      # +-1 s search
        lg, cf = xcorr_lag(a, b)
        pts.append({"face_t": round(f0, 2), "offset_s": round(L0 - 1.0 + lg / 16000, 4), "confidence": round(cf, 2)})
    offs = np.array([p["offset_s"] for p in pts]); ts = np.array([p["face_t"] for p in pts])
    drift_ppm = float(np.polyfit(ts, offs, 1)[0] * 1e6) if len(pts) >= 2 else 0.0
    good = all(p["confidence"] >= 2.0 for p in pts)
    return {"status": "ok" if good else "weak", "offset_s": round(float(np.median(offs)), 4),
            "uncertainty_s": round(float(max(0.005, np.ptp(offs) / 2)), 4), "drift_ppm": round(drift_ppm, 1),
            "points": pts, "coarse_confidence": round(conf, 2)}

def run(cfg, meta):
    rep = {"metadata": metadata_estimate(meta), "audio": None, "manual": cfg["sync"]["manual_offset_s"]}
    if meta["desktop_has_audio"]:
        rep["audio"] = audio_estimate(cfg["sources"]["face_camera"], cfg["sources"]["desktop_recording"])
    maxu = cfg["sync"]["max_uncertainty_s"]
    if rep["manual"] is not None:
        res = {"status": "ok", "offset_s": float(rep["manual"]), "method": "manual (user-confirmed)", "uncertainty_s": None}
    elif rep["audio"] and rep["audio"]["status"] == "ok" and rep["audio"]["uncertainty_s"] <= maxu:
        a = rep["audio"]; res = {"status": "ok", "offset_s": a["offset_s"], "method": "audio cross-correlation",
                                 "uncertainty_s": a["uncertainty_s"], "drift_ppm": a["drift_ppm"]}
        if abs(a["drift_ppm"]) > cfg["sync"]["max_drift_ppm"]:
            res["status"] = "needs_input"; res["reason"] = f"drift {a['drift_ppm']} ppm exceeds {cfg['sync']['max_drift_ppm']} ppm"
    else:
        m = rep["metadata"]
        res = {"status": "needs_input", "offset_s": m["offset_s"] if m else None, "method": "metadata only",
               "uncertainty_s": m["uncertainty_s"] if m else None,
               "reason": "no usable shared audio; metadata alone is not frame-accurate. Confirm with the anchors in the "
                         "report (slide changes / pen strokes vs the words) and set sync.manual_offset_s."}
    rep["result"] = res
    os.makedirs(cfg["paths"]["analysis"], exist_ok=True)
    with open(os.path.join(cfg["paths"]["analysis"], "sync.json"), "w", encoding="utf-8") as f:
        json.dump(rep, f, indent=2)
    _report(cfg, rep)
    return rep

def _report(cfg, rep):
    r = rep["result"]; lines = [f"# Synchronization report: {cfg['project']['lecture_topic']}", "",
        f"**Result:** {r['status']}. desktop = face + **{r['offset_s']} s** ({r['method']}"
        + (f", ±{r['uncertainty_s']} s" if r.get("uncertainty_s") else "") + ").", ""]
    if r.get("reason"): lines += [f"**Needs your input:** {r['reason']}", ""]
    m = rep["metadata"]; lines += ["## Metadata estimate", "", (f"{m['offset_s']} s ± {m['uncertainty_s']} s ({m['basis']})" if m else "unavailable"), ""]
    a = rep["audio"]
    lines += ["## Audio cross-correlation", ""]
    if not a: lines += ["Not possible: the desktop recording has no usable audio.", ""]
    else:
        lines += [f"Status {a['status']}; coarse confidence {a.get('coarse_confidence', a.get('confidence'))}; drift {a.get('drift_ppm', 'n/a')} ppm", "",
                  "| face time (s) | offset (s) | confidence |", "|---|---|---|"] + \
                 [f"| {p['face_t']} | {p['offset_s']} | {p['confidence']} |" for p in a.get("points", [])] + [""]
    lines += ["Pre-render check: `qa.frame_timing` compares rendered slide segments against the raw desktop frames "
              "(catches local deviations like Lesson 01's 1–3 frame lag)."]
    os.makedirs(cfg["paths"]["reports"], exist_ok=True)
    with open(os.path.join(cfg["paths"]["reports"], "synchronization_report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
