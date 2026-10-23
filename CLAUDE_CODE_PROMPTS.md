# Claude Code prompts, in order

Run `claude` from `D:\YouTube-Editing`. Paste one prompt at a time and wait for each step to finish. Review the result before moving on.

---

## Step 1: Analyse the raw recordings

```
Read CLAUDE.md and reference_style_analysis.md, then do the "Current task" in CLAUDE.md on the two files in raw\.

Requirements:
- Install anything missing first (ffmpeg via winget, Python packages faster-whisper, numpy, scipy). Never modify files in raw\.
- Report duration, resolution, frame rate and every audio stream for both files.
- Do not assume both recordings started at the same time. Find the offset by audio cross-correlation, then confirm it at the start, middle and end, and report drift in ms and ppm.
- Pick the best audio track as the main narration and explain why (noise floor, loudness, clipping).
- Transcribe with faster-whisper (large-v3 if the PC can handle it, otherwise medium). Write the transcript in Hinglish (Hindi in Roman script, English technical terms as spoken), with timestamps on the master timeline plus the matching face-cam and desktop times.
- Sample desktop frames to identify the programming concepts, code shown, demos, and on-screen activity per section.
- List unnecessary pauses (>1.5 s) and repeated takes / false starts with exact timestamps, and propose cuts that apply to BOTH tracks so they stay in sync.
- If sync cannot be confirmed reliably, stop and tell me the problem instead of continuing.
- Do not render any video.

Save these in D:\YouTube-Editing\:
transcript.txt, synchronization_report.md, video_content_analysis.md
```

**Check before moving on:** open `synchronization_report.md`. It should state one offset, confirmed at the start, middle and end, with drift close to 0. If it reports a problem, sort that out before Step 2.

---

## Step 2: Build the editing plan (no rendering)

```
Using video_content_analysis.md, synchronization_report.md, transcript.txt and reference_style_analysis.md, create a professional editing plan in D:\YouTube-Editing\editing_timeline.md. Do not render.

Layout rules:
LAYOUT A - FACE FULL-SCREEN: when I introduce a topic, explain theory, speak directly to students, or summarize.
LAYOUT B - DESKTOP + FACE OVERLAY: when I demonstrate coding, flowcharts, Power Apps, browser features or software. Desktop fills the screen; face in the lower-right corner at 20-24% of video width; keep the face-camera aspect ratio; never cover important code, menus, buttons or diagrams.
LAYOUT C - ZOOMED DESKTOP + FACE OVERLAY: when I explain a specific code line, function, property, setting or UI element. Smooth zoom (1.2x-1.8x) to the relevant region, eased in and out; text must stay readable; keep the face overlay lower-right unless it blocks the content, then move it or hide it briefly.

Base every decision on my narration (transcript) and visible desktop activity (check frames at each zoom target to get the real region in desktop pixels x,y,w,h).

The timeline must be a table with: Output timestamp | Original face-camera timestamp | Original desktop timestamp | Topic | Layout | Zoom target (region + zoom level, or none) | Suggested caption | Suggested graphics | Editing notes.

Also include:
- The cut list (removed pauses and retakes) applied to both tracks, and the resulting final duration.
- Exact overlay geometry for the output resolution (size, position, margins).
- Intro and outro structure and chapter markers, following reference_style_analysis.md (hard cuts, simple highlights, no music under speech, voice about -14 LUFS).
- A short list of any sections where the layout choice was uncertain.

Then show me a summary and wait for my approval.
```

**Check before moving on:** read `editing_timeline.md`. Tell Claude Code what to change, e.g. "make 04:10–05:30 Layout C on line 12" or "remove the retake at 12:05". Repeat until you're happy.

---

## Step 3: Render a short test clip first

```
Based on the approved editing_timeline.md, render ONLY a 60-90 second test clip that includes at least one Layout A, one Layout B and one Layout C section, with the zoom in/out, the face overlay and at least one cut. Use ffmpeg, output 1920x1080, same frame rate as the desktop recording, H.264 + AAC, audio from the selected narration track normalised to -14 LUFS. Save to D:\YouTube-Editing\renders\test_clip.mp4. Do not touch raw\. Tell me what to look for when I review it.
```

**Check before moving on:** watch the clip. Make sure lips match the voice, code stays readable when zoomed, the overlay doesn't cover anything important, and the cuts aren't jarring.

---

## Step 4: Render the full video

```
The test clip is approved [add any fixes here]. Render the full video from editing_timeline.md with the same settings to D:\YouTube-Editing\renders\final.mp4. Afterwards verify: total duration matches the plan, audio/video sync is correct at the start, middle and end (check lip sync on face-camera sections), loudness is about -14 LUFS with true peak <= -1 dBTP, and no black or frozen frames. Report the results.
```

---

## Step 5: YouTube extras (optional)

```
From transcript.txt and editing_timeline.md, create youtube_details.md with: a title (3 options), a description, chapter timestamps on the FINAL video timeline, tags, and an SRT subtitle file final.srt matched to the final edited timing.
```

---

## Tips
- Start a long step with: "Work step by step and tell me your progress."
- If it stops on a question about permissions, answering "yes" is fine for installs and for reading or writing files in this folder.
- If something looks wrong, describe it in plain words, e.g. "at 07:30 in the final video my face covers the button".
