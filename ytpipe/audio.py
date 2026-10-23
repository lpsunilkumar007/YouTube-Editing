"""Audio (generic port of mix_audio_v8.py + render_full_v9.build_audio, the approved Lesson 01 mix).

narration: face audio (channel 0) laid on the ACTUAL video frames of each segment; contiguous segments of one take are
           one continuous run; 20 ms equal-power crossfades of real room tone at joints (never a fade to silence).
voice    : approved chain + two-pass loudnorm to audio.narration_lufs_mono (-19 mono = -16 LUFS on the stereo file).
music    : sections [(t0, t1, track_t0|None, level_keys)] in edit time; levels relative to a -16 LUFS mono voice, moved
           by the same -3 dB; ducking up to audio.music.duck_db under speech; None track_t0 = use the track's ending.
sfx      : [(file, edit_time, peak_dbfs)]."""
import json, subprocess
import numpy as np
from scipy.io import wavfile
from . import media

SR, XF, BED_OFFSET_DB = 48000, 0.020, -3.0

def ff_float(args, ch):
    r = media.run(["ffmpeg", "-v", "error", *args, "-ac", str(ch), "-ar", str(SR), "-f", "f32le", "-"])
    return np.frombuffer(r.stdout, np.float32).reshape(-1, ch).astype(np.float64)

def runs_from(pieces, fps):
    """pieces [(face_in, frames)] -> runs [(face_start, duration, edit_start)]; a piece continuing the previous take merges."""
    runs, t = [], 0.0
    for a, n in pieces:
        d = n / fps
        if runs and abs(runs[-1][0] + runs[-1][1] - a) < 0.5 / fps: runs[-1] = (runs[-1][0], runs[-1][1] + d, runs[-1][2])
        else: runs.append((a, d, t))
        t += d
    return runs, t

def narration_raw(face_path, pieces, fps):
    x = ff_float(["-i", face_path, "-af", "pan=mono|c0=c0"], 1)[:, 0]; runs, total = runs_from(pieces, fps)
    y = np.zeros(int(round(total * SR)) + 1); h = XF / 2; nx = int(round(XF * SR))
    for k, (a, d, t) in enumerate(runs):
        pre = h if k > 0 else 0.0; post = h if k < len(runs) - 1 else 0.0
        s = x[int(round((a - pre) * SR)):int(round((a + d + post) * SR))].copy(); w = np.ones(len(s))
        if pre: w[:nx] = np.sin(np.linspace(0, 1, nx) * np.pi / 2)
        if post: w[-nx:] = np.sin(np.linspace(1, 0, nx) * np.pi / 2)
        i0 = int(round((t - pre) * SR)); seg = (s * w)[:len(y) - i0]; y[i0:i0 + len(seg)] += seg
    return y, runs

def voice_chain(cfg, y, tmp_wav):
    wavfile.write(tmp_wav, SR, y.astype(np.float32)); A = cfg["audio"]; I = A["narration_lufs_mono"]
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", tmp_wav, "-af", A["chain"] + f",loudnorm=I={I}:TP=-2.0:LRA=9:print_format=json",
                        "-f", "null", "-"], capture_output=True, text=True)
    j = json.loads(r.stderr[r.stderr.rindex("{"):r.stderr.rindex("}") + 1])
    ln = (f"loudnorm=I={I}:TP=-2.0:LRA=9:measured_I={j['input_i']}:measured_TP={j['input_tp']}:measured_LRA={j['input_lra']}:"
          f"measured_thresh={j['input_thresh']}:offset={j['target_offset']}:linear=true")
    return ff_float(["-i", tmp_wav, "-af", A["chain"] + "," + ln + f",aresample={SR}"], 1)[:len(y), 0]

def level_curve(n, keys, music_lufs):
    t = np.arange(n) / SR; amp = np.zeros(n); to = lambda L: 0.0 if L is None else 10 ** ((L - music_lufs) / 20)
    for (t0, L0), (t1, L1) in zip(keys, keys[1:]):
        m = (t >= t0) & (t < t1)
        if not m.any() or t1 <= t0: continue
        s = 0.5 - 0.5 * np.cos(np.pi * (t[m] - t0) / (t1 - t0))
        amp[m] = 10 ** (((1 - s) * L0 + s * L1 - music_lufs) / 20) if (L0 is not None and L1 is not None) else (1 - s) * to(L0) + s * to(L1)
    return amp

def duck(narr, db=6.0, att=0.08, rel=0.6):
    w = int(0.02 * SR); c = np.concatenate([[0], np.cumsum(narr ** 2)])
    rms = np.sqrt(np.maximum(c[w:] - c[:-w], 0) / w); rms = np.concatenate([rms, np.full(w, rms[-1] if len(rms) else 0)])[:len(narr)]
    act = np.clip((20 * np.log10(rms + 1e-9) + 50) / 10, 0, 1); hop = 480; a = act[::hop]; g = np.zeros_like(a); yv = 0.0
    ka, kr = np.exp(-0.01 / att), np.exp(-0.01 / rel)
    for k, v in enumerate(a):
        kk = ka if v > yv else kr; yv = kk * yv + (1 - kk) * v; g[k] = yv
    return 10 ** (-db * np.interp(np.arange(len(narr)), np.arange(len(a)) * hop, g) / 20)

def music_lufs(path):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-af", "ebur128", "-f", "null", "-"], capture_output=True, text=True).stderr
    return float(r.split("I:")[-1].split("LUFS")[0])

def mix(cfg, pieces, sections, sfx, out_wav, stem_wav):
    fps = cfg["output"]["fps"]; y, runs = narration_raw(cfg["sources"]["face_camera"], pieces, fps)
    wavfile.write(stem_wav, SR, y.astype(np.float32))                       # narration stem for joint QC
    narr = voice_chain(cfg, y, stem_wav.replace(".wav", "_tmp.wav")); n = len(narr); total = n / SR
    M = cfg["audio"]["music"]; music = np.zeros((n, 2))
    if M["enabled"] and sections:
        trk = ff_float(["-i", M["file"]], 2); mL = music_lufs(M["file"]); dk = duck(narr, M["duck_db"])
        for t0, t1, tr0, keys in sections:
            tr0 = len(trk) / SR - (t1 - t0) - 0.5 if tr0 is None else tr0
            i0, i1 = int(max(0, t0) * SR), min(n, int(t1 * SR)); seg = trk[int(tr0 * SR):int(tr0 * SR) + (i1 - i0)]
            k2 = [(0.0, None)] + [(t, None if L is None else L + BED_OFFSET_DB) for t, L in keys] + [(total + 1, None)]
            lv = level_curve(n, k2, mL)[i0:i0 + len(seg)]; music[i0:i0 + len(seg)] += seg * (lv * dk[i0:i0 + len(seg)])[:, None]
    fx = np.zeros((n, 2))
    if cfg["audio"]["sfx"]["enabled"]:
        for f, t, pk in sfx:
            sr, x = wavfile.read(f); x = x.astype(np.float64) / np.abs(x).max() * 10 ** ((pk + BED_OFFSET_DB) / 20)
            if x.ndim == 1: x = np.stack([x, x], 1)
            i0 = int(round(t * SR)); fx[i0:i0 + len(x)] += x[:n - i0]
    out = narr[:, None] + music + fx; k = int(0.03 * SR); out[-k:] *= np.linspace(1, 0, k)[:, None]
    wavfile.write(out_wav, SR, out.astype(np.float32))
    return {"runs": runs, "duration": total}

def mux(video, wav, out, cfg):
    media.run(["ffmpeg", "-v", "error", "-y", "-i", video, "-i", wav, "-map", "0:v", "-map", "1:a", "-c:v", "copy",
               "-af", "alimiter=limit=0.84:attack=3:release=60:level=0:latency=1,aresample=48000", *cfg["output"]["audio_codec"],
               "-movflags", "+faststart", out])
    return out
