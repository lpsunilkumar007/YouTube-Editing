"""QA on fixtures (+ read-only Lesson 01 caption file): full-video checks, frame timing (0 lag expected), captions."""
import os
from ytpipe import sources, sync, analyze, timeline, pipeline, state, qa, config
from tests.test_core import make_cfg

def test_full_and_frame_timing(tmp_path):
    cfg = make_cfg(tmp_path, editing={"max_dead_air_s": 0.8})
    meta = sources.run(cfg); off = sync.run(cfg, meta)["result"]["offset_s"]; a = analyze.run(cfg, meta, steps=("desktop", "speech"))
    plan = timeline.propose(cfg, a, [], off, os.path.join(cfg["paths"]["timelines"], "timeline.json"))
    plan["segments"] = [dict(s, layout="B") for s in plan["segments"]]
    state.approve(cfg, "full_render"); r = pipeline.build(cfg, plan, a, meta, os.path.join(cfg["paths"]["full_video"], "f.mp4"))
    res = qa.full_video(cfg, r["file"], r["edl"])
    assert res["decode_errors"] == 0 and abs(res["duration"] - res["edl_duration"]) < 0.1
    lags = qa.frame_timing(r["file"], r["edl"], cfg["sources"]["desktop_recording"], off, a["ink"], r["geometry"])
    assert lags == [], lags

def test_lesson01_captions_pass():
    cfg = config.load(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lessons", "lesson01", "video_project_config.json"))
    assert qa.captions(os.path.join(cfg["paths"]["transcripts"], "lesson01_hinglish.srt"), 774.07, cfg) == []
