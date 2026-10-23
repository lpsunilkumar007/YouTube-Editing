# Video editing workflow (every lecture)

`⛔` marks an approval checkpoint. Stop, show the result and wait for your explicit yes; then record it with `python -m ytpipe approve <gate>`. Approval for one step doesn't carry over to the next.

All commands take the form `python -m ytpipe <stage> --config lessons\<id>\video_project_config.json`. Module details are in [YOUTUBE_CONTENT_PIPELINE.md](YOUTUBE_CONTENT_PIPELINE.md).

| Step | What | Command | Output |
|---|---|---|---|
| 1 | You provide the two video paths and the topic, in `lessons\<id>\video_project_config.json` (template: [video_project_config.json](video_project_config.json)) | `init` | Lesson folders |
| 2 | Validate and inspect the recordings: HDR/Dolby Vision, rotation, fps, audio, clocks | `inspect` | `analysis\metadata.json` |
| 3 | Synchronise: metadata, then audio cross-correlation (start/middle/end + drift) when possible. **If unsure: stop and ask** for confirmation (set `sync.manual_offset_s`) | `sync` | `reports\synchronization_report.md` |
| 4 | Transcribe once, then correct the draft into Hinglish `transcript.txt` (glossary terms, `≈`/`[unclear]` markers); then analyse slides, counter, ink, pauses and face | `transcribe`, `analyze` | `transcripts\`, `analysis\` |
| 5 | Timeline proposal: keeps at measured pauses, A/B/C layouts, zoom candidates (clearance-checked), restart flags. Claude adds chips, graphics and chapter markers from the transcript. **⛔ `timeline`** | `timeline` | `timelines\timeline.json` |
| 6 | Short preview of representative segments. **⛔ `preview` / style** | `preview --segments …` | `full_video\work\seg_*.mkv` |
| 7 | Full render. **⛔ `full_render`** must be given first. Includes desktop frame-timing, joint, loudness and decode QA | `render` | `full_video\<id>.mp4`, `timelines\edl.json`, `reports\qa_full_video.json` |
| 8 | Subtitles and publishing metadata. Claude writes `description_input.json` from `content_brief.md` | `captions`, `metadata` | SRT, captions review, `metadata\*` |
| 9 | Three thumbnail options. **⛔ `thumbnail`** (you choose) | `thumbnails` | `thumbnails\thumbnail_option_1..3.png` |
| 10 | Shorts/Reels candidates (report only), curated by Claude | `shorts` | `shorts\shorts_candidate_report.md` |
| 11 | **⛔ `shorts`**: you approve specific clips | `approve shorts --note "1,3"` | |
| 12 | Render the approved vertical clips | `shorts-render --clips 1,3` | `shorts\short_NN.mp4` |
| 13 | Short-form metadata for each approved clip (`metadata.short_meta`) | (Claude + validator) | `metadata\shorts\*.md` |
| 14 | Final QA and the publishing package; then go through [PUBLISHING_CHECKLIST.md](PUBLISHING_CHECKLIST.md) | `qa`, `package` | `publishing_package\INDEX.md` |

**Paid assets** (music, images, APIs) need **⛔ `paid_assets`** and a licence entry in `config\credits.json`.

**Restarting:** every stage can be rerun. Cached analysis is reused, and unchanged video segments are not re-rendered. `status` shows the checkpoints and approvals.

**Lesson 01** was made with the `_work\` scripts (see [LESSON01_REFERENCE_IMPLEMENTATION.md](LESSON01_REFERENCE_IMPLEMENTATION.md)). Its publishing material is in `lessons\lesson01\`, generated read-only by `ytpipe`.
