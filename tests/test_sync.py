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

def test_sync_sections_split_segments_and_carry_their_offset():
    segs = [{"layout": "A", "face_in": 6.3, "face_out": 20.2}, {"layout": "B", "face_in": 20.2, "face_out": 59.7},
            {"layout": "B", "face_in": 66.6, "face_out": 315.5}]
    secs = [(20.0, 62.0, 27.4), (62.0, 82.5, 34.5), (82.5, 130.3, 33.0), (130.3, 136.3, 30.9)]
    out = sync.split_sections(segs, secs)
    assert [(s["face_in"], s["face_out"], s.get("desk_offset"), s["parent"]) for s in out] == [
        (6.3, 20.2, None, 0), (20.2, 59.7, 27.4, 1), (66.6, 82.5, 34.5, 2), (82.5, 130.3, 33.0, 2), (130.3, 136.3, 30.9, 2),
        (136.3, 315.5, None, 2)]
    assert sync.desk_offset(out, 70.0, 110.7) == 34.5 and sync.desk_offset(out, 200.0, 110.7) == 110.7
    assert sync.split_sections(segs, []) == [dict(s, parent=i) for i, s in enumerate(segs)]
    assert sync.split_sections(segs, [(0.0, 62.0, 27.4)])[0]["desk_offset"] == 27.4      # a camera shot inside a section
