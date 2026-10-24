"""Segment renderer for layouts A/B/C (generic port of render_preview_v6.render + render_full_v9.render_seg).

A segment = (layout, face_in, face_out[, zoom]) with face_in/out on the output frame grid. The desktop is read at
face time + offset (sync stage). One lossy encode per segment (x264 from config); segments are decode-checked,
re-rendered on error, and joined by stream copy. Audio is NOT taken from segments: audio.py lays the narration on the
actual video frames. Overlays (chip bar MOV, counter badges, HyperFrames elements) are optional inputs."""
import os, subprocess
from . import media

def ease_expr(T, ein, eout, v, E):
    cubic = lambda u: f"if(lt({u},0.5),4*pow({u},3),1-pow(-2*{u}+2,3)/2)"
    up = cubic(f"({v}/{E})") if ein else "1"; down = cubic(f"(({T}-{v})/{E})") if eout else "1"
    return f"if(lt({v},{E}),{up},if(gt({v},{T}-{E}),{down},1))"

def desk_filter(g, T, fps, zoom=None, ease=0.6):
    """Desktop -> (counter patch) -> slide-area crop -> card size; zoom = (x0, y0, w0, ease_in, ease_out) in slide px."""
    sx, sy, SW, SH = g["slide_area"]; cw, ch = g["card"][2], g["card"][3]
    patch = (g.get("counter") or {}).get("patch")
    pre = f"fps={fps}," + (patch["filter"] + "," if patch else "") + f"crop={SW}:{SH}:{sx}:{sy}"
    if not zoom:
        return f"{pre},scale={cw}:{ch}:flags=lanczos,setsar=1"
    x0, y0, w0, ein, eout = zoom; h0 = w0 * SH / SW; Z = SW / w0; cx, cy = x0 + w0 / 2, y0 + h0 / 2
    p = ease_expr(T, ein, eout, f"(in/{fps})", ease); z = f"(1+({p})*{Z - 1:.6f})"
    xs = f"min(max(0,2*({SW / 2}+({p})*{cx - SW / 2:.3f})-{SW}/{z}),{2 * SW}-{2 * SW}/{z})"
    ys = f"min(max(0,2*({SH / 2}+({p})*{cy - SH / 2:.3f})-{SH}/{z}),{2 * SH}-{2 * SH}/{z})"
    return (f"{pre},scale={2 * SW}:{2 * SH}:flags=lanczos,zoompan=z='{z}':x='{xs}':y='{ys}':d=1:s={cw}x{ch}:fps={fps},setsar=1")

def face_filter(cfg, pipeline, w, h, crop=None, fmt="yuv420p"):
    """Approved HDR path (libplacebo + Dolby Vision, crop+downscale in one pass) or plain SDR scaling."""
    if crop:                                          # [x, y, size] (square) or [x, y, w, h], in source pixels
        cw, ch = crop[2], crop[3] if len(crop) > 3 else crop[2]
    if pipeline == "libplacebo":
        c = f":crop_x={crop[0]}:crop_y={crop[1]}:crop_w={cw}:crop_h={ch}:downscaler=ewa_lanczos" if crop else ""
        return f"libplacebo={cfg['color']['libplacebo']}:w={w}:h={h}{c}:format={fmt}"
    c = f"crop={cw}:{ch}:{crop[0]}:{crop[1]}," if crop else ""
    return f"{c}scale={w}:{h}:flags=lanczos,format={fmt}"

def _face_median(face_track, a, b, src_w, src_h):
    """Median face centre in a take, in source pixels (face_track is in 1920x1080 frame space, see analyze.face_track)."""
    import numpy as np
    if face_track is None or not len(face_track): return None
    m = (face_track[:, 0] >= a) & (face_track[:, 0] <= b) & ~np.isnan(face_track[:, 1])
    if not m.sum(): return None
    return np.median(face_track[m, 1]) * src_w / 1920, np.median(face_track[m, 2]) * src_h / 1080

def fixed_crop(cfg, face_track, a, b, src_w=1920, src_h=1080):
    """Whole-pixel crop for one continuous take: median face position, face centre at face_center_y (no moving crops).
    crop_square is for a 1080-high source and scales with the source height."""
    c = cfg["layout"]["camera"]; S = int(round(c["crop_square"] * src_h / 1080))
    f = _face_median(face_track, a, b, src_w, src_h)
    if f:
        cx, cy = f
        return [int(round(min(max(0, cx - S / 2), src_w - S))), int(round(min(max(0, cy - c["face_center_y"] * S), src_h - S))), S]
    return [(src_w - S) // 2, max(0, (src_h - S) // 3), S]

def wide_crop(path, W=1920, H=1080):
    """Centre crop [x, 0, w, h] to W:H for a source wider than the output (displayed pixels), else None. For stills and
    face analysis, so their frames and face boxes are not stretched (face-centred crops: frame_crop)."""
    v = next(s for s in media.probe(path)["streams"] if s["codec_type"] == "video"); w, h = v["width"], v["height"]
    rot = next((d.get("rotation", 0) for d in v.get("side_data_list", []) if "rotation" in d), 0)
    if abs(rot) == 90: w, h = h, w
    cw = int(round(h * W / H / 2)) * 2
    return [(w - cw) // 2, 0, cw, h] if cw < w - 2 else None

def frame_crop(face_track, a, b, src_w, src_h, W=1920, H=1080):
    """Layout A for a source wider than the output (e.g. 2864x1322): full height, sides cropped to W:H around the
    median face of the shot (fixed per shot). None when the source already has the output's aspect ratio."""
    cw = int(round(src_h * W / H / 2)) * 2
    if cw >= src_w - 2: return None
    f = _face_median(face_track, a, b, src_w, src_h); cx = f[0] if f else src_w / 2
    return [int(round(min(max(0, cx - cw / 2), src_w - cw))), 0, cw, src_h]

def tight(png):
    """(path, x, y): an RGBA layer cropped to its visible pixels, written next to it (<name>_tight.png). Overlaying the
    crop at (x, y) gives the same frame as overlaying the full layer, without blending the transparent rest every frame."""
    from PIL import Image
    im = Image.open(png); box = im.getchannel("A").getbbox() or (0, 0, 1, 1)
    out = png[:-4] + "_tight.png"; im.crop(box).save(out)
    return out, box[0], box[1]

def segment(cfg, g, layers, seg, out, offset, pipeline, crop=None, bar=None, badges=(), elements=(), focus=None):
    """seg = {layout, face_in, face_out, zoom?}. bar = (mov, start_face_time). badges = [(png, x, y, t0, t1)] local times.
    elements = [(mov, local_offset)]. Returns the ffmpeg command (also executed)."""
    fps = cfg["output"]["fps"]; W, H = g["W"], g["H"]; a, b = seg["face_in"], seg["face_out"]; T = round(b - a, 6)
    face = cfg["sources"]["face_camera"]; desk = cfg["sources"]["desktop_recording"]
    loop = lambda p: ["-loop", "1", "-framerate", str(fps), "-t", f"{T}", "-i", p]
    aud = f"[0:a]pan=mono|c0=c0,aresample=48000[a]"
    inputs = ["-ss", f"{a:.4f}", "-t", f"{T}", "-i", face]; rgb = "scale=out_color_matrix=bt709:out_range=tv"
    if seg["layout"] == "A":
        fc = f"[0:v]fps={fps},{face_filter(cfg, pipeline, W, H, crop, 'yuv444p')},setsar=1[s0];"; prev = "s0"; n = 1
    else:
        d = g["camera"][2]; cx, cy, cw, ch = g["card"]
        (rg, rx, ry), (sh, hx, hy), (rc, qx, qy) = (tight(layers[k]) for k in ("card_ring", "cam_shadow", "cam_ring"))
        inputs += ["-ss", f"{a + offset:.4f}", "-t", f"{T}", "-i", desk, *loop(layers["bg"]), *loop(layers["card_mask"]),
                   *loop(layers["cam_mask"]), *loop(rg), *loop(sh), *loop(rc)]
        fc = (f"[0:v]fps={fps},{face_filter(cfg, pipeline, d, d, crop, 'yuv444p')},setsar=1,format=yuva444p[c0];"
              f"[4:v]format=gray,setsar=1[cmk];[c0][cmk]alphamerge[cam];"
              f"[1:v]{desk_filter(g, T, fps, seg.get('zoom'), cfg['zoom']['ease_s'])},format=yuva444p[d0];"
              f"[3:v]format=gray,setsar=1[dmk];[d0][dmk]alphamerge[desk];"
              f"[2:v]{rgb},format=yuv444p,setsar=1[bg];[5:v]{rgb},format=yuva444p,setsar=1[rg];"
              f"[6:v]{rgb},format=yuva444p,setsar=1[sh];[7:v]{rgb},format=yuva444p,setsar=1[rc];"
              f"[bg][desk]overlay={cx}:{cy}:shortest=1:format=yuv444[s0];[s0][rg]overlay={rx}:{ry}:format=yuv444[s1];"
              f"[s1][sh]overlay={hx}:{hy}:format=yuv444[s2];[s2][cam]overlay={g['camera'][0]}:{g['camera'][1]}:format=yuv444[s3];"
              f"[s3][rc]overlay={qx}:{qy}:format=yuv444[s4];")
        prev = "s4"; n = 8
        if bar:
            inputs += ["-ss", f"{a - bar[1]:.4f}", "-t", f"{T}", "-i", bar[0]]
            fc += f"[{n}:v]{rgb},format=yuva444p,setsar=1[br];[{prev}][br]overlay={g['bar'][0]}:{g['bar'][1]}:format=yuv444:eof_action=repeat[s5];"
            prev = "s5"; n += 1
        for k, (png, x, y, t0, t1) in enumerate(badges):
            inputs += loop(png)
            fc += (f"[{n}:v]{rgb},format=yuva444p,setsar=1[bd{k}];[{prev}][bd{k}]overlay={x}:{y}:format=yuv444:"
                   f"enable='between(t,{t0:.3f},{t1 - 1e-3:.3f})'[b{k}];"); prev = f"b{k}"; n += 1
    for k, (mov, off) in enumerate(elements):
        inputs += ["-i", mov]
        fc += (f"[{n}:v]format=yuva444p,setpts=PTS+{off:.4f}/TB,setsar=1[e{k}];[{prev}][e{k}]overlay=0:0:format=yuv444:"
               f"eof_action=pass[x{k}];"); prev = f"x{k}"; n += 1
    fc += f"[{prev}]format=yuv420p[v];{aud}"
    hw = ["-init_hw_device", "vulkan"] if pipeline == "libplacebo" else []
    cmd = ["ffmpeg", "-v", "error", "-y", *hw, *inputs, "-filter_complex", fc, "-map", "[v]", "-map", "[a]", *cfg["output"]["x264"],
           "-pix_fmt", "yuv420p", "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", "-color_range", "tv",
           "-c:a", "pcm_s24le", "-t", f"{T}", out]
    return cmd

def render_segment(cmd, out, retries=3):
    """Run, then decode-check; re-render on decode errors (Lesson 01 once produced a corrupt x264 frame)."""
    for _ in range(retries):
        media.run(cmd)
        if not media.decode_errors(out): return out
    raise RuntimeError(f"{out}: decode errors after {retries} attempts")

def join(parts, out):
    lst = out + ".txt"
    with open(lst, "w") as f: f.writelines(f"file '{os.path.abspath(p)}'\n" for p in parts)
    media.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", "-an", out])
    return out

def frame_count(p):
    r = media.run(["ffprobe", "-v", "error", "-select_streams", "v", "-count_packets", "-show_entries", "stream=nb_read_packets", "-of", "csv=p=0", p])
    return int(r.stdout)
