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

def test_music_plan_follows_style_and_maps_to_samples():
    from ytpipe import audio
    cfg = {"audio": {"delivery_lufs": -16.0, "music": {"placement": ["intro", "chapter_breaks"], "below_voice_db": [25, 35], "duck_db": 6}}}
    segs = [{"face_in": 1.0, "face_out": 50.0}, {"face_in": 52.0, "face_out": 90.0}]
    secs = audio.music_plan(cfg, segs, [(1.0, "Intro"), (60.0, "Next")], [[30.0, 31.0], [59.2, 60.4]])
    assert secs[0][:3] == (1.0, 9.0, 0.0)                               # under the opening shot, from the track start
    assert abs((secs[1][0] + secs[1][1]) / 2 - 59.8) < 1e-9             # swell centred on the pause at the chapter
    full = audio.to_edit(secs, [(1.0, 50.0, 0.0), (52.0, 90.0, 49.0)])
    part = audio.to_edit(secs, [(58.0, 62.0, 0.0)])                     # a sample piece around the chapter break
    f = next(x for x in full if x[0] > 40); p = part[0]
    assert abs((f[2] + (58.0 - (f[0] - 49.0 + 52.0))) - p[2]) < 1e-9   # same track position at the same face moment

def test_swells_after_the_track_length_still_have_music(tmp_path):
    """Lesson 03 (11:27) with a 6:15 track: chapter swells after 6:15 read past the track's end and were silent."""
    import numpy as np
    from scipy.io import wavfile
    from ytpipe import audio
    trk = str(tmp_path / "track.wav"); wavfile.write(trk, 48000, (0.1 * np.ones(48000 * 30)).astype(np.float32))   # 30 s track
    cfg = {"audio": {"delivery_lufs": -16.0, "music": {"file": trk, "placement": ["chapter_breaks", "outro"], "below_voice_db": [25, 35], "duck_db": 6}}}
    secs = audio.music_plan(cfg, [{"face_in": 0.0, "face_out": 120.0}], [(0.0, "A"), (50.0, "B"), (100.0, "C")], [])
    sw = [s for s in secs if s[1] - s[0] == 4.0]
    assert len(sw) == 2 and all(0 <= s[2] and s[2] + 4.0 <= 30.0 for s in sw), sw                  # inside the track
