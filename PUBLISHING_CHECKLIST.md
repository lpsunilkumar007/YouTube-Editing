# Publishing checklist

Tick an item only if its check actually ran (see `reports\qa_*.json` and `publishing_package\INDEX.md`). Nothing is uploaded by the system.

## Full video
- [ ] Timeline approved (`approve timeline`), preview approved, full render approved (`approve full_render`)
- [ ] `qa_full_video.json`:
  - [ ] 0 decode errors
  - [ ] duration equals the EDL
  - [ ] −16 ± 1 LUFS, true peak ≤ −1.5 dBTP
- [ ] Narration joints checked on the **narration stem** (not the mix). Every flagged joint listened to.
- [ ] Sync **measured**: INDEX "Camera/desktop sync" says verified (pen/word anchors or audio), or you confirmed it (`anchors_waived`). Claude checked a few anchors in the final video: ink 0–1.5 s after the word.
- [ ] Render fidelity (`sync` in `qa_full_video.json`): pen strokes and slide changes within 1 frame of the plan. This does not prove the offset.
- [ ] No blank "End of slide show" screen or flashed slide in a slide shot (QA finding).
- [ ] `reports/content_cuts.md`: every "speech the recognizer missed" stretch read; cut instructions applied, missing teaching added to the transcript.
- [ ] Camera circle covers no slide content (automatic card fit). Old counter hidden, badge correct.
- [ ] Face colours natural (approved pipeline; no grade).
- [ ] No silent cards and no dead air over 1.5 s (timeline report).

## Captions
- [ ] Listen-check page (`listen`) answered by you and applied: every `≈` line correct or fixed. `captions_review.md`: every "listen-check" line checked. Uncaptioned `(meaning)` or `[unclear]` lines transcribed or consciously left out.
- [ ] `qa captions` passes: no overlaps, ≤ 42 characters per line, ≤ 2 lines, 0.5–6 s, inside the video.
- [ ] Upload the SRT as a YouTube subtitle track (language: Hindi, or the variant you prefer).

## Thumbnail
- [ ] One option chosen (`approve thumbnail`). QA: size, safe margins, mobile text size, no text on the face or behind the body, topic words present. Face frame: mouth closed, eyes on camera.
- [ ] Real face from your own recording.

## Fact check
- [ ] `reports/fact_check.md` says PASS: every claim verified; wrong claims cut or corrected; imprecise ones not repeated in written copy.

## Description and metadata
- [ ] Title research recorded (`description_input.json` `research`, dated, sourced); `metadata` reports no problems.
- [ ] Title chosen from `youtube_titles.md`.
- [ ] All placeholders filled: channel name, playlist link, next-lesson link.
- [ ] Chapters copied from `youtube_chapters.txt`, the first at 0:00.
- [ ] Music credit present verbatim. Licence still valid on the source site.
- [ ] Tags ≤ 500 characters, ≤ 5 hashtags.

## Shorts / Reels
- [ ] Candidates approved individually (`approve shorts`).
- [ ] Per clip QA: 1080×1920, face visible, starts/ends in pauses (`shorts-render` refuses a mid-word edge), captions inside safe areas. Re-rendered after any sync or caption change in the long video.
- [ ] Short-form metadata reviewed. Credit included if the clip has music.

## Blog / WordPress
- [ ] `wp-publish` dry run read: title, slug, category, tags, featured image, SEO fields, internal links, references (`--check-links`: all verified).
- [ ] `approve blog_publish --note payload:<hash>` for exactly that dry run; `--send` made a **draft**.
- [ ] Draft checked in WordPress (theme, images, embed), then published by you. SEO fields: if the report says "NOT stored", enter them from `SEO.txt`.
- [ ] After the YouTube upload: `video_url` and `shorts_urls` added, blog rerun, the draft updated (or the live post edited by hand).

## Never
- [ ] Never modify `raw\`. Never overwrite a final without approval. No paid services or uploads without your explicit go-ahead.
