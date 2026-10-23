"""Import Lesson 01's finished edit (read-only) into the generic formats: timelines/edl.json and the analysis caches.
The EDL comes from the segment list actually rendered (lecture_plan_v9.SEGMENTS) and the frame-exact segment starts in
_work/v9_audio_plan.json, so chapters and captions match output/lesson01_final.mp4."""
import json, os, shutil, sys
import numpy as np

def run(cfg):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); W = os.path.join(root, "_work")
    sys.path.insert(0, W)
    import lecture_plan_v9 as P                                   # noqa: E402 (lesson-specific, read-only)
    plan = json.load(open(os.path.join(W, "v9_audio_plan.json")))
    edl = [{"layout": l, "face_in": a, "face_out": b, "edit_start": s, "frames": n}
           for (l, a, b), s, n in zip(P.SEGMENTS, plan["segment_starts"], plan["frames"])]
    os.makedirs(cfg["paths"]["timelines"], exist_ok=True); os.makedirs(cfg["paths"]["analysis"], exist_ok=True)
    json.dump({"source": "lesson01 v9 render", "offset_s": 100.0, "fps": 30, "segments": edl,
               "duration": sum(e["frames"] for e in edl) / 30}, open(os.path.join(cfg["paths"]["timelines"], "edl.json"), "w"), indent=1)
    shutil.copy(os.path.join(root, "transcript.txt"), os.path.join(cfg["paths"]["transcripts"], "transcript.txt"))
    shutil.copy(os.path.join(W, "face_track.npy"), os.path.join(cfg["paths"]["analysis"], "face_track.npy"))
    return edl
