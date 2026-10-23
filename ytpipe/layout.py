"""Geometry and static layers for layouts A/B/C, computed per lecture (ported from the approved Lesson 01 design:
make_graphics_v2.py v3 layers, render_preview_v6.py PATCH/badge). Nothing here is Lesson 01-specific.

Card   : the measured slide area, scaled to fill the height above the chip band (Lesson 01: 1890x1080 -> 1664x950 at 24,24),
         then shrunk only if slide content would fall under the camera circle (content masks, worst case per slide).
Camera : circle of layout.camera.diameter in the configured corner, layout.camera.margin from the edges.
Counter: if the burned-in counter would be hidden by the circle, it is covered by cloning a strip of slide background
         that is verified empty on every slide, and redrawn as a badge outside the card."""
import math, os
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

def _even(v):
    return int(math.ceil(v / 2.0)) * 2

def camera_box(cfg):
    W, H = cfg["output"]["resolution"]; c = cfg["layout"]["camera"]; d, m = c["diameter"], c["margin"]
    x = W - m - d if "right" in c["position"] else m
    y = H - m - d if "lower" in c["position"] else m
    return [x, y, d]

def geometry(cfg, slide_area, masks=None, counter_box=None):
    W, H = cfg["output"]["resolution"]; L = cfg["layout"]; m = L["card_margin"]
    sx0, sy0, sx1, sy1 = slide_area; sw, sh = sx1 - sx0, sy1 - sy0
    cam = camera_box(cfg)
    ch_max = H - m - L["chip_band"]; scale = ch_max / sh
    if masks is not None:                          # shrink until no slide content sits under the circle (+6 px ring/shadow)
        while scale > 0.6 and _content_under_circle(masks, slide_area, scale, m, cam) > 0:
            scale -= 0.005
    cw, chh = _even(sw * scale), _even(sh * scale)
    cx = m if "right" in L["camera"]["position"] else W - m - cw
    g = {"W": W, "H": H, "slide_area": [sx0, sy0, sw, sh], "card": [cx, m, cw, chh], "scale": round(cw / sw, 5), "camera": cam,
         "bar": [m, m + chh + 21, (cam[0] - m - 44) if "right" in L["camera"]["position"] else W - 2 * m - cam[2] - 44, 64],
         "badge_anchor": [W - m, m] if "right" in L["camera"]["position"] else [m, m], "radius": L["card_radius"]}
    if counter_box:
        g["counter"] = {"box": counter_box, "hidden_by_camera": _counter_hidden(counter_box, g)}
        if g["counter"]["hidden_by_camera"] and masks is not None:
            g["counter"]["patch"] = choose_patch(counter_box, slide_area, masks)
    return g

def _content_under_circle(masks, area, scale, m, cam):
    # the ring is drawn inside the circle and the shadow is translucent: the circle edge (+1 px) is the limit (approved v6 rule)
    sx0, sy0 = area[0], area[1]; cx, cy, d = cam[0] + cam[2] / 2, cam[1] + cam[2] / 2, cam[2] / 2 + 1
    n = 0
    for mk in masks:                               # masks cover the full 1920x1080 desktop at any analysis resolution
        k = 1920 / mk.shape[1]; ys, xs = np.nonzero(mk); fx, fy = (xs + 0.5) * k, (ys + 0.5) * k
        X, Y = m + (fx - sx0) * scale, m + (fy - sy0) * scale
        n += int(((X - cx) ** 2 + (Y - cy) ** 2 < d * d).sum())
    return n

def _counter_hidden(box, g):
    x0, y0, x1, y1 = box; sx0, sy0 = g["slide_area"][:2]; s = g["scale"]; cx, cy, d = g["card"][0], g["card"][1], g["camera"]
    X0, Y0, X1, Y1 = cx + (x0 - sx0) * s, cy + (y0 - sy0) * s, cx + (x1 - sx0) * s, cy + (y1 - sy0) * s
    ccx, ccy, r = d[0] + d[2] / 2, d[1] + d[2] / 2, d[2] / 2 + 8
    nx, ny = min(max(ccx, X0), X1), min(max(ccy, Y0), Y1)
    return bool((nx - ccx) ** 2 + (ny - ccy) ** 2 < r * r or X1 > d[0] - 4 and Y1 > d[1] - 4)

def choose_patch(box, area, masks):
    """Source strip (same size as the counter box) left of / above the counter that is empty on EVERY slide."""
    x0, y0, x1, y1 = box; w, h = x1 - x0, y1 - y0
    union = np.any(masks, axis=0) if len(masks) else None
    for sx, sy in [(x0 - w - 8, y0), (x0 - 2 * w - 16, y0), (x0, y0 - h - 8), (x0, y0 - 2 * h - 16)]:
        if sx < area[0] or sy < area[1]: continue
        k = 1920 / union.shape[1] if union is not None else 1
        if union is None or not union[int(sy / k):int((sy + h) / k) + 1, int(sx / k):int((sx + w) / k) + 1].any():
            return {"src": [sx, sy], "dst": [x0, y0], "size": [w, h],
                    "filter": f"split[dA][dB];[dB]crop={w}:{h}:{sx}:{sy}[pt];[dA][pt]overlay={x0}:{y0}"}
    return None

# ---------------------------------------------------------------- static layers (PNG, full frame)
def _rrect(wh, r, sc=4):
    m = Image.new("L", (wh[0] * sc, wh[1] * sc), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, wh[0] * sc - 1, wh[1] * sc - 1], r * sc, fill=255)
    return m.resize(wh, Image.LANCZOS)

def _circle(d, sc=8):
    m = Image.new("L", (d * sc, d * sc), 0); ImageDraw.Draw(m).ellipse([0, 0, d * sc - 1, d * sc - 1], fill=255)
    return m.resize((d, d), Image.LANCZOS)

def static_layers(cfg, g, out_dir):
    """bg (canvas + card shadow), card mask, card ring, circle mask, circle ring, outside-only circle shadow."""
    os.makedirs(out_dir, exist_ok=True); W, H = g["W"], g["H"]; pal = cfg["graphics"]["palette"]; cam = cfg["layout"]["camera"]
    x, y, w, h = g["card"]; r = g["radius"]; cxy, d = g["camera"][:2], g["camera"][2]
    bg = Image.new("RGB", (W, H), pal["canvas"]); s = Image.new("L", (W, H), 0); s.paste(_rrect((w, h), r), (x, y + 6))
    bg.paste(Image.new("RGB", (W, H), "#000000"), (0, 0), s.filter(ImageFilter.GaussianBlur(16)).point(lambda v: int(v * 0.55)))
    p = {k: os.path.join(out_dir, f"{k}.png") for k in ("bg", "card_mask", "card_ring", "cam_mask", "cam_ring", "cam_shadow")}
    bg.save(p["bg"]); _rrect((w, h), r).save(p["card_mask"])
    ring = Image.new("RGBA", (W, H), (0, 0, 0, 0)); ImageDraw.Draw(ring).rounded_rectangle([x, y, x + w - 1, y + h - 1], r, outline=pal["border"], width=1)
    ring.save(p["card_ring"])
    m = _circle(d); m.save(p["cam_mask"])
    sh = Image.new("L", (W, H), 0); sh.paste(m, (cxy[0], cxy[1] + 5)); sh = np.asarray(sh.filter(ImageFilter.GaussianBlur(12))).astype(float) * 0.45
    inner = np.zeros((H, W)); inner[cxy[1]:cxy[1] + d, cxy[0]:cxy[0] + d] = np.asarray(m) / 255.0
    a = np.zeros((H, W, 4), np.uint8); a[..., 3] = (sh * (1 - inner)).round().astype(np.uint8); Image.fromarray(a, "RGBA").save(p["cam_shadow"])
    sc = 8; rr = Image.new("L", (d * sc, d * sc), 0)
    ImageDraw.Draw(rr).ellipse([0, 0, d * sc - 1, d * sc - 1], outline=255, width=cam["ring_px"] * sc)
    rr = rr.resize((d, d), Image.LANCZOS).point(lambda v: int(v * cam["ring_opacity"]))
    ring_c = Image.new("RGBA", (W, H), (0, 0, 0, 0)); col = tuple(int(cam["ring"][i:i + 2], 16) for i in (1, 3, 5))
    ring_c.paste(Image.new("RGBA", (d, d), col + (255,)), tuple(cxy), rr); ring_c.save(p["cam_ring"])
    return p
