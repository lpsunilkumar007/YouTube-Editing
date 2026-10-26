# Video editing workflow (every lecture)

The cases behind these steps, and what runs by default, are in [PRODUCTION_PLAYBOOK.md](PRODUCTION_PLAYBOOK.md).

`⛔` marks an approval checkpoint. Stop, show the result and wait for your explicit yes; then record it with `python -m ytpipe approve <gate>`. Approval for one step doesn't carry over to the next.

All commands take the form `python -m ytpipe <stage> --config lessons\<id>\video_project_config.json`. Module details are in [YOUTUBE_CONTENT_PIPELINE.md](YOUTUBE_CONTENT_PIPELINE.md).

| Step | What | Command | Output |
|---|---|---|---|
| 1 | You provide the two video paths and the topic, in `lessons\<id>\video_project_config.json` (template: [video_project_config.json](video_project_config.json)) | `init` | Lesson folders |
| 2 | Validate and inspect the recordings: HDR/Dolby Vision, rotation, fps, audio, clocks | `inspect` | `analysis\metadata.json` |
| 3 | Synchronise: metadata, then audio cross-correlation (start/middle/end + drift) when possible. OBS records no mic, so the usual source is **pen/word anchors** in `timelines\sync_anchors.json`: at least 5 (aim for 10+, from different parts of the lecture) spoken words paired with the start of the ink that writes them (dictated numbers, labels written while said). `ink --from/--to` lists the glyphs written in a desktop span and the words near it; check each pair on a desktop crop. The offset is the second-smallest desk−face, so ink never shows before its word; anchors more than 2 s apart stop the stage. A manual offset that disagrees with the anchors by >0.3 s also stops it. Pen-tap audio and hand motion are not reliable. QA's frame checks prove the render shows the planned frames, not that the offset is right. **If unsure: stop and ask** | `sync`, `ink` | `reports\synchronization_report.md` |
| 4 | Transcribe once, then correct the draft into Hinglish `transcript.txt` (glossary terms, `≈`/`[unclear]` markers); then analyse slides, counter, ink, pauses and face | `transcribe`, `analyze` | `transcripts\`, `analysis\` |
| 4b | Spoken cut/pause instructions and retakes become proposed cuts. Speech the recognizer lost (talking but no words) is re-heard in Hindi and English and listed, with instructions flagged; Claude adds the cuts and transcript lines ([PRODUCTION_PLAYBOOK.md](PRODUCTION_PLAYBOOK.md) C2/C3) | `retakes` | `timelines\content_cuts.json`, `reports\content_cuts.md` |
| 5 | Timeline proposal: keeps at measured pauses, A/B/C layouts, zoom candidates (clearance-checked), restart flags. Claude adds chips, graphics and chapter markers from the transcript. **⛔ `timeline`** | `timeline` | `timelines\timeline.json` |
| 6 | ~15 s review sample: presenter, a slide with the circle camera and chips, and a cut, rendered with the final settings (about 25 s). Pick other moments with `--at <final-video seconds>`. Re-run after each change. **⛔ `preview` / style** | `sample` (or `preview --segments …`) | `full_video\sample\sample.mp4`, `sample.json` |
| 7 | Full render. **⛔ `full_render`** must be given first. Includes sync QA (pen strokes and slide changes; it says so when nothing could be compared), joint, music level/placement, loudness and decode QA. `qa --final <video>` re-runs these on a finished video, read only | `render` | `full_video\<id>.mp4`, `timelines\edl.json`, `reports\qa_full_video.json` |
| 7b | **Fact check** (every video, before any publishing copy): the stage lists every claim-like line of the cleaned transcript; Claude verifies each against reliable sources (official docs, standard references) and records a verdict in `metadata\fact_check.json`. A wrong claim is fixed by a cut (`content_cuts.json`, then re-render) or a correction note. `metadata`, `blog` and `wp-publish` refuse to run until it passes | `factcheck` | `reports\fact_check_brief.md`, `reports\fact_check.md` |
| 8a | Caption listen-check page for every `≈` line (Claude publishes it; you mark each line or type the fix) | `listen` | `reports\listen_check.html` |
| 8 | Subtitles and publishing metadata. Claude first researches titles for this video (how YouTube ranks: satisfaction over clicks; the phrases viewers search), records it in `description_input.json` `research` (date, sources, search phrases), then writes the titles and description; `metadata` checks them against the research rules (searched phrase first, ≤ 60 chars, no lesson numbers or clickbait, 200+ word description, 5–15 tags, chapter rules) | `captions`, `metadata` | SRT, captions review, `metadata\*` |
| 8b | Blog post for your website / Medium. Claude writes `metadata\blog_input.json` from `content_brief.md` (only what the video says); the stage renders it and checks SEO (title 30–60 chars, description 120–160, keyword in title, slug, first paragraph and a heading, 800+ words). Add `video_url` after uploading and rerun | `blog` | `blog\<slug>.md`, `.html` (paste into Medium or a CMS), `SEO.txt`, cover image, `blog\screens\` slide stills |
| 8c | WordPress draft ([WORDPRESS_PUBLISHING.md](WORDPRESS_PUBLISHING.md)): dry run, review, **⛔ `blog_publish`** (approves the dry run's payload hash), then `--send` creates or updates the lesson's draft. You press Publish in WordPress | `wp-publish` (`--check-links`, `--send`), `wp-check` | `blog\wordpress\dry_run.md`, `outreach.md`, a draft on your site |
| 9 | Three thumbnail options. **⛔ `thumbnail`** (you choose) | `thumbnails` | `thumbnails\thumbnail_option_1..3.png` |
| 10 | Shorts/Reels candidates (report only), curated by Claude | `shorts` | `shorts\shorts_candidate_report.md` |
| 11 | **⛔ `shorts`**: you approve specific clips | `approve shorts --note "1,3"` | |
| 12 | Render the approved vertical clips | `shorts-render --clips 1,3` | `shorts\short_NN.mp4` |
| 13 | Short-form metadata for each approved clip (`metadata.short_meta`) | (Claude + validator) | `metadata\shorts\*.md` |
| 14 | Final QA and the publishing package; then go through [PUBLISHING_CHECKLIST.md](PUBLISHING_CHECKLIST.md) | `qa`, `package` | `publishing_package\INDEX.md` |

**Paid assets** (music, images, APIs) need **⛔ `paid_assets`** and a licence entry in `config\credits.json`.

**Restarting:** every stage can be rerun. Cached analysis is reused, and unchanged video segments are not re-rendered. `status` shows the checkpoints and approvals.

**Lesson 01** was made with the `_work\` scripts (see [LESSON01_REFERENCE_IMPLEMENTATION.md](LESSON01_REFERENCE_IMPLEMENTATION.md)). Its publishing material is in `lessons\lesson01\`, generated read-only by `ytpipe`.
