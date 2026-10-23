"""Premium thumbnails v2 (replaces the Pillow/v1 look). HTML/CSS/SVG compositions rendered by headless Chrome
(puppeteer-core from the HyperFrames install), the instructor's REAL face from the original recording, BiRefNet portrait
segmentation with edge colour clean-up. The .html of each option is kept next to the PNG: text stays editable.

Layouts (genuinely different compositions):
  premium  : headline block left, face right (bust), CPU/circuit illustration bridging text and subject
  concept  : large central diagram (the lecture's own example), minimal headline top, small portrait lower-right
  curious  : face left (half figure), big question right, one meaningful visual (screen of instructions) right-bottom
Faces: chosen by ytpipe.faces (expression, eyes, gaze, pose, sharpness) per concept, or pinned with frame_t. Pixels of
the person are never reshaped, smoothed, sharpened or regenerated; only an alpha matte and edge colour estimation."""
import html as _h, json, os, subprocess
import numpy as np
from PIL import Image, ImageFilter
from . import faces, render as R

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HF_DIR = os.path.join(ROOT, "_work", "hf")
W, H = 1280, 720

def _chrome():
    base = os.path.expanduser(os.path.join("~", ".cache", "hyperframes", "chrome", "chrome-headless-shell"))
    for r, _, fs in os.walk(base):
        if "chrome-headless-shell.exe" in fs or "chrome-headless-shell" in fs:
            return os.path.join(r, "chrome-headless-shell.exe" if os.name == "nt" else "chrome-headless-shell")
    raise FileNotFoundError("headless Chrome not found (installed by HyperFrames on first render)")

# ---------------------------------------------------------------- cut-out
def cutout(frame_png, face_box, out_png, crop="bust"):
    """BiRefNet portrait matte -> largest component only -> 1 px edge tighten -> pymatting foreground colour estimation
    (removes background colour bleeding at hair/shoulders) -> straight bottom edge. Returns (path, face box fractions)."""
    side = out_png.replace(".png", ".json")
    if os.path.exists(out_png) and os.path.exists(side):
        return out_png, json.load(open(side))["face_frac"]
    from rembg import new_session, remove
    from scipy import ndimage as nd
    from pymatting import estimate_foreground_ml
    x, y, w, h = face_box; cx = x + w / 2
    sx, top, bot = {"head": (1.55, 0.9, 2.2), "bust": (2.1, 0.95, 2.7), "half": (2.6, 1.0, 3.4)}[crop]
    im = Image.open(frame_png).convert("RGB")
    box = (int(max(0, cx - sx * w)), int(max(0, y - top * h)), int(min(im.width, cx + sx * w)), int(min(im.height, y + bot * h)))
    c = im.crop(box)
    m = np.asarray(remove(c, session=new_session("birefnet-portrait"), only_mask=True)).astype(np.float64) / 255
    person = np.asarray(remove(c, session=new_session("u2net_human_seg"), only_mask=True)) > 127   # person only: no laptop/desk
    m = m * nd.gaussian_filter(nd.binary_dilation(person, iterations=10).astype(float), 3)
    lab, n = nd.label(m > 0.5)
    if n > 1:
        keep = lab == (1 + int(np.argmax(nd.sum(m > 0.5, lab, range(1, n + 1)))))
        m = m * nd.binary_dilation(keep, iterations=6)                       # drop stray blobs (wall objects), keep soft edge
    m = np.clip((m - 0.04) / 0.92, 0, 1)                                      # tighten the faint outer fringe slightly
    fg = estimate_foreground_ml(np.asarray(c).astype(np.float64) / 255, m)
    rgba = np.dstack([np.clip(fg * 255, 0, 255), m * 255]).astype(np.uint8)
    img = Image.fromarray(rgba, "RGBA"); bb = img.getchannel("A").point(lambda v: 255 if v > 24 else 0).getbbox()
    a = np.asarray(img.getchannel("A")); rows = np.nonzero((a > 128).mean(1) > 0.02)[0]       # straight bottom cut at the
    bottom = int(rows[-1]) + 1 if len(rows) else img.height                                   # last row of real coverage
    # objects in front of the presenter (laptop lid): a band of near-black rows across the lower part -> cut above it
    lum = np.asarray(c.convert("L"))[bb[1]:, bb[0]:bb[2]].astype(float); dark = (lum < 45).mean(1)
    lo = int(0.55 * len(dark))
    for r_ in range(lo, len(dark)):
        if dark[r_] > 0.45 and dark[r_:].mean() > 0.4:
            bottom = min(bottom, r_ - 4); break
    img = img.crop((bb[0], bb[1], bb[2], min(img.height, bottom))); img.save(out_png)
    fx0, fy0 = x - box[0] - bb[0], y - box[1] - bb[1]
    ff = [fx0 / img.width, fy0 / img.height, (fx0 + w) / img.width, (fy0 + h) / img.height]
    json.dump({"face_frac": ff, "frame": frame_png, "crop": crop}, open(side, "w"))
    return out_png, ff

# ---------------------------------------------------------------- shared look
BASE_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Poppins:wght@600;700;800;900&family=JetBrains+Mono:wght@600;700&display=block');
*{margin:0;padding:0;box-sizing:border-box}
html,body{width:1280px;height:720px;overflow:hidden;background:#0C1525}
body{font-family:'Poppins','Segoe UI',sans-serif;color:#F8FAFC;position:relative}
.abs{position:absolute}
.bg{position:absolute;inset:0;background:
  radial-gradient(760px 520px at var(--lx,78%) var(--ly,38%), rgba(56,189,248,.20), transparent 62%),
  radial-gradient(620px 460px at var(--gx,8%) var(--gy,100%), rgba(163,230,53,.13), transparent 65%),
  linear-gradient(155deg,#132542 0%,#0C1525 52%,#070E1A 100%)}
.grid{position:absolute;inset:0;opacity:.22;background-image:linear-gradient(rgba(148,163,184,.16) 1px,transparent 1px),
  linear-gradient(90deg,rgba(148,163,184,.16) 1px,transparent 1px);background-size:48px 48px;
  -webkit-mask-image:radial-gradient(900px 520px at 40% 55%,#000 20%,transparent 75%)}
.noise{position:absolute;inset:0;opacity:.07;mix-blend-mode:overlay}
.vig{position:absolute;inset:0;background:radial-gradient(1100px 700px at 50% 45%,transparent 55%,rgba(0,0,0,.55))}
.hl{font-weight:900;letter-spacing:-.02em;line-height:.92;text-transform:uppercase;text-shadow:0 6px 24px rgba(0,0,0,.45)}
.lime{color:#A3E635}
.person{position:absolute;filter:drop-shadow(0 22px 40px rgba(0,0,0,.55)) drop-shadow(0 0 1px rgba(0,0,0,.35))}
.backlight{position:absolute;border-radius:50%;filter:blur(40px)}
"""
NOISE = ('<svg class="noise" width="1280" height="720"><filter id="n"><feTurbulence type="fractalNoise" baseFrequency=".9" numOctaves="2" '
         'stitchTiles="stitch"/><feColorMatrix type="saturate" values="0"/></filter><rect width="100%" height="100%" filter="url(#n)"/></svg>')

def _hl(lines, accent):
    acc = {a.upper() for a in accent}
    out = []
    for ln in lines:
        words = [f'<span class="lime">{_h.escape(w)}</span>' if w.upper().strip("?!.,") in acc or w.upper() in acc else _h.escape(w)
                 for w in ln.split(" ")]
        out.append(" ".join(words))
    return out

def _person(src, ff, x, y_bottom, height, cls=""):
    im = Image.open(src); w = height * im.width / im.height; y = y_bottom - height
    face = [x + ff[0] * w, y + ff[1] * height, x + ff[2] * w, y + ff[3] * height]
    tag = (f'<img class="person {cls}" data-qa="person" src="file:///{src.replace(os.sep, "/")}" '
           f'style="left:{x:.0f}px;top:{y:.0f}px;height:{height}px">')
    return tag, face, [x, y, x + w, y + height]

# ---------------------------------------------------------------- SVG illustrations
def svg_chip(label="CPU"):
    pins = "".join(f'<rect x="{94 + i * 28}" y="44" width="10" height="26" rx="3" fill="#38BDF8" opacity=".85"/>'
                   f'<rect x="{94 + i * 28}" y="230" width="10" height="26" rx="3" fill="#38BDF8" opacity=".85"/>'
                   f'<rect x="44" y="{94 + i * 28}" width="26" height="10" rx="3" fill="#38BDF8" opacity=".85"/>'
                   f'<rect x="230" y="{94 + i * 28}" width="26" height="10" rx="3" fill="#38BDF8" opacity=".85"/>' for i in range(5))
    traces = "".join(f'<path d="M{99 + i * 28} 44 V{20 - (i % 2) * 8} H{-40 + i * 30}" stroke="#38BDF8" stroke-opacity=".35" stroke-width="2" fill="none"/>'
                     f'<circle cx="{-40 + i * 30}" cy="{20 - (i % 2) * 8}" r="3.5" fill="#A3E635"/>' for i in range(5))
    return (f'<svg width="300" height="300" viewBox="-60 -10 340 300" style="overflow:visible">{traces}'
            '<defs><linearGradient id="cg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#1E3A5F"/><stop offset="1" stop-color="#0F1E36"/></linearGradient>'
            '<linearGradient id="ce" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#A3E635"/><stop offset="1" stop-color="#38BDF8"/></linearGradient></defs>'
            f'{pins}<rect x="70" y="70" width="160" height="160" rx="22" fill="url(#cg)" stroke="url(#ce)" stroke-width="3"/>'
            '<rect x="96" y="96" width="108" height="108" rx="12" fill="#0C1525" stroke="#38BDF8" stroke-opacity=".5"/>'
            f'<text x="150" y="163" text-anchor="middle" font-family="JetBrains Mono" font-weight="700" font-size="34" fill="#F8FAFC">{_h.escape(label)}</text></svg>')

def html_flow(steps):
    """steps [(label, value)] -> glass cards joined by gradient connectors (the lecture's own example)."""
    cards = []
    for k, (lab, val) in enumerate(steps):
        accent = "#A3E635" if k != 1 else "#38BDF8"
        cards.append(f'<div class="card" style="--a:{accent}"><div class="lab">{_h.escape(lab)}</div>'
                     f'<div class="val" data-qa="text">{_h.escape(val)}</div></div>')
        if k < len(steps) - 1:
            cards.append('<div class="conn"><svg width="86" height="40"><defs><linearGradient id="ar" x1="0" x2="1"><stop offset="0" '
                         'stop-color="#A3E635"/><stop offset="1" stop-color="#38BDF8"/></linearGradient></defs><path d="M4 20 H70" '
                         'stroke="url(#ar)" stroke-width="6" stroke-linecap="round"/><path d="M62 8 L80 20 L62 32" fill="none" stroke="#38BDF8" '
                         'stroke-width="6" stroke-linecap="round" stroke-linejoin="round"/></svg></div>')
    return "".join(cards)

def html_screen(lines):
    rows = "".join(f'<div class="ln"><span class="no">{i + 1}</span>{_h.escape(t)}</div>' for i, t in enumerate(lines))
    return (f'<div class="screen"><div class="bar"><i></i><i></i><i></i></div><div class="code">{rows}'
            f'<div class="ln"><span class="no">{len(lines) + 1}</span><span class="cur"></span></div></div></div>')

# ---------------------------------------------------------------- layouts
def _headline(lines, accent, left, top, size, block=True):
    hl = _hl(lines, accent)
    inner = "".join(f'<div data-qa="text" style="display:inline-block;white-space:nowrap">{l}</div><br>' for l in hl) if block \
        else " ".join(f'<span data-qa="text" style="white-space:nowrap">{l}</span>' for l in hl)
    return f'<div class="abs hl" data-qa="headline" style="left:{left}px;top:{top}px;font-size:{size}px">{inner}</div>'

def page_premium(o, person):
    """Headline block left; subject right (bust, ~78 % height); CPU chip anchored bottom-left, traces run to the subject."""
    src, ff = person; im = Image.open(src); h = o.get("person_h", 560); w = h * im.width / im.height
    tag, face, pb = _person(src, ff, 1280 - w + 30 + o.get("person_dx", 0), 720, h)
    body = (f'<div class="backlight" style="left:{pb[0] + 60:.0f}px;top:110px;width:440px;height:440px;background:rgba(56,189,248,.30)"></div>'
            f'<svg class="abs" style="left:0;top:0" width="1280" height="720"><g stroke="#38BDF8" stroke-opacity=".28" stroke-width="2" fill="none">'
            f'<path d="M330 560 H520 L560 520 H{pb[0] + 40:.0f}"/><path d="M330 600 H600 L640 640 H{pb[0] + 20:.0f}"/></g>'
            f'<circle cx="{pb[0] + 40:.0f}" cy="520" r="4" fill="#A3E635"/><circle cx="{pb[0] + 20:.0f}" cy="640" r="4" fill="#A3E635"/></svg>'
            f'<div class="abs" style="left:70px;top:430px;transform:scale(1.05);transform-origin:left top">{svg_chip(o.get("chip", "CPU"))}</div>'
            f'{tag}' + _headline(o["headline"], o.get("accent", ()), 64, 80, o.get("size", 100)))
    return body, face, "--lx:84%;--ly:40%;--gx:10%;--gy:96%"

def page_concept(o, person):
    """The lecture's own example as a large central diagram; minimal headline on top; small portrait lower-right."""
    src, ff = person; im = Image.open(src); h = o.get("person_h", 470); w = h * im.width / im.height
    tag, face, pb = _person(src, ff, 1280 - w + 20 + o.get("person_dx", 0), 720, h)
    css = """.flow{position:absolute;left:64px;top:236px;display:flex;align-items:center}
.card{width:214px;height:200px;border-radius:24px;background:linear-gradient(160deg,rgba(30,41,59,.94),rgba(15,23,42,.94));
  border:2px solid var(--a);box-shadow:0 0 0 6px rgba(255,255,255,.02),0 24px 50px rgba(0,0,0,.45),inset 0 1px 0 rgba(255,255,255,.08);
  display:flex;flex-direction:column;align-items:center;justify-content:center;gap:12px}
.lab{font:800 22px Poppins;letter-spacing:.16em;color:var(--a)}
.val{font:700 58px 'JetBrains Mono';color:#F8FAFC;white-space:nowrap}
.conn{width:74px;display:flex;justify-content:center}.conn svg{width:70px}"""
    body = (f'<style>{css}</style>' + _headline(o["headline"], o.get("accent", ()), 64, 84, o.get("size", 74), block=False) +
            f'<div class="flow">{html_flow(o["flow"])}</div>'
            f'<div class="backlight" style="left:{pb[0] + 40:.0f}px;top:300px;width:380px;height:380px;background:rgba(163,230,53,.20)"></div>{tag}')
    return body, face, "--lx:34%;--ly:52%;--gx:94%;--gy:96%"

def page_curious(o, person):
    """Subject left (half figure), big question right, one visual: the screen of instructions that answers it."""
    src, ff = person; im = Image.open(src); h = o.get("person_h", 600); w = h * im.width / im.height
    tag, face, pb = _person(src, ff, -40 + o.get("person_dx", 0), 720, h)
    left = int(face[2] + 0.35 * (face[2] - face[0]) + 40)                     # text starts right of the head, not the shoulders
    css = """.screen{position:absolute;top:420px;width:500px;height:226px;border-radius:18px;background:#0B1322;
  border:2px solid rgba(56,189,248,.55);box-shadow:0 30px 60px rgba(0,0,0,.5),0 0 40px rgba(56,189,248,.12);transform:perspective(900px) rotateY(-10deg)}
.bar{height:34px;border-bottom:1px solid rgba(148,163,184,.2);display:flex;gap:8px;align-items:center;padding-left:14px}
.bar i{width:11px;height:11px;border-radius:50%;background:#334155}.bar i:first-child{background:#A3E635}
.code{padding:14px 22px;font:600 27px 'JetBrains Mono';color:#E2E8F0}
.ln{height:40px;display:flex;align-items:center}.no{width:34px;color:#475569;font-size:21px}
.cur{width:16px;height:30px;background:#A3E635;display:inline-block}"""
    body = (f'<style>{css}</style><div class="backlight" style="left:30px;top:120px;width:520px;height:520px;background:rgba(56,189,248,.24)"></div>'
            f'{tag}' + _headline(o["headline"], o.get("accent", ()), left, 84, o.get("size", 100)) +
            html_screen(o["screen"]).replace('class="screen"', f'class="screen" style="left:{left + 10}px"'))
    return body, face, "--lx:20%;--ly:45%;--gx:96%;--gy:8%"

LAYOUTS = {"premium": (page_premium, "confident", "bust"), "concept": (page_concept, "explaining", "head"),
           "curious": (page_curious, "curious", "half")}

def render(o, person, out_png):
    body, face, vars_ = LAYOUTS[o["layout"]][0](o, person)
    doc = (f'<!doctype html><html><head><meta charset="utf-8"><style>{BASE_CSS}</style></head><body style="{vars_}">'
           f'<div class="bg"></div><div class="grid"></div>{NOISE}{body}<div class="vig"></div></body></html>')
    html_path = out_png.replace(".png", ".html"); open(html_path, "w", encoding="utf-8").write(doc)
    env = dict(os.environ, HF_DIR=HF_DIR, CHROME=_chrome()); bj = out_png.replace(".png", ".boxes.json")
    r = subprocess.run(["node", os.path.join(ROOT, "assets", "thumbnails", "render_html.js"), html_path, out_png, bj], env=env, capture_output=True, text=True)
    if r.returncode: raise RuntimeError(r.stderr[-600:])
    info = json.load(open(bj)); info["face_box"] = face
    return info

# ---------------------------------------------------------------- QA
def head_box(face):
    """Face landmarks box -> head box: +55 % of face height above (hair), +18 % each side (ears/hair), +8 % below."""
    x0, y0, x1, y1 = face; w, h = x1 - x0, y1 - y0
    return [x0 - 0.18 * w, y0 - 0.55 * h, x1 + 0.18 * w, y1 + 0.08 * h]

def fit(o, info, cfg):
    """One fitting step from the measured layout; returns updated option params or None when nothing must change."""
    m = cfg["thumbnails"]["safe_margin"]; hb = head_box(info["face_box"]); o = dict(o)
    t = [b for b in info["boxes"] if b["qa"] == "text"]
    right = max(b["x"] + b["w"] for b in t); left = min(b["x"] for b in t); bottom = max(b["y"] + b["h"] for b in t)
    over = right - (W - m)
    hits = [b for b in t if b["x"] < hb[2] and b["x"] + b["w"] > hb[0] and b["y"] < hb[3] and b["y"] + b["h"] > hb[1]]
    if not over > 0 and not hits: return None
    if o["layout"] == "premium":                      # subject right of a left text block: slide right, then shrink
        need = max(b["x"] + b["w"] for b in hits) + 30 - hb[0] if hits else 0
        if o.get("person_dx", 0) + need <= 160: o["person_dx"] = o.get("person_dx", 0) + need
        else: o["person_h"] = int(o.get("person_h", 560) * 0.92)
    elif o["layout"] == "curious":                    # text right of the subject: move subject left, shrink it, then the text
        if over > 0 and o.get("person_dx", 0) > -120: o["person_dx"] = o.get("person_dx", 0) - min(120, over)
        elif over > 0 and o.get("person_h", 600) > 500: o["person_h"] = int(o.get("person_h", 600) * 0.93)
        else: o["size"] = int(o.get("size", 100) * 0.94)
    else:                                             # concept: portrait lower-right, keep it below/right of the diagram
        o["person_h"] = int(o.get("person_h", 470) * 0.93)
    return o

def qa(cfg, info, png, topic_words, headline_words_max=5):
    p = []; im = Image.open(png); m = cfg["thumbnails"]["safe_margin"]
    if im.size != (W, H): p.append(f"size {im.size}")
    if not {"Poppins 900"} <= set(info["fonts"]): p.append(f"headline font not loaded: {info['fonts']}")
    texts = [b for b in info["boxes"] if b["qa"] in ("text", "headline")]; fx0, fy0, fx1, fy1 = head_box(info["face_box"])
    pad = 0.04 * (fx1 - fx0)
    for b in texts:
        x0, y0, x1, y1 = b["x"], b["y"], b["x"] + b["w"], b["y"] + b["h"]
        if x0 < m - 1 or y0 < m * 0.75 - 1 or x1 > W - m + 1 or y1 > H - m * 0.75 + 1: p.append(f"'{b['text']}' outside the safe margin")
        if x1 > W - 190 and y1 > H - 80: p.append(f"'{b['text']}' under the duration badge")
        if x0 < fx1 + pad and x1 > fx0 - pad and y0 < fy1 + pad and y1 > fy0 - pad: p.append(f"'{b['text']}' overlaps the face")
        if b["font_px"] * 0.25 < 13: p.append(f"'{b['text']}' {b['font_px']}px: too small on a phone")
    hw = " ".join(b["text"] for b in info["boxes"] if b["qa"] == "headline").split()
    if len(hw) > headline_words_max: p.append(f"headline has {len(hw)} words (max {headline_words_max})")
    if (fx1 - fx0) < 110: p.append("face too small to read on a phone")
    if (fx1 - fx0) > 330: p.append("face too large (oversized cut-out)")
    colors = {b["color"] for b in texts if b["font_px"] >= 60}
    return p

def distinct(pngs):
    """Pairwise visual difference of 64x36 grayscale thumbnails (layout-level); < 18 means too similar."""
    a = [np.asarray(Image.open(x).convert("L").resize((64, 36))).astype(float) for x in pngs]
    return {f"{i + 1}-{j + 1}": round(float(np.abs(a[i] - a[j]).mean()), 1) for i in range(len(a)) for j in range(i + 1, len(a))}

def run(cfg, rows, spec_file, out_dir, name="thumbnail_premium_v2", only=None):
    spec = json.load(open(spec_file, encoding="utf-8")); res = []; fdir = os.path.join(out_dir, "frames_v2"); os.makedirs(fdir, exist_ok=True)
    for k, o in enumerate(spec["options"], 1):
        if only and k not in only: continue
        page, concept, crop = LAYOUTS[o["layout"]]
        cand = [r for r in rows if abs(r["t"] - o["frame_t"]) < 0.01] if o.get("frame_t") else faces.pick(rows, concept, 1)
        if not cand: raise RuntimeError(f"no usable face frame for '{concept}' (reasons: {faces.rejection_summary(rows)})")
        r = cand[0]; fr = os.path.join(fdir, f"F{r['t']:07.2f}.png")
        if not os.path.exists(fr):
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-init_hw_device", "vulkan", "-ss", f"{r['t']:.2f}", "-i", cfg["sources"]["face_camera"],
                            "-frames:v", "1", "-vf", R.face_filter(cfg, "libplacebo", 1920, 1080, R.wide_crop(cfg["sources"]["face_camera"]), "yuv420p"), fr], check=True)
        person = cutout(fr, r["box"], fr.replace(".png", f"_{crop}_cut.png"), crop)
        png = os.path.join(out_dir, f"{name}_{k}.png"); info = render(o, person, png)
        for _ in range(4):                                       # measured-layout fitting (text never on the head, inside margins)
            o2 = fit(o, info, cfg)
            if o2 is None: break
            o = o2; info = render(o, person, png)
        fitted = {k2: o[k2] for k2 in ("person_h", "person_dx", "size") if k2 in o}
        res.append({"file": png, "html": png.replace(".png", ".html"), "layout": o["layout"], "frame_t": r["t"], "fitted": fitted, "expression": {x: r[x] for x in ("smile", "jaw", "blink", "yaw", "roll")},
                    "qa": qa(cfg, info, png, spec["topic_words"])})
    d = distinct([os.path.join(out_dir, f"{name}_{k}.png") for k in range(1, len(spec["options"]) + 1)
                  if os.path.exists(os.path.join(out_dir, f"{name}_{k}.png"))])
    for r in res: r["distinct"] = d
    json.dump(res, open(os.path.join(out_dir, f"{name}.json"), "w"), indent=1)
    return res
