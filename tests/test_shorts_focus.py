"""Guided split screen (ytpipe/shorts_focus.py): matching narration to slide text and readable crops. Synthetic OCR data."""
from ytpipe import shorts_focus as sf

AREA = [0, 0, 1890, 1080]; ASPECT = 1080 / 900

def line(text, x, y, h=40, cw=22):
    words, cx = [], x
    for t in text.split():
        words.append({"t": t, "x": cx, "y": y, "w": len(t) * cw, "h": h}); cx += len(t) * cw + cw
    return {"text": text, "words": words}

SLIDE = [line("A computer is two things working together", 92, 146, 45),            # title band: topic, not a target
         line("HARDWARE", 142, 365, 47), line("parts you can touch", 185, 454, 26, 14),
         line("SOFTWARE", 720, 365, 47), line("instructions you cannot touch", 682, 451, 23, 14),
         line("Hardware without software does nothing", 131, 673, 26, 14)]

def test_blocks_skip_title_and_group_heading_with_subline():
    B = sf.blocks(SLIDE, AREA)
    words = [[w for w, _ in b["words"]] for b in B]
    assert ["A", "computer"] not in [w[:2] for w in words]
    assert ["HARDWARE", "parts", "you", "can", "touch"] in words

def test_heading_beats_body_text():
    B = sf.blocks(SLIDE, AREA)
    m = sf.match("Hardware kya hai? Jo cheez", B)
    assert m[1] == 365 and m[0] == 142                                       # the HARDWARE block, not the paragraph

def test_title_words_alone_are_weak():
    B = sf.blocks(SLIDE, AREA); weak = sf.title_words(SLIDE)
    assert sf.match("ek computer hai kya", B, weak=weak) is None

def test_nothing_named():
    assert sf.match("jaise ki screen ho gayi", sf.blocks(SLIDE, AREA)) is None

def test_crop_readable_and_inside():
    c = sf.crop_for([142, 365, 512, 480], AREA, ASPECT)
    assert c[2] >= 900 - 2 and abs(c[2] / c[3] - ASPECT) < 0.01
    assert c[0] <= 142 and c[0] + c[2] >= 512 and c[1] <= 365 and c[1] + c[3] >= 480 and c[0] >= 0 and c[1] + c[3] <= 1080

def test_too_wide_region_falls_back():
    assert sf.crop_for([50, 300, 1850, 400], AREA, ASPECT) is None

def test_edge_does_not_slice_text_line():
    boxes = [[850, 600, 1100, 630]]                                           # a line across the right edge of a 900 crop at x 0
    c = sf.crop_for([100, 500, 400, 640], AREA, ASPECT, boxes=boxes)
    assert not (c[0] < 1100 and c[0] + c[2] > 850 and c[0] + c[2] < 1100)

def test_no_text_line_cut_at_any_edge():
    LB = sf.line_boxes(SLIDE) + [[1295, 364, 1658, 413], [914, 672, 1624, 699]]          # a third card and a wide line
    for roi in ([142, 365, 512, 480], [682, 451, 1114, 480], [92, 146, 1000, 210], [131, 672, 803, 705]):
        c = sf.crop_for(roi, AREA, ASPECT, boxes=LB)
        assert c and not sf.sliced(c, LB) and c[0] <= roi[0] and c[0] + c[2] >= roi[2] and c[1] <= roi[1] and c[1] + c[3] >= roi[3]

def test_unclip_keeps_the_writing_and_never_zooms_more():
    LB = [[233, 810, 1539, 844]]; c0 = [8, 384, 700, 696]
    c = sf.unclip(c0, AREA, 1080 / 1260, LB, must=[136, 468, 576, 790])
    assert not sf.sliced(c, LB) and c[0] <= 136 and c[0] + c[2] >= 576 and min(1080 / c[2], 1260 / c[3]) <= min(1080 / 700, 1260 / 696) + 1e-6
