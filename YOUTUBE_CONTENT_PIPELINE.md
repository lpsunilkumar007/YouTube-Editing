# YouTube content pipeline (`ytpipe`)

This is a configuration-driven system. You give it three inputs: a face-camera video, a desktop recording and a lecture topic.

**It produces:**
- an edited teaching video
- Hinglish subtitles
- three thumbnail options
- YouTube titles, description, chapters, tags, hashtags and pinned comment
- a Shorts/Reels candidate report, then vertical clips and their metadata once you approve them
- a publishing package

**Rules:** the style comes from [TEACHING_VIDEO_STYLE.md](TEACHING_VIDEO_STYLE.md), the steps from [VIDEO_EDITING_WORKFLOW.md](VIDEO_EDITING_WORKFLOW.md), and the delivery checks from [PUBLISHING_CHECKLIST.md](PUBLISHING_CHECKLIST.md).

**Lesson 01's original scripts in `_work\`:** kept unchanged as the proven fallback. `ytpipe` is a generic port of them (see [COMPONENTS.md](COMPONENTS.md)).

## Data flow

```
config (3 inputs + overrides) ─▶ inspect ─▶ sync ─▶ transcribe ─▶ analyze ─▶ timeline (proposal) ──⛔ approve timeline
      ─▶ preview ──⛔ approve full_render ─▶ render ─▶ QA ─▶ captions ─▶ metadata ─▶ thumbnails ──⛔ approve thumbnail
      ─▶ shorts (report) ──⛔ approve shorts ─▶ shorts-render ─▶ QA ─▶ package
```

Every stage reads cached results from earlier stages:
- `analysis\metadata.json`, `sync.json`, `analysis.json`
- `speech_env.npy`, `face_track.npy`, `content_masks.npz`
- `transcripts\words.json`, `transcript.txt`
- `timelines\timeline.json`, `edl.json`, `geometry.json`

**The lecture is transcribed once.** Captions, chapters, the content brief, thumbnails and Shorts all reuse that transcript.

## Modules (`ytpipe\`)

| Module | Job | Replaces this Lesson 01 hardcoding |
|---|---|---|
| `config.py` + `config\defaults.json`, `schema.json` | Merge defaults with the lecture config; reject unknown keys; check required fields and files; resolve lesson folders | Fixed paths and filenames |
| `state.py` | Checkpoints in `lessons\<id>\state.json`; approval gates; fingerprints | n/a |
| `media.py` | ffprobe/ffmpeg wrappers (read-only on sources) | n/a |
| `sources.py` | Source facts; picks the colour pipeline (HDR/Dolby Vision → libplacebo, SDR → scale) | Assumed iPhone DV/HLG |
| `sync.py` | Offset from metadata, plus audio cross-correlation (start/middle/end) and drift when both files have audio. Returns "needs your input" otherwise | `L = 100.0` |
| `transcript.py` | faster-whisper words (once), a draft for correction, the cleaned-transcript format | Fixed transcript timestamps |
| `analyze.py` | Slide area, slide changes, counter box, ink events, content masks, speech map, face track | Slide area 1890, counter coordinates, `SLIDES` |
| `timeline.py` | Proposal: keeps at measured pauses, dead-air trims, A/B layouts, zoom candidates, restart flags | Hand-made `SHOTS` / `KEEP` / `SEGMENTS` |
| `layout.py` | Card/camera/bar geometry from the slide area. The card is shrunk only if content would sit under the circle. Counter clone strip verified empty. Static layers | Card 1664×950, circle (1528, 688), `PATCH` |
| `render.py` | Layouts A/B/C (the v6 filter graph), fixed crop per take, zoom ease, decode-checked segments, stream-copy join | `render_preview_v6.py` constants |
| `graphics.py` | Chip-bar MOVs, counter badges, HyperFrames elements: `title`, `topic`, `term`, `ipo`/`steps`, `rings`, `end`, `code`. Diagram coordinates are parameters | Slide-3 ring coordinates |
| `audio.py` | Narration on the video frames, room-tone crossfades, voice chain (−16 LUFS stereo), music sections with ducking, SFX | `mix_audio_v8.py` |
| `pipeline.py` | Preview/full render from an approved timeline; segments reused when their inputs are unchanged; never overwrites finals | `render_full_v9.py` |
| `captions.py` | Transcript → cues (sentence/clause split, measured speech timing, final-edit mapping) → SRT/ASS. Glossary spelling. Review list. Manual-correction file | (missing in Lesson 01) |
| `metadata.py` | Chapters from the final EDL (YouTube rules), content brief, description/tags/hashtags/pinned comment/titles, validation, short-form metadata | (missing) |
| `thumbnails.py` | Real-face frame selection, rembg head-and-shoulders cut-out (pixels unchanged), three layouts, QA | (missing) |
| `shorts.py` | Candidate finder and report, layout-following 1080×1920 renderer with captions in safe areas | (missing) |
| `qa.py` | Full video (decode, duration, loudness, joints on the narration stem, **desktop frame timing**), captions, Shorts | Lesson 01 verify scripts |
| `publish.py` | `publishing_package\` with an `INDEX.md` listing approvals and the QA checks that actually ran | n/a |
| `legacy_lesson01.py` | Imports the finished Lesson 01 edit (read-only) as `edl.json`, so captions and metadata match its final MP4 | n/a |

## Commands

```
python -m ytpipe <stage> --config lessons\lessonNN\video_project_config.json
```

**Stages:**
- `init`, `inspect`, `sync`, `transcribe`, `analyze`, `timeline`
- `preview --segments 0,3`, `render`
- `captions`, `metadata`, `thumbnails`
- `shorts`, `shorts-render --clips 1,3`
- `qa`, `package`
- `approve <gate>`, `status`

**Gates:** `timeline`, `preview`, `full_render`, `thumbnail`, `shorts`, `paid_assets`. Only you set them, by running `approve`.

## Where Claude writes text

The deterministic stages produce data. Claude then writes the human-facing text **from that data only**, and it is validated:

| Text | Written from | Saved in |
|---|---|---|
| Corrected transcript | `transcript_draft.txt` + glossary | `transcripts\transcript.txt` |
| Chips and graphics | `timeline.json` (`chips`, `elements`) | `timelines\timeline.json` |
| Titles, description, tags | `metadata\content_brief.md` | `metadata\description_input.json` |
| Thumbnail text | the content brief | `thumbnails\thumbnail_input.json` |
| Shorts curation | the candidate report | `shorts\candidates_curated.json` |

## Tests

`python -m pytest tests` runs 20 tests on synthetic fixtures (`tests\make_fixtures.py`): a known 7.4 s offset, slide changes, ink, a counter, a black bar and speech pauses. Two tests also read Lesson 01 data read-only (geometry equivalence, caption QA). See REUSABLE_SYSTEM_README.md §2 for what is and isn't tested.
