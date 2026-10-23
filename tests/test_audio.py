"""Audio on fixtures: narration laid on frames is sample-exact vs the source; joints have no gap/click; loudness target."""
import os, subprocess
import numpy as np
from scipy.io import wavfile
from ytpipe import audio
from tests.test_core import make_cfg, FX

def test_narration_alignment_and_loudness(tmp_path):
    cfg = make_cfg(tmp_path, audio={"music": {"enabled": False}})
    pieces = [(1.0, 60), (3.0, 45), (10.0, 90)]          # take 1.0-3.0 + 3.0-4.5 (contiguous) | cut | 10.0-13.0
    y, runs = audio.narration_raw(cfg["sources"]["face_camera"], pieces, 30)
    assert [(round(a, 3), round(d, 3), round(t, 3)) for a, d, t in runs] == [(1.0, 3.5, 0.0), (10.0, 3.0, 3.5)]
    src = audio.ff_float(["-i", cfg["sources"]["face_camera"], "-af", "pan=mono|c0=c0"], 1)[:, 0]
    k = int(5.0 * 48000); ref = src[int(11.5 * 48000):int(11.5 * 48000) + 4800]      # edit 5.0 s = face 11.5 s
    assert np.abs(y[k:k + 4800] - ref).max() < 1e-6
    res = audio.mix(cfg, pieces, [], [], str(tmp_path / "mix.wav"), str(tmp_path / "stem.wav"))
    assert abs(res["duration"] - 6.5) < 0.01
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(tmp_path / "mix.wav"), "-af", "ebur128", "-f", "null", "-"],
                       capture_output=True, text=True).stderr
    I = float(r.split("I:")[-1].split("LUFS")[0]); assert abs(I - (-16.0)) < 1.0, I   # mono -19 duplicated -> -16 stereo
