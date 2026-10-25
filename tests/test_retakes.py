"""Retake detection on synthetic ASR words: a spoken cut instruction removes the abandoned attempt through the
instruction up to the clean restart (edges in pauses); 'phir se' used while teaching loops is not an instruction;
a repeated start without an instruction keeps the later take; the timeline removes applied cuts."""
from ytpipe import retakes, timeline

def asr(*utts):
    """utts: (start_s, "words ...") with 0.3 s per word."""
    segs = []
    for t, text in utts:
        ws = [[round(t + k * 0.3, 2), round(t + k * 0.3 + 0.25, 2), " " + w, 0.9] for k, w in enumerate(text.split())]
        segs.append({"start": t, "end": ws[-1][1], "text": text, "words": ws})
    return {"language": "hi", "segments": segs}

def test_spoken_cut_finds_the_attempt_and_the_restart():
    a = asr((0.0, "hello students aaj hum algorithm seekhenge"), (3.0, "algorithm ek step by step uh galat"),
            (6.0, "isko cut kar dena"), (9.0, "algorithm ek step by step process hai"), (13.0, "jo problem solve karta hai"))
    c = retakes.detect(a)
    assert len(c) == 1 and c[0]["confidence"] == "high" and c[0]["apply"]
    assert 2.0 < c[0]["face_in"] < 3.0 and 8.5 < c[0]["face_out"] < 9.0          # inside the pauses, words untouched
    assert c[0]["removed"].startswith("algorithm ek step by step uh galat isko cut") and c[0]["after"].startswith("algorithm ek step by step process")

def test_cut_without_matching_restart_is_low_confidence():
    a = asr((0.0, "pehla point ye hai"), (3.0, "mujhse galti ho gayi"), (5.0, "ye cut karna"), (8.0, "doosra point dekhte hain"))
    c = retakes.detect(a)
    assert len(c) == 1 and c[0]["confidence"] == "low" and c[0]["removed"].startswith("mujhse galti")

def test_loop_language_is_not_an_instruction_and_retakes_keep_the_later_take():
    a = asr((0.0, "loop mein ye step phir se chalega"), (4.0, "jab tak condition true hai"),
            (8.0, "flowchart mein hum"), (9.5, "flowchart mein hum decision ke liye diamond use karte hain"))
    c = retakes.detect(a)
    assert len(c) == 1 and c[0]["reason"] == "repeated start (retake)" and 7.5 < c[0]["face_in"] < 8.0 and 9.0 < c[0]["face_out"] < 9.5

def test_devanagari_instruction():
    a = asr((0.0, "एल्गोरिदम एक प्रोसेस गलत"), (3.0, "इसको कट कर देना"), (6.0, "एल्गोरिदम एक प्रोसेस है"))
    c = retakes.detect(a); assert len(c) == 1 and c[0]["confidence"] == "high"

def test_timeline_removes_applied_cuts():
    k = timeline.remove([(0.0, 20.0)], [(2.75, 8.75, {})])                   # edges snap to the 30 fps grid (within 1 frame)
    assert len(k) == 2 and abs(k[0][1] - 2.75) <= 1 / 30 and abs(k[1][0] - 8.75) <= 1 / 30 and k[1][1] == 20.0

def test_writing_silences_are_not_dead_air():
    pauses = [(10.0, 13.0), (20.0, 23.0)]                                      # both longer than max_dead 1.5 s
    k = timeline.keeps(pauses, 0.0, 30.0, protect=[(20.5, 22.0)])             # the presenter writes during the second
    assert len(k) == 2 and k[0][1] < 11 and k[1][0] > 12 and k[1][1] > 29      # first silence cut, second kept whole

def test_cut_through_writing_gets_a_cutaway():
    segs = [{"layout": "B", "face_in": 0.0, "face_out": 10.0}, {"layout": "B", "face_in": 13.0, "face_out": 30.0}]
    out, done = timeline.cutaways(segs, [(10.0, 13.0, {})], [{"start": 11.0, "end": 11.5}], [(15.0, 15.5)])
    assert done == [13.0] and [s["layout"] for s in out] == ["B", "A", "B"] and abs(out[1]["face_out"] - 15.25) < 1 / 30
    out2, done2 = timeline.cutaways(segs, [(10.0, 13.0, {})], [{"start": 20.0, "end": 21.0}], [(15.0, 15.5)])
    assert done2 == [] and len(out2) == 2                                         # no writing inside the cut: no cut-away
