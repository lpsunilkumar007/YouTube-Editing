"""Renderer tests: (1) generic geometry reproduces the approved Lesson 01 layout from Lesson 01's measurements
(read-only use of _work/slide_content.npz); (2) A/B/C segments render from synthetic fixtures with correct size, frame
count, no decode errors, circle placed where the geometry says."""
import os
import numpy as np
from ytpipe import config, layout, render, sources, analyze, media
from tests.test_core import make_cfg

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def test_geometry_reproduces_lesson01():
    cfg = make_cfg(os.path.join(ROOT, "tests", "_tmp"))
    g = layout.geometry(cfg, [0, 0, 1890, 1080], None, counter_box=[1709, 1030, 1755, 1047])
    assert g["card"] == [24, 24, 1664, 950], g["card"]          # approved v3-v9 card
    assert g["camera"] == [1528, 688, 368]                      # approved circle
    assert g["bar"][:2] == [24, 995] and g["bar"][2] == 1460    # approved chip bar
    assert g["counter"]["hidden_by_camera"]
    # with Lesson 01's worst-case content masks the clearance rule is stricter than the hand check of v6: the leftover
    # pre-camera ink on slides 1-2 reaches ~10 px under the circle at 0.88, so the card is shrunk until nothing is covered
    d = np.load(os.path.join(ROOT, "_work", "slide_content.npz")); masks = [d[k] > 0 for k in d.files if not k.startswith("n")]
    g2 = layout.geometry(cfg, [0, 0, 1890, 1080], masks, counter_box=[1709, 1030, 1755, 1047])
    assert g2["card"][2] < 1664 and layout._content_under_circle(masks, [0, 0, 1890, 1080], g2["scale"], 24, g2["camera"]) == 0
    assert g2["counter"]["patch"] is not None

def test_render_abc_segments(tmp_path):
    cfg = make_cfg(tmp_path); meta = sources.run(cfg); a = analyze.run(cfg, meta, steps=("desktop",))
    masks = list(np.load(os.path.join(cfg["paths"]["analysis"], "content_masks.npz")).values())
    g = layout.geometry(cfg, a["slide_area"], masks, a["counter_box"]); L = layout.static_layers(cfg, g, str(tmp_path / "layers"))
    off = 7.4; parts = []
    for i, seg in enumerate([{"layout": "A", "face_in": 2.0, "face_out": 4.0},
                             {"layout": "B", "face_in": 6.0, "face_out": 8.0},
                             {"layout": "C", "face_in": 8.0, "face_out": 10.0, "zoom": (100, 100, 1100, True, True)}]):
        out = str(tmp_path / f"s{i}.mkv"); crop = render.fixed_crop(cfg, None, seg["face_in"], seg["face_out"])
        render.render_segment(render.segment(cfg, g, L, seg, out, off, "sdr", crop), out); parts.append(out)
        assert render.frame_count(out) == 60
        v = next(s for s in media.probe(out)["streams"] if s["codec_type"] == "video"); assert (v["width"], v["height"]) == (1920, 1080)
    j = render.join(parts, str(tmp_path / "joined.mkv")); assert render.frame_count(j) == 180 and not media.decode_errors(j)
    # camera circle: pixels inside the circle differ from the canvas colour, pixels just outside the ring do not (B segment)
    f = media.frames(parts[1], 1.0, 0.04, 1920, 1080, 30, pix="rgb24")[0].astype(int)
    cx, cy, d = g["camera"]; c = f[cy + d // 2, cx + d // 2]; o = f[cy + d // 2, min(1919, cx + d + 14)]
    assert np.abs(c - np.array([16, 24, 39])).sum() > 30 and np.abs(o - np.array([16, 24, 39])).sum() < 30
