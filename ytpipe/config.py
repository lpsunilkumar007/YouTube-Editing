"""Configuration: defaults (config/defaults.json) deep-merged with a lecture config.

A lecture config needs only three fields — face_camera, desktop_recording, lecture_topic — either at top level
(video_project_config.json style) or under "sources"/"project". Everything else may be overridden under "overrides"
(or by giving the same section at top level). Unknown override keys are errors, so typos never silently do nothing."""
import copy, json, os, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLACEHOLDERS = {"PATH_TO_FACE_VIDEO", "PATH_TO_DESKTOP_VIDEO", "LECTURE_TOPIC", "", None}

class ConfigError(ValueError):
    pass

def _load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def deep_merge(base, over, path="", strict=True):
    out = copy.deepcopy(base)
    for k, v in over.items():
        if k.startswith("_"):
            continue
        if strict and k not in base:
            raise ConfigError(f"unknown setting: {path}{k}")
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            out[k] = deep_merge(base[k], v, f"{path}{k}.", strict)
        else:
            out[k] = v
    return out

def slug(text):
    return re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).strip("_")[:40] or "lecture"

def load(path=None, data=None, check_files=True):
    """Return the resolved config dict (adds 'paths' with the per-lecture folders). Raises ConfigError."""
    defaults = _load_json(os.path.join(ROOT, "config", "defaults.json"))
    user = data if data is not None else _load_json(path)
    cfg = copy.deepcopy(defaults)
    # top-level shorthand fields
    short = {"face_camera": ("sources", "face_camera"), "desktop_recording": ("sources", "desktop_recording"),
             "lecture_topic": ("project", "lecture_topic"), "lesson_number": ("project", "lesson_number"),
             "lesson_id": ("project", "lesson_id"), "language": ("project", "language")}
    for k, (sec, key) in short.items():
        if k in user and user[k] is not None:
            cfg[sec][key] = user[k]
    for k, v in user.items():
        if k in defaults and isinstance(v, dict):
            cfg[k] = deep_merge(cfg[k], v, f"{k}.")
    if "overrides" in user:
        ov = {k: v for k, v in user["overrides"].items() if not k.startswith("_")}
        # accept the legacy template names from templates/video_project_defaults.json
        legacy = {"camera_overlay": ("layout", "camera"), "background_music": ("audio", "music")}
        for k, v in list(ov.items()):
            if k in legacy:
                sec, sub = legacy[k]
                cfg[sec][sub] = deep_merge(cfg[sec][sub], _legacy_camera(v) if k == "camera_overlay" else v, f"{sec}.{sub}.")
                del ov[k]
        cfg = deep_merge(cfg, ov, "overrides.")
    errs = validate(cfg, check_files)
    if errs:
        raise ConfigError("; ".join(errs))
    p = cfg["project"]
    if not p["lesson_id"]:
        p["lesson_id"] = f"lesson{int(p['lesson_number']):02d}" if p["lesson_number"] else slug(p["lecture_topic"])
    out_dir = user.get("output_dir") or os.path.join(ROOT, p["lessons_root"], p["lesson_id"])
    cfg["paths"] = {k: os.path.join(out_dir, k) for k in
                    ("raw", "analysis", "transcripts", "timelines", "assets", "thumbnails", "full_video", "shorts", "metadata", "reports")}
    cfg["paths"]["root"] = out_dir
    return cfg

def _legacy_camera(v):
    m = {"diameter_px": "diameter", "margin_px": "margin", "crop_square_px": "crop_square"}
    return {m.get(k, k): x for k, x in v.items() if m.get(k, k) in
            ("diameter", "margin", "position", "crop_square", "face_center_y", "shape", "crop_mode")}

def validate(cfg, check_files=True):
    errs = []
    s, p = cfg["sources"], cfg["project"]
    for k in ("face_camera", "desktop_recording"):
        v = s.get(k)
        if v in PLACEHOLDERS:
            errs.append(f"required: {k}")
        elif check_files and not os.path.isfile(v):
            errs.append(f"{k}: file not found: {v}")
    if p.get("lecture_topic") in PLACEHOLDERS:
        errs.append("required: lecture_topic")
    cam = cfg["layout"]["camera"]
    W, H = cfg["output"]["resolution"]
    if not (0 < cam["diameter"] < min(W, H) / 2):
        errs.append("layout.camera.diameter out of range")
    if cam["position"] not in ("lower-right", "lower-left", "upper-right", "upper-left"):
        errs.append("layout.camera.position must be lower-right|lower-left|upper-right|upper-left")
    lo, hi = cfg["zoom"]["range"]
    if not (1.0 <= lo <= hi <= cfg["zoom"]["max"]):
        errs.append("zoom.range must satisfy 1 <= lo <= hi <= zoom.max")
    if cfg["output"]["overwrite_finals"] not in (True, False):
        errs.append("output.overwrite_finals must be true/false")
    try:
        import jsonschema  # optional, stricter type checks
        jsonschema.validate(cfg, _load_json(os.path.join(ROOT, "config", "schema.json")))
    except ImportError:
        pass
    except Exception as e:  # jsonschema.ValidationError
        errs.append(f"schema: {getattr(e, 'message', e)}")
    return errs

def ensure_dirs(cfg):
    for k, d in cfg["paths"].items():
        os.makedirs(d, exist_ok=True)
    return cfg["paths"]
