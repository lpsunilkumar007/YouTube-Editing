"""Transcription and the cleaned-transcript format (shared by captions, chapters, metadata, thumbnails and Shorts;
transcribe ONCE per lecture).

words.json   : raw ASR (faster-whisper) {"segments": [{"start","end","text","words": [[s, e, w, p], ...]}]}
transcript.txt: the human/Claude-cleaned Hinglish transcript, one line per phrase, the Lesson 01 format:
    [MASTER hh:mm:ss.ss | FACE hh:mm:ss.ss | DESK hh:mm:ss.ss | EDIT hh:mm:ss.ss]  text
  markers kept from Lesson 01: '≈' reconstructed wording, '[unclear…]', '(meaning…)' = English rendering, not verbatim,
  '←' annotations, '—cut—' removed lines. Lines starting with '··' or '──' are notes (pauses / on-screen events)."""
import json, os, re, time
import numpy as np

LINE = re.compile(r"^\[MASTER [^|]+\| FACE (\d+):(\d+):(\d+(?:\.\d+)?) \|[^\]]*\]\s+(.*)$")

def speech_chunks(env, thr, max_len=28.0, join_gap=0.6, pad=0.25):
    """Speech map (10 ms dB frames, analysis/speech_env.npy) -> [(a, b)] seconds: speech runs joined across gaps
    < join_gap, packed into chunks of at most max_len split at pauses; silences between chunks are never decoded."""
    on = np.append(env > thr, False); runs, s = [], None
    for i, v in enumerate(on):
        if v and s is None: s = i
        if not v and s is not None:
            if runs and (s - runs[-1][1]) * 0.01 < join_gap: runs[-1][1] = i
            else: runs.append([s, i])
            s = None
    out = []
    for a, b in ((r[0] * 0.01, r[1] * 0.01) for r in runs if (r[1] - r[0]) * 0.01 >= 0.15):
        while b - a > max_len: out.append((a, a + max_len)); a += max_len            # a very long run: hard split
        if out and b - out[-1][0] <= max_len: out[-1] = (out[-1][0], b)
        else: out.append((a, b))
    T = len(env) * 0.01
    return [(round(max(0.0, a - pad), 2), round(min(T, b + pad), 2)) for a, b in out]

def transcribe_chunks(cfg, audio_path, out_json, env, log=print):
    """Chunked faster-whisper over the speech only: one stuck window cannot stall the lecture, retries are limited, and
    progress is saved after each chunk (<out>.partial.json; a rerun resumes)."""
    from faster_whisper import WhisperModel
    from . import media
    t = cfg["transcription"]; chunks = speech_chunks(env, cfg["editing"]["speech_threshold_dbfs"], t.get("max_chunk_s", 28.0))
    part = out_json.replace(".json", ".partial.json"); done = json.load(open(part, encoding="utf-8")) if os.path.exists(part) else {"segments": [], "done": 0}
    x = media.audio(audio_path, sr=16000); model = WhisperModel(t["model"], device="cpu", compute_type=t["compute_type"]); t0 = time.time()
    for n, (a, b) in enumerate(chunks):
        if n < done["done"]: continue
        segs, _ = model.transcribe(x[int(a * 16000):int(b * 16000)], language=t["language"], word_timestamps=True, vad_filter=False,
                                   condition_on_previous_text=False, temperature=t.get("temperatures", [0.0, 0.2, 0.4]),
                                   hallucination_silence_threshold=2.0)
        for s in segs:
            done["segments"].append({"start": round(a + s.start, 2), "end": round(a + s.end, 2), "text": s.text, "chunk": n,
                                     "words": [[round(a + w.start, 2), round(a + w.end, 2), w.word, w.probability] for w in (s.words or [])]})
        done["done"] = n + 1; json.dump(done, open(part, "w", encoding="utf-8"), ensure_ascii=False)
        log(f"chunk {n + 1}/{len(chunks)} {a:.0f}-{b:.0f} s done, {time.time() - t0:.0f} s elapsed")
    out = {"language": t["language"], "chunked": True, "segments": done["segments"]}
    json.dump(out, open(out_json, "w", encoding="utf-8"), ensure_ascii=False, indent=0); os.remove(part)
    return out

HALLUCINATIONS = ("thanks for watching", "thank you for watching", "please subscribe", "subscribe to", "like and subscribe")

def drop_hallucinations(asr, max_s=2.0):
    """Whisper's stock phrases invented in near-silence ("Thanks for watching!") are removed from short segments,
    and from the end of a segment whose words have zero duration. Returns how many were dropped."""
    n = 0
    for s in asr["segments"]:
        low = s["text"].lower()
        hit = next((h for h in HALLUCINATIONS if h in low), None)
        if not hit: continue
        ws = s.get("words") or []
        tail = [w for w in ws if hit.split()[0] in w[2].lower() or w[1] - w[0] < 0.06]
        if s["end"] - s["start"] < max_s or (tail and all(w[1] - w[0] < 0.06 for w in ws[-len(hit.split()):])):
            s["words"] = [w for w in ws if not (w[1] - w[0] < 0.06 and w[0] >= ws[-len(hit.split())][0])] if len(ws) > len(hit.split()) else []
            s["text"] = " ".join(w[2].strip() for w in s["words"]); s["dropped"] = hit; n += 1
    return n

def garbled(seg, max_ratio=2.4, min_prob=0.25):
    """ASR loop/garbage: text that compresses far too well (one syllable repeated) or words the model barely believed."""
    import zlib
    t = seg["text"].strip().encode("utf-8"); ws = seg.get("words") or []
    ratio = len(t) / max(1, len(zlib.compress(t))); prob = sum(w[3] for w in ws) / len(ws) if ws else 1.0
    return len(t) > 20 and (ratio > max_ratio or prob < min_prob)

def repair(cfg, audio_path, asr, log=print):
    """Re-decode each garbled segment on its own (beam search, no temperature fallback; the configured language, then
    auto-detect, then English) and keep the cleanest result. One that stays garbled is marked unclear, to be checked by
    ear: its words are dropped so captions and cut detection never use them. Sets asr["repaired"]."""
    bad = [i for i, s in enumerate(asr["segments"]) if garbled(s)]
    if not bad: asr["repaired"] = []; return asr
    from faster_whisper import WhisperModel
    from . import media
    import zlib
    t = cfg["transcription"]; x = media.audio(audio_path, sr=16000); model = WhisperModel(t["model"], device="cpu", compute_type=t["compute_type"]); done = []
    for i in bad:
        s = asr["segments"][i]; a, b = s["start"], s["end"]; best = None
        for lang in (t["language"], None, "en"):
            segs, info = model.transcribe(x[int(a * 16000):int(b * 16000)], language=lang, word_timestamps=True, vad_filter=False, beam_size=5,
                                          temperature=0.0, condition_on_previous_text=False)
            segs = [{"start": round(a + q.start, 2), "end": round(a + q.end, 2), "text": q.text,
                     "words": [[round(a + w.start, 2), round(a + w.end, 2), w.word, w.probability] for w in (q.words or [])]} for q in segs]
            if segs and not any(garbled(q) for q in segs):
                best = (lang or info.language, segs); break
        if best: asr["segments"][i] = {"start": a, "end": b, "text": " ".join(q["text"].strip() for q in best[1]), "repaired": best[0],
                                       "words": [w for q in best[1] for w in q["words"]]}
        else: asr["segments"][i] = {"start": a, "end": b, "text": "[unclear: ASR could not decode this; check by ear]", "unclear": True, "words": []}
        done.append({"start": a, "end": b, "result": best[0] if best else "unclear", "text": asr["segments"][i]["text"][:120]})
        log(f"repair {a:.1f}-{b:.1f} s: {done[-1]['result']}: {done[-1]['text']}")
    asr["repaired"] = done
    return asr

def transcribe(cfg, audio_path, out_json, env=None):
    """faster-whisper with word timestamps (local; medium int8 fits 8 GB RAM). Chunked over the speech map when it
    exists (transcription.chunked), else one pass with VAD. Cached: skipped if out_json exists."""
    if os.path.exists(out_json):
        return json.load(open(out_json, encoding="utf-8"))
    t = cfg["transcription"]; os.makedirs(os.path.dirname(out_json), exist_ok=True)
    if t.get("chunked") and env is not None: return transcribe_chunks(cfg, audio_path, out_json, env)
    from faster_whisper import WhisperModel
    model = WhisperModel(t["model"], device="cpu", compute_type=t["compute_type"])
    segs, info = model.transcribe(audio_path, language=t["language"], word_timestamps=t["word_timestamps"],
                                  vad_filter=t["vad"], condition_on_previous_text=False)
    out = {"language": info.language, "segments": [
        {"start": s.start, "end": s.end, "text": s.text, "words": [[w.start, w.end, w.word, w.probability] for w in (s.words or [])]}
        for s in segs]}
    os.makedirs(os.path.dirname(out_json), exist_ok=True)
    json.dump(out, open(out_json, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    return out

def _hms(t):
    h = int(t // 3600); m = int(t % 3600 // 60); return f"{h:02d}:{m:02d}:{t % 60:05.2f}"

def draft_from_words(words, offset_s, out_txt):
    """First draft of transcript.txt from ASR segments, to be corrected (glossary + review) before captions are built."""
    with open(out_txt, "w", encoding="utf-8") as f:
        f.write("TRANSCRIPT DRAFT (ASR, not yet reviewed). Correct the text after the ']' and keep the brackets.\n")
        for s in words["segments"]:
            F = s["start"]
            f.write(f"[MASTER {_hms(F + offset_s)} | FACE {_hms(F)} | DESK {_hms(F + offset_s)} | EDIT --:--:--.--]  {s['text'].strip()}\n")

def parse(path):
    """-> [{'face': seconds, 'text': str, 'flags': set}] in file order (notes and removed lines excluded)."""
    out = []
    for raw in open(path, encoding="utf-8"):
        m = LINE.match(raw.rstrip("\n"))
        if not m:
            continue
        h, mi, s, text = m.groups(); F = int(h) * 3600 + int(mi) * 60 + float(s)
        if "—cut—" in raw:
            continue
        flags = set()
        if "≈" in text: flags.add("reconstructed")
        if "[unclear" in text: flags.add("unclear")
        if "(meaning" in text: flags.add("translation")
        text = re.sub(r"\s*←.*$", "", text)
        out.append({"face": F, "text": text.strip(), "flags": flags})
    return out
