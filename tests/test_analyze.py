import json, os
from ytpipe import config, sources, analyze
from tests.test_core import make_cfg, TRUTH

def test_desktop_analysis(tmp_path):
    c = make_cfg(tmp_path); meta = sources.run(c); a = analyze.run(c, meta, steps=("desktop", "speech"))
    x0, y0, x1, y1 = a["slide_area"]; tx1 = TRUTH["slide_area"][2]
    assert x0 == 0 and y0 == 0 and abs(x1 - tx1) <= 8 and y1 == 1080, a["slide_area"]
    assert len(a["slide_changes"]) == 2 and all(abs(t - u) <= 0.6 for t, u in zip(a["slide_changes"], TRUTH["slide_changes_desktop"])), a["slide_changes"]
    cb, tb = a["counter_box"], TRUTH["counter_box"]
    assert cb is not None and cb[0] < tb[2] and cb[2] > tb[0] and cb[1] < tb[3] and cb[3] > tb[1], cb
    on = [e["start"] for e in a["ink"]]
    assert len(on) == 2 and all(abs(o - t[0]) <= 0.25 for o, t in zip(on, TRUTH["ink"])), a["ink"]
    # speech pauses: every true gap >= 0.4 s between speech segments is found
    segs = TRUTH["speech_segments_face"]
    gaps = [(b0, a1) for (_, b0), (a1, _) in zip(segs, segs[1:]) if a1 - b0 >= 0.4]
    for g0, g1 in gaps:
        assert any(p0 <= g0 + 0.1 and p1 >= g1 - 0.1 for p0, p1 in a["pauses"]), (g0, g1)
