# Setting up on a Mac

This folder is a copy of the `ytpipe` YouTube editing system, made on 2026-10-22 from the Windows project `D:\YouTube-Editing`. It contains:
- the code
- the settings
- the templates and tests
- the assets (CC BY music, face model, HyperFrames styles)
- the docs

**Not included:**
- raw recordings
- rendered videos
- Lesson 01's work files (`_work\`, `lessons\lesson01\`)
- the HyperFrames `node_modules`

> **The code is copied unchanged from Windows and has not been run on a Mac yet.** Five pieces are Windows-specific (see the table below). Fix them before relying on the output.

## 1. Install
```sh
brew install python@3.12 ffmpeg node
cd mc_yourtubeEdit
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cd _work/hf && npm install && cd ../..       # HyperFrames 0.8.181 (graphics, thumbnails)
python -m pytest -q tests                    # synthetic fixtures; some tests will hit the Windows pieces below
```

faster-whisper downloads its model (`medium`) on the first transcription.

## 2. Windows-specific pieces to change
| Piece | Where | Mac replacement |
|---|---|---|
| **Slide-text OCR** for the readable split screen | `ytpipe/shorts_focus.py` → `ocr()` calls `ytpipe/ocr_win.ps1` (Windows.Media.Ocr) | Apple Vision OCR (offline), e.g. a small Swift script or `pyobjc-framework-Vision`, returning the same JSON (lines → words with x, y, w, h). Until then, set `shorts.v4.guided_split.enabled` to `false`, or the split falls back to pen ink only after removing the OCR call |
| **Fonts** | `config/defaults.json` → `graphics.font_bold` / `font_semibold` (`C:/Windows/Fonts/...`), `ytpipe/thumbnails.py` (`seguibl.ttf`); caption styles name **Segoe UI** (`shorts_v3.py`, `captions.py`, `shorts.py`) | Use a font present on the Mac, e.g. Poppins (OFL, already used in thumbnails v2) or SF Pro / Helvetica Neue, and point the paths to `/Library/Fonts/...`. Check caption sizes after the change |
| **HDR→SDR colour** (the iPhone's Dolby Vision) | `-init_hw_device vulkan` + `libplacebo` in `render.py`, `shorts_v3.py`, `shorts_v2.py`, `faces.py`, `thumbnails.py`, `thumbs_v2.py` | It needs an ffmpeg build with libplacebo (Vulkan through MoltenVK). Check with `ffmpeg -filters \| grep libplacebo`. If it's missing, `inspect` picks the fallback pipeline: **compare its colours with the approved Lesson 01 look before publishing** |
| **npx** | `ytpipe/graphics.py` already chooses `npx` on macOS | No change needed |
| **Paths in lesson configs** | `lessons/<id>/video_project_config.json` | Use Mac paths (`/Users/...`). Start from `templates/video_project_config.example.json` |

## 3. Use
Same as on Windows: see `REUSABLE_SYSTEM_README.md` and `VIDEO_EDITING_WORKFLOW.md`.
```sh
python -m ytpipe init --config lessons/lesson02/video_project_config.json
```

The approval gates, rules and styles in `CLAUDE.md` and the style guides apply unchanged. Lesson 01 itself isn't here; documents that mention its files (`output\lesson01_final.mp4`, `_work\`) describe the Windows original.

`ytpipe/legacy_lesson01.py` only rebuilds Lesson 01 from its Windows work files and won't run here.
