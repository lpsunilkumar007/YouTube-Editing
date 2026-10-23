# Thumbnail style (v2, premium)

**Implemented in:**
- `ytpipe\thumbs_v2.py`: layouts, cut-out, QA
- `ytpipe\faces.py`: frame analysis
- `assets\thumbnails\render_html.js`: headless Chrome render

**Input:** `thumbnails\thumbnail_input_v2.json`, plus per-option `.html` files that you can edit. **Command:** `python -m ytpipe thumbnails --config …`

v1 (Pillow text and boxes) is retired as the default, because it looked like a lecture slide.

## Why HTML/CSS
Pillow can only draw flat text and shapes. v2 composes each thumbnail as HTML/CSS/SVG and renders it in headless Chrome (the browser HyperFrames already installed). That gives:
- **Real typography:** Poppins 900 and JetBrains Mono, both OFL fonts from Google Fonts, with kerning and text shadows.
- **Depth:** layered gradients, a grain texture, a vignette and soft lighting behind the subject.
- **Sharp illustrations:** SVG.
- **Editable text:** each option's `.html` is kept next to its PNG.

**No image-generation service is used** (none is configured, and paid APIs need your approval). Every visual is drawn locally from vector shapes, and your face is always a real frame.

## Your face: real frames only
- **Frame analysis:** MediaPipe face landmarks run on 1 frame per second of the face shots, decoded from the **original recording** with the approved colour pipeline. Each frame is scored on:
  - eyes open, and gaze (not looking down or away)
  - head yaw, pitch and roll
  - mouth openness and smile; raised brows
  - sharpness and exposure
- **Hard rejects:** blinking, looking down or away, head turned more than 20°, blur, bad exposure. Lesson 01: 133 of 298 frames were usable.
- **Concepts:**
  - *confident* (premium): eyes on the lens, soft smile
  - *explaining* (concept): natural speaking expression
  - *curious*: attentive, slight head tilt
- **Honesty about expressions:** no expression is ever synthesised. If no frame suits a concept, the generator reports it (for example, Lesson 01 has no raised-brow frames, so "curious" uses a calm, attentive tilt).
- **Pinning:** a reviewed frame can be pinned per option with `frame_t`. A contact sheet of the top picks is saved in `frames_v2\`.

## Cut-out quality
1. Crop around the face box: `head`, `bust` or `half`, by layout.
2. **BiRefNet-portrait** matte for fine hair and shoulder edges.
3. Multiplied by a softened **person-only** mask (u2net human segmentation), so the laptop and desk in front of you never come along.
4. Only the largest region is kept, which drops stray background blobs. The faint outer fringe is tightened slightly.
5. **Edge colour estimation** (pymatting), so the light wall behind you doesn't bleed into hair edges as a halo.
6. A straight bottom cut, above the laptop lid when one is detected.
7. **No outline or glow ring.** Separation comes from a soft drop shadow and a diffuse coloured light *behind* the subject. Your pixels are never smoothed, sharpened or reshaped.

## Text
- **The headline is a hook, not the title.** 2–5 words, drawn from the lecture's real content (e.g. HOW COMPUTERS WORK · 3 STEPS OF A PROGRAM · HOW DOES IT KNOW?).
- **Two text colours only:** white #F8FAFC and lime #A3E635 for the key word. Cyan #38BDF8 appears only in visuals.
- No lesson labels, subtitles or repeated branding.
- Headline Poppins 900, 74–100 px, tight leading. Readable at 1/4 size on a phone.

## Three distinct compositions
| Option | Composition | Face | Visual |
|---|---|---|---|
| **Premium** | Headline block left, subject right (bust, ~78 % height), blue backlight | confident | CPU chip anchored bottom-left; circuit traces run to the subject |
| **Concept** | One-line headline on top, **large central diagram** (the lecture's own example), small portrait lower-right | explaining | Glass cards INPUT 7 + 5 → PROCESS ADD → OUTPUT 12 with gradient connectors |
| **Curious** | Subject left (half figure), big question right | curious | A code-editor screen listing the instructions that answer the question |

The QA also checks that the options differ visually: the mean difference between options is reported, and must be ≥ 18 (Lesson 01: 36–69).

## Background
Base #0C1525, with:
- two soft colour lights (cyan near the subject, lime in a far corner)
- a faint grid faded toward the edges
- fine grain
- a vignette

There are no neon glows on text or the subject.

## QA (each option, recorded in `thumbnail_premium_v2.json`)
1. Size 1280×720.
2. Headline font actually loaded (Poppins 900).
3. All text inside the safe margins, and clear of the YouTube duration badge.
4. No text over the face, with an 8 % padding around the detected face box.
5. Text ≥ 13 px at 1/4 size (phone).
6. Headline ≤ 5 words.
7. Face size between 110 and 330 px wide: readable, not oversized.
8. Options visually distinct.

**Checked by review, not automatically:** whether the headline and visual match the lecture, and whether the content is honest (no claims the video doesn't support).

## Approval
Choose an option, then run `python -m ytpipe approve thumbnail --note option_N`. Nothing is uploaded.
