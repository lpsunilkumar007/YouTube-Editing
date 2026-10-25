"""Stage 'retakes': find the parts the presenter asked to cut while recording, and repeated starts (retakes), and
propose face-time content cuts for the timeline (timelines/content_cuts.json + reports/content_cuts.md).

Spoken instructions ("isko cut kar dena", "cut this part", "कट कर देना") are STRONG: always proposed. Words that are
also normal teaching language ("phir se", "dobara", "again" - loops repeat steps!) are WEAK: they only count when the
presenter then repeats an earlier sentence opening. For each instruction the cut runs from where the abandoned attempt
started to where the clean restart starts:
  - restart  = the first utterance after the instruction (after a pause)
  - attempt  = the latest earlier utterance whose opening words match the restart's (the same sentence tried again);
               if none matches, the utterance before the instruction (its start is a guess: confidence "low", review it)
Repeated starts without an instruction (an utterance whose first 3 words open the next one within 20 s) are proposed
too, keeping the later, complete take. Every cut lands inside measured pauses with room tone on both sides, never in a
word. Nothing is removed silently: each cut has apply true/false and the words on both sides for review."""
import json, os, re

STRONG = [r"\bcut\b", r"\bkat (do|dena|dijiye)\b", r"\bedit (kar|karna|kardo|kar do|out)\b", r"\bremove (this|that|it)\b",
          r"\b(isko|ise|isse|ye|yeh|is part ko|ye part|that part|this part) (hata|nikal|remove)", r"\bretake\b",
          "कट", "काट दे", "हटा दे", "एडिट कर"]
WEAK = [r"\bphir se\b", r"\bdobara\b", r"\bdubara\b", r"\bonce again\b", r"\bagain\b", r"\bfrom (the )?(start|beginning)\b",
        "फिर से", "दोबारा", "दुबारा"]

def _norm(w):
    return re.sub(r"[^\wऀ-ॿ']+", "", w.lower())

def words_of(asr):
    return [(float(s), float(e), _norm(t)) for seg in asr["segments"] for s, e, t, *_ in seg["words"] if _norm(t)]

def utterances(W, gap=0.4):
    """Word runs split at gaps >= gap s -> [(first_word_index, last_word_index)]."""
    out, a = [], 0
    for i in range(1, len(W) + 1):
        if i == len(W) or W[i][0] - W[i - 1][1] >= gap: out.append((a, i - 1)); a = i
    return out

def _text(W, i, j):
    return " ".join(w[2] for w in W[max(0, i):max(0, j)])

def _bounds(W, i, j, side=0.25):
    """Cut from before word i to before word j: edges in the pauses around them, with up to `side` s of room tone."""
    a = W[i][0] - min(side, (W[i][0] - W[i - 1][1]) / 2) if i > 0 else max(0.0, W[i][0] - side)
    b = W[j][0] - min(side, (W[j][0] - W[j - 1][1]) / 2) if j < len(W) else W[-1][1] + side
    return round(a, 3), round(b, 3)

def _match(W, us, k, start, n=3):
    """Latest utterance before index `start` whose first n words equal utterance k's first n words (n=3, then 2)."""
    for m in (n, 2):
        key = [w[2] for w in W[us[k][0]:us[k][0] + m]]
        if len(key) < m: continue
        for u in reversed([u for u in us if u[0] < start and W[start][0] - W[u[0]][0] < 90]):
            if [w[2] for w in W[u[0]:u[0] + m]] == key: return u
    return None

def detect(asr, strong=STRONG, weak=WEAK):
    W = words_of(asr); us = utterances(W); cuts = []
    for ui, (i, j) in enumerate(us):
        text = _text(W, i, j + 1); kind = "strong" if any(re.search(p, text) for p in strong) else "weak" if any(re.search(p, text) for p in weak) else None
        if not kind or ui + 1 >= len(us): continue
        k = ui + 1; att = _match(W, us, k, i)
        if att is None and kind == "weak": continue                  # 'phir se' in a sentence about loops: not an instruction
        conf = "high" if att else "low"
        if att is None: att = us[ui - 1] if ui > 0 else us[ui]       # guess: the utterance just before the instruction
        a, b = _bounds(W, att[0], us[k][0])
        cuts.append({"face_in": a, "face_out": b, "reason": f"spoken instruction ({kind}): \"{text}\"", "confidence": conf, "apply": kind == "strong",
                     "before": _text(W, att[0] - 10, att[0]), "removed": _text(W, att[0], us[k][0]), "after": _text(W, us[k][0], us[k][0] + 10)})
    for ui in range(len(us) - 1):                                    # repeated starts without an instruction
        (i, j), (k0, _) = us[ui], us[ui + 1]
        if j - i < 2 or W[k0][0] - W[i][0] > 20: continue
        if [w[2] for w in W[i:i + 3]] == [w[2] for w in W[k0:k0 + 3]] and not any(c["face_in"] <= W[i][0] < c["face_out"] for c in cuts):
            a, b = _bounds(W, i, k0)
            cuts.append({"face_in": a, "face_out": b, "reason": "repeated start (retake)", "confidence": "medium", "apply": True,
                         "before": _text(W, i - 10, i), "removed": _text(W, i, k0), "after": _text(W, k0, k0 + 10)})
    cuts.sort(key=lambda c: c["face_in"]); merged = []
    for c in cuts:                                                   # overlapping proposals become one cut
        if merged and c["face_in"] < merged[-1]["face_out"]:
            m = merged[-1]; m["face_out"] = max(m["face_out"], c["face_out"]); m["reason"] += " + " + c["reason"]
            m["apply"] = m["apply"] or c["apply"]; m["after"] = c["after"]; m["removed"] += " … " + c["removed"]
        else: merged.append(c)
    return merged

def report(cuts, path):
    mm = lambda t: f"{int(t // 60)}:{t % 60:05.2f}"
    L = ["# Content cuts (proposal)", "", "Face-camera times. `apply: true` cuts go into the timeline proposal; set false to keep a part,",
         "true to cut a low-confidence one. Review each: nothing good lost, and the restart starts cleanly.", ""]
    for n, c in enumerate(cuts, 1):
        L += [f"## {n}. {mm(c['face_in'])} – {mm(c['face_out'])} ({c['face_out'] - c['face_in']:.1f} s) · {c['confidence']} · apply: {str(c['apply']).lower()}", "",
              f"{c['reason']}", "", f"- before: …{c['before']}", f"- **removed:** {c['removed']}", f"- after: {c['after']}…", ""]
    open(path, "w", encoding="utf-8").write("\n".join(L))
    return path

def run(cfg, asr):
    cuts = detect(asr); P = cfg["paths"]; os.makedirs(P["timelines"], exist_ok=True); os.makedirs(P["reports"], exist_ok=True)
    out = os.path.join(P["timelines"], "content_cuts.json")
    if os.path.exists(out):                                          # keep reviewed apply decisions for cuts that still exist
        old = {(round(c["face_in"], 1), round(c["face_out"], 1)): c["apply"] for c in json.load(open(out, encoding="utf-8"))}
        for c in cuts: c["apply"] = old.get((round(c["face_in"], 1), round(c["face_out"], 1)), c["apply"])
    json.dump(cuts, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return cuts, out, report(cuts, os.path.join(P["reports"], "content_cuts.md"))
