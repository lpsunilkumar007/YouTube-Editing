"""Stage 'sample': a ~15 s review clip before the full render (replaces the multi-segment preview).

Three ~5 s pieces of the approved timeline, joined: the full-frame presenter, a slide with the circle camera and chips
(around a chip change), and a cut between takes or a layout switch. They are rendered by the full-render code with the
final settings (crops from the full takes, same encoder, same audio chain), so what is approved is what the full render
produces. --at picks the pieces yourself (final-video times in seconds). Output: full_video/sample/sample.mp4 and
sample.json (where each piece sits in the final video, and the sync check of its slide shots at pen strokes and
slide changes: pick a piece with writing or a slide change to verify the offset). Review it, then: approve preview."""
import json, os
from . import pipeline, qa

def _clip(segs, i, a, b, fps):
    snap = lambda t: round(t * fps) / fps
    return {**segs[i], "face_in": snap(max(a, segs[i]["face_in"])), "face_out": snap(min(b, segs[i]["face_out"])), "parent": i}

def _edit_starts(segs, fps):
    out, t = [], 0.0
    for s in segs: out.append(t); t += round((s["face_out"] - s["face_in"]) * fps) / fps
    return out

def pick(plan, fps, n=5.0, at=None):
    """[(label, [clipped segments])]. Pieces never overlap; a missing kind (no slide, no cut) is skipped."""
    segs = plan["segments"]; E = _edit_starts(segs, fps); used = []
    free = lambda a, b: all(b <= u0 or a >= u1 for u0, u1 in used)
    def piece(label, i, a, b):
        used.append((a, b)); return (label, [_clip(segs, i, a, b, fps)])
    if at:                                            # a piece may span joints (cuts, layout switches): that is what to review
        out = []
        for t in at:
            a, b = t - n / 2, t + n / 2; used.append((a, b)); parts = []
            for i, (s, e) in enumerate(zip(segs, E)):
                d = s["face_out"] - s["face_in"]
                if e < b and e + d > a: parts.append(_clip(segs, i, s["face_in"] + max(0.0, a - e), s["face_in"] + min(d, b - e), fps))
            out.append((f"at {t:.0f} s", [p for p in parts if p["face_out"] - p["face_in"] >= 2 / fps]))
        return out
    out = []
    A = [i for i, s in enumerate(segs) if s["layout"] == "A"]
    if A: out.append(piece("presenter", A[0], segs[A[0]]["face_in"], segs[A[0]]["face_in"] + n))
    B = [i for i, s in enumerate(segs) if s["layout"] != "A"]
    hit = next(((i, t) for t in sorted(c[0] for c in plan.get("chips", [])) for i in B
                if segs[i]["face_in"] + n / 2 <= t <= segs[i]["face_out"] - n / 2 and free(t - n / 2, t + n / 2)), None)
    if not hit and B:
        i = max(B, key=lambda i: segs[i]["face_out"] - segs[i]["face_in"]); hit = (i, (segs[i]["face_in"] + segs[i]["face_out"]) / 2)
    if hit: out.append(piece("slide", hit[0], hit[1] - n / 2, hit[1] + n / 2))
    cuts = [i for i in range(1, len(segs)) if abs(segs[i - 1]["face_out"] - segs[i]["face_in"]) > 1e-6]
    switches = [i for i in range(1, len(segs)) if segs[i - 1]["layout"] != segs[i]["layout"] and i not in cuts]
    for i in cuts + switches:
        l, r = segs[i - 1], segs[i]
        if free(l["face_out"] - n / 2, l["face_out"]) and free(r["face_in"], r["face_in"] + n / 2):
            used += [(l["face_out"] - n / 2, l["face_out"]), (r["face_in"], r["face_in"] + n / 2)]
            out.append(("cut" if i in cuts else "layout switch", [_clip(segs, i - 1, l["face_out"] - n / 2, l["face_out"], fps),
                                                                  _clip(segs, i, r["face_in"], r["face_in"] + n / 2, fps)]))
            break
    return out

def build(cfg, plan, analysis, meta, n=5.0, at=None):
    fps = cfg["output"]["fps"]; d = os.path.join(cfg["paths"]["full_video"], "sample"); os.makedirs(d, exist_ok=True)
    pieces = pick(plan, fps, n, at); E = _edit_starts(plan["segments"], fps); segs = [s for _, p in pieces for s in p]
    sub = {**plan, "segments": segs, "parent_segments": plan["segments"]}
    out = os.path.join(d, "sample.mp4")
    r = pipeline.build(cfg, sub, analysis, meta, out, gate="timeline", wd=os.path.join(d, "work"), record=False)
    mm = lambda t: f"{int(t // 60)}:{t % 60:04.1f}"
    info = {"file": out, "duration": r["edl"][-1]["edit_start"] + r["edl"][-1]["frames"] / fps if r["edl"] else 0, "encoder": cfg["output"]["x264"],
            "pieces": [{"label": lab, "final_video": f"{mm(E[p[0]['parent']] + p[0]['face_in'] - plan['segments'][p[0]['parent']]['face_in'])}"
                                                    f"–{mm(E[p[-1]['parent']] + p[-1]['face_out'] - plan['segments'][p[-1]['parent']]['face_in'])}",
                        "layouts": [s["layout"] for s in p]} for lab, p in pieces]}
    info["sync"] = qa.sync_checks(cfg, out, r["edl"], cfg["sources"]["desktop_recording"], plan["offset_s"], analysis, r["geometry"])
    json.dump(info, open(os.path.join(d, "sample.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return info
