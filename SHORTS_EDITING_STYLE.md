# Shorts / Reels editing style (v4, approved 2026-10-22)

Implemented in `ytpipe\shorts_v3.py` (layouts), `ytpipe\shorts_focus.py` (guided split) and `ytpipe\shorts_audio.py` (music), run with `python -m ytpipe shorts-render --clips … --style v4`. Settings: `config\defaults.json` → `shorts.v4`. Output: `lessons\<id>\shorts\v4\short_NN.mp4` (earlier versions are kept). **Nothing is rendered until you approve** the candidates (`approve shorts`).

> **Permanent rule.**
> **Long-form videos:** use the approved circular lower-right picture-in-picture during desktop explanations.
> **Short-form videos:** use rectangular split-screen, full-frame presenter or desktop-focused layouts.
> **Never automatically reuse the long-form circular overlay for vertical Shorts.**

## Output
1080×1920 (9:16), 30 fps, MP4 (H.264 + AAC).

**Pictures** always come from the **original** iPhone face recording, with the approved libplacebo + Dolby Vision HDR→SDR conversion, and from the original desktop recording. They're taken at exactly the face and desktop times the final edit uses, so pen strokes stay in sync. The finished horizontal video is used only for the **audio** of the same span, muxed once, so voice, music and sync are identical to the lecture.

There are no face filters or enhancements, and the footage is never stretched (scale-to-fit plus navy padding).

## Layouts
| Layout | When | Composition |
|---|---|---|
| **B: full-frame presenter** | Hook (first sentence), questions, direct explanations, takeaways, conclusion (last sentence) | 9:16 crop of the original camera (608×1080 source → 1080×1920), centred on your measured face, with head-and-shoulders room |
| **A: rectangular split screen** | Explaining code, diagrams or concepts on the desktop | **Desktop** full width on top: in v4 a 1080×900 box that follows the explained region (see *Guided split screen*); in v3 the whole content region, fitted and padded (never stretched). **Caption band** (130 px) under it. **Presenter** as a full-width rectangle below, with your face in its upper part. No circles, bubbles or borders |
| **C: desktop focus** | Concentrated writing or a key code step | Zoom on the region being worked on: the new ink of that span (robust box, specks ignored) and its surroundings. Edges are snapped between cards and columns, so a card is never sliced. Presenter hidden, captions below the desktop. A text line sliced by the zoom's side edges near its top or bottom (e.g. a long heading) is cut off cleanly when ≥ 85 % of the ink stays visible, otherwise shown whole |

## Automatic layout selection (from your narration and the desktop)
1. **Hook:** the first sentence of the clip → **B**.
2. **Middle, while a slide is shown** → **A**.
3. **Concentrated writing for ≥ 3 s** → **C**, **at most one zoom per Short** (the longest writing run), so A and C never alternate. Concentrated means the new ink of consecutive 0.5 s windows stays within 45 % of the slide width. Ink spread across a diagram (e.g. circling INPUT, PROCESS and OUTPUT in turn) keeps **A**, because the whole diagram matters there.
4. **Conclusion:** the last sentence → **B**.

**Every switch is a hard cut placed in a measured speech pause.** Parts shorter than 3 s are merged, so there are no unnecessary switches.

## Lecture cuts
A Short follows the lecture's own cuts (pauses removed in the main edit). The picture is cut at the same face times, so the lecture audio and the captions stay in sync. Before this fix (2026-10-22), Short 01 drifted 1.5 s after its jump cut.

## Music (optional, per Short)
Implemented in `ytpipe\shorts_audio.py`; see `lessons\lesson01\shorts\shorts_music_report.md`.

**Voice:** rebuilt from the camera with the approved chain (no lecture card ticks).

**Music:**
- A licensed track, high-passed at 110 Hz.
- **20 dB under speech**; rises up to 5 dB in pauses ≥ 0.35 s (80 ms attack, 0.6 s release).
- Its start is chosen so beats land on the existing cuts. Cuts never move.

**Master:** −14 LUFS, true peak ≤ −1.5 dBTP.

**Licensing:** record every track in `config\credits.json`, and put its credit in the Short's description or caption.

## Approved v4 style (Short 01 review, 2026-10-22)
| Item | Setting |
|---|---|
| **Pacing** | Narration first. Every measured pause ≥ 0.35 s is shortened to 0.25 s by a jump cut inside the pause; never inside a word or sentence |
| **Captions** | 2–4 word chunks of the reviewed SRT. Segoe UI Black 68 px, white with a black outline, glossary terms in **lime**. Hard switches, no animation |
| **Music** | **Tech Live** (Kevin MacLeod, CC BY 4.0) **20 dB under the narration**, rising up to 5 dB in pauses (automatic ducking), high-passed at 110 Hz. Don't raise it to 17 dB without the user's go-ahead. Credit in every description and caption (`config\credits.json` → `tech_live_macleod`, `attribution_shorts`) |
| **Sound effects** | None. The lecture's card ticks are not carried over |
| **Presenter** | Natural footage, **no extra zoom** beyond the approved crops (B: 608×1080 source; A: full-width rectangle). No punch-ins |
| **Transitions** | Hard cuts only, in measured pauses. No decorative transitions or silent animations |
| **Hook title** | Optional: at most 2 s at the start, never over the face, restating the spoken hook. **No permanent title bar.** Off by default |
| **Master** | −14 LUFS, true peak ≤ −1.5 dBTP |

## Guided split screen (readable desktop, v4)
In layout **A** the desktop half follows what is being explained instead of showing the whole slide (`ytpipe\shorts_focus.py`).

1. **What is being explained**, per narration line of the A part:
   - the **new pen ink** drawn while the line is spoken (strongest signal), and
   - the **slide text the line names**: Windows' built-in offline OCR of the original desktop frame (`ytpipe\ocr_win.ps1`, cached in `shorts\ocr_cache.json`) matched to the English words of the Hinglish line ("hardware", "touch", "operating system" …). Words are grouped in blocks and rows; big heading words weigh more than body text. Slide-title words are the topic and count little.
   - When the pen and the words disagree, the pen wins.
2. **Crop:** that region plus up to 70 px of context, into a fixed **1080×900 desktop box**, never zoomed past 1.2× (900 source px wide).
   - **No word is ever cut at a crop edge** (you, 2026-10-22: wider crops rather than clipped words). Every crop edge lies in a gap between text lines. Lines are found twice: by OCR, and from the pixels (every printed letter that isn't pen ink, joined into lines; dividers ignored), so words OCR misses or that sit under the pen are protected too. When the explained region touches a line, the whole line is in frame, even if the crop gets wider and the text smaller.
   - Among the crops that cut nothing, the one with the largest text wins, weighted by how much of the box it fills (a thin strip in the tall box wastes the screen). A crop that doesn't match the box shape is padded, never stretched.
   - The C desktop-focus zoom follows the same rule: it keeps the pen writing and is widened until no line is cut, never zoomed further than before.
3. **Shots:** neighbouring lines about the same region share one framing (the union, when it stays readable). A line naming nothing keeps the current framing. Shots last ≥ 4 s. Each reframe is a hard cut in a measured pause, preferably a tightened jump cut.
4. **Context:** when the opening line of an A part names nothing in particular (e.g. "teen-chaar tarah ke parts"), the whole content is shown first. Regions too wide to read in a crop fall back to the whole content.
5. **Fixed per part:** the split proportions (desktop 900 px, caption band 130 px, presenter 890 px) and the presenter crop don't change at a reframe. Only the desktop moves.
6. Nothing is generated: every frame is a crop of the recorded desktop.

Typical result in Lesson 01: desktop text at **0.9–1.2×** source size, against **0.59–0.65×** for the whole slide in v3.

## Captions
- **Source:** the lecture's Hinglish SRT. Glossary terms (CPU, input, program, …) are highlighted in **lime**.
- **Style (v4):** chunk captions as above. (v3: Segoe UI Semibold 52 px lines on translucent navy.)
- **Position by layout:**
  - **A:** in the band between the desktop and the presenter (never over code or your face).
  - **C:** under the zoomed desktop.
  - **B:** at chest height, ending at y 1470.
- **Safe zones:** nothing important below y 1480 or in the right-hand 190 px (Shorts/Reels title, handle and buttons).

## Validation preview (Lesson 01)
`output\shorts_layout_preview.mp4`, 28.5 s, face time 733.75–762.20:

| Part | Face time | Layout | What you say |
|---|---|---|---|
| Hook | 733.75–739.66 | B (crop x 724) | "agar main bolun, to program ko teen cheezon ki zaroorat hoti hai" |
| Explanation | 739.66–749.79 | A (desktop 0.64×, face rectangle) | input → process → output, while you circle each one |
| Key step | 749.79–758.31 | C (desktop **1.54×**: INPUT card + "Sum of 2 digit" handwriting) | "sum of two digits…" while writing |
| Conclusion | 758.31–762.20 | B (crop x 827) | "…koi bhi two digit ho sakti hain" |

**Checks:**
- Picture matches the original camera at 0 frames offset.
- Audio matches the final mix to within 0.3 ms.
- Automatic Shorts QA passes: 1080×1920, face detected, starts and ends in pauses, no decode errors.

## Known limits
- **Guided split:** OCR sees only English text; a line that names nothing on the slide keeps the previous framing. Since no line may be cut, a long line next to the explained region (a full-width title or summary line) makes that crop wider and the text smaller (as low as about 0.6×, the whole slide). Handwritten pen text isn't protected (the pen is what's being explained, and the crop keeps the new ink in frame anyway). Check the contact sheet.
- **Full-frame presenter** shots are enlarged 1.78× (a 1080 px camera height filling 1920 px), which is unavoidable for 9:16.
- **Split-screen zoom is limited by the ink:** when your pen strokes span the slide, the desktop stays near full width (0.64×) so that every stroke remains visible.
- **The laptop lid** in front of you shows at the bottom of full-frame shots. It falls inside the platform interface zone.

## QA per clip
- Size 1080×1920, 30 fps, duration within limits, no decode errors.
- Face detected in at least 2/3 of 6 sampled frames, counting only presenter parts (A and B; the presenter is hidden in C by design).
- Starts and ends inside speech pauses (no cut-off sentence).
- Picture/sound sync is verified on the validation preview by frame matching against the original camera.
