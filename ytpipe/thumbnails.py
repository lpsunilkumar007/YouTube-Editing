"""Stage 'thumbnails': three 1280x720 options from the instructor's REAL face (original recording, approved colour
pipeline), local compositing only (Pillow + rembg cut-out). No generative imagery, no face reshaping or retouching:
the cut-out is scaled and placed, nothing else. Text comes from thumbnails/thumbnail_input.json (written from the
content brief). Final choice requires the user's approval (gate 'thumbnail').

Frame selection: frames every N s inside the final edit's face-visible time, scored by frontal face found (Haar),
face size, sharpness (Laplacian variance on the face), both eyes found, exposure, and mouth at rest (in a speech pause)."""
import json, os, subprocess
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from . import media

W, H, SS = 1280, 720, 2                        # render at 2x, downscale (clean edges)

def _font(cfg, kind, px):
    f = {"black": "C:/Windows/Fonts/seguibl.ttf", "bold": cfg["graphics"]["font_bold"], "semi": cfg["graphics"]["font_semibold"]}[kind]
    return ImageFont.truetype(f, int(px * SS))

def face_frame_chain(meta_pipeline, cfg):
    if meta_pipeline == "libplacebo":
        return f"libplacebo={cfg['color']['libplacebo']}:w=1920:h=1080:format=yuv420p"
    return "scale=1920:1080"

def candidates(cfg, edl, env=None, pipeline="libplacebo", every=None, top=6, layouts=("A",)):
    import cv2
    every = every or cfg["thumbnails"]["frame_sample_every_s"]
    fc = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    ec = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_eye.xml")
    segs = [s for s in edl if s.get("layout") in layouts] or edl          # full-face shots first; any segment otherwise
    times = [t for s in segs for t in np.arange(s["face_in"] + 0.5, s["face_out"] - 0.5, every)]
    if env is not None:   # mouth at rest: keep times inside a pause of >= 0.25 s
        times = [t for t in times if int(t * 100) + 13 < len(env) and env[int(t * 100) - 12:int(t * 100) + 13].max() < -50]
    scored = []
    src = cfg["sources"]["face_camera"]; vf = face_frame_chain(pipeline, cfg) + ",scale=960:540"
    for t in times:
        r = subprocess.run(["ffmpeg", "-v", "error", "-init_hw_device", "vulkan", "-ss", f"{t:.2f}", "-i", src, "-frames:v", "1",
                            "-vf", vf, "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True)
        if len(r.stdout) != 960 * 540: continue
        g = np.frombuffer(r.stdout, np.uint8).reshape(540, 960)
        f = fc.detectMultiScale(g, 1.1, 6, minSize=(70, 70))
        if len(f) != 1: continue
        x, y, w, h = f[0]; roi = g[y:y + h, x:x + w]
        eyes = ec.detectMultiScale(roi[: h // 2], 1.1, 6, minSize=(w // 10, w // 10))
        sharp = cv2.Laplacian(roi, cv2.CV_64F).var(); expo = 1 - abs(roi.mean() - 125) / 125
        centred = 1 - abs((x + w / 2) / 960 - 0.5)
        score = (2.0 * (len(eyes) >= 2) + np.log1p(sharp) / 3 + expo + centred + w / 300)
        scored.append({"t": round(float(t), 2), "score": round(float(score), 3), "eyes": int(len(eyes)), "sharp": round(float(sharp), 1),
                       "face": [int(v * 2) for v in (x, y, w, h)]})
    scored.sort(key=lambda d: -d["score"]); picked = []
    for c in scored:                                   # spread picks across the lecture (>= 20 s apart)
        if all(abs(c["t"] - p["t"]) >= 20 for p in picked): picked.append(c)
        if len(picked) == top: break
    out = os.path.join(cfg["paths"]["thumbnails"], "candidates"); os.makedirs(out, exist_ok=True)
    for c in picked:
        c["file"] = os.path.join(out, f"face_{c['t']:08.2f}.png")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-init_hw_device", "vulkan", "-ss", f"{c['t']:.2f}", "-i", src, "-frames:v", "1",
                        "-vf", face_frame_chain(pipeline, cfg), c["file"]], check=True)
    json.dump(picked, open(os.path.join(out, "candidates.json"), "w"), indent=1)
    if picked:                                        # contact sheet so the user can pin a frame (frame_t) per option
        tiles = [Image.open(c["file"]).resize((480, 270)) for c in picked]; sheet = Image.new("RGB", (480 * 3, 270 * ((len(tiles) + 2) // 3)))
        for i, t in enumerate(tiles):
            ImageDraw.Draw(t).text((10, 8), f"F {c_t(picked[i])}", fill="white", font=ImageFont.truetype(cfg["graphics"]["font_bold"], 22))
            sheet.paste(t, (480 * (i % 3), 270 * (i // 3)))
        sheet.save(os.path.join(out, "candidates_sheet.png"))
    return picked

def c_t(c):
    return f"{c['t']:.2f}"

def cutout(cfg, frame_png, out_png, face=None):
    """Person cut-out with rembg (u2net_human_seg). Pixels of the person are copied unchanged; only alpha is added.
    With a face box (x, y, w, h) the frame is first cropped to head and shoulders (0.7 h above the face, 1.0 h below it,
    3.2 h wide), so objects in front of the presenter (laptop, desk) are excluded; the bottom edge is a straight cut.
    Returns (RGBA image, face box as fractions of that image) and keeps both on disk (<out>.png + <out>.json)."""
    side = out_png.replace(".png", ".json")
    if os.path.exists(out_png) and os.path.exists(side):
        return Image.open(out_png), json.load(open(side))["face_frac"]
    from rembg import new_session, remove
    im = Image.open(frame_png).convert("RGB"); ox = oy = 0
    if face:
        x, y, w, h = face; cx = x + w / 2; ox, oy = int(max(0, cx - 1.6 * h)), int(max(0, y - 0.7 * h))
        im = im.crop((ox, oy, int(min(im.width, cx + 1.6 * h)), int(min(im.height, y + 2.0 * h))))
    mask = remove(im, session=new_session("u2net_human_seg"), only_mask=True, post_process_mask=True)
    rgba = im.copy(); rgba.putalpha(mask.filter(ImageFilter.GaussianBlur(1)))
    bb = rgba.getchannel("A").point(lambda v: 255 if v > 20 else 0).getbbox(); rgba = rgba.crop((bb[0], bb[1], bb[2], rgba.height))
    if face:
        x, y, w, h = face; fx0, fy0 = x - ox - bb[0], y - oy - bb[1]
        ff = [fx0 / rgba.width, fy0 / rgba.height, (fx0 + w) / rgba.width, (fy0 + h) / rgba.height]
    else:
        ff = [0.35, 0.2, 0.65, 0.55]
    rgba.save(out_png); json.dump({"face_frac": ff, "source_frame": frame_png}, open(side, "w"))
    return rgba, ff

# ---------------------------------------------------------------- drawing helpers (2x canvas)
def _bg(cfg, glow_xy):
    p = cfg["graphics"]["palette"]; im = Image.new("RGB", (W * SS, H * SS), p["canvas"]); d = ImageDraw.Draw(im)
    for x in range(0, W * SS, 64 * SS): d.line([(x, 0), (x, H * SS)], fill="#152036", width=SS)       # subtle grid
    for y in range(0, H * SS, 64 * SS): d.line([(0, y), (W * SS, y)], fill="#152036", width=SS)
    g = Image.new("L", im.size, 0); ImageDraw.Draw(g).ellipse([glow_xy[0] - 420 * SS, glow_xy[1] - 420 * SS, glow_xy[0] + 420 * SS, glow_xy[1] + 420 * SS], fill=30)
    im.paste(Image.new("RGB", im.size, p["lime"]), (0, 0), g.filter(ImageFilter.GaussianBlur(160 * SS)))
    return im

def _place_person(im, person, face_frac, height, right=None, left=None, bottom=0, rim="#A3E635"):
    """Place the cut-out (scaled only). Returns (person box, face box) in 1x px; the face box comes from the detector."""
    s = height * SS / person.height; pr = person.resize((int(person.width * s), int(height * SS)), Image.LANCZOS)
    x = int(W * SS - pr.width - right * SS) if right is not None else int(left * SS); y = H * SS - pr.height - bottom * SS
    a = pr.getchannel("A")
    sh = Image.new("RGBA", im.size, (0, 0, 0, 0)); sh.paste((0, 0, 0, 150), (x + 10 * SS, y + 10 * SS), a)
    im.paste(sh.filter(ImageFilter.GaussianBlur(18 * SS)), (0, 0), sh.filter(ImageFilter.GaussianBlur(18 * SS)))
    edge = a.filter(ImageFilter.MaxFilter(5)).point(lambda v: v * 0.7); ring = Image.new("RGBA", pr.size, rim); ring.putalpha(edge)
    im.paste(ring, (x, y), ring); im.paste(pr, (x, y), pr)          # thin rim light behind, person pixels untouched
    f = face_frac
    face = tuple(int(v) for v in ((x + f[0] * pr.width) / SS, (y + f[1] * pr.height) / SS,
                                  (x + f[2] * pr.width) / SS, (y + f[3] * pr.height) / SS))
    return (x // SS, y // SS, (x + pr.width) // SS, (y + pr.height) // SS), face

def fit_person(person, face_frac, side, text_edge, h_max, h_min=380, gap=36):
    """Largest height (<= h_max) and offset that keep the face box >= gap px clear of the text column.
    side='right': text on the left, ends at text_edge; side='left': text starts at text_edge. The person may be pushed
    up to 18 % of its width off the canvas edge (shoulder cut) before shrinking."""
    for h in range(h_max, h_min - 1, -10):
        w = person.width * h / person.height
        for off in np.arange(40, -0.18 * w, -10):
            if side == "right" and W - off - w + face_frac[0] * w >= text_edge + gap:
                return h, float(off)
            if side == "left" and off + face_frac[2] * w <= text_edge - gap:
                return h, float(off)
    return h_min, -0.18 * person.width * h_min / person.height

def _text(d, xy, text, font, fill, boxes, anchor="la", spacing=8):
    d.multiline_text((xy[0] * SS, xy[1] * SS), text, font=font, fill=fill, anchor=anchor, spacing=spacing * SS)
    bb = d.multiline_textbbox((xy[0] * SS, xy[1] * SS), text, font=font, anchor=anchor, spacing=spacing * SS)
    boxes.append({"text": text, "box": [v // SS for v in bb], "px": font.size // SS})

def _pill(d, xy, text, font, fill, fg, boxes):
    bb = d.textbbox((0, 0), text, font=font); w, h = bb[2] - bb[0] + 36 * SS, bb[3] - bb[1] + 22 * SS
    x, y = xy[0] * SS, xy[1] * SS; d.rounded_rectangle([x, y, x + w, y + h], h // 2, fill=fill)
    d.text((x + w // 2, y + h // 2), text, font=font, fill=fg, anchor="mm")
    boxes.append({"text": text, "box": [x // SS, y // SS, (x + w) // SS, (y + h) // SS], "px": font.size // SS})

def _hilite(d, lines, xy, font, cfg, boxes, accent_words=()):
    """Headline lines; words in accent_words drawn lime."""
    p = cfg["graphics"]["palette"]; x0, y = xy; lh = int(font.size / SS * 1.08)
    for ln in lines:
        x = x0
        for wd in ln.split(" "):
            col = p["lime"] if wd.strip("?!.,").upper() in {a.upper() for a in accent_words} else p["text"]
            d.text((x * SS, y * SS), wd, font=font, fill=col); bb = d.textbbox((x * SS, y * SS), wd, font=font)
            boxes.append({"text": wd, "box": [v // SS for v in bb], "px": font.size // SS}); x = bb[2] // SS + int(font.size / SS * 0.28)
        y += lh

def _flow(d, cfg, x, y, steps, boxes, w=150, h=96, gap=46):
    p = cfg["graphics"]["palette"]; fl, fv = _font(cfg, "bold", 26), _font(cfg, "black", 40)
    for k, (lab, val, col) in enumerate(steps):
        X = x + k * (w + gap)
        d.rounded_rectangle([X * SS, y * SS, (X + w) * SS, (y + h) * SS], 16 * SS, fill=p["card"], outline=col, width=3 * SS)
        d.text(((X + w / 2) * SS, (y + 28) * SS), lab, font=fl, fill=col, anchor="mm")
        d.text(((X + w / 2) * SS, (y + 66) * SS), val, font=fv, fill=p["text"], anchor="mm")
        boxes.append({"text": lab, "box": [X, y, X + w, y + h], "px": 26})
        if k < len(steps) - 1:
            ax = X + w + 8; d.line([(ax * SS, (y + h / 2) * SS), ((ax + gap - 16) * SS, (y + h / 2) * SS)], fill=p["lime"], width=5 * SS)
            d.polygon([((ax + gap - 16) * SS, (y + h / 2 - 9) * SS), ((ax + gap - 4) * SS, (y + h / 2) * SS), ((ax + gap - 16) * SS, (y + h / 2 + 9) * SS)], fill=p["lime"])

def _width(cfg, lines, kind, px):
    f = _font(cfg, kind, px); return max(f.getlength(l) for l in lines) / SS

def render(cfg, person, face_frac, spec, out_png):
    """spec (from thumbnail_input.json): layout, kicker, headline (list of lines), accent, sub, flow (for B).
    Text is measured first; the person is then sized/placed so the face never sits under any text."""
    p = cfg["graphics"]["palette"]; boxes = []; lay = spec["layout"]
    if lay == "clean_professional":
        im = _bg(cfg, (980 * SS, 420 * SS)); d = ImageDraw.Draw(im)
        edge = 72 + max(_width(cfg, spec["headline"], "black", 80), _width(cfg, [spec["sub"]], "semi", 34))
        h, off = fit_person(person, face_frac, "right", edge, 640); pb, fb = _place_person(im, person, face_frac, h, right=off)
        _pill(d, (72, 92), spec["kicker"], _font(cfg, "bold", 30), p["lime"], p["canvas"], boxes)
        _hilite(d, spec["headline"], (72, 168), _font(cfg, "black", 80), cfg, boxes, spec.get("accent", ()))
        _text(d, (76, 168 + 87 * len(spec["headline"]) + 18), spec["sub"], _font(cfg, "semi", 34), p["cyan"], boxes)
    elif lay == "educational_visual":
        im = _bg(cfg, (260 * SS, 470 * SS)); d = ImageDraw.Draw(im)
        h, off = fit_person(person, face_frac, "left", 500, 600); pb, fb = _place_person(im, person, face_frac, h, left=off)
        _hilite(d, spec["headline"], (500, 92), _font(cfg, "black", 74), cfg, boxes, spec.get("accent", ()))
        _flow(d, cfg, 500, 300, [(a, b, p["lime"] if k != 1 else p["cyan"]) for k, (a, b) in enumerate(spec["flow"])], boxes)
        _text(d, (502, 440), spec["sub"], _font(cfg, "semi", 34), p["muted"], boxes)
    else:  # curiosity
        im = _bg(cfg, (1000 * SS, 360 * SS)); d = ImageDraw.Draw(im)
        edge = 72 + max(_width(cfg, spec["headline"], "black", 80), _width(cfg, [spec["kicker"]], "bold", 30) + 36)
        h, off = fit_person(person, face_frac, "right", edge, 620); pb, fb = _place_person(im, person, face_frac, h, right=off)
        _hilite(d, spec["headline"], (72, 110), _font(cfg, "black", 80), cfg, boxes, spec.get("accent", ()))
        _pill(d, (72, 110 + 87 * len(spec["headline"]) + 30), spec["kicker"], _font(cfg, "bold", 30), p["card"], p["cyan"], boxes)
    im.resize((W, H), Image.LANCZOS).save(out_png)
    return {"file": out_png, "person_box": pb, "face_box": fb, "person_height": h, "text": boxes}

def qa(cfg, result, topic_words):
    """Resolution, safe margins, mobile text size (>= 18 px at 1/4 scale -> font >= 72 px for headlines, >= 26 px for
    any text), text clear of the person's face box, YouTube timestamp corner clear, real-face source recorded."""
    m = cfg["thumbnails"]["safe_margin"]; probs = []
    im = Image.open(result["file"])
    if im.size != tuple(cfg["thumbnails"]["size"]): probs.append(f"size {im.size}")
    for b in result["text"]:
        x0, y0, x1, y1 = b["box"]
        if x0 < m or y0 < m or x1 > W - m or y1 > H - m: probs.append(f"'{b['text']}' outside {m}px safe margin {b['box']}")
        if x1 > W - 190 and y1 > H - 80: probs.append(f"'{b['text']}' under the YouTube duration badge")
        if b["px"] < 26: probs.append(f"'{b['text']}' {b['px']} px is too small for mobile")
        fx0, fy0, fx1, fy1 = result["face_box"]
        if x0 < fx1 and x1 > fx0 and y0 < fy1 and y1 > fy0: probs.append(f"'{b['text']}' overlaps the instructor's face")
    if max(b["px"] for b in result["text"]) * 0.25 < cfg["thumbnails"]["min_text_px_at_quarter"]: probs.append("no headline readable at 1/4 size")
    txt = " ".join(b["text"] for b in result["text"]).lower()
    if not any(w.lower() in txt for w in topic_words): probs.append("topic words not present in the text")
    return probs

def run(cfg, edl, env, spec_file, pipeline):
    cands = candidates(cfg, edl, env, pipeline)
    if not cands: raise RuntimeError("no usable face frame found (frontal, sharp, eyes visible, in a pause)")
    spec = json.load(open(spec_file, encoding="utf-8")); results = []
    for k, opt in enumerate(spec["options"], 1):
        c = next((c for c in cands if c["t"] == opt.get("frame_t")), cands[min(k - 1, len(cands) - 1)])
        person, ff = cutout(cfg, c["file"], c["file"].replace(".png", "_cut.png"), c.get("face"))
        r = render(cfg, person, ff, opt, os.path.join(cfg["paths"]["thumbnails"], f"thumbnail_option_{k}.png"))
        r.update(frame_t=c["t"], frame_file=c["file"], layout=opt["layout"], qa=qa(cfg, r, spec["topic_words"])); results.append(r)
    json.dump(results, open(os.path.join(cfg["paths"]["thumbnails"], "thumbnails.json"), "w"), indent=1)
    return results
