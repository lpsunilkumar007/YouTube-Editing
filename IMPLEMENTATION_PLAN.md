# Implementation plan: configuration-driven YouTube content production system

Status: **plan** (Phase 1 audit done 2026-10-21; no working code changed, nothing rendered).

## 1. Audit results

### Works today (proven on Lesson 01, in `_work\`)
- **Picture:** layouts A, B and C; the circle camera; the libplacebo/Dolby Vision conversion; the slide card; chips and counter badge.
- **Graphics:** zoom with clearance search; HyperFrames elements (title, topic, term, ipo, rings, end).
- **Audio:** narration rebuilt on video frames with room-tone crossfades; −16 LUFS chain; music sections with ducking; synthesised SFX.
- **Export:** segment render with decode check and stream-copy join.
- **QC:** transition QC (EDL and file modes), per-segment sync, pen-frame matching, loudness.
- **Transcript:** a faster-whisper transcript with word timings, hand-cleaned into Hinglish.

### Hardcoded Lesson 01 assumptions (from the scan of `_work\*.py`)

| Assumption | Scripts |
|---|---|
| Source paths `../raw/face_camera.MOV`, `desktop_recording.mkv` | 23 scripts |
| Offset `L = 100.0` / `F + 100` | 18 scripts |
| Shot, keep and slide lists (`SHOTS`, `KEEP`, `SLIDES`, `SEGMENTS`, `FULL_V8`, `BAR_TL`, `ELEMENTS`) | 9 scripts, incl. `lecture_plan_v9.py`, `render_preview_v6.py` |
| Slide area `1890`, counter `PATCH` (1641/1705/1713) | 14 scripts |
| Diagram coordinates (`rings`), chip texts, word times | `make_overlays_v9.py`, `lecture_plan_v9.py` |
| Output paths `../output` | 19 scripts |

**Not "reusable logic" today:** slide-area detection, counter detection, slide-change detection, offset estimation and shot/layout proposal were all done by hand or with one-off scripts for Lesson 01.

### Documented but not implemented
- SRT captions
- Code highlighting
- Config-driven scripts
- Slide-area and counter auto-detection
- Per-segment desktop frame-timing check before render

### Not built at all yet
- Thumbnails
- Titles, description, tags, hashtags, pinned comment
- Shorts/Reels candidates, vertical render and their metadata
- Publishing package

### Machine constraints
- i7-8650U, **8 GB RAM**, Intel UHD 620 (Vulkan works for libplacebo), no NVIDIA GPU.
- faster-whisper **large-v3 does not fit**. Medium int8 on the CPU is the local ceiling (about 1–1.5× real time).

## 2. Architecture

A new package `ytpipe\` at the project root (shared by all lectures). Lesson 01's `_work\` stays untouched as the **proven fallback**.

```
ytpipe\
  config.py       load/merge/validate config (defaults + overrides), JSON Schema; resolve lesson folders
  state.py        checkpoints: lessons\<id>\state.json (stage done, inputs hash) -> restartable, idempotent
  sources.py      ffprobe -> metadata.json (streams, HDR/DV, rotation, fps, audio silence, timestamps)
  sync.py         offset from metadata + audio xcorr (if both have audio) + event anchors; drift; report
  transcribe.py   faster-whisper (word timings, VAD) -> transcripts\words.json  (once; cached)
  analyze.py      slide area, slide changes, burned-in counter, ink events, face track, pauses (cached .npz/.json)
  timeline.py     proposal: keep segments at measured pauses, layouts A/B/C, zoom windows, chips/cards -> timeline.json
  render.py       layouts A/B/C as functions of geometry (from config + analysis); segment render; join
  graphics.py     HyperFrames element generation/render (kinds from make_overlays_v9, parameterised)
  audio.py        narration on frames, crossfades, voice chain, music sections, ducking, SFX
  captions.py     words -> sentences -> caption cues -> EDL mapping -> SRT (+ optional styled ASS); glossary
  thumbnails.py   frame selection from the original face video + 3 layouts (Pillow/SVG) -> 1280x720
  metadata.py     chapters from the final EDL, description/tags/hashtags/pinned comment assembly, credits
  shorts.py       candidate finder (transcript), vertical 1080x1920 compositions, short-form metadata
  qa.py           full-video, caption, thumbnail, shorts and metadata checks -> reports\qa_*.json/md
  __main__.py     python -m ytpipe <stage> --lesson lessons\lessonNN [--dry-run]
config\defaults.json, config\schema.json, config\glossary.json (technical terms)
tests\            pytest on synthetic fixtures (ffmpeg testsrc/sine clips, fake transcripts); no lecture footage
```

**Per-lecture folder** (Phase 12):
```
lessons\<id>\
  raw/  analysis/  transcripts/  timelines/  assets/  thumbnails/  full_video/  shorts/  metadata/  reports/
  state.json
```

**How the hardcoded values become logic, not config:**

| Hardcoded today | Becomes |
|---|---|
| Offset L | `sync.py` estimate with uncertainty, checked at the start, middle and end. The run stops for your input if the uncertainty is over 0.5 s. |
| Slide area | Black-bar detection on sampled desktop frames |
| Counter position | Small region that changes exactly at slide changes and is static in between; none if not found |
| Slide timeline | Desktop frame-difference events, confirmed by the counter when present |
| Shots, chips, cards | `timeline.py` proposal from the transcript, slide changes, ink and pauses; you approve it (no fixed counts) |
| Geometry | Derived from the output resolution, slide area and circle size; clearance computed per lecture from content masks |

**Timing issue at 7:53 / 10:15 / 12:13 (Lesson 01):** `qa.py` gets a pre-render desktop frame check per slide segment (the `frame_match_v9` method). It flags any segment more than 1 frame off before the full render.

## 3. Dependencies

| Need | Status | Plan |
|---|---|---|
| ffmpeg 9.0.2 (libplacebo, Vulkan), Node 22, HyperFrames 0.8.181, Python 3.12, numpy/scipy/OpenCV 4.14/Pillow, faster-whisper 1.2.1, PyYAML, pytest, onnxruntime | installed | reuse |
| `jsonschema` | missing | pip, MIT, small: config validation |
| `srt` | missing | not needed (SRT writer is about 20 lines) |
| Face cut-out for thumbnails (`rembg` + u2net model, about 170 MB, MIT) | missing | **decision D2** |
| Larger or cloud transcription | n/a | **decision D3** |
| Image-generation or paid APIs | none | **not used** (local compositing only) |

## 4. Stages (each tested before the next)

1. **Foundation:** package, config + schema + defaults, lesson folder init, `state.py`, `sources.py` (planned as the inspect module), CLI (`__main__.py`); tests on synthetic clips.
2. **Captions:** `captions.py` + glossary; tests on fixtures (and Lesson 01 transcript data if D1 = yes).
3. **Metadata:** chapters from the EDL, description, tags, hashtags, pinned comment, credits; titles drafted by Claude from a generated content brief.
4. **Thumbnails:** frame selection + 3 layouts + QA (resolution, safe margins, text size at 1/4 scale).
5. **Sync and analysis:** generalised sync, slide area, slide changes, counter, ink, face track; tests on synthetic desktop clips with a known offset.
6. **Render:** layouts A, B and C as functions; filter-graph builders tested by dry run, then tiny renders of synthetic clips. Audio module.
7. **Shorts:** candidate finder + vertical compositions + metadata; tested on synthetic clips only (no Lesson 01 extraction without approval).
8. **QA + docs:** QA suite and the documentation updates (Phase 14).

## 5. Decisions needed (asked in the session)
- **D1:** may Lesson 01 be used **read-only** as a test fixture for captions, metadata and thumbnails? Outputs would go to a new `lessons\lesson01\` folder; the final MP4 and raw files would not be touched.
- **D2:** thumbnail face treatment: install `rembg` for a clean cut-out, or no cut-out (a framed photo)?
- **D3:** transcription engine: local faster-whisper medium (free, this laptop), or a cloud API (needs a key and is paid)?
- **D4:** channel details for the description (name, links): placeholders until you supply them.

## 6. Progress (2026-10-21: all stages implemented)

- **Implemented** (`ytpipe\`): config, state, media, sources, sync, transcript, analyze, timeline, layout, render, graphics, audio, pipeline, captions, metadata, thumbnails, shorts, qa, publish, CLI (`python -m ytpipe`), legacy_lesson01.
- **Tests:** 20 pass (`tests\last_run.txt`, 6 min 43 s), on synthetic fixtures plus read-only Lesson 01 data.
  - Ran after the last test run, with no automated test yet: the `--final` package option, the QA-count fix in the index, and the stage-checkpoint recording.
- **Produced for Lesson 01** (read-only, in `lessons\lesson01\`):
  - SRT (221 cues, QA pass)
  - chapters, description, titles, tags, hashtags and pinned comment
  - 3 thumbnails (QA pass)
  - Shorts candidate report (5 clips; nothing rendered)
  - publishing package
- **Waiting for you:**
  - choose a thumbnail
  - choose Shorts to render
  - supply your channel name and the playlist and next-lesson links
  - review the caption listen-check lines
- **Docs:** CLAUDE.md is concise and links to everything; the 5 new documents and LESSON01_REFERENCE_IMPLEMENTATION.md are written; `_work\validate_docs.py` passes.
- **Lesson 01 integrity:** re-checked at the end (`_work\integrity_after_upgrade.txt`).
