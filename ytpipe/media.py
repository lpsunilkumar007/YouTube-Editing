"""Thin, testable wrappers around ffprobe/ffmpeg (read-only on sources)."""
import json, subprocess
import numpy as np

def run(cmd, check=True, capture=True):
    r = subprocess.run(cmd, capture_output=capture, text=False)
    if check and r.returncode != 0:
        raise RuntimeError(f"{cmd[0]} failed ({r.returncode}): {r.stderr.decode(errors='replace')[-800:]}")
    return r

def probe(path):
    r = run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path])
    return json.loads(r.stdout)

def audio(path, ss=None, t=None, sr=16000, channel=None):
    """Mono float32 audio; channel=None downmixes, an int picks that channel."""
    af = ["-af", f"pan=mono|c0=c{channel}"] if channel is not None else ["-ac", "1"]
    cmd = ["ffmpeg", "-v", "error", *(["-ss", f"{ss:.3f}"] if ss is not None else []), *(["-t", f"{t:.3f}"] if t else []),
           "-i", path, "-map", "0:a:0", *af, "-ar", str(sr), "-f", "f32le", "-"]
    return np.frombuffer(run(cmd).stdout, np.float32)

def frames(path, ss, t, w, h, fps, vf_pre="", pix="gray"):
    """Downscaled frames (n, h, w[, 3]) for analysis."""
    ch = 3 if pix == "rgb24" else 1
    vf = (vf_pre + "," if vf_pre else "") + f"fps={fps},scale={w}:{h}:flags=area"
    r = run(["ffmpeg", "-v", "error", "-ss", f"{ss:.3f}", "-t", f"{t:.3f}", "-i", path, "-vf", vf, "-f", "rawvideo",
             "-pix_fmt", pix, "-"])
    a = np.frombuffer(r.stdout, np.uint8)
    return a.reshape(-1, h, w, ch) if ch == 3 else a.reshape(-1, h, w)

def decode_errors(path):
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-f", "null", "-"], capture_output=True, text=True)
    return [l for l in r.stderr.splitlines() if l.strip()]

def rms_db(x):
    return float(20 * np.log10(np.sqrt(np.mean(np.square(x, dtype=np.float64))) + 1e-12)) if len(x) else -240.0
