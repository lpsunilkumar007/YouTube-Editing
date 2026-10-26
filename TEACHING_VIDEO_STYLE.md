# Teaching video style (approved)

This is the approved look and editing style, taken from the finished Lesson 01 (`output\lesson01_final.mp4`) and previews v3–v9, all approved by you.

Values are for **1920×1080 at 30 fps**. If the resolution changes, scale every pixel value by width ÷ 1920.

Implementation details: [CLAUDE.md](CLAUDE.md) and [COMPONENTS.md](COMPONENTS.md).

## 1. Educational presentation principles

- **The narration is the timeline.** Picture, graphics and music follow the spoken explanation; nothing waits for a graphic.
- **Emphasis comes from the presenter's own pen.** Graphics support it and never duplicate or replace the handwriting.
- **One idea on screen at a time.** Show a step only once it is spoken.
- **Calm, steady pacing.** Natural pauses stay. Dead air over about 1.5 s goes.
- **Cuts:** hard cuts only. No dissolves or wipes in the lesson body.

## 2. Full-screen presenter (layout A)

- The original face frame, full-screen, through the approved HDR → SDR chain (§17).
- **Used for:** the hook, topic openers, stories and analogies told to camera, and the outro.
- **Overlays:**
  - A topic label at the top left (§8) for about 4 s at the start of a topic.
  - The lesson title at the bottom left over the opening shot.
  - A next-lesson card in the last 5 s.
- **Face safe area:** in Lesson 01 the face was always right of x 640. Keep labels inside x 64–620, and re-check this for each new recording.

## 3. Desktop + circular camera (layout B)

- **Canvas:** #101827.
- **Slide card:** the desktop's slide area (Lesson 01: x 0–1889; the OBS capture had a black bar at x ≥ 1890) scaled **0.88** to **1664×950 at (24, 24)**.
  - 14 px corner radius, 1 px #334155 ring, soft shadow.
- **Camera circle:**
  - **368 px** diameter at **(1528, 688)**, 24 px from the right and bottom.
  - 2 px #E2E8F0 ring at 85 % opacity, soft outside-only shadow, no rectangle behind it.
  - Natural head-and-shoulders framing: the face centre at 42 % of a 756 px source square.
  - One fixed crop per continuous take.
- **Chip bar:** at (24, 995), under the card (§9).
- **Counter badge:** at the top right (§10).

## 4. Zoomed desktop (layout C)

- Layout B with an eased (0.6 s cubic) crop of the slide.
- **Strength:** about 1.2–1.5× relative to B. Higher only if all clearance rules hold (Lesson 01 slide 5: 1.63× relative to B).
- **Allowed only when:**
  - every stroke drawn during the shot stays inside the window
  - no text or ink sits under the circle
  - no line, column or paragraph is cut
- If no window passes, stay on B. **Not zooming is the correct choice** when zooming would cut content.
- Optional focus dim: 45 % black, 40 px feather on rows that are not being explained, fading with the zoom. Use it rarely.

## 5. Colour theme (dark navy)

| Token | Hex | Use |
|---|---|---|
| Canvas | #101827 | Background behind the card, full-screen cards |
| Card | #1E293B | Chips (inactive), gutter cards, badges |
| Text | #F8FAFC | Primary text on graphics |
| Muted | #94A3B8 | Inactive chip text, descriptions, counter text |
| Border | #334155 | Card ring, chip and badge outlines, rules |

## 6. Accent colours

| Token | Hex | Use |
|---|---|---|
| Lime | #A3E635 | Active chip, accent bars, progressive arrows, lit steps |
| Cyan | #38BDF8 | Chip-bar section label, "KEY TERM", "TOPIC" and "NEW TOPIC" labels, kickers |

The presenter's **red pen ink is never recoloured**, and neither are the slide or the camera footage.

## 7. Typography and readable sizes

- **Fonts:** Segoe UI Semibold (`seguisb.ttf`) and Segoe UI Bold (`segoeuib.ttf`). Windows system fonts, rendered into the picture.

| Element | Size |
|---|---|
| Chip text | 26 px (chip height 48 px) |
| Chip-bar section label | 22 px, uppercase, cyan |
| Counter badge | 23 px (badge height 42 px) |
| Gutter card | term 32 px (26 px if longer than 10 characters); description 20 px; label 15 px |
| Topic label (layout A) | 34 px bold, label 17 px |
| Lesson title (layout A) | 52 px bold, two lines |
| Next-lesson card | 44 px |

- **Minimum** for any added text: 20 px at 1080p.
- **Slide text:** small slide text can only get bigger through zoom (§4). Never sharpen it.

## 8. Card layout

- **Gutter cards:** "KEY TERM" and "NEW TOPIC" cards sit in the right gutter, between the slide card and the circle.
  - x 1712–1896 (184 px wide), top 96 px, below the counter badge.
  - #1E293B fill, #334155 border, 14 px radius, soft shadow.
  - They slide in 14 px over 0.35 s, a lime underline grows in, and they fade out over 0.35 s.
- **Panels on face shots** (topic label, title, next lesson):
  - Translucent #101827 at 86 %, #334155 border, 16 px radius.
  - A lime accent bar on the left edge grows in.

## 9. Bottom navigation chips

- **Layout:** the section label, then the chips joined by "→".
- **Active chip:** lime with #101827 text. Inactive chips: #1E293B with muted text and a border.
- **Timing:**
  - The active chip changes **on the spoken word**, with a 0.25 s crossfade.
  - The section label can change, e.g. to "Example: sum of 2 digits".
  - A chip only lights when its term is spoken. Nothing lights ahead of the narration.
- The bar sits at (24, 995), at most 1460 px wide so it stays clear of the circle. Slide shots only.

## 10. Slide counters

- **The problem:** the slide's own burned-in counter (Lesson 01: "NN / 10" at x 1713–1751, y 1034–1043) would sit behind the circle.
- **Hide it:** clone a verified-empty strip of the slide background over it, before any scaling.
- **Redraw it:** as a badge "NN / total" at the **top right of the canvas**: right edge 1896, top 24.
  - It switches on the same frame as the slide change.
  - Slide shots only.

## 11. Teaching diagrams

- **Highlight steps on the slide's own diagram.** Use soft glow rings and lime arrows that draw from one step into the next, each on its word.
- **Earlier steps stay softly lit.** Clear everything **before the presenter's first pen stroke** on that diagram.
- **Sequences as a gutter card:** "NEW TOPIC: Every program" with Input ↓ Process ↓ Output, each step revealed when spoken.
- If the presenter circles items by hand while naming them, **don't add a graphic highlight**, because it would duplicate the ink. The chips are enough.

## 12. Pen-stroke preservation

- The desktop frames are shown exactly as recorded: never redrawn, retimed, blurred or recoloured.
- Every stroke must appear on the frame the planned sync gives it. Verify with frame matching.
- Never cover ink with graphics. Zoom windows must contain every stroke drawn during the shot.
- **No cut inside a continuous take while the presenter is writing,** because it would make the ink jump.

## 13. Caption appearance

- **Main video:** a Hinglish **SRT sidecar** (YouTube CC track). Nothing burned in, which matches the reference and keeps the chip band clear.
- **Lines:** ≤ 42 characters, ≤ 2 balanced lines, 1–6 s each, technical terms spelled per `config\glossary.json`.
- **Implemented:** `ytpipe\captions.py`. Lesson 01: `lessons\lesson01\transcripts\lesson01_hinglish.srt`.
- **Optional styled ASS** (Segoe UI Semibold 40 px, white on translucent navy) for burn-in when wanted.
- **Shorts burn in captions** inside safe areas: see [SHORTS_EDITING_STYLE.md](SHORTS_EDITING_STYLE.md).
- **Thumbnails:** see [THUMBNAIL_STYLE.md](THUMBNAIL_STYLE.md).

## 14. Background music

- **Instrumental only:** calm and minimal, with no heavy beats and no vocals. Lesson 01 used "Sincerely" by Kevin MacLeod (CC BY 4.0, credit required).
- **Only at:**
  - the intro, under the opening shot
  - genuine chapter breaks, as a short swell of about 4 s across an existing pause
  - the outro, using the track's natural ending
- **Never** under technical explanation, and **never to fill a gap**.
- **Level:** about 25–35 dB below the voice, plus up to 6 dB of speech ducking. Fades are smooth.

## 15. Transitions

- **Hard cuts.** Cuts between face and slide happen at natural sentence boundaries.
- **Hide slide changes:** cut to layout A just before a slide change happens, unless the change is spoken ("next screen").
- **Never show a blank desktop:** `analyze` finds spans where the slide area is all black (PowerPoint's "End of slide show", a black slide); `timeline` switches the slide shot around each one to layout A, from the pause before it to the pause after it (`timeline.cover_blanks`), and full-video QA reports any blank still shown (`qa.blank_shown`).
- **No** silent chapter cards, wipes or whooshes. A chapter change is marked by:
  - the spoken transition
  - a topic label (on A) or a gutter card (on B)
  - an optional short music swell

## 16. Chapter introduction and outro style

- **Lecture intro:** the lesson title panel (kicker "LESSON 01 • COMPUTER BASICS", two-line title) over the presenter's own "Hello guys…" opening.
  - About 6 s, with a soft swell and light music.
  - **No separate intro card.** It adds 0 s.
- **Chapter starts:** a topic label for about 4 s on the A shot that opens the topic.
- **Outro:** a "NEXT LESSON" card for the last 5 s over the closing face shot, with light closing music.
  - The video ends about 0.3 s after the last word.

## 17. Camera colours and HDR handling

- **The original iPhone colours:**
  - libplacebo BT.2390 tone mapping with **Dolby Vision metadata applied**, output BT.709 TV range.
  - Crop and downscale (ewa_lanczos) in the same GPU pass.
- **No** grade, vignette, sharpening, beauty filter or saturation change.
- Use the same conversion for the full-screen and the circle footage.

## 18. Screen-framing safe areas (1080p)

| Region | Reserved for |
|---|---|
| x 24–1688, y 24–974 | Slide card (content) |
| Circle centred (1712, 872), r 184 (plus about 6 px of ring and shadow) | Camera |
| x 24–1484, y 995–1059 | Chip bar |
| x ≈ 1800–1896, y 24–66 | Counter badge |
| x 1712–1896, y 96–about 660 | Gutter cards |
| Layout A: x 64–620 | Labels and title (re-check against the face track) |

## 19. Mobile readability

- **Card size:** 88 % (the largest without the circle covering content) maximises the slide size.
- **Added text:** ≥ 20 px at 1080p. The chip text (26 px) and counter (23 px) were enlarged in v6 for phones.
- **Zoom** only where small text matters and it is clearance-safe.
- **Encoding:** CRF 14, x264 preset medium, no B-frames, so text edges and the camera stay clean after YouTube's re-encode. Until 2026-10-24 it was CRF 12 / slow. On Lesson 02 the change measured 0.995 SSIM (structural similarity) against the old setting, encoded face shots about 2.5× faster and made files about 30 % smaller.

## 20. Common mistakes to avoid

- **Silent title or chapter cards mid-lesson.** You rejected these in v7.
- **Cut placement:** cutting on faster-whisper word ends instead of measured pauses, which clips the starts and ends of words.
- **Moving or face-following camera crops,** which cause slat-wall shimmer. Also x264 B-frames, which cause a 4-frame pulsing.
- **Graded or vignetted face footage,** which looks faded. Use DV-aware tone mapping.
- **Zooms that cut columns or sentences,** or hide pen strokes.
- **Graphics that light a step before it is spoken,** or duplicate the presenter's ink.
- **Music:** under explanations, or used to mask a narration gap (check the narration stem, not the mix).
- **Audio joints:** fading to digital silence at joints instead of crossfading room tone.
- **Frame grid:** segment boundaries off the 30 fps grid make the audio drift from the picture.
- **Licences:** assuming a free download is licensed.
