"""Orchestration of the full-video render from an APPROVED timeline (gate 'full_render'; previews need gate 'timeline').

timeline.json (approved) -> geometry + static layers -> fixed crop per continuous take -> chip-bar MOV per slide segment
-> counter badges from the slide timeline -> HyperFrames element MOVs -> segments (decode-checked) -> stream-copy join
-> narration on frames + music + SFX -> mux -> QA. Restartable: finished segments are reused unless their inputs changed."""
import json, os
import numpy as np
from . import layout, render, graphics, audio, state, media, sync

def _takes(segs):
    groups, cur = [], None
    for i, s in enumerate(segs):
        if s["layout"] == "A": cur = None; continue
        if cur is not None and abs(segs[cur[-1]]["face_out"] - s["face_in"]) < 1e-6: cur.append(i)
        else: cur = [i]; groups.append(cur)
    return groups

def _fp(cmd):
    """Segment fingerprint: the command plus CONTENT hashes of generated inputs (< 64 MB: layers, bars, badges, elements)
    and size/mtime of large sources; regenerated-but-identical inputs do not force a re-render."""
    import hashlib
    h = hashlib.sha256(" ".join(x for x in cmd if not os.path.isfile(x)).encode())
    for x in cmd:
        if os.path.isfile(x):
            st = os.stat(x)
            if st.st_size < 64 << 20:
                h.update(open(x, "rb").read())
            else:
                h.update(f"{os.path.abspath(x)}|{st.st_size}|{int(st.st_mtime)}".encode())
    return h.hexdigest()[:16]

def slide_numbers(changes_desktop, offset):
    """[(face_t0, face_t1, n, total)] numbering slides by order of appearance (validated by the user with the timeline)."""
    edges = [-1e9] + [t - offset for t in changes_desktop] + [1e9]
    return [(a, b, k + 1, len(edges) - 1) for k, (a, b) in enumerate(zip(edges, edges[1:]))]

def build(cfg, plan, analysis, meta, out_mp4, only=None, gate="full_render", wd=None, record=True):
    """record=False (review samples): out_mp4 may be replaced and timelines/edl.json, geometry.json are not written.
    A plan may carry "parent_segments" (the full timeline) with segment["parent"] indices: crops then come from the full
    takes, so a clipped sample frames the camera exactly as the full render does."""
    state.require(cfg, gate)
    if only is None and record and os.path.exists(out_mp4) and not cfg["output"]["overwrite_finals"]:
        raise FileExistsError(f"{out_mp4} exists; set output.overwrite_finals or choose a new name (finals are never overwritten silently)")
    A, wd = cfg["paths"], wd or os.path.join(cfg["paths"]["full_video"], "work"); os.makedirs(wd, exist_ok=True)
    masks = list(np.load(os.path.join(A["analysis"], "content_masks.npz")).values())
    g = layout.geometry(cfg, analysis["slide_area"], masks, analysis.get("counter_box")); L = layout.static_layers(cfg, g, os.path.join(wd, "layers"))
    off = plan["offset_s"]; segs = plan["segments"]; ft = None
    base = plan.get("parent_segments", segs); secs = sync.sections(cfg)
    if secs: segs = sync.split_sections(segs, secs)
    if os.path.exists(os.path.join(A["analysis"], "face_track.npy")): ft = np.load(os.path.join(A["analysis"], "face_track.npy"))
    v = meta["face_camera"]["video"]; sw, sh = v["width"], v["height"]
    if abs(v.get("rotation") or 0) == 90: sw, sh = sh, sw                         # crops are in displayed (rotated) pixels
    bc = {}
    for grp in _takes(base):
        c = render.fixed_crop(cfg, ft, base[grp[0]]["face_in"], base[grp[-1]]["face_out"], sw, sh)
        for i in grp: bc[i] = c
    for i, s in enumerate(base):
        if s["layout"] == "A": bc[i] = render.frame_crop(ft, s["face_in"], s["face_out"], sw, sh, g["W"], g["H"])
    crops = {i: bc.get(s.get("parent", i)) for i, s in enumerate(segs)}
    els = graphics.render_elements(cfg, plan.get("elements", [])) if plan.get("elements") else {}
    nums = slide_numbers(analysis["slide_changes"], off) if (g.get("counter") or {}).get("hidden_by_camera") else []
    parts = []
    for i, s in enumerate(segs):
        out = os.path.join(wd, f"seg_{i:03d}.mkv"); parts.append(out)
        if only is not None and i not in only: continue
        bar = None
        if s["layout"] != "A" and plan.get("chips"):
            bar = (graphics.bar_video(cfg, g, [tuple(c) for c in plan["chips"]], s["face_in"], s["face_out"], os.path.join(wd, f"bar_{i:03d}.mov")), s["face_in"])
        badges = []
        for a, b, n, tot in nums:
            lo, hi = max(a, s["face_in"]), min(b, s["face_out"])
            if s["layout"] != "A" and hi > lo:
                png, w = graphics.badge(cfg, n, tot, os.path.join(wd, f"badge_{n:02d}.png"))
                badges.append((png, g["badge_anchor"][0] - w, g["badge_anchor"][1], lo - s["face_in"], hi - s["face_in"]))
        mine = [(els[e["start"]], e["start"] - s["face_in"]) for e in plan.get("elements", []) if s["face_in"] <= e["start"] < s["face_out"]]
        cmd = render.segment(cfg, g, L, s, out, off, meta["face_color_pipeline"], crops.get(i), bar, badges, mine)
        fp = _fp(cmd[:-1])                                                              # restartable (output path excluded)
        if os.path.exists(out) and os.path.exists(out + ".fp") and open(out + ".fp").read() == fp and not media.decode_errors(out):
            continue
        render.render_segment(cmd, out); open(out + ".fp", "w").write(fp)
    if only is not None: return {"segments": parts}
    joined = render.join(parts, os.path.join(wd, "joined.mkv")); nfr = [render.frame_count(p) for p in parts]
    starts = list(np.concatenate([[0], np.cumsum(nfr)[:-1]]) / cfg["output"]["fps"])
    music = plan.get("music")
    if music is None and str(plan.get("music_sections", "")).startswith("auto") and cfg["audio"]["music"]["enabled"]:
        music = audio.to_edit(audio.music_plan(cfg, base, plan.get("chapters", []), analysis.get("pauses", [])),
                              [(s["face_in"], s["face_out"], t) for s, t in zip(segs, starts)])
    json.dump([[a, b] for a, b, *_ in (music or [])], open(os.path.join(wd, "music_plan.json"), "w"))   # for the music QA
    res = audio.mix(cfg, [(s["face_in"], n) for s, n in zip(segs, nfr)], music or [], plan.get("sfx", []),
                    os.path.join(wd, "mix.wav"), os.path.join(wd, "narration_stem.wav"))
    audio.mux(joined, os.path.join(wd, "mix.wav"), out_mp4, cfg)
    edl = [{"layout": s["layout"], "face_in": s["face_in"], "face_out": s["face_out"], "edit_start": t, "frames": n,
            **{k: s[k] for k in ("desk_offset", "desk_hold") if k in s}} for s, t, n in zip(segs, starts, nfr)]
    if record: json.dump(g, open(os.path.join(A["timelines"], "geometry.json"), "w"), indent=1)
    if record: json.dump({"offset_s": off, "fps": cfg["output"]["fps"], "segments": edl, "duration": sum(nfr) / cfg["output"]["fps"]},
              open(os.path.join(A["timelines"], "edl.json"), "w"), indent=1)
    return {"file": out_mp4, "edl": edl, "geometry": g, "audio": res}
