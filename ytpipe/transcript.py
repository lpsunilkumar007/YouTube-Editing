"""Transcription and the cleaned-transcript format (shared by captions, chapters, metadata, thumbnails and Shorts;
transcribe ONCE per lecture).

words.json   : raw ASR (faster-whisper) {"segments": [{"start","end","text","words": [[s, e, w, p], ...]}]}
transcript.txt: the human/Claude-cleaned Hinglish transcript, one line per phrase, the Lesson 01 format:
    [MASTER hh:mm:ss.ss | FACE hh:mm:ss.ss | DESK hh:mm:ss.ss | EDIT hh:mm:ss.ss]  text
  markers kept from Lesson 01: '≈' reconstructed wording, '[unclear…]', '(meaning…)' = English rendering, not verbatim,
  '←' annotations, '—cut—' removed lines. Lines starting with '··' or '──' are notes (pauses / on-screen events)."""
import json, os, re

LINE = re.compile(r"^\[MASTER [^|]+\| FACE (\d+):(\d+):(\d+(?:\.\d+)?) \|[^\]]*\]\s+(.*)$")

def transcribe(cfg, audio_path, out_json):
    """faster-whisper with word timestamps + VAD (local; medium int8 fits 8 GB RAM). Cached: skipped if out_json exists."""
    if os.path.exists(out_json):
        return json.load(open(out_json, encoding="utf-8"))
    from faster_whisper import WhisperModel
    t = cfg["transcription"]
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
