"""Fact-check gate and research-based title rules: every claim needs a verdict, a wrong claim needs a source and a fix
(an applied cut covering it, or a correction note); titles lead with a researched search phrase, carry no lesson
numbers or clickbait, and the research note is dated and sourced."""
import datetime
from ytpipe import factcheck, metadata
from tests.test_core import make_cfg

LINES = [{"face": 10.0, "text": "Modulus operator is based on percentage", "flags": set()},
         {"face": 20.0, "text": "11 modulus 2 gives the remainder 1", "flags": set()},
         {"face": 30.0, "text": "Namaste doston, aaj hum", "flags": set()}]

def test_claims_and_gate():
    cl = factcheck.claims(LINES)
    assert [c["text"][:7] for c in cl] == ["Modulus", "11 modu"]                     # greetings are not claims
    assert factcheck.check(cl, None)[0].startswith("no metadata/fact_check.json")
    fc = {"claims": [{"id": "c001", "verdict": "wrong"}, {"id": "c002", "verdict": "correct", "source": "x"}]}
    p = factcheck.check(cl, fc)
    assert any("needs a source" in x for x in p) and any("action 'cut' or 'note'" in x for x in p)
    fc["claims"][0].update(source="https://learn.microsoft.com/...", action="cut")
    assert any("no applied cut covers" in x for x in factcheck.check(cl, fc))
    assert factcheck.check(cl, fc, [{"face_in": 9.0, "face_out": 12.0, "apply": True}]) == []
    fc["claims"][0].update(action="note"); assert any("correction text" in x for x in factcheck.check(cl, fc))
    assert any("has no verdict" in x for x in factcheck.check(cl, {"claims": [{"id": "c001", "verdict": "opinion"}]}))

def test_title_rules(tmp_path):
    cfg = make_cfg(tmp_path); ch = [(0, "a"), (40, "b"), (90, "c")]
    inp = {"intro": "Is video mein if else flowchart samjhenge", "pinned_comment": "Practice?", "recommended": 1,
           "titles": [{"angle": "s", "title": "If Else Flowchart: Even or Odd Example"}],
           "research": {"date": datetime.date.today().isoformat(), "sources": ["https://a", "https://b"], "search_phrases": ["if else flowchart"]}}
    tags = ["a", "b", "c", "d", "e"]
    assert metadata.seo(cfg, inp, "word " * 250, ch, tags) == []
    old = dict(inp, research=dict(inp["research"], date="2020-01-01"))
    assert any("days old" in x for x in metadata.seo(cfg, old, "word " * 250, ch, tags))
    assert any("no 'research'" in x for x in metadata.seo(cfg, {k: v for k, v in inp.items() if k != "research"}, "word " * 250, ch, tags))
    bad = dict(inp, titles=[{"angle": "s", "title": "SHOCKING Trick You Won't Believe | Lesson 4, an extremely long title"}])
    p = metadata.seo(cfg, bad, "word " * 250, ch, tags)
    for want in ("cut off on phones", "search phrase", "lesson number", "clickbait", "all-caps"): assert any(want in x for x in p), (want, p)
