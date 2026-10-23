"""Energetic music mix for a Short (narration first).

narration : rebuilt from the face camera over the Short's own face spans (the lecture's cuts applied) with the approved
            voice chain, so it is lip-synced to the Short's picture by construction.
music     : a licensed track, high-passed (no bass masking the voice), level set relative to the voice:
            speech -> voice - speech_db, pauses -> + gap_boost_db, smooth gain (attack/release), raised-cosine fades.
            The track start is chosen so its beats fall as close as possible to the Short's cuts (picture never moves).
master    : gain to target LUFS, limiter, verified true peak."""
import json, os, re, subprocess
import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, sosfiltfilt
from . import audio, media

SR = audio.SR

def spans(F0, F1, segments, fps=30):
    """Face spans of [F0, F1] that survive the lecture's cuts (same rule as shorts_v3.render)."""
    s = [(max(F0, g["face_in"]), min(F1, g["face_in"] + g["frames"] / fps)) for g in segments]
    return [(a, b) for a, b in s if b - a > 0.5 / fps]

def lufs(path_or_args):
    args = path_or_args if isinstance(path_or_args, list) else ["-i", path_or_args]
    e = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", *args, "-af", "ebur128=peak=true", "-f", "null", "-"], capture_output=True, text=True).stderr
    tail = e[e.rindex("Summary:"):]
    return {"I": float(re.search(r"I:\s+(-?[\d.]+)", tail).group(1)), "LRA": float(re.search(r"LRA:\s+([\d.]+)", tail).group(1)),
            "TP": float(re.search(r"Peak:\s+(-?[\d.inf]+)", tail).group(1))}

def speech_activity(narr, rel=0.6, att=0.08, min_gap=0.35):
    """0..1 speech envelope (20 ms RMS gate), pauses shorter than min_gap count as speech (no pumping between words)."""
    w = int(0.02 * SR); c = np.concatenate([[0], np.cumsum(narr ** 2)]); hop = int(0.01 * SR)
    rms = np.sqrt(np.maximum(c[w::hop][:len(narr) // hop] - c[:-w:hop][:len(narr) // hop], 0) / w)
    lv = 20 * np.log10(rms + 1e-9); thr = max(-50.0, np.percentile(lv, 10) + 12)   # 12 dB above the room tone
    on = (lv > thr).astype(float); n = int(min_gap / 0.01); k = 0
    while k < len(on):                                       # fill short gaps
        if on[k] == 0:
            j = k
            while j < len(on) and on[j] == 0: j += 1
            if j - k < n and k > 0 and j < len(on): on[k:j] = 1
            k = j
        else: k += 1
    g = np.zeros_like(on); y = on[0]; ka, kr = np.exp(-0.01 / att), np.exp(-0.01 / rel)
    for i, v in enumerate(on):
        kk = ka if v > y else kr; y = kk * y + (1 - kk) * v; g[i] = y
    return np.interp(np.arange(len(narr)), np.arange(len(g)) * hop, g), on

def beat_offset(track, bpm, cuts, search=(0.0, 60.0)):
    """Track start (s) whose beat grid lands closest to the cut times. The track's own beat phase is measured from its
    onset envelope; candidate starts are the track's beats inside `search`."""
    x = track.mean(1); hop = 512; fr = np.lib.stride_tricks.sliding_window_view(x[:len(x) // hop * hop], 1024)[::hop]
    e = np.log1p(100 * np.sqrt((fr ** 2).mean(1))); o = np.maximum(np.diff(e), 0); T = 60 / bpm
    ph = np.linspace(0, T, 48, endpoint=False); tt = np.arange(len(o)) * hop / SR
    score = [o[np.minimum((np.arange(p, tt[-1], T) * SR / hop).astype(int), len(o) - 1)].mean() for p in ph]
    phase = ph[int(np.argmax(score))]
    # Short time t plays track time s0 + t, so its beats sit at d + kT with d = (phase - s0) mod T: pick d for the cuts
    err = lambda c, d: abs(((c - d) % T + T / 2) % T - T / 2)
    sub = np.linspace(0, T, 97); d = sub[int(np.argmin([sum(err(c, x) for c in cuts) for x in sub]))]
    s0 = phase - d
    while s0 < search[0]: s0 += T
    return float(s0), float(phase), [round(err(c, d), 3) for c in cuts]

def mix(cfg, face_spans, music_file, bpm, cuts, out_wav, speech_db=20.0, gap_boost_db=5.0, hp_hz=110, fade_in=0.4, fade_out=1.5,
        target_lufs=-14.0, tp_max=-1.5, stem_dir=None):
    pieces = [(a, int(round((b - a) * cfg["output"]["fps"]))) for a, b in face_spans]
    y, _ = audio.narration_raw(cfg["sources"]["face_camera"], pieces, cfg["output"]["fps"])
    tmp = out_wav.replace(".wav", "_narr_tmp.wav"); narr = audio.voice_chain(cfg, y, tmp); os.remove(tmp); n = len(narr)
    trk = audio.ff_float(["-i", music_file], 2); trk = sosfiltfilt(butter(4, hp_hz, "hp", fs=SR, output="sos"), trk, axis=0)
    s0, phase, cut_err = beat_offset(trk, bpm, cuts); seg = trk[int(s0 * SR):int(s0 * SR) + n]
    if len(seg) < n: raise ValueError("music track too short for this Short")
    # levels: music short-term loudness relative to the narration's
    nl = lufs_arr(narr[:, None].repeat(2, 1), out_wav); ml = lufs_arr(seg, out_wav)
    act, on = speech_activity(narr)
    lvl_db = (nl - speech_db - ml) + gap_boost_db * (1 - act)
    t = np.arange(n) / SR; env = np.ones(n)
    a = t < fade_in; env[a] = 0.5 - 0.5 * np.cos(np.pi * t[a] / fade_in)
    b = t > t[-1] - fade_out; env[b] = 0.5 + 0.5 * np.cos(np.pi * (t[b] - (t[-1] - fade_out)) / fade_out)
    music = seg * (10 ** (lvl_db / 20) * env)[:, None]
    mixd = narr[:, None] + music
    if stem_dir:
        wavfile.write(os.path.join(stem_dir, "narration_stem.wav"), SR, narr.astype(np.float32))
        wavfile.write(os.path.join(stem_dir, "music_stem.wav"), SR, music.astype(np.float32))
    pre = out_wav.replace(".wav", "_pre.wav"); wavfile.write(pre, SR, mixd.astype(np.float32))
    I = lufs(pre)["I"]; g = target_lufs - I
    lim = 10 ** ((tp_max - 0.7) / 20)                       # sample-peak ceiling with margin for inter-sample peaks
    media.run(["ffmpeg", "-v", "error", "-y", "-i", pre, "-af", f"volume={g:.2f}dB,alimiter=limit={lim:.4f}:attack=2:release=60:level=disabled:latency=1",
               "-ar", str(SR), "-c:a", "pcm_f32le", out_wav]); os.remove(pre)
    m = lufs(out_wav)
    return {"music_start_s": round(s0, 3), "beat_phase_s": round(phase, 3), "beat_s": round(60 / bpm, 4), "cut_beat_error_s": cut_err,
            "music_vs_voice_speech_db": -speech_db, "gap_boost_db": gap_boost_db, "highpass_hz": hp_hz, "final": m,
            "narration_lufs": round(nl, 2), "music_track_lufs_segment": round(ml, 2)}

def lufs_arr(x, near):
    p = near.replace(".wav", "_meas_tmp.wav"); wavfile.write(p, SR, x.astype(np.float32)); v = lufs(p)["I"]; os.remove(p); return v
