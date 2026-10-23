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

> **Set up and tested on macOS 26.2 (Apple silicon) on 2026-10-23:** 27 of 29 tests pass. The two failures need Lesson 01's work files, which aren't in this copy. Fonts and HDR→SDR colour are ported; slide OCR still isn't (see the table below). No real recording has been rendered on the Mac yet.

## 1. Install
```sh
brew install ffmpeg-full node uv molten-vk vulkan-loader
cd YouTube-Editing
uv venv --python 3.12 --python-preference only-managed .venv && source .venv/bin/activate
uv pip install -r requirements.txt
cd _work/hf && npm install && cd ../..       # HyperFrames 0.8.181 (graphics, thumbnails)
cp assets/fonts/Poppins-*.ttf ~/Library/Fonts/   # libass finds caption fonts by name
python tests/make_fixtures.py                # synthetic fixtures (not in git)
python -m pytest -q tests
```

Add to `~/.zshrc`, then open a new terminal:
```sh
export PATH="/opt/homebrew/opt/ffmpeg-full/bin:$PATH"
export DYLD_FALLBACK_LIBRARY_PATH="/opt/homebrew/lib${DYLD_FALLBACK_LIBRARY_PATH:+:$DYLD_FALLBACK_LIBRARY_PATH}"
```

Why these pieces:
- **`ffmpeg-full`, not `ffmpeg`.** Homebrew's plain `ffmpeg` has no libass (the `subtitles` filter, used for all captions) and no libplacebo. `ffmpeg-full` is keg-only, hence the `PATH` line.
- **`uv`'s Python, not Homebrew's `python@3.12`.** On macOS 26.2, Homebrew's 3.12.15 can't load `pyexpat` (it links the system `libexpat`, which is too old), and that breaks `pip` and `venv`. uv's standalone build bundles its own expat.
- **`molten-vk` + `vulkan-loader` + `DYLD_FALLBACK_LIBRARY_PATH`.** libplacebo needs Vulkan. ffmpeg opens `libvulkan.1.dylib` by name, and macOS doesn't search `/opt/homebrew/lib` by default. macOS strips `DYLD_*` variables when a command passes through a system binary (`/usr/bin/env`, `/bin/sh`), so run `python -m ytpipe ...` from the activated venv. Check with `ffmpeg -v error -init_hw_device vulkan -f lavfi -i nullsrc=d=0.01 -f null -` (no output means it works).
- **esbuild.** npm doesn't run esbuild's install script until it's approved. If HyperFrames rendering fails, run `npm install-scripts approve esbuild` in `_work/hf`.

faster-whisper downloads its model (`medium`) on the first transcription.

## 2. Windows-specific pieces
| Piece | Where | Mac status |
|---|---|---|
| **Slide-text OCR** for the readable split screen | `ytpipe/shorts_focus.py` → `ocr()` calls `ytpipe/ocr_win.ps1` (Windows.Media.Ocr) | Apple Vision OCR (offline), e.g. a small Swift script or `pyobjc-framework-Vision`, returning the same JSON (lines → words with x, y, w, h). Until then, set `shorts.v4.guided_split.enabled` to `false`, or the split falls back to pen ink only after removing the OCR call |
| **Fonts** | `config/defaults.json` → `graphics.font_black` / `font_bold` / `font_semibold`; caption styles in `captions.py`, `shorts.py`, `shorts_v2.py`, `shorts_v3.py` | **Done (2026-10-23).** Segoe UI is replaced by Poppins Black / Bold / SemiBold (OFL, files and `OFL.txt` in `assets/fonts/`). Font paths are repo-relative. Captions need the fonts installed in `~/Library/Fonts` (step 1). **Not yet checked:** Poppins is wider than Segoe UI, so check caption and thumbnail text sizes in the first real render |
| **HDR→SDR colour** (the iPhone's Dolby Vision) | `-init_hw_device vulkan` + `libplacebo` in `render.py`, `shorts_v3.py`, `shorts_v2.py`, `faces.py`, `thumbnails.py`, `thumbs_v2.py` | **Done (2026-10-23):** ffmpeg-full's libplacebo on Vulkan through MoltenVK (step 1). It runs the `color.libplacebo` settings on synthetic 10-bit video. **Not yet checked:** a real iPhone Dolby Vision clip. MoltenVK on the Apple GPU may tone-map differently from the Windows Intel GPU, so **compare the first render with the approved Lesson 01 look before publishing** |
| **npx** | `ytpipe/graphics.py` already chooses `npx` on macOS | No change needed |
| **Paths in lesson configs** | `lessons/<id>/video_project_config.json` | Use Mac paths (`/Users/...`). Start from `templates/video_project_config.example.json` |

## 3. Use
Same as on Windows: see `REUSABLE_SYSTEM_README.md` and `VIDEO_EDITING_WORKFLOW.md`.
```sh
python -m ytpipe init --config lessons/lesson02/video_project_config.json
```

The approval gates, rules and styles in `CLAUDE.md` and the style guides apply unchanged. Lesson 01 itself isn't here; documents that mention its files (`output\lesson01_final.mp4`, `_work\`) describe the Windows original.

`ytpipe/legacy_lesson01.py` only rebuilds Lesson 01 from its Windows work files and won't run here. For the same reason, `tests/test_qa.py::test_lesson01_captions_pass` and `tests/test_render.py::test_geometry_reproduces_lesson01` fail here.
