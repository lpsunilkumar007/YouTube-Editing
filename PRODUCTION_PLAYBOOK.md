# Production playbook: problems we have solved, and what now happens by default

Built from Lessons 02–04 (2026-10-23 to 2026-10-26). For each problem: how it showed up, the cause, and the default fix,
marked **auto** (the pipeline does it), **Claude** (Claude does it on every video without being asked) or **you** (needs
your decision). New lectures follow this playbook. When a new check is added, Claude also runs it over the videos
already delivered and reports what it finds, but changes a delivered video only after you say yes.

## Default run for a new lecture

| # | Step | Command | Default checks (cases below) |
|---|---|---|---|
| 1 | Inspect recordings | `inspect` | |
| 2 | Transcribe once, then Claude cleans `transcript.txt` (Roman Hinglish, glossary, `≈` for reconstructed lines) | `transcribe` | |
| 3 | Analyse desktop, speech and face | `analyze` | blank screens (C6) |
| 4 | Spoken cut/pause instructions, retakes, **speech the recognizer lost** | `retakes` | C2, C3 |
| 5 | Sync from pen/word anchors | `ink`, `sync` | C1 |
| 6 | Timeline: Claude adds chips, title and chapters ⛔ `timeline` | `timeline` | C6, C9 |
| 7 | Sample ⛔ `preview`, full render ⛔ `full_render` | `sample`, `render` | C7, C8, C6 QA |
| 8 | Fact check (cut wrong claims, then re-render) | `factcheck` | C4, C5 |
| 9 | Captions, then the listen-check page for you | `captions`, `listen` | C10 |
| 10 | Title research, then metadata | `metadata` | C11 |
| 11 | Thumbnails ⛔ `thumbnail` | `thumbnails` | C12 |
| 12 | Shorts: candidates, Claude curates, ⛔ `shorts`, render | `shorts`, `shorts-render` | C13 |
| 13 | Blog, WordPress dry run, package | `blog`, `wp-publish`, `package` | C14 |

## Cases

### C1. Pen writing appears seconds after (or before) the explanation
- **Seen:** Lesson 04: the pen was 4.8 s late ("pen writing 3–4 s delayed"). Lesson 03: 0.7 s early.
- **Cause:** OBS records no mic, so the camera and desktop clocks are aligned by hand. In Lesson 04 the written "4" was matched to the second time "4 plus 5" was said, not the first. QA's pen and slide frame checks only prove that the render shows the planned frames; they cannot catch a wrong offset.
- **Default:**
  - **auto:** `sync` requires pen/word anchors on a silent desktop recording (`timelines/sync_anchors.json`). The offset is the second-smallest desk − face, so ink never shows before its word.
  - **auto:** fewer than 5 pairs, pairs more than 2 s apart, or a manual offset more than 0.3 s from the anchors stops the stage.
  - **auto:** a lecture with no writing needs `sync.anchors_waived` with a reason.
  - **auto:** the package INDEX says whether the sync was measured or only confirmed by you.
  - **Claude:** picks 10+ anchors from different parts of the lecture (dictated numbers, labels written while said), using `ink --from/--to` and desktop crops. After the render, Claude checks a few anchors in the final video frame by frame (ink 0–1.5 s after the word).
  - **Anchor on shapes drawn while you name them** ("start kar liya" as the Start oval appears, "input" as the input box appears). Writing done while **reading a slide aloud** does not line up with the words: on Lesson 05 those pairs gave +110.7 s and you saw the pen 2–3 s late; draw-while-naming pairs gave +113.3 s.
  - Your viewing is the final check: if the pen still looks late or early, the anchors are wrong, not your eyes.
  - Pen-tap audio, hand motion (gestures swamp the writing) and automatic numeral matching were tried and are **not reliable**.
- **You:** an OBS mic track would make this automatic (audio cross-correlation).

### C2. A spoken instruction ("in sab ko cut kar dena", "pause here, editor…") is still in the video
- **Seen:** Lesson 04's end fumble survived, because the recognizer dropped those 8 s, so the instruction never reached the detector.
- **Default:**
  - **auto:** `retakes` cuts pause instructions (from the measured pause before the instruction to the restart) and spoken cut instructions, and flags repeated starts.
  - **auto:** any stretch where the level map shows talking but no words were transcribed is **re-heard on its own, in Hindi and in English**. The text goes into `reports/content_cuts.md`, and a cut/pause instruction inside it is flagged. On Lesson 04 this found "हाँ इन सब को काट कर दें" by itself.
  - **Claude:** reads every re-heard stretch, adds the cut (`content_cuts.json`, with before/removed/after) and splits the transcript line so the removed part is marked `—cut—`.
- **auto:** rerunning `retakes` keeps cuts that were added by hand (fact corrections, fumbles).

### C3. Real teaching is missing from the captions
- **Seen:** Lesson 04: "operators are plus, minus, divide, multiply…" (4:00), the 17 % 5 example, and "N % 2 = 0 hai, to kya yeh even hai?". A guessed `[…]` there was wrong.
- **Cause:** the recognizer stretched one word over seconds of speech it lost.
- **Default:** the same re-hearing as C2. **Claude** adds the lines as `≈` (never as certain), re-runs the fact check and captions, and re-renders any Short whose burned-in captions cover that time.

### C4. Something said in the video is wrong
- **Default:**
  - **auto:** `factcheck` lists claim-like lines. `metadata`, `blog` and `wp-publish` refuse to run until every one has a sourced verdict.
  - **Claude:** also reads the whole transcript for claims the heuristic misses (Lesson 04's operators line had no numbers).
  - **Claude, pre-authorised by you:** a wrong claim is cut (then re-rendered) or corrected in a note. Imprecise claims stay in the speech but are never repeated in written copy: description, blog, Shorts.
  - Lesson 03 was checked retroactively. "Process: a formula" in its blog became "a processing step, such as a calculation".

### C5. Fact-check verdicts attach to the wrong claim after a transcript edit
- **auto:** verdicts carry their claim text and match by it. A changed line shows up as "no verdict" and gets a fresh check.

### C6. A black "End of slide show" screen, or slides from another lecture flashing
- **Seen:** Lesson 04 (fixed by hand at first). Lesson 03: 4 s at 5:50 that showed a later lecture's modulus slide around the black screen.
- **Default:**
  - **auto:** `analyze` finds blank slide areas. `timeline.widen_blanks` extends each one over slide changes within 2 s.
  - **auto:** `timeline.cover_blanks` puts the presenter (layout A) over it, pause to pause.
  - **auto:** full-video QA reports any blank still shown.

### C7. Picture drifting behind the sound at joins
- **auto:** every segment is rendered frame-exact from t = 0, and a test checks the joined video for timestamp gaps.

### C8. Music silent in long lessons (after 6:15)
- **auto:** swells wrap inside the track, and QA flags planned music that is silent.

### C9. Lesson numbers on screen or in copy
- **Claude:** the kicker is the topic ("ALGORITHM BASICS • DECISIONS"). Titles, blog, thumbnails and Shorts never carry "Lesson N". Your slides may show one; that's yours.

### C10. Caption lines that are guesses (`≈`)
- **auto:** `listen` builds a page with a play button (your voice from the camera, no music), the final-video time and the current text for every `≈` line. Line IDs use the face time, so they survive edits.
- **Claude:** publishes it as a private page that saves your answers, reads them back, fixes the transcript, rebuilds the captions and re-renders affected Shorts.
- **You:** about 6 minutes of listening per video.

### C11. Titles and description
- **Claude:** dated title research (sources, search phrases) on every video.
- **auto:** checks the searched phrase comes first, the title is 60 characters or less, there are no lesson numbers, clickbait or ALL CAPS, the description has 200+ words, there are 5–15 tags, and the chapters follow YouTube's rules.

### C12. Thumbnails
- **Seen:**
  - every video frame caught you mid-word or looking down
  - one option's "ODD" pill sat behind your shoulder while QA passed
- **Default:**
  - **Claude:** scans the face densely (4 fps around good moments) for a closed mouth and eyes on camera, and picks layouts from the video's idea, not its title (e.g. the decision diamond for if-else).
  - **auto:** QA now checks text against your whole cut-out (shoulders, arms), not just the face.
  - **You:** a still photo taken for the thumbnail right after recording is sharper than any video frame.

### C13. Shorts
- **Claude:**
  - picks whole ideas: starts on a full sentence, stays clear of the lecture's cuts, and leaves out unverified claims
  - keeps titles honest (no "in 1 minute" for a 69-second clip)
  - moves an unchosen Short's copy to `shorts/not_chosen/`
- **auto:** `shorts-render` refuses a clip that starts or ends while you are audibly speaking (a clipped syllable caught on Lesson 03's flowchart-symbols Short), and notes a jump across a lecture cut.
- **Claude:** re-renders Shorts whenever the long video's sync or captions change. Old files are kept in a sub-folder.

### C14. Blog and package
- **auto:**
  - the blog's Shorts list is built from the Shorts copy files, using the rendered length
  - `package` clears stale copies
  - INDEX shows the fact-check and sync status
  - the blog cover is the approved thumbnail

### C16. The greeting is cut off at the start
- **Seen:** Lesson 05 started at 9.1 s, after "Hello programmers, welcome back to the series" (6.6 s); the recognizer missed those words. Lesson 04 also lost "Hello programmer, welcome back to another video".
- **auto:** the edit starts where your voice starts (`timeline.voice_onset`), not at the first transcribed word.
- **Claude:** re-hears the first seconds and puts the greeting in the transcript.
- **auto (your rule):** the greeting is always written **"Hello programmers"** (plural) in transcripts and captions, even when the recognizer hears "Hello programmer" (`captions.phrases` in `config/defaults.json`).

### C15. Re-renders
- **Claude:**
  - never overwrites a final: the previous one is renamed with a suffix that says why (`_v3_pen_late`)
  - sends 540–720p previews of the changed moment
  - re-checks QA, length and picture/sound match after every render
  - verifies a fix in the rendered video, not only in the plan

## What you can do while recording
- Add a mic track to OBS: sync then becomes automatic.
- When you fumble, say clearly "**isko cut kar dena**" and restart the sentence from its beginning.
- For a break: "**pause here, editor**" … "**start now**".
- Write while you say the word (it makes sync anchors), and don't click past the last slide.
