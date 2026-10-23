"""End-to-end on fixtures: inspect -> sync -> analyze -> timeline proposal -> (approve) -> render -> mux, plus gates."""
import json, os
import pytest
from ytpipe import sources, sync, analyze, timeline, pipeline, state, media, render
from tests.test_core import make_cfg, TRUTH

def test_keeps_cut_dead_air_only():
    k = timeline.keeps([(5.0, 8.0), (10.0, 10.8)], 1.0, 20.0, max_dead=1.5)
    assert k == [(0.7, 5.3667), (7.6333, 20.3)] or k == [(0.7, 5.35), (7.65, 20.3)] or (k[0][1] < 5.5 and k[1][0] > 7.5 and len(k) == 2), k

def test_end_to_end(tmp_path):
    cfg = make_cfg(tmp_path, editing={"max_dead_air_s": 0.8})
    meta = sources.run(cfg); off = sync.run(cfg, meta)["result"]["offset_s"]
    a = analyze.run(cfg, meta, steps=("desktop", "speech"))
    plan = timeline.propose(cfg, a, [], off, os.path.join(cfg["paths"]["timelines"], "timeline.json"))
    assert plan["segments"] and all(s["face_out"] > s["face_in"] for s in plan["segments"])
    plan["segments"] = plan["segments"][:3]                               # keep the test short
    plan["chips"] = [[0.0, "Fixture", ["Input", "Output"], None], [5.0, "Fixture", ["Input", "Output"], 0]]
    with pytest.raises(PermissionError):
        pipeline.build(cfg, plan, a, meta, os.path.join(cfg["paths"]["full_video"], "x.mp4"))
    state.approve(cfg, "full_render", "test")
    r = pipeline.build(cfg, plan, a, meta, os.path.join(cfg["paths"]["full_video"], "fixture.mp4"))
    assert not media.decode_errors(r["file"])
    dur = float(media.probe(r["file"])["format"]["duration"]); assert abs(dur - sum(e["frames"] for e in r["edl"]) / 30) < 0.1
    with pytest.raises(FileExistsError):                                  # finals are never overwritten silently
        pipeline.build(cfg, plan, a, meta, r["file"])

def test_short_vertical_render(tmp_path):
    from ytpipe import shorts
    cfg = make_cfg(tmp_path, editing={"max_dead_air_s": 0.8})
    meta = sources.run(cfg); off = sync.run(cfg, meta)["result"]["offset_s"]; a = analyze.run(cfg, meta, steps=("desktop", "speech"))
    plan = timeline.propose(cfg, a, [], off, os.path.join(cfg["paths"]["timelines"], "timeline.json"))
    plan["segments"] = [dict(s, layout="B") for s in plan["segments"][:2]]
    state.approve(cfg, "full_render"); r = pipeline.build(cfg, plan, a, meta, os.path.join(cfg["paths"]["full_video"], "f.mp4"))
    c = {"start": 0.5, "end": 4.5, "layout": "desktop + face circle", "hook_text": "What is input?"}
    out = shorts.render_short(cfg, r["file"], [(0.6, 2.0, "Input is what enters"), (2.1, 4.0, "the computer.")], c,
                              os.path.join(cfg["paths"]["shorts"], "s1.mp4"), r["geometry"])
    v = next(s for s in media.probe(out)["streams"] if s["codec_type"] == "video")
    assert (v["width"], v["height"]) == (1080, 1920) and abs(float(media.probe(out)["format"]["duration"]) - 4.0) < 0.15

def test_short_follows_layouts(tmp_path):
    from ytpipe import shorts
    cfg = make_cfg(tmp_path, editing={"max_dead_air_s": 0.8})
    meta = sources.run(cfg); off = sync.run(cfg, meta)["result"]["offset_s"]; a = analyze.run(cfg, meta, steps=("desktop", "speech"))
    plan = timeline.propose(cfg, a, [], off, os.path.join(cfg["paths"]["timelines"], "timeline.json"))
    s0 = plan["segments"][0]; mid = round((s0["face_in"] + s0["face_out"]) / 2 * 30) / 30
    plan["segments"] = [dict(s0, layout="A", face_out=mid), dict(s0, layout="B", face_in=mid)]       # face shot, then slide shot
    state.approve(cfg, "full_render"); r = pipeline.build(cfg, plan, a, meta, os.path.join(cfg["paths"]["full_video"], "f.mp4"))
    total = sum(e["frames"] for e in r["edl"]) / 30
    c = {"start": 0.2, "end": total - 0.2, "layout": "desktop + face circle", "hook_text": "Mixed"}
    out = shorts.render_short(cfg, r["file"], [], c, os.path.join(cfg["paths"]["shorts"], "mixed.mp4"), r["geometry"], r["edl"])
    d = float(media.probe(out)["format"]["duration"]); assert abs(d - (total - 0.4)) < 0.15, d
    assert not media.decode_errors(out)

def test_segments_are_reused(tmp_path):
    import time
    cfg = make_cfg(tmp_path, editing={"max_dead_air_s": 0.8})
    meta = sources.run(cfg); off = sync.run(cfg, meta)["result"]["offset_s"]; a = analyze.run(cfg, meta, steps=("desktop", "speech"))
    plan = timeline.propose(cfg, a, [], off, os.path.join(cfg["paths"]["timelines"], "timeline.json")); plan["segments"] = plan["segments"][:2]
    state.approve(cfg, "full_render"); out = os.path.join(cfg["paths"]["full_video"], "a.mp4")
    pipeline.build(cfg, plan, a, meta, out); seg = os.path.join(cfg["paths"]["full_video"], "work", "seg_000.mkv"); m0 = os.path.getmtime(seg)
    time.sleep(1.1); os.remove(out); pipeline.build(cfg, plan, a, meta, out)
    assert os.path.getmtime(seg) == m0                                  # unchanged segment not re-rendered
