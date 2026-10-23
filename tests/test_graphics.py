"""Graphics on fixtures: chip states, badge, bar MOV frame count, every HyperFrames kind renders (short durations)."""
import os
import numpy as np
from ytpipe import graphics, render, layout
from tests.test_core import make_cfg

def test_bar_and_badge(tmp_path):
    cfg = make_cfg(tmp_path); g = layout.geometry(cfg, [0, 0, 1890, 1080])
    st = graphics.bar_state(cfg, (g["bar"][2], 64), "Every program", ["Input", "Process", "Output"], 1)
    assert st.shape == (64, 1460, 4) and st[..., 3].max() == 255
    p = graphics.bar_video(cfg, g, [(0.0, "Hardware", ["Input", "CPU"], None), (1.0, "Hardware", ["Input", "CPU"], 0)], 0.0, 2.0, str(tmp_path / "bar.mov"))
    assert render.frame_count(p) == 62
    png, w = graphics.badge(cfg, 3, 10, str(tmp_path / "b.png")); assert 80 < w < 160
    try:
        graphics.bar_state(cfg, (300, 64), "A very long section label", ["Alpha", "Beta", "Gamma"], 0); assert False
    except ValueError:
        pass

def test_hyperframes_kinds(tmp_path):
    cfg = make_cfg(tmp_path)
    els = [{"kind": "term", "start": 1.0, "duration": 1.2, "t": "Variable", "d": "A named place for a <b>value</b>."},
           {"kind": "topic", "start": 2.0, "duration": 1.2, "text": "Loops"},
           {"kind": "title", "start": 3.0, "duration": 1.2, "kicker": "Lesson 02 • C#", "lines": ["Variables", "and loops"]},
           {"kind": "end", "start": 4.0, "duration": 1.2, "text": "Arrays"},
           {"kind": "ipo", "start": 5.0, "duration": 1.5, "title": "Every program", "steps": ["Input", "Process", "Output"], "times": [0.2, 0.6, 1.0]},
           {"kind": "rings", "start": 6.0, "duration": 1.6, "circles": [{"cx": 300, "cy": 400, "r": 70, "color": "#A3E635"},
            {"cx": 700, "cy": 400, "r": 70, "color": "#38BDF8"}], "times": [0.1, 0.6], "clear_at": 1.5},
           {"kind": "code", "start": 7.0, "duration": 1.2, "lines": [{"x": 200, "y": 300, "w": 900, "h": 40, "t": 0.2}]}]
    movs = graphics.render_elements(cfg, els)
    for m in movs.values():
        assert render.frame_count(m) >= 30
