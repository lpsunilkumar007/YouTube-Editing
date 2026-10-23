# Thumbnail style (v2, premium)

**Implemented in:**
- `ytpipe\thumbs_v2.py`: layouts, cut-out, QA
- `ytpipe\faces.py`: frame analysis
- `assets\thumbnails\render_html.js`: headless Chrome render

**Input:** `thumbnails\thumbnail_input_v2.json`, plus per-option `.html` files that you can edit. **Command:** `python -m ytpipe thumbnails --config …`

v1 (Pillow text and boxes) is retired as the default, because it looked like a lecture slide.

## v3 rules: what successful channels do (research, 2026-10-23)

The v2 options for Lesson 02 were technically clean but weak as thumbnails: they repeated the title, used a mid-word frame and added decorative graphics. These rules come from creator-tool guidance ([vidIQ CTR guide](https://vidiq.com/blog/post/youtube-custom-thumbnails-ctr/), [vidIQ design tips](https://vidiq.com/blog/post/youtube-thumbnail-design-tips/), [thumbnailtest.com](https://thumbnailtest.com/guides/youtube-thumbnail-explained/)) and analyses of top creators ([Kapwing, faces](https://www.kapwing.com/resources/the-youtube-thumbnail-faces-that-attract-the-most-views/), [Income School](https://incomeschool.com/how-to-make-thumbnails-like-mrbeast/)). These are practitioner guides, not controlled studies, so test with YouTube's **Test & Compare** (up to 3 variants) when possible.

1. **Start from the video's idea, not its title.** Take the one surprising or useful point the viewer gets, written in the description and content brief. Lesson 02: "don't start with code, start with a flowchart on copy and pen".
2. **Thumbnail and title work together and never repeat each other.** The title says what the video is ("Learn Programming from Zero"); the thumbnail gives the hook ("DON'T CODE FIRST!").
3. **2–4 huge words**, one of them on a yellow highlight block (#FACC15, dark text). White words get a dark outline. They must be readable when the thumbnail is about 160 px wide on a phone.
4. **One idea, one focal point.** A single visual that shows the payoff or a **wrong vs right** contrast (red ✕ / lime ✓), or the **journey** (0 → … → result). No decorative graphics.
5. **Large face, eye contact, a clear expression** (confident smile, curious, surprised), mouth closed or clearly expressive, never mid-word. The head box can be up to 400 px wide (v3 QA).
6. **Bright accents on the dark brand background:** yellow highlight, red = wrong, lime = right/result, cyan for diagrams. Indian education audiences respond to vibrant thumbnails; the navy keeps them on-brand.
7. **Honest:** every promise must be in the video. A misleading thumbnail costs retention, which costs reach.
8. **Same template every lesson** (fonts, highlight block, face side) so the channel is recognisable in a feed.

**Best photos:** a video frame of your face is only about 280 px wide (Lesson 02), so it looks soft enlarged. Most creators **shoot a separate still for the thumbnail**, with the iPhone camera at the desk right after recording, using a deliberate expression for the video's hook. It's still your real face. Put it in `lessons\<id>\thumbnails\photos\`; until the generator reads photos, give it to Claude to use.

**v3 layouts** (`thumbs_v2.py`, input `thumbnail_input_v3.json`, output `thumbnail_v3_N.png`):

| Layout | Composition | Use for |
|---|---|---|
| `versus` | Headline top-left; wrong tile (red ✕) → right tile (lime ✓); large face right | "Don't do X, do Y" lessons |
| `journey` | Headline top-left; 3–4 node path (`nodes`: text, `flow`, `app`); large face right | Roadmaps, "from zero to …", step series |
| `paper` | Face left; headline right; notebook page with a red-pen flowchart and a pen | Copy-and-pen, flowchart and algorithm lessons |
| `stairs` | Headline top-left; rising staircase of stages (`steps`, low to high, optional `icons`: `flow`, `array`, `app`), star on the top step; large face right | Course intros, "basic to advanced", levels |

Options: `headline` (lines), `mark` (words on the yellow block), `frame_t` (pinned face frame), `person_h` / `person_dx` / `size`. Fonts load from `assets\fonts` (no network). Frames are taken at the source's full resolution.

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
