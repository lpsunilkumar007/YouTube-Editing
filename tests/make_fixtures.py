"""Synthetic fixtures (no lecture footage): a 'face' clip and a 'desktop' clip with a KNOWN offset.
desktop: dark slide frames with white text blocks that change at known times + red 'ink' strokes drawn at known times,
         a black bar on the right (slide area 0..1789), a burned-in counter bottom-right; audio = the same chirp/beep
         track as the face clip shifted by OFFSET (so audio xcorr can be tested) - or silent (--silent-desktop).
face:    test pattern with a moving bright 'face' disc; audio = beeps + noise bursts ('speech') with pauses.
Known truth is written to fixtures/truth.json."""
import json, os, subprocess, sys
import numpy as np
from PIL import Image, ImageDraw
from scipy.io import wavfile

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
OFFSET = 7.4            # desktop time = face time + OFFSET
FD, DD = 30.0, 40.0     # durations (s)
SLIDE_T = [0.0, 12.0, 23.5]                     # desktop times of slide changes
INK = [(15.0, 16.0, (300, 600, 700, 640)), (26.0, 27.0, (400, 300, 900, 360))]   # (start, end, line box) desktop time
SR = 48000; FPS = 30

def speech_track(dur, seed=1):
    rng = np.random.default_rng(seed); t = np.arange(int(dur * SR)) / SR; y = np.zeros_like(t)
    # 'sentences': noise bursts shaped like syllables, separated by pauses (known)
    k = 0.8; segs = []
    while k < dur - 1.5:
        L = rng.uniform(1.2, 3.0); segs.append((k, k + L))
        m = (t >= k) & (t < k + L); syl = 0.5 + 0.5 * np.sin(2 * np.pi * 4 * t[m]) ** 2
        y[m] = 0.2 * rng.standard_normal(m.sum()) * syl * (0.6 + 0.4 * np.sin(2 * np.pi * 180 * t[m]))
        k += L + rng.uniform(0.35, 1.0)
    y += 10 ** (-66 / 20) * rng.standard_normal(len(y))          # room tone
    return y.astype(np.float32), segs

def main(silent_desktop=False):
    os.makedirs(OUT, exist_ok=True)
    face_a, segs = speech_track(FD)
    wavfile.write(os.path.join(OUT, "face.wav"), SR, face_a)
    desk_a = np.zeros(int(DD * SR), np.float32)
    if not silent_desktop:
        i0 = int(OFFSET * SR); n = min(len(face_a), len(desk_a) - i0); desk_a[i0:i0 + n] = 0.5 * face_a[:n]
    wavfile.write(os.path.join(OUT, "desk.wav"), SR, desk_a)
    # desktop frames
    fdir = os.path.join(OUT, "desk_frames"); os.makedirs(fdir, exist_ok=True)
    for k in range(int(DD * FPS)):
        t = k / FPS; s = sum(t >= x for x in SLIDE_T)
        im = Image.new("RGB", (1920, 1080), (10, 12, 18)); d = ImageDraw.Draw(im)
        d.rectangle([1790, 0, 1919, 1079], fill=(0, 0, 0))                       # black bar -> slide area 0..1789
        d.rectangle([80, 60, 900 + 200 * s, 120], fill=(235, 235, 240))           # title block differs per slide
        for r in range(3): d.rectangle([120, 220 + r * 140, 700 + 150 * ((r + s) % 3), 250 + r * 140], fill=(200, 200, 210))
        d.text((1700, 1040), f"0{s} / 03", fill=(150, 150, 160))                 # burned-in counter
        for a, b, (x0, y0, x1, y1) in INK:
            if t >= a:
                u = min(1.0, (t - a) / (b - a)); d.line([x0, y0, x0 + (x1 - x0) * u, y0 + (y1 - y0) * u], fill=(220, 30, 40), width=6)
        im.save(os.path.join(fdir, f"{k:05d}.png"))
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", str(FPS), "-i", os.path.join(fdir, "%05d.png"),
                    "-i", os.path.join(OUT, "desk.wav"), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-c:a", "aac",
                    "-shortest", os.path.join(OUT, "desktop.mkv")], check=True)
    # face: moving bright disc on a pattern; slight dark border
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=s=1920x1080:r={FPS}:d={FD}",
                    "-i", os.path.join(OUT, "face.wav"), "-vf", "drawbox=x=860+80*sin(t/3):y=300:w=220:h=260:color=0xE0B090@1:t=fill",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-c:a", "aac", "-shortest", os.path.join(OUT, "face.mp4")], check=True)
    for f in os.listdir(fdir): os.remove(os.path.join(fdir, f))
    os.rmdir(fdir)
    json.dump({"offset_s": OFFSET, "slide_changes_desktop": SLIDE_T[1:], "ink": INK, "speech_segments_face": segs,
               "slide_area": [0, 0, 1790, 1080], "counter_box": [1690, 1030, 1800, 1065], "desktop_audio_silent": silent_desktop},
              open(os.path.join(OUT, "truth.json"), "w"), indent=1)
    print("fixtures written to", OUT)

if __name__ == "__main__":
    main("--silent-desktop" in sys.argv)
