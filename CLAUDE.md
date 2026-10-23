# YouTube-Editing: instructions for Claude Code

This project produces technical teaching videos (Hinglish) and their publishing material from two recordings per lecture: an iPhone face camera and an OBS desktop recording with live red-pen annotation.

## Hard rules
- **Raw files:**
  > Never modify or overwrite anything in `raw\`. Write new outputs beside it.

  This also applies to every `lessons\<id>\raw\`.
- **Lesson 01 is finished.** Never modify, re-render or delete `output\lesson01_final.mp4`, its raw files or `_work\` (the proven fallback). Fingerprints: `_work\integrity_before_docs.txt`. Lesson 01 may be **read** as a test case.
- **Narration drives the edit.**
  - No silent cards, decorative pauses or graphics that delay speech.
  - Cut only at measured pauses.
  - Never cut sentences.
  - Never show a step before it is spoken.
- **Camera layout by format (permanent):**
  - **Long-form videos:** the approved circular lower-right picture-in-picture during desktop explanations.
  - **Short-form videos (Shorts/Reels):** rectangular split-screen, full-frame presenter or desktop-focused layouts.
  - **Never automatically reuse the long-form circular overlay for vertical videos.** See [SHORTS_EDITING_STYLE.md](SHORTS_EDITING_STYLE.md).
- **Sources for every output:** the original recordings (approved HDR→SDR). Rendered videos may be used only for audio or timing reference when the originals are available.
- **Approval gates are yours:** timeline, preview, full render, thumbnail, shorts, paid assets. Run `python -m ytpipe approve <gate>` only after you've said yes.
- **Nothing external without your go-ahead:** no uploads, purchases, paid APIs, or downloads of copyrighted material.
- **Licences:** verify every asset's licence and record it in `config\credits.json`. Never claim an asset is Content-ID-safe.
- **Don't guess:** if sync, transcript wording or licensing is uncertain, ask. Mark unverified things as such.

## How to work
- **New lecture:** follow [VIDEO_EDITING_WORKFLOW.md](VIDEO_EDITING_WORKFLOW.md) using `python -m ytpipe <stage> --config lessons\<id>\video_project_config.json` ([REUSABLE_SYSTEM_README.md](REUSABLE_SYSTEM_README.md)).
- **System and modules:** [YOUTUBE_CONTENT_PIPELINE.md](YOUTUBE_CONTENT_PIPELINE.md) · status and gaps: [COMPONENTS.md](COMPONENTS.md).
- **Style:**
  - video: [TEACHING_VIDEO_STYLE.md](TEACHING_VIDEO_STYLE.md)
  - thumbnails: [THUMBNAIL_STYLE.md](THUMBNAIL_STYLE.md)
  - Shorts/Reels: [SHORTS_EDITING_STYLE.md](SHORTS_EDITING_STYLE.md)
  - metadata: [YOUTUBE_METADATA_GUIDE.md](YOUTUBE_METADATA_GUIDE.md)
- **Before delivery:** [PUBLISHING_CHECKLIST.md](PUBLISHING_CHECKLIST.md).
- **How Lesson 01 was made** (sync evidence, colour pipeline, HyperFrames, audio, QC): [LESSON01_REFERENCE_IMPLEMENTATION.md](LESSON01_REFERENCE_IMPLEMENTATION.md).

## Efficiency
- **Reuse cached results:** transcribe once; reuse `analysis\`, `transcripts\` and `timelines\` across all outputs.
- **Use scripts for deterministic work.** Claude writes only the text (transcript corrections, chips, titles, descriptions, thumbnail text, Shorts curation), from the generated content brief.
- **Render small first:** test-render a few segments before a full render; long renders run in the background; unchanged segments are reused.
- **Output:** print summaries, not logs.
- **Records:** keep decisions in lesson files and reports.

## Machine
- **This copy is for macOS** (copied from the Windows project on 2026-10-22). Setup, and the Windows-specific pieces still to port (slide OCR, fonts, libplacebo/Vulkan colour, paths), are in [MAC_SETUP.md](MAC_SETUP.md). Check those before trusting any render.
- **Lesson 01 is not in this copy.** The rule above protects the Windows original.
- **Windows original, for reference:** Windows 11, i7-8650U, 8 GB RAM, Intel UHD 620 (Vulkan for libplacebo); ffmpeg 9 (libplacebo), Node 22, HyperFrames 0.8.181 in `_work\hf`, Python 3.12 (`requirements.txt`).
