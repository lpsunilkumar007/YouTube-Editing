# Reusable YouTube content production system: README

You give it three inputs: your face-camera video, your desktop recording and the lecture topic. It produces an edited teaching video, Hinglish subtitles, three thumbnail options, the YouTube title/description/chapters/tags, and approved Shorts/Reels with their metadata. Nothing is published automatically.

| Document | For |
|---|---|
| [CLAUDE.md](CLAUDE.md) | Hard rules and where everything is (Claude reads this first) |
| [VIDEO_EDITING_WORKFLOW.md](VIDEO_EDITING_WORKFLOW.md) | The 14 steps and the ⛔ approval gates |
| [YOUTUBE_CONTENT_PIPELINE.md](YOUTUBE_CONTENT_PIPELINE.md) | Architecture, modules, data flow, commands |
| [COMPONENTS.md](COMPONENTS.md) | What is tested, what is a scaffold, remaining gaps |
| [TEACHING_VIDEO_STYLE.md](TEACHING_VIDEO_STYLE.md), [THUMBNAIL_STYLE.md](THUMBNAIL_STYLE.md), [SHORTS_EDITING_STYLE.md](SHORTS_EDITING_STYLE.md), [YOUTUBE_METADATA_GUIDE.md](YOUTUBE_METADATA_GUIDE.md) | The approved style rules |
| [PUBLISHING_CHECKLIST.md](PUBLISHING_CHECKLIST.md) | Before you upload |
| [LESSON01_REFERENCE_IMPLEMENTATION.md](LESSON01_REFERENCE_IMPLEMENTATION.md) | How Lesson 01 was actually made |
| [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) | The upgrade plan, audit and progress |

## 1. Start the next lecture

1. Make the folder `lessons\lesson02\raw\` and copy both recordings into it (they are never written to afterwards).
2. Create `lessons\lesson02\video_project_config.json`:
   ```json
   {
     "face_camera": "D:/YouTube-Editing/lessons/lesson02/raw/face_camera.MOV",
     "desktop_recording": "D:/YouTube-Editing/lessons/lesson02/raw/desktop_recording.mkv",
     "lecture_topic": "Algorithms and Flowcharts",
     "lesson_number": 2
   }
   ```
   - **Defaults:** everything else comes from `config\defaults.json`.
   - **Overrides:** put changes in `"overrides"`, using the same section names: `layout`, `zoom`, `captions`, `audio`, `thumbnails`, `youtube`, `shorts`, `output`, …
   - **Your links:** set them under `youtube.links`; until then they stay `{{…}}` placeholders.
   - **Template:** [video_project_config.json](video_project_config.json).
3. Open Claude Code in `D:\YouTube-Editing` and say:
   > "New lecture: lessons\lesson02. Follow VIDEO_EDITING_WORKFLOW.md."

   Claude runs `python -m ytpipe init|inspect|sync|transcribe|analyze|timeline …`, then stops at each ⛔ gate for your decision.

## 2. Verified vs not yet verified

**Verified** (tests on synthetic fixtures; `python -m pytest tests`; last run recorded in `tests\last_run.txt`):
- config validation
- sync (a known offset recovered within 10 ms; stops when there's no shared audio)
- slide/counter/ink/pause analysis against ground truth
- the A/B/C renderer
- narration placement (sample-exact) and −16 LUFS
- the full pipeline end to end with gates and segment reuse
- vertical Shorts (single and mixed layouts)
- all HyperFrames element kinds
- QA, including desktop frame timing

**Produced for Lesson 01, read-only** (in `lessons\lesson01\`):
- the SRT (221 cues, QA pass)
- chapters, description, titles, tags, hashtags and pinned comment
- 3 thumbnail options (QA pass)
- the Shorts candidate report (5 clips, nothing rendered)
- a publishing package

**Not verified on a real new lecture:** the full chain on new footage, and the timeline layout heuristics. See the gaps in [COMPONENTS.md](COMPONENTS.md).

## 3. Assets and licences
- **Music:** "Sincerely" by Kevin MacLeod, CC BY 4.0. The credit is required in every description and is inserted automatically from `config\credits.json`:
  ```
  "Sincerely" Kevin MacLeod (incompetech.com)
  Licensed under Creative Commons: By Attribution 4.0
  https://creativecommons.org/licenses/by/4.0/
  ```
  The track is pre-registered in Content ID. Attribution does not guarantee that no claim will appear.
- **SFX:** original (synthesised).
- **Tools:**
  - HyperFrames (Apache-2.0), GSAP (standard no-charge licence)
  - rembg (MIT) with the u2net_human_seg model, downloaded once to `C:\Users\admin\.rembg\models`
  - Segoe UI (Windows system font)
- **No paid services are used.** Adding one needs the ⛔ `paid_assets` gate.

## 4. Folder layout
```
D:\YouTube-Editing\
  CLAUDE.md + the documents above
  config\        defaults.json, schema.json, glossary.json, credits.json
  ytpipe\        the reusable modules            tests\   pytest + synthetic fixtures
  assets\hyperframes\   shared HyperFrames styles/template
  templates\     example configs
  lessons\<id>\  raw  analysis  transcripts  timelines  assets  thumbnails  full_video  shorts  metadata  reports
                 publishing_package  state.json  video_project_config.json
  raw\  output\  _work\      Lesson 01 sources, finals and the proven scripts (kept exactly as they are)
```
Moving Lesson 01's `raw\`, `output\` and `_work\` into `lessons\lesson01\` is possible, but the `_work` scripts use relative paths. That needs your approval and a path update, so it has **not** been done.
