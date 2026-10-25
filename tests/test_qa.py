"""QA on fixtures (+ read-only Lesson 01 caption file): full-video checks, sync at pen strokes and slide changes (0 lag
expected, a wrong offset is caught), music level and placement, captions."""
import os
import numpy as np, pytest
from scipy.io import wavfile
from ytpipe import sources, sync, analyze, timeline, pipeline, state, qa, config
from tests.test_core import make_cfg

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def test_full_and_frame_timing(tmp_path):
    cfg = make_cfg(tmp_path, editing={"max_dead_air_s": 0.8})
    meta = sources.run(cfg); off = sync.run(cfg, meta)["result"]["offset_s"]; a = analyze.run(cfg, meta, steps=("desktop", "speech"))
    plan = timeline.propose(cfg, a, [], off, os.path.join(cfg["paths"]["timelines"], "timeline.json"))
    plan["segments"] = [dict(s, layout="B") for s in plan["segments"]]
    state.approve(cfg, "full_render"); r = pipeline.build(cfg, plan, a, meta, os.path.join(cfg["paths"]["full_video"], "f.mp4"))
    res = qa.full_video(cfg, r["file"], r["edl"])
    assert res["decode_errors"] == 0 and abs(res["duration"] - res["edl_duration"]) < 0.1
    sc = qa.sync_checks(cfg, r["file"], r["edl"], cfg["sources"]["desktop_recording"], off, a, r["geometry"])
    assert sc["pen_strokes"]["checked"] >= 1 and sc["slide_changes"]["checked"] >= 1 and sc["findings"] == [], sc
    bad = qa.sync_checks(cfg, r["file"], r["edl"], cfg["sources"]["desktop_recording"], off + 4 / 30, a, r["geometry"])
    assert bad["slide_changes"]["lags"] and all(abs(x["lag_frames"] + 4) <= 1 for x in bad["slide_changes"]["lags"]), bad
    none = qa.sync_checks(cfg, r["file"], r["edl"], cfg["sources"]["desktop_recording"], off, {"ink": [], "slide_changes": []}, r["geometry"])
    assert any("sync not verified" in f for f in none["findings"])

def test_music_level_and_placement(tmp_path):
    cfg = make_cfg(tmp_path); sr = 48000; n = 60 * sr; t = np.arange(n) / sr; x = np.zeros(n)
    tone = lambda a, b, db: np.where((t >= a) & (t < b), 10 ** (db / 20) * np.sqrt(2) * np.sin(2 * np.pi * 440 * t), 0)
    x += tone(0, 8, -46) + tone(30, 34, -46) + tone(40, 52, -46) + tone(55, 60, -36)   # intro, swell, too long, too loud outro
    p = str(tmp_path / "music_stem.wav"); wavfile.write(p, sr, np.stack([x, x], 1).astype(np.float32))
    m = qa.music(cfg, p, 60.0); k = [s["kind"] for s in m["sections"]]
    assert k == ["intro", "swell", "swell", "outro"], m
    assert 25 <= m["sections"][0]["below_voice_db"] <= 35, m
    assert len(m["findings"]) == 2 and "mid-video at 40.0" in m["findings"][0] and "outro" not in m["findings"][1] and "55.0" in m["findings"][1], m

@pytest.mark.skipif(not os.path.exists(os.path.join(ROOT, "lessons", "lesson01", "video_project_config.json")),
                    reason="Lesson 01 is not in this copy (Windows original only)")
def test_lesson01_captions_pass():
    cfg = config.load(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lessons", "lesson01", "video_project_config.json"))
    assert qa.captions(os.path.join(cfg["paths"]["transcripts"], "lesson01_hinglish.srt"), 774.07, cfg) == []

def test_joint_gap_allows_designed_room_tone(tmp_path):
    sr = 48000; rng = np.random.default_rng(0); x = 0.1 * rng.standard_normal(10 * sr)
    x[int(2.70 * sr):int(3.30 * sr)] = 0.0                      # 0.6 s: both sides' kept room tone at a cut (by design)
    x[int(6.50 * sr):int(7.50 * sr)] = 0.0                      # 1.0 s: a real hole at a cut
    p = str(tmp_path / "stem.wav"); wavfile.write(p, sr, x.astype(np.float32)); cfg = make_cfg(tmp_path)
    j = qa.joints(p, [3.0, 7.0], max_gap=2 * cfg["editing"]["room_tone_each_side_s"][1] + 0.1)
    assert [x["cut"] for x in j] == [7.0], j
