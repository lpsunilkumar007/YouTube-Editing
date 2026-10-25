# Reusable components

## A. `ytpipe` (current system, configuration-driven): status as of 2026-10-21

"Tested" means checked by `python -m pytest tests` on synthetic fixtures, or on Lesson 01 data read-only. "Not run on a real new lecture" means exactly that: it has not been used end to end on new footage yet.

| # | Component | Module | Status |
|---|---|---|---|
| 1 | Full-screen face scene (A) | `render.segment` | Tested (fixtures) |
| 2 | Desktop + circular camera (B) | `render.segment`, `layout.static_layers` | Tested (fixtures); geometry reproduces Lesson 01's approved layout exactly |
| 3 | Zoomed desktop (C) | `render.desk_filter` | Tested (fixtures); zoom windows are proposed only as candidates |
| 4 | Smooth zoom animation | `render.ease_expr` (0.6 s cubic) | Tested (fixtures) |
| 5 | Code highlighting | `graphics` kind `code` | **Scaffold**: renders on fixtures, never used in a lecture |
| 6 | Flowchart / diagram animation | kinds `rings` (parameterised circles + arrows), `ipo`/`steps` | Tested (fixtures); `ipo` approved in Lesson 01 |
| 7 | Concept cards | kind `term` | Tested; approved in Lesson 01 |
| 8 | Topic heading animation | kind `topic` | Tested; approved in Lesson 01 |
| 9 | Captions | `captions` (SRT + optional ASS) | **Produced for Lesson 01** (221 cues, QA pass) |
| 10 | Chapter transition | topic label + music swell (no cards) | Approved in Lesson 01; the music sections are configured in the timeline |
| 11 | Lecture intro | kind `title` over the opening shot | Approved in Lesson 01 |
| 12 | Lecture outro | kind `end` + outro music | Approved in Lesson 01 |
| 13 | Music and audio mixing | `audio` | Tested (fixtures): sample-exact narration placement, −16 LUFS |
| 14 | Final video export | `pipeline.build` (gates, segment reuse, never overwrites) | Tested end to end (fixtures). **Not run on a real new lecture** |
| 15 | Automated QA | `qa` (full video, joints, **sync at pen strokes and slide changes**, music level/placement, captions, Shorts; `qa --final` re-checks a finished video), `thumbnails.qa`, `metadata` validation | Tested (fixtures + Lesson 01 captions) |
| 16 | Sync | `sync` (metadata + audio xcorr + drift; stops when unsure) | Tested (fixtures: offset within 10 ms) |
| 17 | Analysis | `analyze` (slide area, changes, counter, ink, masks, pauses, face) | Tested against the fixture ground truth |
| 18 | Timeline proposal | `timeline` | Tested on fixtures; **its layout heuristics need review on a real lecture** |
| 19 | Thumbnails | `thumbnails` (rembg cut-out, 3 layouts, QA) | **Produced for Lesson 01** (3 options, QA pass) |
| 20 | YouTube metadata | `metadata` | **Produced for Lesson 01** (placeholders remain for your links) |
| 21 | Shorts/Reels | `shorts` (candidates, report); **`shorts_v3`** (render: B full-frame presenter / A rectangular split / C desktop focus, automatic layout plan, term-highlighted captions; **no circular overlay**) | v3 validated on Lesson 01: `output\shorts_layout_preview.mp4` (picture 0 frames vs the original camera, audio within 0.3 ms). `shorts_v2` (circle) and the v1 reframing are **retired** for vertical video |
| 22 | Publishing package | `publish` | Built for Lesson 01 (no video copied) |
| 23 | Blog article | `blog` (Markdown, HTML, SEO checks, slide stills, Shorts, references, internal links) | **Produced for Lesson 02** |
| 24 | WordPress draft | `wordpress` (`wp-publish` dry run / `--send` after `blog_publish`, `wp-check`): drafts only, Keychain credentials | Tested against a fake WordPress; **no real site connected yet** |

### Gaps that remain
1. **Timeline layouts are heuristic:** a face shot when there is no desktop activity, a slide shot otherwise. Expect to adjust the proposal at the timeline gate. Chips, graphics and chapter markers are written by Claude from the transcript.
2. **Counter-badge numbers** count slides in order of appearance; they are not read from the slide (no OCR). Check them at the timeline gate.
3. **Shorts:** no circle any more (v3). Full-frame presenter shots are enlarged 1.78× (unavoidable for 9:16).
4. **Transcription quality:** limited by the local medium model on 8 GB RAM. Hinglish needs manual correction (the draft → `transcript.txt` step).
5. **Sync without shared audio:** needs your confirmation via `sync.manual_offset_s`. There is no automatic visual-anchor solver yet; it lists the evidence instead.
6. **The `code` kind is a scaffold:** line boxes must be given by hand. No OCR of code.

---

## B. Lesson 01 implementation (`_work\`, proven fallback, unchanged)

These are the components used to make Lesson 01. All files are in `_work\`; nothing has been moved or rewritten.

**Status key:**
- **Verified**: used in the approved final lecture and checked by QC.
- **Partial**: works, but only in a lecture-specific form.
- **Spec only**: not implemented; a specification is given.

**Before reusing a script:** most scripts hard-code Lesson 01 facts. Set these first:
- relative paths `../raw/face_camera.MOV` and `../raw/desktop_recording.mkv`
- the offset `L = 100.0`
- the `SHOTS` / `SEGMENTS` lists and the `SLIDES` timeline
- the counter `PATCH` coordinates
- the slide area `SW = 1890`

Wrapping them behind `video_project_config.json` is the main refactor still to do (see "Gaps" below). It was deliberately not done now, to avoid touching working code without a test render.

| # | Component | Status | Files | Lesson-specific inputs to change |
|---|---|---|---|---|
| 1 | Full-screen face scene (A) | Verified | `render_full_v9.render_seg()` (A branch), `PL` in `render_preview_v6.py` | source path |
| 2 | Desktop + circular camera (B) | Verified | `render_preview_v6.render()` (B branch) + `render_full_v9.py` wrapper; layers from `make_graphics_v2.py --v3` (`v3_bg.png`, `v2_card_mask.png`, `v2_ring_card.png`, `v3_cam_mask.png`, `v3_ring_cam.png`, `v3_cam_shadow.png`) | slide area `SW`, counter `PATCH`, `SLIDES`, `L` |
| 3 | Zoomed desktop (C) | Verified (slide 5) | same as 2, with a zoom tuple; `FOCUS` dim from `make_graphics_v6.focus_mask()` | window per shot (from 4's search) |
| 4 | Smooth zoom animation and clearance | Verified | `desk_chain()` + `EASE = 0.6` in `render_preview_v2.py`; `zoom_check_full.py`, `zoom_search_full.py` (use `slide_content.npz`) | zoom list, content masks per lecture |
| 5 | Code highlighting | **Spec only** | none (Lesson 01 had no code) | Spec: a gutter or below-line highlight bar drawn as a HyperFrames element at the line's position, timed to the spoken line, ≤ 2 lines lit at once, never covering the code; zoom on the code block only if it passes the clearance rules |
| 6 | Flowchart / sequence animation | Partial | `make_overlays_v9.py` kinds `rings` (diagram rings and progressive arrows; coordinates are slide-3 specific) and `ipo` (stepwise card) | ring centres/arrows per diagram; step times |
| 7 | Concept cards | Verified | `make_overlays_v9.py` kind `term`; `hf/v7/style.css` `.term` | text and start/duration in `ELEMENTS` |
| 8 | Topic heading animation | Verified | kind `topic` (layout A, top left) | text and time; face safe area |
| 9 | Caption styling | **Spec only** | none | see CLAUDE.md §11 and TEACHING_VIDEO_STYLE.md §13 |
| 10 | Chapter transition | Verified (no standalone card) | topic label + music swell (`CHAPTER_JOINTS` in `lecture_plan_v9.py`; `render_full_v9.build_audio`) | chapter joints |
| — | *(Superseded)* full-screen chapter card | Rejected in v8 | `hf/v7/chapter.html` | do not use mid-lesson |
| 11 | Lecture intro | Verified | kind `title` over the opening face shot + `sfx_intro.wav` + intro music | lesson number, title |
| — | *(Superseded)* separate 4 s intro card | Replaced in v9 | `hf/v7/intro.html` | kept for reference only |
| 12 | Lecture outro | Verified | kind `end` + outro music (track ending) | next-lesson title |
| 13 | Music and audio mixing | Verified | `mix_audio_v8.py` (narration on video frames, room-tone crossfades, voice chain, −16 LUFS), `mix_audio_v7.py` (`level_curve`, `duck`, `CHAIN`), `render_full_v9.build_audio` (sections, SFX), `make_sfx_v7.py`, `music_metrics.py` | music sections, SFX list |
| 14 | Final video export | Verified | `render_full_v9.py` (segments → decode check → stream-copy join → audio mux); x264 settings `X264` in `render_preview_v6.py` | `lecture_plan_v9.py` content |
| 15 | Automated quality checks | Verified | see the table below | joint and segment lists |

## Quality-check tools

| Tool | Checks | Mode |
|---|---|---|
| `transition_qc.py` | Words cut, tight edges, cut in sound, pause length, low gaps, loudness step, repeats, silent cards, dead air | EDL mode (`v7 v8 full full_v8`) or `--file <stem> --cuts t1,t2` |
| `env_probe.py` | 10 ms speech map around source times (to place cuts) | `python env_probe.py 615.0:617.8` |
| `interval_review_v8.py` | Low-audio intervals vs source: which take, words, pen activity | clip-specific |
| `verify_full_v9.py` | Decode, sound vs picture per segment, joints, pen strokes, loudness, music levels | final file |
| `frame_match_v9.py` | Which raw desktop frame the final shows at pen-moving moments | final file |
| `pen_sync_v8.py` | Ink-growth correlation clip vs raw | clip |
| `verify_flicker.py` | Camera jitter, wall shimmer, slide stability | preview |
| `verify_face_v3.py`, `compare_face_versions.py` | Face colour fidelity vs lossless reference | preview |
| `verify_sync_v2.py`, `verify_sync_v2_focus.py` | Planned desktop frame best match (preview) | preview |

## Analysis and data components (cached per lecture)

| File | Produced by | Content |
|---|---|---|
| `face48.wav` | ffmpeg extraction | Face audio, 48 kHz; channel 0 = narration |
| `part1.json`, `part2.json` | `transcribe.py` / `transcribe2.py` (faster-whisper) | Segments and word timings (word ends are padded: don't use them as cut points) |
| `transcript.txt` | `build_transcript.py` | Hand-cleaned Hinglish transcript with master/face/desk/edit times |
| `face_track.npy` | `face_track.py` | Face centre and size every 0.5 s |
| `slide_content.npz` | slide-content analysis | Per-slide content masks (worst case) for clearance checks |
| `counter_keys.npy` | counter clustering (v4) | Slide timeline from the burned-in counter |
| `ink_onsets.npy`, `ink_events.py` | ink detection | Pen-stroke onsets |
| `editing_timeline.md`, `build_timeline.py` | timeline build | Shot table (Lesson 01) |
| `full_edl_v8.py`, `lecture_plan_v9.py` | hand-made, QC'd | Final keep list, segments, chip timeline, elements, music |

## HyperFrames project

| Path | Purpose |
|---|---|
| `_work\hf\node_modules\hyperframes` | v0.8.181 install (`npm install hyperframes`) |
| `_work\hf\v7\style.css` | Shared styles (palette, `.term`, `.node`, `.label`) |
| `_work\hf\v7\el_*.html` | Generated Lesson 01 elements (`make_overlays_v9.py`) |
| `_work\hf\v7\out9\*.mov` | Rendered element overlays (ProRes 4444 alpha) |
| `_work\hf\v7\intro.html`, `chapter.html`, `ov_s3.html`, `ov_s9*.html` | v7/v8 previews (superseded or folded into the v9 kinds) |

## Gaps (needed before the system is fully "three inputs only")

1. **Parameterise the scripts** (paths, `L`, slide area, counter `PATCH`, `SLIDES`) from the resolved config. Today they are module constants.
2. **Captions:** an SRT generator (spec in CLAUDE.md §11).
3. **Code highlighting** element (spec above).
4. **Generic `rings`:** take diagram coordinates as parameters instead of the slide-3 constants.
5. **Automatic detection:** detect the slide area and the burned-in counter position for new recordings (Lesson 01 values were measured by hand).
6. **Desktop frame-timing check:** run per segment before the full render (CLAUDE.md §4, known issue).
7. **Folder layout:** the scripts assume `_work\` next to `raw\` and `output\` (relative `../raw`, `../output`). Re-organising (README §5) needs those paths updated first.
