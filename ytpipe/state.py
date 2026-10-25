"""Stage checkpoints: lessons/<id>/state.json records each finished stage with a fingerprint of its inputs, so stages are
restartable and idempotent (a stage reruns only if forced or its inputs changed). Approval gates are recorded the
same way and can only be set by an explicit CLI command from the user (`python -m ytpipe approve <gate>`)."""
import hashlib, json, os, time

GATES = ("timeline", "preview", "full_render", "thumbnail", "shorts", "paid_assets", "blog_publish")

def _path(cfg):
    return os.path.join(cfg["paths"]["root"], "state.json")

def load(cfg):
    p = _path(cfg)
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return {"stages": {}, "approvals": {}}

def save(cfg, st):
    os.makedirs(cfg["paths"]["root"], exist_ok=True)
    tmp = _path(cfg) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, indent=2)
    os.replace(tmp, _path(cfg))

def fingerprint(*items):
    """Hash of JSON-able items and of files' (size, mtime) — cheap, no full-file hashing of videos."""
    h = hashlib.sha256()
    for it in items:
        if isinstance(it, str) and os.path.isfile(it):
            s = os.stat(it); h.update(f"{os.path.abspath(it)}|{s.st_size}|{int(s.st_mtime)}".encode())
        else:
            h.update(json.dumps(it, sort_keys=True, default=str).encode())
    return h.hexdigest()[:16]

def done(cfg, stage, fp):
    return load(cfg)["stages"].get(stage, {}).get("fp") == fp

def mark(cfg, stage, fp, outputs=()):
    st = load(cfg); st["stages"][stage] = {"fp": fp, "at": time.strftime("%Y-%m-%d %H:%M:%S"), "outputs": list(outputs)}
    save(cfg, st)

def approved(cfg, gate):
    return bool(load(cfg)["approvals"].get(gate))

def approve(cfg, gate, note=""):
    if gate not in GATES:
        raise ValueError(f"unknown gate {gate}; one of {GATES}")
    st = load(cfg); st["approvals"][gate] = {"at": time.strftime("%Y-%m-%d %H:%M:%S"), "note": note}; save(cfg, st)

def require(cfg, gate):
    if not approved(cfg, gate):
        raise PermissionError(f"approval '{gate}' missing: review the output, then run "
                              f"python -m ytpipe approve {gate} --config <config>")
