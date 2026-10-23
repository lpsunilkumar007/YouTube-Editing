"""Quality checks (each returns a list of findings; [] = pass). Results are written to reports/qa_<name>.json so the
publishing checklist only shows checks that actually ran."""
import json, os, re, subprocess
import numpy as np
from . import media

def _save(cfg, name, data):
    os.makedirs(cfg["paths"]["reports"], exist_ok=True)
    json.dump(data, open(os.path.join(cfg["paths"]["reports"], f"qa_{name}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return data

def loudness(path):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-af", "ebur128=peak=true", "-f", "null", "-"],
                       capture_output=True, text=True).stderr
    g = lambda k, u: float(r.split(k)[-1].split(u)[0])
    return {"I": g("I:", "LUFS"), "LRA": g("LRA:", "LU"), "TP": g("Peak:", "dBFS")}

def joints(stem_wav, cut_times, sr=48000):
    """Narration stem (NOT the mix: music can mask gaps): low-audio runs > 0.5 s within +-2 s, clicks, level jumps."""
    x = media.audio(stem_wav, sr=sr); hop, win = int(0.01 * sr), int(0.05 * sr)
    c = np.concatenate([[0], np.cumsum(x.astype(np.float64) ** 2)]); idx = np.arange(0, len(x) - win, hop)
    env = 10 * np.log10((c[idx + win] - c[idx]) / win + 1e-12); tt = (idx + win / 2) / sr; speech = np.percentile(env, 75)
    low = env < speech - 30; runs, s = [], None
    for i, v in enumerate(low):
        if v and s is None: s = tt[i]
        if (not v or i == len(low) - 1) and s is not None: runs.append((s, tt[i])); s = None
    out = []
    for T in cut_times:
        near = [(round(a, 2), round(b, 2)) for a, b in runs if b - a > 0.5 and a < T + 2 and b > T - 2]
        i = int(T * sr); lb, la = media.rms_db(x[i - 480:i]), media.rms_db(x[i:i + 480])
        loc = np.sqrt(np.mean(x[i - 960:i + 960] ** 2)) + 1e-9; step = abs(float(x[i]) - float(x[i - 1])) / loc
        f = (["low gap " + str(near)] if near else []) + (["abrupt level change"] if abs(la - lb) > 20 else []) + (["click risk"] if step > 4 else [])
        if f: out.append({"cut": round(T, 2), "findings": f})
    return out

def frame_timing(video, edl, desktop, offset, ink_events_desktop, g, tol_frames=1, max_checks=40):
    """At pen-moving moments, which raw desktop frame does the rendered slide card show? Compares the card (mapped back to
    slide px) with raw frames planned-6..+6 on pixels whose ink state changes. Flags |lag| > tol_frames. Run on the
    joined video BEFORE the final mux (pre-render check) and on the final."""
    sx, sy, sw, sh = g["slide_area"]; cx, cy, cw, ch = g["card"]; out = []; n = 0
    moments = [e["start"] + 0.5 * (e["end"] - e["start"]) for e in ink_events_desktop]
    for D in moments:
        F = D - offset; seg = next((s for s in edl if s["layout"] == "B" and s["face_in"] + 0.3 <= F <= s["face_out"] - 0.3), None)
        if not seg or n >= max_checks: continue
        n += 1; t = seg["edit_start"] + F - seg["face_in"]
        fin = media.frames(video, t, 0.034, 480, 270, 30, vf_pre=f"crop={cw}:{ch}:{cx}:{cy}", pix="rgb24")[0].astype(np.int16)
        seq = media.frames(desktop, D - 6 / 30, 13 / 30, 480, 270, 30, vf_pre=f"crop={sw}:{sh}:{sx}:{sy}", pix="rgb24").astype(np.int16)
        red = (seq[..., 0] > 150) & (seq[..., 1] < 90) & (seq[..., 2] < 100); roi = red.any(0) & ~red.all(0)
        if roi.sum() < 15 or len(seq) < 13: continue
        err = [np.abs(fin[roi] - s[roi]).mean() for s in seq]; lag = int(np.argmin(err)) - 6
        if abs(lag) > tol_frames: out.append({"edit_time": round(t, 2), "face_time": round(F, 2), "lag_frames": lag})
    return out

def captions(srt_path, duration, cfg):
    blocks = open(srt_path, encoding="utf-8").read().strip().split("\n\n"); prev = 0.0; out = []
    ts = lambda x: sum(float(v) * m for v, m in zip(x.replace(",", ".").split(":"), (3600, 60, 1)))
    for b in blocks:
        l = b.split("\n"); a, e = [ts(x) for x in l[1].split(" --> ")]; txt = l[2:]
        if a < prev - 1e-3: out.append(f"cue {l[0]} overlaps the previous cue")
        if e - a < 0.5 or e - a > cfg["captions"]["max_duration_s"] + 0.01: out.append(f"cue {l[0]} duration {e - a:.2f} s")
        if len(txt) > cfg["captions"]["max_lines"] or any(len(t) > cfg["captions"]["max_chars_per_line"] for t in txt): out.append(f"cue {l[0]} too long")
        if e > duration + 0.05: out.append(f"cue {l[0]} after the end of the video")
        prev = e
    return out

def short(path, cfg, clip=None, env=None, parts=None):
    p = media.probe(path); v = next(s for s in p["streams"] if s["codec_type"] == "video"); d = float(p["format"]["duration"]); out = []
    if (v["width"], v["height"]) != tuple(cfg["shorts"]["size"]): out.append(f"size {v['width']}x{v['height']}")
    if not (cfg["shorts"]["duration_s"][0] - 0.5 <= d <= cfg["shorts"]["allow_up_to_s"]): out.append(f"duration {d:.1f} s")
    if media.decode_errors(path): out.append("decode errors")
    import cv2
    cas = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml"); seen = 0
    ts = np.linspace(0.5, d - 0.5, 6)
    if parts:                                            # v3: the presenter is hidden in desktop-focus (C) parts by design
        ts = [t for t in ts if any(a - parts[0][0] <= t < b - parts[0][0] and l != "C" for a, b, l in parts)]
    for t in ts:
        g = media.frames(path, t, 0.04, 540, 960, 25)[0]; seen += len(cas.detectMultiScale(g, 1.1, 5, minSize=(40, 40))) > 0
    if seen < -(-2 * len(ts) // 3): out.append(f"face detected in only {seen}/{len(ts)} sampled presenter frames")
    if clip and env is not None:                         # starts/ends in a pause (no cut-off sentence)
        for k in ("face_start", "face_end"):
            if k in clip and env[int(clip[k] * 100)] > cfg["editing"]["speech_threshold_dbfs"]: out.append(f"{k} {clip[k]} is inside speech")
    return out

def full_video(cfg, final, edl, stem=None, cut_times=()):
    res = {"decode_errors": len(media.decode_errors(final))}
    d = float(media.probe(final)["format"]["duration"]); res["duration"] = d; res["edl_duration"] = sum(s["frames"] for s in edl) / cfg["output"]["fps"]
    res["loudness"] = loudness(final); f = []
    if res["decode_errors"]: f.append("decode errors")
    if abs(d - res["edl_duration"]) > 0.1: f.append("duration differs from the EDL")
    if abs(res["loudness"]["I"] - cfg["audio"]["delivery_lufs"]) > 1.0: f.append(f"loudness {res['loudness']['I']} LUFS")
    if res["loudness"]["TP"] > cfg["audio"]["true_peak_dbtp"]: f.append(f"true peak {res['loudness']['TP']} dBTP")
    if stem: res["joints"] = joints(stem, cut_times); f += [f"joint {j['cut']}: {j['findings']}" for j in res["joints"]]
    res["findings"] = f
    return _save(cfg, "full_video", res)
