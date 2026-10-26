"""Face-frame analysis for thumbnails (real frames from the ORIGINAL face recording, approved colour pipeline).

One continuous decode per face shot at `fps` (fast; no per-frame seeking), MediaPipe FaceLandmarker (blendshapes +
head pose) on every frame, plus sharpness / exposure of the face region. Scores per thumbnail concept:
  confident  : eyes open, looking at the lens, frontal, mouth closed or soft smile
  explaining : eyes open, looking at the lens, frontal, natural speaking mouth allowed
  curious    : eyes open, brows raised and/or slight head tilt, frontal-ish
Hard rejects: eyes closed/blinking, looking down, head turned > 20 deg, blurred, face too small.
If no frame passes for a concept, that is REPORTED (no expression is ever synthesised)."""
import json, math, os, subprocess
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL = os.path.join(ROOT, "assets", "models", "face_landmarker.task")

def _landmarker():
    import mediapipe as mp
    from mediapipe.tasks.python import vision, BaseOptions
    opt = vision.FaceLandmarkerOptions(base_options=BaseOptions(model_asset_path=MODEL), output_face_blendshapes=True,
                                       output_facial_transformation_matrixes=True, num_faces=1)
    return mp, vision.FaceLandmarker.create_from_options(opt)

def _pose(m):
    """yaw, pitch, roll in degrees from the 4x4 facial transformation matrix."""
    R = np.array(m)[:3, :3]
    yaw = math.degrees(math.atan2(-R[2, 0], math.hypot(R[2, 1], R[2, 2])))
    pitch = math.degrees(math.atan2(R[2, 1], R[2, 2])); roll = math.degrees(math.atan2(R[1, 0], R[0, 0]))
    return yaw, pitch, roll

def decode(cfg, src, a, b, fps, pipeline, w=1280, h=720):
    from . import render
    crop = render.wide_crop(src)                       # sources wider than 16:9 are cropped, not stretched
    chain = (render.face_filter(cfg, pipeline, w, h, crop, "yuv444p") + ",scale=in_color_matrix=bt709:in_range=tv,format=rgb24"
             if pipeline == "libplacebo" else render.face_filter(cfg, pipeline, w, h, crop, "rgb24"))
    cmd = ["ffmpeg", "-v", "error", *(["-init_hw_device", "vulkan"] if pipeline == "libplacebo" else []), "-ss", f"{a:.3f}", "-t", f"{b - a:.3f}",
           "-i", src, "-vf", f"fps={fps},{chain}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE); k = 0
    while True:
        buf = p.stdout.read(w * h * 3)
        if len(buf) < w * h * 3: break
        yield a + k / fps, np.frombuffer(buf, np.uint8).reshape(h, w, 3); k += 1
    p.wait()

def analyse(cfg, spans, pipeline, fps=1.0, out_json=None):
    import cv2
    mp, lm = _landmarker(); rows = []
    for a, b in spans:
        for t, fr in decode(cfg, cfg["sources"]["face_camera"], a, b, fps, pipeline):
            r = lm.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(fr)))
            if not r.face_landmarks: continue
            pts = np.array([(p.x * fr.shape[1], p.y * fr.shape[0]) for p in r.face_landmarks[0]])
            x0, y0 = np.maximum(pts.min(0), 0); x1, y1 = np.minimum(pts.max(0), (fr.shape[1], fr.shape[0])); bs = {c.category_name: c.score for c in r.face_blendshapes[0]}
            if x1 - x0 < 8 or y1 - y0 < 8: continue                      # face (almost) outside the frame
            yaw, pitch, roll = _pose(r.facial_transformation_matrixes[0])
            roi = cv2.cvtColor(fr[int(y0):int(y1), int(x0):int(x1)], cv2.COLOR_RGB2GRAY)
            rows.append({"t": round(t, 2), "box": [round(v * 1920 / fr.shape[1]) for v in (x0, y0, x1 - x0, y1 - y0)],
                         "yaw": round(yaw, 1), "pitch": round(pitch, 1), "roll": round(roll, 1),
                         "blink": round(max(bs["eyeBlinkLeft"], bs["eyeBlinkRight"]), 3),
                         "look_down": round(min(bs["eyeLookDownLeft"], bs["eyeLookDownRight"]), 3),
                         "look_side": round(max(bs["eyeLookOutLeft"], bs["eyeLookOutRight"], bs["eyeLookInLeft"], bs["eyeLookInRight"]), 3),
                         "jaw": round(bs["jawOpen"], 3), "smile": round((bs["mouthSmileLeft"] + bs["mouthSmileRight"]) / 2, 3),
                         "brow_up": round(max(bs["browInnerUp"], (bs["browOuterUpLeft"] + bs["browOuterUpRight"]) / 2), 3),
                         "sharp": round(float(cv2.Laplacian(roi, cv2.CV_64F).var()), 1), "light": round(float(roi.mean()), 1)})
    if out_json: json.dump(rows, open(out_json, "w"), indent=0)
    return rows

def usable(r):
    """Hard rejects (returns reason or None)."""
    if r["blink"] > 0.45: return "eyes closed/blinking"
    if r["look_down"] > 0.45: return "looking down"
    if r["look_side"] > 0.6: return "looking away"
    if abs(r["yaw"]) > 20: return "head turned"
    if r["box"][2] < 180: return "face too small"
    if r["sharp"] < 40: return "blurred"
    if not 70 <= r["light"] <= 210: return "badly exposed"
    return None

CONCEPTS = {
    "confident": lambda r: 2 * (1 - r["blink"]) + 1.5 * (1 - r["look_down"]) + max(0, 1 - abs(r["yaw"]) / 12) + 2 * min(r["smile"], 0.5)
                           - 3 * max(0, r["jaw"] - 0.15) + math.log1p(r["sharp"]) / 4,
    "explaining": lambda r: 2 * (1 - r["blink"]) + 1.5 * (1 - r["look_down"]) + max(0, 1 - abs(r["yaw"]) / 12)
                            + (1.0 if 0.08 <= r["jaw"] <= 0.35 else 0) + min(r["smile"], 0.4) + math.log1p(r["sharp"]) / 4,
    "curious": lambda r: 2 * (1 - r["blink"]) + 1.2 * (1 - r["look_down"]) + 3 * r["brow_up"] + min(abs(r["roll"]), 12) / 12
                         - 2 * max(0, r["jaw"] - 0.3) + math.log1p(r["sharp"]) / 4,
}

def pick(rows, concept, n=4, min_gap=15.0):
    ok = [r for r in rows if usable(r) is None]
    ranked = sorted(ok, key=lambda r: -CONCEPTS[concept](r)); out = []
    for r in ranked:
        if all(abs(r["t"] - p["t"]) >= min_gap for p in out): out.append(dict(r, score=round(CONCEPTS[concept](r), 2)))
        if len(out) == n: break
    return out

def rejection_summary(rows):
    from collections import Counter
    return dict(Counter(usable(r) or "usable" for r in rows))
