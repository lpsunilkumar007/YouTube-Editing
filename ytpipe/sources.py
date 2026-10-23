"""Stage 'inspect': ffprobe facts for both sources -> analysis/metadata.json. Decides the colour pipeline (HDR/DV vs SDR),
rotation, fps, audio presence/silence and candidate clock timestamps for synchronisation. Never assumes Lesson 01."""
import json, os
from . import media

def _ratio(s):
    try:
        n, d = s.split("/"); return float(n) / float(d) if float(d) else None
    except Exception:
        return None

def describe(path, silence_probe_s=60):
    p = media.probe(path); fmt = p["format"]; tags = {k.lower(): v for k, v in fmt.get("tags", {}).items()}
    v = next((s for s in p["streams"] if s["codec_type"] == "video"), None)
    auds = [s for s in p["streams"] if s["codec_type"] == "audio"]
    out = {"path": os.path.abspath(path), "duration": float(fmt.get("duration", 0)), "size": int(fmt.get("size", 0)),
           "container": fmt.get("format_name"), "creation_time": tags.get("creation_time"),
           "apple_creationdate": tags.get("com.apple.quicktime.creationdate"),
           "device": " ".join(x for x in (tags.get("com.apple.quicktime.make"), tags.get("com.apple.quicktime.model")) if x) or None,
           "encoder": tags.get("encoder"), "mtime": os.path.getmtime(path)}
    if v:
        sd = v.get("side_data_list", [])
        rot = next((s.get("rotation") for s in sd if "rotation" in s), None)
        dv = next((s for s in sd if s.get("side_data_type", "").lower().startswith("dovi")), None)
        trc = v.get("color_transfer")
        out["video"] = {"codec": v.get("codec_name"), "profile": v.get("profile"), "width": v["width"], "height": v["height"],
                        "pix_fmt": v.get("pix_fmt"), "fps": _ratio(v.get("r_frame_rate", "0/1")),
                        "avg_fps": _ratio(v.get("avg_frame_rate", "0/1")), "start_time": float(v.get("start_time", 0) or 0),
                        "color_transfer": trc, "color_primaries": v.get("color_primaries"), "color_space": v.get("color_space"),
                        "rotation": rot, "dolby_vision_profile": dv.get("dv_profile") if dv else None,
                        "hdr": trc in ("arib-std-b67", "smpte2084") or dv is not None}
    out["audio"] = []
    for i, a in enumerate(auds):
        info = {"index": i, "codec": a.get("codec_name"), "channels": a.get("channels"), "sample_rate": int(a.get("sample_rate", 0))}
        try:
            x = media.audio(path, ss=min(30.0, out["duration"] / 3), t=silence_probe_s, sr=16000)
            info["probe_rms_dbfs"] = round(media.rms_db(x), 1); info["silent"] = info["probe_rms_dbfs"] < -80
        except Exception as e:
            info["probe_error"] = str(e)[:200]
        out["audio"].append(info)
    return out

def color_pipeline(face_desc, cfg):
    """'libplacebo' (HDR/DV, approved Lesson 01 chain) or 'sdr' (plain scale) unless forced in config."""
    forced = cfg["color"]["face_pipeline"]
    if forced != "auto":
        return forced
    return "libplacebo" if face_desc.get("video", {}).get("hdr") else "sdr"

def run(cfg):
    face = describe(cfg["sources"]["face_camera"]); desk = describe(cfg["sources"]["desktop_recording"])
    warn = []
    for name, d in (("face_camera", face), ("desktop_recording", desk)):
        v = d.get("video") or {}
        if not v: warn.append(f"{name}: no video stream")
        elif v.get("fps") and abs(v["fps"] - cfg["output"]["fps"]) > 0.01: warn.append(f"{name}: {v['fps']:.3f} fps (output {cfg['output']['fps']})")
    if not face["audio"] or all(a.get("silent") for a in face["audio"]):
        warn.append("face_camera has no usable audio: narration source must be chosen manually")
    meta = {"face_camera": face, "desktop_recording": desk, "face_color_pipeline": color_pipeline(face, cfg),
            "desktop_has_audio": any(not a.get("silent", True) for a in desk["audio"]), "warnings": warn}
    os.makedirs(cfg["paths"]["analysis"], exist_ok=True)
    with open(os.path.join(cfg["paths"]["analysis"], "metadata.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    return meta
