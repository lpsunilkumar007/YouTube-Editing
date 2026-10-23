"""Shorts v2: vertical clips built from the ORIGINAL face and desktop recordings (sharper than reframing the edit).

Each part of a clip follows the main edit's layout at that moment and uses exactly the same face/desktop times as the
final edit (frame-grid exact), so pen strokes stay in sync; the audio is the final mix of the same span, muxed once.
  slide shot : content panel = crop of the desktop around what is being taught (all red ink of the span included,
               slide header/footer bands and the burned-in counter ignored), full width 1040 px, rounded corners;
               face circle 400 px from the original camera (approved colour pipeline, one GPU pass), thin light ring.
  face shot  : 9:16 crop of the original camera centred on the measured face.
Safe areas: hook text y 120-260, captions end at y 1470 (clear of the Shorts/Reels caption + handle area and the
right-hand button column: right margin 190 px)."""
import os
import numpy as np
from . import media, render as R

V2 = {"panel_w": 1040, "panel_max_h": 800, "panel_top": 250, "circle": 400, "gap": 36, "cap_bottom": 1470, "min_crop_w": 900}

def _esc(p):
    return p.replace("\\", "/").replace(":", "\\:")

def content_crop(desktop, D0, D1, area, counter_box=None, aspect=1040 / 780, min_w=900):
    fr = media.frames(desktop, D0, max(0.6, D1 - D0), 480, 270, 2.0, pix="rgb24").astype(np.int16)
    sx0, sy0, sx1, sy1 = area; k = 4
    bg = np.median(fr[:, ::6, ::6].reshape(-1, 3), 0)
    content = (np.abs(fr - bg).max(-1) > 40).any(0)
    red = ((fr[..., 0] > 150) & (fr[..., 1] < 90) & (fr[..., 2] < 100)).any(0)
    m = content.copy(); m[: int(0.09 * 270)] = False; m[int(0.93 * 270):] = False         # slide header / footer bands
    m[:, : sx0 // k] = False; m[:, sx1 // k:] = False
    if counter_box:
        x0, y0, x1, y1 = counter_box; m[max(0, y0 // k - 2):y1 // k + 3, max(0, x0 // k - 2):x1 // k + 3] = False
    m |= red                                                                                 # every pen stroke stays visible
    ys, xs = np.nonzero(m)
    if not len(xs):
        return [sx0, sy0, sx1 - sx0, sy1 - sy0]
    bx0, by0, bx1, by1 = xs.min() * k - 30, ys.min() * k - 30, (xs.max() + 1) * k + 30, (ys.max() + 1) * k + 30
    w, h = bx1 - bx0, by1 - by0
    w, h = (w, w / aspect) if w / h > aspect else (h * aspect, h)
    w = min(max(w, min_w), sx1 - sx0); h = w / aspect
    if h > sy1 - sy0:                                    # very wide content: full slide height, keep the computed width
        h = sy1 - sy0
    cx, cy = (bx0 + bx1) / 2, (by0 + by1) / 2
    x = int(min(max(sx0, cx - w / 2), sx1 - w)); y = int(min(max(sy0, cy - h / 2), sy1 - h))
    return [x // 2 * 2, y // 2 * 2, int(w) // 2 * 2, int(h) // 2 * 2]

def _assets(cfg, d, panel_wh):
    from PIL import Image, ImageDraw, ImageFilter
    os.makedirs(d, exist_ok=True); W, H = cfg["shorts"]["size"]; C = V2["circle"]; out = {}
    bgp = os.path.join(d, "v2_bg.png")
    if not os.path.exists(bgp):
        y = np.linspace(0, 1, H)[:, None, None]
        base = np.array([12, 21, 37]) * (0.65 + 0.35 * y) + np.array([19, 37, 66]) * (0.35 * (1 - y))
        im = Image.fromarray(np.repeat(base, W, 1).clip(0, 255).astype(np.uint8), "RGB")
        glow = Image.new("L", (W, H), 0); ImageDraw.Draw(glow).ellipse([140, 900, 940, 1700], fill=70)
        im.paste(Image.new("RGB", (W, H), (56, 189, 248)), (0, 0), glow.filter(ImageFilter.GaussianBlur(160))); im.save(bgp)
    out["bg"] = bgp
    pw, ph = panel_wh; pm = os.path.join(d, f"v2_panel_{pw}x{ph}.png")
    if not os.path.exists(pm):
        m = Image.new("L", (pw * 4, ph * 4), 0); ImageDraw.Draw(m).rounded_rectangle([0, 0, pw * 4 - 1, ph * 4 - 1], 22 * 4, fill=255)
        m.resize((pw, ph), Image.LANCZOS).save(pm)
    out["panel_mask"] = pm
    cm, cr = os.path.join(d, f"v2_circle_{C}.png"), os.path.join(d, f"v2_ring_{C}.png")
    if not os.path.exists(cm):
        m = Image.new("L", (C * 8, C * 8), 0); ImageDraw.Draw(m).ellipse([0, 0, C * 8 - 1, C * 8 - 1], fill=255)
        m.resize((C, C), Image.LANCZOS).save(cm)
        r = Image.new("L", (C * 8, C * 8), 0); ImageDraw.Draw(r).ellipse([0, 0, C * 8 - 1, C * 8 - 1], outline=255, width=3 * 8)
        ring = Image.new("RGBA", (C, C), (226, 232, 240, 0)); ring.putalpha(r.resize((C, C), Image.LANCZOS).point(lambda v: int(v * 0.85)))
        ring.save(cr)
    out["circle"], out["ring"] = cm, cr
    return out

def _ass(cfg, cues, path, title):
    W, H = cfg["shorts"]["size"]; mv = H - V2["cap_bottom"]
    head = (f"[Script Info]\nScriptType: v4.00+\nPlayResX: {W}\nPlayResY: {H}\n\n[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
            "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
            f"Style: Cap,Segoe UI Semibold,54,&H00FFFFFF,&H00FFFFFF,&H00000000,&H40251510,0,0,0,0,100,100,0,0,3,16,0,2,70,190,{mv},1\n"
            "Style: Hook,Segoe UI Black,70,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,3,8,70,190,120,1\n\n"
            "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
    ts = lambda t: f"{int(t // 3600)}:{int(t // 60 % 60):02d}:{max(0, t) % 60:05.2f}"
    with open(path, "w", encoding="utf-8") as f:
        f.write(head)
        if title:
            f.write(f"Dialogue: 1,{ts(0)},{ts(3.5)},Hook,,0,0,0,,{title}\n")
        for a, b, t in cues:
            f.write(f"Dialogue: 0,{ts(max(0, a))},{ts(b)},Cap,,0,0,0,,{t.replace(chr(10), chr(92) + 'N')}\n")

def spans_of(c, edl):
    spans = []
    for x in edl:
        a, b = max(c["start"], x["edit_start"]), min(c["end"], x["edit_start"] + x["frames"] / 30)
        if b - a > 0.02:
            F0 = x["face_in"] + a - x["edit_start"]
            if spans and spans[-1]["layout"] == x["layout"] and abs(spans[-1]["b"] - a) < 1e-3 and abs(spans[-1]["F1"] - F0) < 1e-3:
                spans[-1].update(b=b, F1=F0 + b - a)
            else:
                spans.append({"a": a, "b": b, "F0": F0, "F1": F0 + b - a, "layout": x["layout"]})
    return spans

def render(cfg, src_final, cues, c, out, edl, offset, face_track, pipeline, area=(0, 0, 1890, 1080), counter_box=None):
    os.makedirs(os.path.dirname(out), exist_ok=True); W, H = cfg["shorts"]["size"]; fps = cfg["shorts"]["fps"]; C = V2["circle"]
    d = os.path.join(os.path.dirname(out), "_v2"); os.makedirs(d, exist_ok=True); parts, info = [], []
    hw = ["-init_hw_device", "vulkan"] if pipeline == "libplacebo" else []
    pl = cfg["color"]["libplacebo"]
    for k, sp in enumerate(spans_of(c, edl)):
        T = sp["b"] - sp["a"]; po = os.path.join(d, f"{os.path.basename(out)[:-4]}_p{k}.mp4"); ass = po.replace(".mp4", ".ass")
        _ass(cfg, [(x - sp["a"], y - sp["a"], t) for x, y, t in cues if y > sp["a"] and x < sp["b"]], ass, c.get("hook_text", "") if k == 0 else "")
        if sp["layout"] == "A":
            fx = 960
            if face_track is not None:
                m = (face_track[:, 0] >= sp["F0"]) & (face_track[:, 0] <= sp["F1"]) & ~np.isnan(face_track[:, 1])
                if m.any(): fx = int(np.median(face_track[m, 1]))
            cw = 608; x0 = int(min(max(0, fx - cw / 2), 1920 - cw)) // 2 * 2
            chain = (f"libplacebo={pl}:w={W}:h={H}:crop_x={x0}:crop_y=0:crop_w={cw}:crop_h=1080:downscaler=ewa_lanczos:format=yuv420p"
                     if pipeline == "libplacebo" else f"crop={cw}:1080:{x0}:0,scale={W}:{H}:flags=lanczos")
            fc = f"[0:v]fps={fps},{chain},setsar=1,subtitles='{_esc(ass)}'[v]"
            cmd = ["ffmpeg", "-v", "error", "-y", *hw, "-ss", f"{sp['F0']:.4f}", "-t", f"{T:.4f}", "-i", cfg["sources"]["face_camera"],
                   "-filter_complex", fc, "-map", "[v]"]
            info.append({"part": k, "layout": "A", "face_crop_x": x0})
        else:
            D0 = sp["F0"] + offset; cx, cy, cw, ch = content_crop(cfg["sources"]["desktop_recording"], D0, D0 + T, area, counter_box, min_w=V2["min_crop_w"])
            pw = V2["panel_w"]; ph = min(V2["panel_max_h"], int(round(pw * ch / cw / 2)) * 2); A = _assets(cfg, d, (pw, ph))
            px, py = (W - pw) // 2, V2["panel_top"]; ccx, ccy = (W - C) // 2, py + ph + V2["gap"]
            crop = R.fixed_crop(cfg, face_track, sp["F0"], sp["F1"])
            face = (f"libplacebo={pl}:w={C}:h={C}:crop_x={crop[0]}:crop_y={crop[1]}:crop_w={crop[2]}:crop_h={crop[2]}:downscaler=ewa_lanczos:format=yuv444p"
                    if pipeline == "libplacebo" else f"crop={crop[2]}:{crop[2]}:{crop[0]}:{crop[1]},scale={C}:{C}")
            fc = (f"[2:v]format=yuv444p,setsar=1[bg];"
                  f"[1:v]fps={fps},crop={cw}:{ch}:{cx}:{cy},scale={pw}:{ph}:flags=lanczos,format=yuva444p,setsar=1[dk0];"
                  f"[3:v]format=gray,setsar=1[pm];[dk0][pm]alphamerge[dk];"
                  f"[0:v]fps={fps},{face},format=yuva444p,setsar=1[f0];[4:v]format=gray,setsar=1[cm];[f0][cm]alphamerge[fc];"
                  f"[5:v]format=yuva444p,setsar=1[rg];"
                  f"[bg][dk]overlay={px}:{py}:format=yuv444[s1];[s1][fc]overlay={ccx}:{ccy}:format=yuv444[s2];"
                  f"[s2][rg]overlay={ccx}:{ccy}:format=yuv444,format=yuv420p,subtitles='{_esc(ass)}'[v]")
            lp = lambda p: ["-loop", "1", "-framerate", str(fps), "-t", f"{T:.4f}", "-i", p]
            cmd = ["ffmpeg", "-v", "error", "-y", *hw, "-ss", f"{sp['F0']:.4f}", "-t", f"{T:.4f}", "-i", cfg["sources"]["face_camera"],
                   "-ss", f"{D0:.4f}", "-t", f"{T:.4f}", "-i", cfg["sources"]["desktop_recording"], *lp(A["bg"]), *lp(A["panel_mask"]),
                   *lp(A["circle"]), *lp(A["ring"]), "-filter_complex", fc, "-map", "[v]"]
            info.append({"part": k, "layout": "B", "desktop_crop": [cx, cy, cw, ch], "panel": [px, py, pw, ph], "slide_scale": round(pw / cw, 3)})
        cmd += ["-t", f"{T:.4f}", "-r", str(fps), *cfg["output"]["x264"][:6], "-pix_fmt", "yuv420p", "-color_primaries", "bt709",
                "-color_trc", "bt709", "-colorspace", "bt709", "-color_range", "tv", "-an", po]
        media.run(cmd); parts.append(po)
    lst = out + ".txt"
    with open(lst, "w") as f:
        f.writelines(f"file '{os.path.abspath(p)}'\n" for p in parts)
    media.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-ss", f"{c['start']:.3f}", "-t", f"{c['end'] - c['start']:.3f}",
               "-i", src_final, "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", out])
    os.remove(lst)
    for p in parts: os.remove(p)
    if media.decode_errors(out): raise RuntimeError(f"{out}: decode errors")
    return out, info
