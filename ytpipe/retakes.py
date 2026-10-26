"""Stage 'retakes': find the parts the presenter asked to cut while recording, and repeated starts (retakes), and
propose face-time content cuts for the timeline (timelines/content_cuts.json + reports/content_cuts.md).

A pause instruction ("now pause here, editor, I'll tell you when to resume" ... "okay, start now") removes only the break:
from the instruction to the first utterance after it and its start/okay cues. Spoken cut instructions ("isko cut kar
dena", "cut this part", "कट कर देना") are STRONG: always proposed. Words that are
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
PAUSE = [r"\bpause\b", r"\beditor\b", r"\bresume\b", r"\bstop (the )?recording\b", "पॉज", "पोस है", "एडिटर", "रिसूम"]
RESUME = [r"\bstart\b", r"\bcontinue\b", r"\bresume\b", r"^\W*(okay|ok|so)\W*$", "स्टार्ट", "ओके"]
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

def detect(asr, strong=STRONG, weak=WEAK, pause=PAUSE, resume=RESUME, pauses=None):
    """pauses: the measured speech-map pauses (analysis.json). ASR word times can run words together; a measured pause
    just before an instruction is the exact place to start its cut."""
    W = words_of(asr); us = utterances(W); cuts = []; skip = set()
    for ui, (i, j) in enumerate(us):                 # "pause here, editor... start now": only the break goes, not the sentence before
        text = _text(W, i, j + 1)
        if ui in skip or not any(re.search(p, text) for p in pause): continue
        k = ui + 1
        while k < len(us) and W[us[k][0]][0] - W[j][1] < 120 and any(re.search(p, _text(W, us[k][0], us[k][1] + 1)) for p in pause + resume):
            skip.add(k); k += 1
        if k >= len(us): continue
        m = m0 = next(m for m in range(i, j + 1) if any(re.search(p, _text(W, m, m + 3)) for p in pause))   # first instruction word
        m = max(range(max(i, m - 2), m + 1), key=lambda x: W[x][0] - W[x - 1][1] if x > 0 else 9)  # the instruction opens at the
                                                                                     # biggest gap just before it ("now | pause here")
        i = m; text = _text(W, i, j + 1)
        a, b = _bounds(W, i, us[k][0]); skip.add(ui)
        pm = [p for p in pauses or [] if p[0] < W[m0][0] and p[1] > W[m0][0] - 3.0 and p[1] - p[0] >= 0.25]
        if pm: p0, p1 = max(pm, key=lambda p: p[1]); a = round(p0 + min(0.25, (p1 - p0) / 2), 3)
        i = next(x for x in range(len(W)) if W[x][0] >= a - 0.05 or x == us[k][0]); text = _text(W, i, j + 1)   # words really cut
        cuts.append({"face_in": a, "face_out": b, "reason": f"spoken pause instruction (break in the recording): \"{text}\"", "confidence": "high", "apply": True,
                     "before": _text(W, i - 10, i), "removed": _text(W, i, us[k][0]), "after": _text(W, us[k][0], us[k][0] + 10)})
    for ui, (i, j) in enumerate(us):
        if ui in skip: continue
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

def untranscribed(W, env, thr=-45.0, min_s=3.0, step=0.01, active=0.4):
    """Gaps between transcribed words where the narration level says someone is talking (>= `active` of the gap above
    `thr` dBFS) for >= min_s: the recognizer dropped speech there. A fumble or a spoken cut instruction can hide in such a
    gap (lesson04: 8 s at 590 s), so each one is re-transcribed and reviewed before the cuts are final."""
    out = []                                     # a word "lasting" seconds is the recognizer stretching over lost speech
    for (a, b) in zip([min(w[1], w[0] + 1.2) for w in W[:-1]], [w[0] for w in W[1:]]):
        if b - a < min_s: continue
        seg = env[int(a / step):int(b / step)]
        if len(seg) and (seg > thr).mean() >= active: out.append([round(a, 2), round(b, 2)])
    return out

def retranscribe(cfg, spans, cache_json, pad=0.5):
    """Each missed span heard again on its own (no VAD, no previous-text conditioning), in Hindi and in English, so a
    fumble or a cut instruction shows as words. -> [{start, end, hi, en, instruction}] (cached per span)."""
    cache = json.load(open(cache_json, encoding="utf-8")) if os.path.exists(cache_json) else {}
    todo = [sp for sp in spans if f"{sp[0]:.2f}-{sp[1]:.2f}" not in cache]
    if todo:
        from faster_whisper import WhisperModel
        from . import media
        t = cfg["transcription"]; x = media.audio(cfg["sources"]["face_camera"], sr=16000)
        model = WhisperModel(t["model"], device="cpu", compute_type=t["compute_type"])
        for a, b in todo:
            clip = x[int(max(0, a - pad) * 16000):int((b + pad) * 16000)]; r = {}
            for lang in ("hi", "en"):
                segs, _ = model.transcribe(clip, language=lang, vad_filter=False, condition_on_previous_text=False)
                r[lang] = " ".join(sg.text.strip() for sg in segs)
            cache[f"{a:.2f}-{b:.2f}"] = r
        json.dump(cache, open(cache_json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    out = []
    for a, b in spans:
        r = cache[f"{a:.2f}-{b:.2f}"]; txt = (r["hi"] + " " + r["en"]).lower()
        out.append({"start": a, "end": b, "hi": r["hi"], "en": r["en"],
                    "instruction": any(re.search(k, txt) for k in STRONG + PAUSE)})
    return out

def report(cuts, path, missed=()):
    mm = lambda t: f"{int(t // 60)}:{t % 60:05.2f}"
    L = ["# Content cuts (proposal)", "", "Face-camera times. `apply: true` cuts go into the timeline proposal; set false to keep a part,",
         "true to cut a low-confidence one. Review each: nothing good lost, and the restart starts cleanly.", ""]
    for n, c in enumerate(cuts, 1):
        L += [f"## {n}. {mm(c['face_in'])} – {mm(c['face_out'])} ({c['face_out'] - c['face_in']:.1f} s) · {c['confidence']} · apply: {str(c['apply']).lower()}", "",
              f"{c['reason']}", "", f"- before: …{c['before']}", f"- **removed:** {c['removed']}", f"- after: {c['after']}…", ""]
    if missed:
        L += ["## Speech the recognizer missed (review before the cuts are final)", "",
              "You are talking here but no words were transcribed: re-transcribe each span and listen for a fumble or a cut instruction.", ""]
        for m in missed:
            if isinstance(m, dict):
                L += [f"- {mm(m['start'])} – {mm(m['end'])} ({m['end'] - m['start']:.1f} s)" + (" · **contains a cut/pause instruction**" if m["instruction"] else ""),
                      f"  - heard (hi): {m['hi'] or '—'}", f"  - heard (en, may be translated): {m['en'] or '—'}"]
            else: L += [f"- {mm(m[0])} – {mm(m[1])} ({m[1] - m[0]:.1f} s)"]
        L += [""]
    open(path, "w", encoding="utf-8").write("\n".join(L))
    return path

def run(cfg, asr):
    P = cfg["paths"]; an = os.path.join(P["analysis"], "analysis.json")
    cuts = detect(asr, pauses=json.load(open(an, encoding="utf-8")).get("pauses") if os.path.exists(an) else None); os.makedirs(P["timelines"], exist_ok=True); os.makedirs(P["reports"], exist_ok=True)
    out = os.path.join(P["timelines"], "content_cuts.json")
    if os.path.exists(out):                                          # keep reviewed apply decisions for cuts that still exist
        prev = json.load(open(out, encoding="utf-8"))
        old = {(round(c["face_in"], 1), round(c["face_out"], 1)): c["apply"] for c in prev}
        for c in cuts: c["apply"] = old.get((round(c["face_in"], 1), round(c["face_out"], 1)), c["apply"])
        cuts += [c for c in prev if not any(c["face_in"] < k["face_out"] and k["face_in"] < c["face_out"] for k in cuts)]  # hand-added cuts stay
        cuts.sort(key=lambda c: c["face_in"])
    json.dump(cuts, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    ej = os.path.join(P["analysis"], "speech_env.npy")
    missed = untranscribed(words_of(asr), __import__("numpy").load(ej), cfg["editing"]["speech_threshold_dbfs"]) if os.path.exists(ej) else []
    if missed and cfg["editing"].get("retranscribe_missed", True):
        missed = retranscribe(cfg, missed, os.path.join(P["analysis"], "missed_speech.json"))
    return cuts, out, report(cuts, os.path.join(P["reports"], "content_cuts.md"), missed), missed
