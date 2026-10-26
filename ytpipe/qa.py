"""Quality checks (each returns a list of findings; [] = pass). Results are written to reports/qa_<name>.json so the
publishing checklist only shows checks that actually ran."""
import json, os, re, subprocess
import numpy as np
from . import media

def _save(cfg, name, data):
    os.makedirs(cfg["paths"]["reports"], exist_ok=True)
    json.dump(data, open(os.path.join(cfg["paths"]["reports"], f"qa_{name}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return data

def loudness(path, ss=None, t=None):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", *(["-ss", f"{ss:.3f}", "-t", f"{t:.3f}"] if t else []), "-i", path,
                        "-af", "ebur128=peak=true", "-f", "null", "-"], capture_output=True, text=True).stderr
    g = lambda k, u: float(r.split(k)[-1].split(u)[0])
    return {"I": g("I:", "LUFS"), "LRA": g("LRA:", "LU"), "TP": g("Peak:", "dBFS")}

def joints(stem_wav, cut_times, sr=48000, max_gap=0.5):
    """Narration stem (NOT the mix: music can mask gaps): low-audio runs > max_gap within +-2 s, clicks, level jumps.
    full_video passes max_gap = both sides' kept room tone + 0.1 s, so the pause the timeline keeps by design is no finding."""
    x = media.audio(stem_wav, sr=sr); hop, win = int(0.01 * sr), int(0.05 * sr)
    c = np.concatenate([[0], np.cumsum(x.astype(np.float64) ** 2)]); idx = np.arange(0, len(x) - win, hop)
    env = 10 * np.log10((c[idx + win] - c[idx]) / win + 1e-12); tt = (idx + win / 2) / sr; speech = np.percentile(env, 75)
    low = env < speech - 30; runs, s = [], None
    for i, v in enumerate(low):
        if v and s is None: s = tt[i]
        if (not v or i == len(low) - 1) and s is not None: runs.append((s, tt[i])); s = None
    out = []
    for T in cut_times:
        near = [(round(float(a), 2), round(float(b), 2)) for a, b in runs if b - a > max_gap and a < T + 2 and b > T - 2]
        i = int(T * sr); lb, la = media.rms_db(x[i - 480:i]), media.rms_db(x[i:i + 480])
        loc = np.sqrt(np.mean(x[i - 960:i + 960] ** 2)) + 1e-9; step = abs(float(x[i]) - float(x[i - 1])) / loc
        f = (["low gap " + str(near)] if near else []) + (["abrupt level change"] if abs(la - lb) > 20 else []) + (["click risk"] if step > 4 else [])
        if f: out.append({"cut": round(T, 2), "findings": f})
    return out

def frame_timing(video, edl, desktop, offset, ink_events_desktop, g, tol_frames=1, max_checks=40, fps=30):
    """At pen-moving moments, which raw desktop frame does the rendered slide card show? Compares the card (mapped back to
    slide px) with raw frames planned-6..+6 on pixels whose ink state changes. Flags |lag| > tol_frames.
    Known limit: strokes drawn over earlier ink (circling, overwriting) give ambiguous matches and can show false lags
    in both directions; a real offset shows as the SAME lag on most strokes. Render timing itself is guaranteed by
    render.segment (exact frame count, frame k at k/fps) and tested in tests/test_render.py.
    -> {"checked": moments actually compared, "lags": [...]} (checked 0 = nothing verified, not a pass)."""
    sx, sy, sw, sh = g["slide_area"]; cx, cy, cw, ch = g["card"]; out = []; n = 0
    moments = [e["start"] + 0.5 * (e["end"] - e["start"]) for e in ink_events_desktop]
    for D in moments:
        F = D - offset; seg = next((s for s in edl if s["layout"] == "B" and s["face_in"] + 0.3 <= F <= s["face_out"] - 0.3), None)
        if not seg or n >= max_checks: continue
        t = seg["edit_start"] + F - seg["face_in"]
        fin = media.frames(video, t, 1.1 / fps, 480, 270, fps, vf_pre=f"crop={cw}:{ch}:{cx}:{cy}", pix="rgb24")[0].astype(np.int16)
        seq = media.frames(desktop, D - 6 / fps, 13 / fps, 480, 270, fps, vf_pre=f"crop={sw}:{sh}:{sx}:{sy}", pix="rgb24").astype(np.int16)
        red = (seq[..., 0] > 150) & (seq[..., 1] < 90) & (seq[..., 2] < 100); roi = red.any(0) & ~red.all(0)
        if roi.sum() < 15 or len(seq) < 13: continue
        n += 1; err = np.array([np.abs(fin[roi] - s[roi]).mean() for s in seq])     # a finished dot or duplicated source frames
        lag = int(np.argmax(err <= err.min() + max(0.5, 0.05 * np.ptp(err)))) - 6   # give a flat minimum: take its first frame
        if abs(lag) > tol_frames: out.append({"edit_time": round(float(t), 2), "face_time": round(F, 2), "lag_frames": lag})
    return {"checked": n, "lags": out}

def _step(seq):
    """Index k of the one clear picture change in a frame sequence (frame k differs from frame k-1), None if unclear."""
    d = np.array([np.abs(seq[k] - seq[k - 1]).mean() for k in range(1, len(seq))])
    if len(d) < 5: return None
    k = int(np.argmax(d)); rest = np.delete(d, [j for j in (k - 1, k, k + 1) if 0 <= j < len(d)])
    return k + 1 if d[k] >= 2.0 and d[k] >= 4 * max(float(np.median(rest)), 0.25) and rest.max() <= 0.5 * d[k] else None

def slide_timing(video, edl, desktop, offset, changes_desktop, g, tol_frames=1, fps=30, win=0.8):
    """Slide changes as sync anchors (for lessons without pen writing): the frame where the rendered card changes vs
    the frame where the raw desktop changes, both searched in the same +-win window around the planned instant.
    lag_frames as in frame_timing: shown desktop frame minus planned (negative = the slide card is behind).
    -> {"checked", "lags"}; a change that is not one clear step in both (two changes close together) is not counted."""
    out = []; n = 0
    for D in changes_desktop:
        F = D - offset; seg = next((s for s in edl if s["layout"] == "B" and s["face_in"] + win + 0.1 <= F <= s["face_out"] - win - 0.1), None)
        if not seg: continue
        t = seg["edit_start"] + F - seg["face_in"]
        grab = lambda path, t0, box: media.frames(path, t0, 2 * win, 480, 270, fps, vf_pre="crop={2}:{3}:{0}:{1}".format(*box)).astype(np.int16)
        kr, kd = _step(grab(video, t - win, g["card"])), _step(grab(desktop, D - win, g["slide_area"]))
        if kr is None or kd is None: continue
        n += 1
        if abs(kd - kr) > tol_frames: out.append({"edit_time": round(float(t), 2), "face_time": round(F, 2), "lag_frames": kd - kr})
    return {"checked": n, "lags": out}

def sync_checks(cfg, video, edl, desktop, offset, analysis, g):
    """Rendered slide shots vs the raw desktop at pen strokes and slide changes. Says so when nothing could be compared."""
    fps, tol = cfg["output"]["fps"], cfg["sync"]["frame_check_tolerance_frames"]
    pen = frame_timing(video, edl, desktop, offset, analysis.get("ink", []), g, tol, fps=fps)
    sl = slide_timing(video, edl, desktop, offset, analysis.get("slide_changes", []), g, tol, fps)
    f = [f"pen stroke lag {x}" for x in pen["lags"]] + [f"slide change lag {x}" for x in sl["lags"]]
    if pen["checked"] + sl["checked"] == 0:
        f.append("sync not verified: no pen stroke or slide change inside a slide shot to compare; confirm the offset by eye")
    return {"pen_strokes": pen, "slide_changes": sl, "findings": f}

def music(cfg, music_wav, duration, planned=None):
    """Music stem (written by audio.mix): each section's loudness under the -16 LUFS delivery voice (style section 14:
    25-35 dB under, plus up to duck_db of ducking), and placement: only the intro, the outro and short chapter swells."""
    M = cfg["audio"]["music"]; lo, hi = M["below_voice_db"]; x = media.audio(music_wav, sr=8000)
    blk = np.abs(x[:len(x) // 80 * 80]).reshape(-1, 80).max(1) > 1e-5; runs, s = [], None   # 10 ms blocks
    for i, v in enumerate(np.append(blk, False)):
        if v and s is None: s = i
        if not v and s is not None:
            if runs and s / 100 - runs[-1][1] < 1.0: runs[-1][1] = i / 100
            else: runs.append([s / 100, i / 100])
            s = None
    out, f = [], []
    for a, b in (r for r in runs if r[1] - r[0] >= 0.5):
        L = loudness(music_wav, a, b - a)["I"]; gap = round(cfg["audio"]["delivery_lufs"] - L, 1)
        kind = "intro" if a < 1.0 else "outro" if b > duration - 3.0 else "swell"      # a track's own ending can fade early
        out.append({"start": round(a, 2), "end": round(b, 2), "kind": kind, "lufs": L, "below_voice_db": gap})
        if gap < lo - 1: f.append(f"music {a:.1f}-{b:.1f} s only {gap} dB under the voice (style: {lo}-{hi})")
        if gap > hi + M["duck_db"] + 1: f.append(f"music {a:.1f}-{b:.1f} s is {gap} dB under the voice: barely audible")
        if kind == "swell" and b - a > 6.0: f.append(f"music runs {b - a:.1f} s mid-video at {a:.1f} s (style: only short swells at chapter breaks)")
    for a, b in planned or []:                        # every planned section must be heard (a track can end too soon)
        if not any(s["start"] < b and s["end"] > a for s in out): f.append(f"planned music {a:.1f}-{b:.1f} s is silent")
    return {"sections": out, "findings": f}

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

def full_video(cfg, final, edl, stem=None, cut_times=(), sync=None, music_wav=None):
    res = {"decode_errors": len(media.decode_errors(final))}
    d = float(media.probe(final)["format"]["duration"]); res["duration"] = d; res["edl_duration"] = sum(s["frames"] for s in edl) / cfg["output"]["fps"]
    res["loudness"] = loudness(final); f = []
    if res["decode_errors"]: f.append("decode errors")
    if abs(d - res["edl_duration"]) > 0.1: f.append("duration differs from the EDL")
    if abs(res["loudness"]["I"] - cfg["audio"]["delivery_lufs"]) > 1.0: f.append(f"loudness {res['loudness']['I']} LUFS")
    if res["loudness"]["TP"] > cfg["audio"]["true_peak_dbtp"]: f.append(f"true peak {res['loudness']['TP']} dBTP")
    if stem: res["joints"] = joints(stem, cut_times, max_gap=2 * cfg["editing"]["room_tone_each_side_s"][1] + 0.1); f += [f"joint {j['cut']}: {j['findings']}" for j in res["joints"]]
    if sync: res["sync"] = sync; f += sync["findings"]
    if music_wav and os.path.exists(music_wav):
        mp = os.path.join(os.path.dirname(music_wav), "music_plan.json")
        res["music"] = music(cfg, music_wav, d, json.load(open(mp)) if os.path.exists(mp) else None); f += res["music"]["findings"]
    elif cfg["audio"]["music"]["enabled"]: res["music"] = "not checked: no music_stem.wav (render made before this check)"
    res["findings"] = f
    return _save(cfg, "full_video", res)

def run_full(cfg, final, edl, offset, analysis, g, wd):
    """Every full-video check, with the stems of the render in wd (<full_video>/work): decode, duration, loudness,
    narration joints, sync at pen strokes and slide changes, music level and placement -> reports/qa_full_video.json."""
    cuts = [e["edit_start"] for x, e in zip(edl, edl[1:]) if abs(x["face_out"] - e["face_in"]) > 1e-6]
    stem = os.path.join(wd, "narration_stem.wav")
    sync = sync_checks(cfg, final, edl, cfg["sources"]["desktop_recording"], offset, analysis, g)
    r = full_video(cfg, final, edl, stem if os.path.exists(stem) else None, cuts, sync, os.path.join(wd, "music_stem.wav"))
    from .timeline import widen_blanks
    r["findings"] += blank_shown(edl, widen_blanks(analysis.get("blank_spans", []), analysis.get("slide_changes", [])), offset)
    return r

def blank_shown(edl, blanks, offset):
    """Slide shots that show a blank desktop ('End of slide show', a black slide) or the slides flashed around it
    (spans from timeline.widen_blanks): final-video times."""
    f = []
    for b0, b1 in blanks:
        for x in edl:
            a, b = max(x["face_in"], b0 - offset), min(x["face_out"], b1 - offset)
            if x["layout"] != "A" and b > a:
                t = x["edit_start"] + a - x["face_in"]
                f.append(f"blank desktop ('End of slide show' or slides flashed around it) shown at {int(t // 60)}:{t % 60:04.1f} for {b - a:.1f} s")
    return f
