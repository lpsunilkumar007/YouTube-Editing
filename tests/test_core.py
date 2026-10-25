"""Stage-1/3 tests on synthetic fixtures (tests/make_fixtures.py). No lecture footage is used."""
import json, os, tempfile
import pytest
from ytpipe import config, sources, sync, state

FX = os.path.join(os.path.dirname(__file__), "fixtures")
TRUTH = json.load(open(os.path.join(FX, "truth.json")))

def make_cfg(tmp, **extra):
    data = {"face_camera": os.path.join(FX, "face.mp4"), "desktop_recording": os.path.join(FX, "desktop.mkv"),
            "lecture_topic": "Fixture topic", "output_dir": str(tmp), **extra}
    return config.load(data=data)

def test_required_fields():
    with pytest.raises(config.ConfigError) as e:
        config.load(data={"face_camera": "PATH_TO_FACE_VIDEO", "desktop_recording": "x", "lecture_topic": "LECTURE_TOPIC"})
    assert "required: face_camera" in str(e.value) and "required: lecture_topic" in str(e.value)

def test_unknown_override_rejected(tmp_path):
    with pytest.raises(config.ConfigError):
        make_cfg(tmp_path, overrides={"zoom": {"rnage": [1.2, 1.4]}})

def test_overrides_and_legacy_keys(tmp_path):
    c = make_cfg(tmp_path, overrides={"camera_overlay": {"diameter_px": 340}, "zoom": {"range": [1.2, 1.4]}})
    assert c["layout"]["camera"]["diameter"] == 340 and c["zoom"]["range"] == [1.2, 1.4]
    assert c["paths"]["thumbnails"].startswith(str(tmp_path))

def test_template_and_example_parse():
    root = os.path.dirname(FX.rstrip("/\\")); root = os.path.dirname(root)
    for f in ("video_project_config.json", "templates/video_project_config.example.json"):
        json.load(open(os.path.join(root, f), encoding="utf-8"))

def test_inspect_and_audio_sync(tmp_path):
    c = make_cfg(tmp_path); meta = sources.run(c)
    assert meta["face_color_pipeline"] == "sdr" and meta["desktop_has_audio"]
    rep = sync.run(c, meta)
    assert rep["result"]["status"] == "ok"
    assert abs(rep["result"]["offset_s"] - TRUTH["offset_s"]) < 0.01          # within 10 ms of the known offset
    assert abs(rep["audio"]["drift_ppm"]) < 50

def test_sync_needs_input_without_audio(tmp_path):
    c = make_cfg(tmp_path); meta = sources.run(c); meta["desktop_has_audio"] = False
    assert sync.run(c, meta)["result"]["status"] == "needs_input"
    c2 = make_cfg(tmp_path, sync={"manual_offset_s": 7.4})
    assert sync.run(c2, meta)["result"]["offset_s"] == 7.4

def test_checkpoints_and_gates(tmp_path):
    c = make_cfg(tmp_path); fp = state.fingerprint(c["sources"]["face_camera"], {"a": 1})
    assert not state.done(c, "inspect", fp); state.mark(c, "inspect", fp); assert state.done(c, "inspect", fp)
    with pytest.raises(PermissionError): state.require(c, "full_render")
    state.approve(c, "full_render"); state.require(c, "full_render")

def test_blog_builds_and_checks_seo(tmp_path):
    from ytpipe import blog
    cfg = {"paths": {"root": str(tmp_path), "metadata": str(tmp_path)}}
    (tmp_path / "youtube_chapters.txt").write_text("0:00 Intro\n1:05 Flowcharts\n")
    para = "How to start programming: " + "word " * 120
    inp = {"title": "How to Start Programming", "slug": "how-to-start-programming", "focus_keyword": "how to start programming",
           "seo_title": "How to Start Programming: Flowchart First", "meta_description": "How to start programming: " + "x" * 110,
           "tags": ["a", "b"], "cover_alt": "cover", "video_url": "https://youtu.be/abcdefghijk", "intro": [para],
           "sections": [{"heading": "How to start programming on paper", "body": [para] * 6 + ["- one\n- two", "```\nSTART\nEND\n```"]}],
           "faq": [{"q": "Q?", "a": "A **bold** answer."}]}
    r = blog.build(cfg, inp)
    assert r["problems"] == [] and r["todo"] and r["words"] > 800
    h = (tmp_path / "blog" / "how-to-start-programming.html").read_text()
    assert "youtube.com/embed/abcdefghijk" in h and "&t=65s" in h and '"FAQPage"' in h and "<strong>bold</strong>" in h
    inp["seo_title"] = "x" * 70; assert any("SEO title" in p for p in blog.check(inp, 900))
