# Production readiness report: ytpipe after Lesson 02

Date: 2026-10-25. Machine: Apple M2, 8 GB, macOS 26.2. Branch reviewed: `music-long-video` (contains all four branches).

**Verdict:** ready for Lesson 03, with 2 open items:
- the encoder change needs your approval (§3)
- the inputs you supply each lesson (§7)

The quality-check gaps in §6 are fixed on branch `qa-hardening` (PR #7).

Lesson 02 assets were not re-rendered or modified during this review. A before-and-after snapshot of all 142 files in `lessons/` showed no change.

## Checklist

| # | Check | Result | Evidence |
|---|---|---|---|
| 1 | Branch dependencies | PASS | One straight line from `main` (7f53eff): thumbnails-v3 → render-speed-sample → blog-posts → music-long-video. `main` has not moved, so each merges without conflicts. |
| 2 | Conflicts between modules | PASS | §2 |
| 3 | Test suite | PASS | After `qa-hardening`: 33 pass, 2 skip (they need Lesson 01 files, which are not on this Mac; §4). Before it: 30 passed and those 2 failed. |
| 4 | Encoder CRF 14 / medium vs the approved encode | PASS (needs your approval) | VMAF 97.1 mean, 96.1 worst frame (§3). Not yet the production default on `main`. |
| 5 | Reusable configuration | PASS with caveats | Lesson configs hold only paths, topic, number and two overrides. 4 hard-coded fallbacks remain (§5). |
| 6 | Modules working together | PASS | Re-ran captions, metadata, blog, shorts, qa and package on a copy of Lesson 02. Outputs match the originals exactly, apart from build timestamps and folder paths. |
| 7a | QA: narration continuity | PASS | Every cut checked on the narration stem (not the mix). The old note at 1:59.7 (a 0.58 s pause, within the 2 × 0.35 s room tone the timeline keeps) is no longer flagged; the threshold now comes from config. |
| 7b | QA: synchronisation | PASS | Slide changes are now a second sync anchor. On Lesson 02: 5 slide changes compared, 0 off by more than 1 frame, so the 11.96 s offset is verified. QA now says so when nothing can be compared. |
| 7c | QA: caption accuracy | MANUAL | QA checks timing, length and overlaps (pass, 51 cues). The wording of 10 reconstructed (≈) lines needs a listen-check (`reports/captions_review.md`). |
| 7d | QA: audio levels | PASS | −16.0 LUFS integrated, −1.9 dBFS peak (target −16 ± 1, ≤ −1.5). Music is now checked automatically: Lesson 02's 5 sections are 27–34 dB under the voice, placed only at the intro, the chapter breaks and the outro. |
| 8 | Manual steps listed | DONE | §7 |
| 9 | Pull requests | PREPARED | 5 stacked PRs (#3–#7), none merged. |

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

Fixed in `qa-hardening`: they skip automatically when the data is missing, so a red test always means a real problem. The Lesson 01 geometry test is split, so its layout half still runs.

## 5. Values that only fit the current recording setup

| Where | Value | Risk for Lesson 03 |
|---|---|---|
| `__main__.py` shorts-render | slide area falls back to `[0,0,1890,1080]` (the Lesson 01 value) if analysis is missing | Low: analysis always exists after the `analyze` stage |
| `shorts_v3.ink_runs(slide_w=1890)` | the caller does not pass the measured slide width (Lesson 02: 1892) | Low: a 2 px difference |
| `__main__.py` shorts-render, `qa.frame_timing` | `/ 30` instead of `cfg.output.fps` | Only if fps changes |
| `shorts_v2`, `layout.py` | assume a 1920×1080 desktop recording | Only if OBS resolution changes |
| `audio.music_plan` | intro 8 s, swell 4 s, outro 6 s are function defaults, not config | None (style rule §14) |

Keep OBS at 1920×1080, 30 fps for Lesson 03 and none of these matter. I recommend a small follow-up branch that reads them from config.

## 6. Quality-check fixes (branch `qa-hardening`, PR #7)

| Gap found in the review | Fix |
|---|---|
| The pen-sync check compared 0 moments on Lesson 02 and still looked like a pass | It reports how many moments it compared. **Slide changes are a second anchor** (`qa.slide_timing`). QA says "sync not verified" when neither can be compared. |
| The frame-timing result was never saved | Everything goes into `qa_full_video.json`, under `sync` and `music`. |
| Music level was checked only by hand | `qa.music` reads a separate music track (`work/music_stem.wav`) and checks each section's level against the 25–35 dB rule. It also flags music longer than 6 s mid-video. |
| A 0.58 s designed joint pause was flagged every render | The joint gap limit comes from the config: 2 × kept room tone + 0.1 s = 0.8 s. A 1 s hole is still caught (tested). |
| The sync report said "pre-render" | It now says the check runs after the render, and what to do when it can't verify. |
| `analyze.run` never shut its thread pool | The pool is shut down in a `finally`. |
| A finished video could not be re-checked | `qa --final <video>` re-runs all full-video checks, read only, with the stems from that render. |

Verified on fixtures: a deliberate 4-frame sync error is caught by both anchors, and the test with no anchors reports "not verified".

Verified on Lesson 02, on a scratch copy with only the audio stems rebuilt (they match the delivered audio to −37.6 dB): **0 findings**.

## 7. Manual steps that stay with you

Every lesson:
- **Approval gates:** timeline, sample/preview, full render, thumbnail and Shorts.
- **Sync:** if OBS has no audio, confirm the offset when QA says "sync not verified" (no pen strokes or slide changes inside slide shots).
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
