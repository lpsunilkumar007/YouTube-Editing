# Lesson 01 reference implementation (moved from CLAUDE.md, 2026-10-21)

This document records how the finished Lesson 01 was actually made with the scripts in `_work\`. Those scripts stay as the proven fallback. New lectures use `ytpipe` (see YOUTUBE_CONTENT_PIPELINE.md), which ports this implementation. Section numbers are kept from the old CLAUDE.md.

---
# (former) YouTube-Editing: instructions for Claude Code

This is the main instruction file. Claude Code loads it automatically in `D:\YouTube-Editing`.

**Companion documents:**
- [TEACHING_VIDEO_STYLE.md](TEACHING_VIDEO_STYLE.md): the approved look
- [VIDEO_EDITING_WORKFLOW.md](VIDEO_EDITING_WORKFLOW.md): steps and approval checkpoints
- [COMPONENTS.md](COMPONENTS.md): reusable scripts and their status
- [REUSABLE_SYSTEM_README.md](REUSABLE_SYSTEM_README.md): quick start
- [video_project_config.json](video_project_config.json): per-lecture inputs

**Precedence:** where an older planning file conflicts with these documents, these documents win. The older files are `CLAUDE_CODE_PROMPTS.md`, `editing_timeline.md` §1 and `reference_style_analysis.md` (for example its "16:9 rectangle overlay", "no music" and "−14 LUFS"). They record decisions made before the style was approved.

---

## 1. Project purpose

The project produces technical teaching videos (Hinglish narration) from **two recordings per lecture**:
1. An iPhone face camera.
2. A desktop/screen recording (OBS) of slides with live red-pen annotation.

The edited lecture combines:
- the original face footage, colour-converted faithfully
- the desktop recording, framed as a slide card
- the narration as the master timeline
- subtle educational motion graphics (HyperFrames)
- properly licensed background music used sparingly
- Hinglish captions (**pending**: see §11)

**Lesson 01 ("How computers follow instructions") is finished:**
- `output\lesson01_final.mp4`, 12:54, rendered 21 Oct 2026.
- Its files are the reference implementation. **Do not modify, re-render or reprocess it.**

## 2. Reference editing style

- **Reference:** Apna College lectures, e.g. https://youtu.be/VTLCoHnyACE?list=PLfqMhTWNBTe137I_EPQd34TsgV6IO55pt
- **Verified analysis:** `reference_style_analysis.md`, measured from Lecture 2 of the DSA series.
- **What we take from it:** teaching principles only.
  - The narration leads.
  - Hard cuts.
  - Emphasis comes from the presenter's own pen.
  - Zoom only for text that matters.
  - Steady pacing.
- **Do not copy** the creator's branding, logos, colours, intro/outro or other distinctive assets.
- The approved look is our own; see TEACHING_VIDEO_STYLE.md.

## 3. Video source rules

> Never modify or overwrite anything in `raw\`. Write new outputs beside it.

- **Sources:** always read the original recordings. Never use previews, proxies or exported MP4s as sources.
- **Lesson 01:** the finished lecture and its raw files are fingerprinted in `_work\integrity_before_docs.txt` (SHA-256 prefix, size, mtime). Re-check them before and after any work in this folder.
- **Per-lecture outputs:** go to that lecture's output folder (see REUSABLE_SYSTEM_README.md §5). Scratch files go to `_work\`.

## 4. Synchronization (what was actually done in Lesson 01)

Full method and evidence: `synchronization_report.md`.

**Model:** `D = F + L`
- D = desktop time, F = face-camera time.
- Lesson 01: **L = +100.0 s ± 0.3 s**, with **no measurable drift**, so no time-stretch was applied.
- The desktop clock is the master timeline. The narration comes from the face file, so lip sync is exact by construction.

**Method, in order:**
1. **Metadata.** Run `ffprobe` on every stream and timestamp. Identify which clocks are trustworthy:
   - The iPhone `com.apple.quicktime.creationdate` was correct.
   - The MOV `creation_time` atoms were wrong, so don't trust them.
   - OBS stores no absolute time. Use the file mtime as an upper bound, plus the **taskbar clock burned into the desktop frames**.
   - Result: L ≈ 99.5 s, accurate to about ±1 s.
2. **Audio cross-correlation, when both files have audio.** In Lesson 01 the OBS audio track was **digital silence**, so this step was impossible.
   - Procedure for future lectures: mono 16 kHz, coarse correlation over the whole file, then refinement in 30–60 s windows at the start, middle and end.
3. **Visual and event anchors:**
   - Slide changes on the desktop vs the spoken "next slide" moments.
   - Pen-stroke onsets vs the words they illustrate.
   - Scripts: `_work\ink_events.py`, `_work\vsync.py`.
   - These narrowed the metadata estimate to L = 100.0 s ± 0.3 s.
4. **Drift:** measure the offset at the start, middle and end. Lesson 01 measured no drift, with a physical bound of ≤ 50 ppm (≤ 42 ms over 14 min).
5. **Timeline correction:** none needed. If drift is ever found, report it in ppm and correct it with a time-stretch of the desktop, never of the narration.
6. **Edit-level check:** after rendering, check pen strokes against the raw desktop frames (`_work\pen_sync_v8.py`, `_work\frame_match_v9.py`).

- **Never assume** the two recordings started at the same moment.
- If sync can't be established reliably, report it before editing.

**Known open issue (Lesson 01):**
- **What:** the final QC found 3 slide segments (around 7:53, 10:15 and 12:13 of the final) where the desktop picture runs 1–3 frames (≤ 0.1 s) behind the planned desktop frame.
- **Where it's fine:** the other checked segments match at 0 frames.
- **Cause:** not determined. The OBS file's frame timing is the main suspect, but the last probe was inconclusive.
- **Effect:** it is inside the ±0.3 s sync tolerance and was left as rendered.
- **For future lectures:** run `frame_match_v9.py`-style checks per segment **before** the full render.

## 5. Camera layouts

| Layout | Use | Implementation |
|---|---|---|
| **A**: full-screen face | Hook/intro, topic openers, stories and analogies told to camera, summaries, outro | Face frame full-screen through the libplacebo chain (§6); topic labels at the top left |
| **B**: slide card + circular camera | Whenever a slide is explained or drawn on | Desktop cropped to the slide area, scaled 0.88 into a rounded card at (24, 24); 368 px camera circle at the lower right; chip bar under the card |
| **C**: B with zoom | Only where small slide text or live ink matters **and** a clearance-safe window exists | Same as B with a cropped, eased desktop window (§7) |

**Circular camera (approved, v3–v9):**
- **Size and position:** **368 px** diameter (19.2 % of 1920) at **(1528, 688)**, 24 px margins.
- **Mask:** anti-aliased circular alpha mask, `v3_cam_mask.png`.
- **Border and shadow:** 2 px #E2E8F0 ring at 85 % (`v3_ring_cam.png`) and a soft **outside-only** shadow (`v3_cam_shadow.png`). No rectangular background.
- **Framing:** a **fixed, whole-pixel crop per continuous take**: 756 px square, face centre at 42 % of the height, the median of `face_track.npy` (Haar detection every 0.5 s).
- **Never use a moving or face-following crop.** Sub-pixel motion over the slatted wall caused shimmer (fixed in v5).
- **Content clearance:** the card size (0.88) is the largest at which no slide text or ink falls under the circle. Check every new lecture with the content masks.

## 6. iPhone video processing (verified)

**Lesson 01 source:**
- iPhone 15, iOS 26.6.1, **HEVC Main 10**, 1920×1080, 30 fps (avg 29.998), **HLG / BT.2020**, **Dolby Vision profile 8.4**.
- Rotation −180° in the display matrix; ffmpeg auto-rotates.
- Two `mebx` timed-metadata tracks, which are ignored.
- You reported it was recorded in Cinematic mode. Any depth effect is already baked into the video, so nothing extra is needed.

**Approved HDR → SDR conversion** (one GPU pass; crop and downscale in the same pass for the circle):
```
ffmpeg -init_hw_device vulkan ... -vf "libplacebo=tonemapping=bt.2390:apply_dolbyvision=1:colorspace=bt709:
  color_primaries=bt709:color_trc=bt709:range=tv[:w=368:h=368:crop_x=..:crop_y=..:crop_w=756:crop_h=756:downscaler=ewa_lanczos]"
```
- **Code:** `PL` in `_work\render_preview_v6.py`.
- **Used for:** both the full-screen and the circle footage, always read from the original file.
- **Fidelity:** it matched a lossless raw render at SSIM 0.98–0.99 (`output\face_camera_quality_comparison.md`).

**Do not apply** a grade, vignette, sharpening, beauty filter or saturation boost.
- v2 used a mobius tonemap, a highlight curve (1/0.82) and a vignette. You rejected that look as faded, so it was removed in v3.
- `face_track.py` still uses a zscale/mobius tonemap, but **only for face detection**, never for output.

**For future lectures:** inspect the source metadata first. Don't assume HLG/DV, the rotation or the frame rate. Without Dolby Vision, keep the same libplacebo chain with `apply_dolbyvision=1` (harmless when there is no DV metadata), and check the result against a lossless reference frame.

## 7. Screen zooming (layout C)

- **Mechanism:** fixed-size crop and scale of the desktop with a **0.6 s cubic ease** in and out. Code: `desk_chain()` in `_work\render_preview_v2.py`, window `(x, y, w, ease_in, ease_out)`.
  - The window aspect is the card's, 1664:950.
  - The camera stays fixed on top at normal size.
- **Default strength:** about 1.2–1.5× relative to layout B. Lesson 01 used 1.63× relative to B (1.43× in the card) on slide 5, approved in v6.
- **A zoom is allowed only if all of these hold** (check with `_work\zoom_check_full.py` and search with `_work\zoom_search_full.py`):
  1. Every pen stroke drawn during the shot stays inside the window.
  2. No slide text or ink lands under the camera circle.
  3. No text line, diagram column or paragraph is cut by the window edge.
  4. The zoom follows what is being explained.
- **If no window passes, don't zoom.** In Lesson 01, slides 3, 4, 6 and 9 failed these rules and stay at layout B.
- **Never** start or end a zoom while the presenter is writing or scrolling.
- An optional focus dim (45 % black on the rows not being explained, faded with the zoom) is used once (slide 5, shot 16): `make_graphics_v6.focus_mask()`.

## 8. Teaching continuity (critical)

**Narration drives every edit.** These rules came from your v7 → v8 review.

**Never:**
- Insert silent full-screen title or chapter cards.
- Add decorative pauses.
- Freeze or delay narration for a graphic.
- Cut inside a word or sentence.
- Show a later step or annotation before it is spoken.

**Rules:**
- **Cut placement:** place every cut in a **real pause measured on the audio**, using the 10 ms speech maps from `_work\env_probe.py`. faster-whisper word end times are padded into the silence, so they are not reliable cut points.
- **Edges:** keep about 0.15–0.35 s of room tone on each side of a cut.
- **Joints:** join with 20 ms equal-power crossfades of real room tone (`mix_audio_v8.py`), never a fade to digital silence.
- **Pauses:** keep natural thinking pauses and pauses where the presenter is drawing. Removing those would mean jump cuts in the face and the ink.
- **Dead air:** remove anything longer than about 1.5 s, preferably at a layout change (A↔B) so no jump is visible.
- **Graphics:** they ride on narrated footage as overlays, such as gutter cards or topic labels.
- **The only full-screen title allowed:** the lesson title, **shown over the opening face shot** (adds 0 s).
- **Frame grid:** snap every segment boundary to the 30 fps grid so contiguous segments tile exactly and sound can't drift from picture (`lecture_plan_v9.snap`).

## 9. HyperFrames (as integrated)

**Install and project:**
- Installed: `hyperframes` **0.8.181** (Apache-2.0), locally in `_work\hf` (`npm install hyperframes`; Node 22+, ffmpeg).
- Compositions: `_work\hf\v7\`.
  - `style.css`: palette and Segoe UI, gutter-card and step styles.
  - Element HTML files generated by `_work\make_overlays_v9.py` from `ELEMENTS` in `_work\lecture_plan_v9.py`.
- GSAP 3.14.2 loads from cdn.jsdelivr.net **at render time**, so rendering needs network access.
- Each composition: a root `data-composition-id` and `data-duration`, a paused GSAP timeline registered on `window.__timelines[id]`, and local time 0 = the element's start.

**Element types** (`make_overlays_v9.KINDS`):
- `term`: key-term card in the right gutter
- `topic`: topic label on A shots, top left
- `title`: lesson title on the opening shot
- `end`: next-lesson card on the outro
- `ipo`: Input → Process → Output steps revealed on the spoken words
- `rings`: diagram rings and progressive arrows on a slide diagram, cleared before the first pen stroke

**Render:**
- Overlays: `npx hyperframes render v7 -c <file>.html --format mov -o v7/out9/<file>.mov` (run in `_work\hf`), giving ProRes 4444 with alpha.
- Opaque full-frame cards: `--format mp4` with an explicit background `div`. MOV export ignores the body background and bands soft gradients.

**Timeline integration:**
- `render_full_v9.add_overlays()` inserts each element MOV as the **top layer**, offset with `setpts=PTS+offset/TB` and `eof_action=pass`, inside the same single encode as the segment.
- Elements are placed by face time F and assigned to the segment that contains them.

**Rules:**
- Graphics appear **while** the concept is spoken.
- They never cover slide content, ink or the face. Gutter cards sit at x 1712–1896; face-shot labels stay left of x 640, where the face never was.
- They never extend the video.

## 10. Music and sound effects (as implemented)

**Approved track:**
- "Sincerely" by Kevin MacLeod (incompetech.com), **CC BY 4.0**, ISRC USUAN1900016.
- File: `_work\music_dl\Sincerely.mp3`, unmodified.
- **The credit is required** in the YouTube description; full details in `output\music_and_asset_credits.md`.
- The track is pre-registered in Content ID, so add the credit before publishing.

**Licence process for any new asset:**
1. Read the licence on the source's own site.
2. Record the source URL, licence, attribution text and commercial-use terms in the credits file.
3. Don't use the asset if its licence can't be verified.
4. "Free download" is not the same as free to use.
5. Never claim an asset is Content-ID-safe.
6. The YouTube Audio Library needs your account: ask for the file rather than bypassing access.

**Selection:** `_work\music_metrics.py`. It prefers low percussiveness and little energy in the 1–4 kHz speech band. No vocals.

**Placement** (`render_full_v9.build_audio`):
- **Intro:** under the opening shot, ducked.
- **Genuine chapter breaks only** (3 in Lesson 01): a short swell across the existing pause (about 4 s), ducked.
- **Outro:** a light close using the track's own ending.
- **Never** under technical explanation, and **never to fill a gap**.

**Levels:**
- Music sits about 25–35 dB below the voice.
- Ducking adds up to 6 dB more under speech (80 ms attack, 0.6 s release; `mix_audio_v7.duck`).
- Fades are raised-cosine.

**SFX:**
- Four original effects, synthesised in `_work\make_sfx_v7.py`, so no licence is needed.
- Each is tied to a visual event: a soft tick for each card, one pluck for a diagram reveal, a soft swell for the title.
- Peaks are −31 to −36 dBFS after the −3 dB delivery offset.
- No whooshes on cuts, no per-word effects.

**Voice chain (approved):**
1. high-pass 80 Hz
2. +16 dB
3. `acompressor` 2:1, threshold −24 dB, knee 6, attack 15 ms, release 250 ms
4. `alimiter` 0.70
5. **two-pass `loudnorm` I = −19 LUFS on the mono narration**, which measures **−16 LUFS on the stereo file**
6. TP −2

The final limiter is `alimiter=limit=0.84:latency=1`, then AAC 192 kbit/s.

**Delivered (Lesson 01):** −16.0 LUFS integrated, LRA 2.9 LU, −1.8 dBTP, per-segment narration spread 0.5 LU.

## 11. Captions (pending: not implemented)

**What exists:** `transcript.txt`, a hand-cleaned Hinglish transcript.
- Hindi in Roman script, English technical terms as spoken.
- MASTER/FACE/DESK/EDIT timestamps; "≈" and "[unclear]" mark weak passages.
- Word timings are in `_work\part1.json` and `part2.json`.
- Made with faster-whisper **medium** int8 on the CPU. large-v3 did not fit in 8 GB of RAM.

**Not done:** no SRT or VTT file exists, and nothing is burned in.

**Planned specification:**
- An **SRT sidecar** uploaded as a YouTube CC track. Don't burn captions in; the reference doesn't use them, and the chip bar occupies the bottom band.
- Build it from transcript lines mapped through the final EDL.
- Line limits: ≤ 42 characters per line, ≤ 2 lines, each caption on screen for 1–6 s.
- Correct technical terms: CPU, RAM, operating system, input/process/output, and so on.
- Check "≈" and "[unclear]" lines by ear.

## 12. Final quality control (before any full render or export)

Scripts: see COMPONENTS.md §15.

| Check | How | Lesson 01 result |
|---|---|---|
| Sound vs picture per segment | `verify_full_v9.py` §2 | within ±1 ms (33 segments) |
| Audio continuity at joints | `transition_qc.py --file <narration stem> --cuts ...`, run on the **narration stem**, because music can mask gaps | 11 joints; no click; 3 short pauses (0.56–0.63 s) reviewed and kept |
| Edit-list joint review | `transition_qc.py full_v8` (EDL mode) | 2 joints listed for listening (3:51 and 10:42) |
| Pen-stroke timing | `verify_full_v9.py` §4 and `frame_match_v9.py` | 0 frames in 5 segments; 1–3 frames in 3 (§4 known issue) |
| Zoom clearance | `zoom_check_full.py` | slide-5 windows: 0 px under the circle |
| Circle, flicker, camera jitter | `verify_flicker.py`, `verify_face_v3.py` | jitter 0.018–0.021 (source 0.028) |
| Slide counter hidden and redrawn | v4 method: 0 of 2,556 frames showed the old counter | not re-run for the full render |
| Loudness | ebur128 integrated, LRA, true peak | −16.0 LUFS, −1.8 dBTP |
| Decode | `ffmpeg -v error -i <file> -f null -` per segment **and** on the final file | 0 errors |
| Licences and credits | `output\music_and_asset_credits.md` | done |
| Captions | pending | – |

## 13. Efficiency

**Reuse instead of redoing:**
- Reuse cached analysis: `face_track.npy`, `slide_content.npz`, `counter_keys.npy`, `part*.json`, `face48.wav`.
- **Never** re-transcribe or re-sync a lecture that already has results.

**Rendering:**
- Re-render only the affected segments. Every segment is a separate `.mkv` joined by stream copy, so unchanged segments are reused bit-for-bit.
- Test-render 2–3 representative segments before a long render. Run long renders in the background.

**Output and records:**
- Print summaries, not frame dumps. Pipe through `tail`, and use `grep --line-buffered` when logging.
- Keep decisions in project files (timeline, plan, reports), not only in chat.
