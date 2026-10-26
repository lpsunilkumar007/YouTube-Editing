"""Offset from pen/word anchors (silent OBS audio): ink follows its spoken word, never precedes it."""
from ytpipe import sync

def test_anchor_offset_lesson04():
    d = [(72.9, 76.8), (87.0, 89.6), (92.9, 95.8), (99.2, 102.5), (226.2, 229.9), (226.8, 230.4), (227.4, 231.0), (229.1, 231.9),
         (229.7, 232.5), (527.4, 530.6), (528.2, 531.5), (529.0, 532.6)]
    r = sync.anchor_offset([{"face": f, "desk": k} for f, k in d])
    assert r["status"] == "ok" and r["offset_s"] == 2.8 and r["lag_after_word_s"] == [-0.2, 1.1]

def test_too_few_or_disagreeing_anchors_need_input():
    assert sync.anchor_offset([{"face": 1, "desk": 2}] * 3)["status"] == "needs_input"
    r = sync.anchor_offset([{"face": 0, "desk": x} for x in (1.0, 1.1, 1.2, 1.3, 6.0)])
    assert r["status"] == "needs_input" and "disagree" in r["reason"]

def test_silent_desktop_needs_anchors_or_a_waiver(tmp_path):
    from tests.test_core import make_cfg
    cfg = make_cfg(tmp_path); cfg["sync"]["manual_offset_s"] = -2.0
    meta = {"desktop_has_audio": False, "face_camera": {}, "desktop_recording": {}}
    assert sync.run(cfg, meta)["result"]["status"] == "needs_input"
    cfg["sync"]["anchors_waived"] = "no writing in this lecture"
    assert sync.run(cfg, meta)["result"]["status"] == "ok"
