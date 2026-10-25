# Production readiness report: ytpipe after Lesson 02

Date: 2026-10-25. Machine: Apple M2, 8 GB, macOS 26.2. Branch reviewed: `music-long-video` (contains all four branches).

**Verdict:** ready for Lesson 03, with 3 open items:
- the encoder change needs your approval (§3)
- the pen-sync check didn't run on Lesson 02 (§6)
- the inputs you supply each lesson (§7)

Lesson 02 assets were not re-rendered or modified during this review. A before-and-after snapshot of all 142 files in `lessons/` showed no change.

## Checklist

| # | Check | Result | Evidence |
|---|---|---|---|
| 1 | Branch dependencies | PASS | One straight line from `main` (7f53eff): thumbnails-v3 → render-speed-sample → blog-posts → music-long-video. `main` has not moved, so each merges without conflicts. |
| 2 | Conflicts between modules | PASS | §2 |
| 3 | Test suite | PASS (30/32) | 30 pass. 2 fail because Lesson 01 files are not on this Mac (§4). |
| 4 | Encoder CRF 14 / medium vs the approved encode | PASS (needs your approval) | VMAF 97.1 mean, 96.1 worst frame (§3). Not yet the production default on `main`. |
| 5 | Reusable configuration | PASS with caveats | Lesson configs hold only paths, topic, number and two overrides. 4 hard-coded fallbacks remain (§5). |
| 6 | Modules working together | PASS | Re-ran captions, metadata, blog, shorts, qa and package on a copy of Lesson 02. Outputs match the originals exactly, apart from build timestamps and folder paths. |
| 7a | QA: narration continuity | PASS | Every cut checked on the narration stem (not the mix). 1 note at 1:59.7 is a natural 0.58 s pause, also present in the approved version. |
| 7b | QA: synchronisation | PARTIAL | The offset (11.96 s) is your manual confirmation. The automatic pen-stroke check compared **0 moments**, because Lesson 02 has no pen writing on slides (§6). |
| 7c | QA: caption accuracy | MANUAL | QA checks timing, length and overlaps (pass, 51 cues). The wording of 10 reconstructed (≈) lines needs a listen-check (`reports/captions_review.md`). |
| 7d | QA: audio levels | PASS | −16.0 LUFS integrated, −1.9 dBFS peak (target −16 ± 1, ≤ −1.5). Music measured 27–33 dB under the voice by hand, not by QA. |
| 8 | Manual steps listed | DONE | §7 |
| 9 | Pull requests | PREPARED | 4 stacked PRs (#3–#6), none merged. |

## 2. Overlap between the branches

Three files are changed by more than one branch. The changes sit at different points in each file:

- **`pipeline.build`:** sample adds `wd`, `record` and `parent_segments`; music adds the `music_sections: auto` path. Samples get the same music as the full render at the same moments.
- **`publish.py`:** v3 thumbnails, UPLOAD_COPY and the blog section, each added on top of the last.
- **`__main__.py`:** the new `sample` and `blog` stages.

Rendering stays sequential, so the cropped overlay files (`*_tight.png`) can't race.

Approved style: the thumbnails module was untouched by the later branches, and the Shorts renderers were untouched by all four.

## 3. Encoder: CRF 14 / medium vs the approved CRF 12 / slow

Measured by comparing frame by frame against the approved encode. No re-render was done for this.

| Comparison | VMAF mean | VMAF worst | SSIM | PSNR-Y |
|---|---|---|---|---|
| Review sample (450 frames, `sample_new_settings` vs `sample_old_settings`) | 97.19 | 96.74 | 0.9997 | 50.9 dB |
| Full video (5,636 frames, `lesson02.mp4` vs `lesson02_no_music.mp4`) | 97.14 | 96.06 | 0.9997 | 51.8 dB |

- **What the numbers mean:** VMAF above 95 means viewers can't tell the two apart. No frame scores below 96. The weakest frames are 0:27.7, 2:12.3 and 0:55.7, and they are still above 96.
- **Speed and size:**
  - full render: 5.6 min → 3.6 min
  - file size: 456 MB → 327 MB, which also makes the upload 28 % smaller
- **Status:** the change is committed only on `render-speed-sample` (PR #4). **Merging PR #4 makes it the production default.** It is your call.
  - If you'd rather keep CRF 12 / slow, I'll split the encoder line out of the PR and keep the other speed-ups. They produce identical frames.

## 4. Test failures

| Test | Cause |
|---|---|
| `test_qa.py::test_lesson01_captions_pass` | Needs the Lesson 01 SRT, which is not on this Mac |
| `test_render.py::test_geometry_reproduces_lesson01` | Needs `_work/slide_content.npz` (Lesson 01 analysis) |

These two tests depend on the Windows-era Lesson 01 data, not on this code.

Recommendation: skip them automatically when the data is missing, so a red test always means a real problem.

## 5. Values that only fit the current recording setup

| Where | Value | Risk for Lesson 03 |
|---|---|---|
| `__main__.py` shorts-render | slide area falls back to `[0,0,1890,1080]` (the Lesson 01 value) if analysis is missing | Low: analysis always exists after the `analyze` stage |
| `shorts_v3.ink_runs(slide_w=1890)` | the caller does not pass the measured slide width (Lesson 02: 1892) | Low: a 2 px difference |
| `__main__.py` shorts-render, `qa.frame_timing` | `/ 30` instead of `cfg.output.fps` | Only if fps changes |
| `shorts_v2`, `layout.py` | assume a 1920×1080 desktop recording | Only if OBS resolution changes |
| `audio.music_plan` | intro 8 s, swell 4 s, outro 6 s are function defaults, not config | None (style rule §14) |

Keep OBS at 1920×1080, 30 fps for Lesson 03 and none of these matter. I recommend a small follow-up branch that reads them from config.

## 6. Quality-check gaps (recommended follow-up, not yet changed)

1. **The pen-sync check is silent when it checks nothing.**
   - `qa.frame_timing` reports only failures. On Lesson 02 it compared 0 moments: the 5 "ink" events are screen flashes at the start and end of the OBS recording, outside the lesson.
   - Fix: report how many moments were checked, fail when it is 0, and also use slide changes as sync anchors.
2. **The frame-timing result is never saved.** It is attached after `qa_full_video.json` is written, so the file never contains it.
3. **Music level isn't checked automatically.** QA measures the whole mix. Add a music-only measurement (new mix minus the narration stem) against the 25–35 dB rule.
4. **The sync report says "pre-render check"**, but the check runs after the render.
5. **`analyze.run`** never closes its thread pool, so if desktop analysis fails, the background decodes keep running.

None of these affect the delivered Lesson 02 files. I recommend fixing them in one `qa-hardening` branch before Lesson 03. Each is small.

## 7. Manual steps that stay with you

Every lesson:
- **Approval gates:** timeline, sample/preview, full render, thumbnail and Shorts.
- **Sync:** if OBS has no audio, confirm the offset, unless the lesson has pen writing for the automatic check.
- **Captions:** listen-check the ≈ caption lines.
- **Before uploading:** go through `PUBLISHING_CHECKLIST.md`.
- **Uploading:** to YouTube, Instagram and the blog. The pipeline never uploads.
- **After uploading:** give me the YouTube link, then I rerun `blog` and `package`.

Lesson 02 now:
- Listen-check its 10 caption lines.
- Upload it.
- Blog: give me your author name and website address.
- Decide on the encoder (§3).

Once:
- Merge PRs #3 → #6 in order, after review.
- Supply photos if you want photo-based thumbnails.
- Approve the ~1.6 GB mlx-whisper download (faster transcription) if wanted.

## 8. Speed (Lesson 02, 3:08 final)

| Stage | Time |
|---|---|
| Transcription | ~4.5 min |
| Analysis | 60 s |
| Review sample | ~23 s |
| Full render | 3.6 min |
| Captions, metadata, blog, package | seconds each |
| Thumbnails | ~1 min |
| Shorts | ~2.3 min each |
