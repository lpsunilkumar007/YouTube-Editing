"""Graphics: chip bar, slide-counter badges and HyperFrames elements (generic ports of make_graphics_v6.py and
make_overlays_v9.py; approved sizes: chips 26 px / 48 px high, section label 22 px, badge 23 px / 42 px high).

Chip timeline : [(F, lead, chips, active)] (face time) -> one RGBA MOV per segment, 0.25 s crossfades.
Elements      : {"kind", "start" (F), "duration", params}. Kinds: title, topic, term, ipo, rings, end, code (spec'd scaffold).
               'rings' takes the diagram's circles [{"cx","cy","r","color"}] in CANVAS px (from the card geometry), so
               nothing is tied to Lesson 01's slide 3. HyperFrames is run from _work/hf (local install, v0.8.181)."""
import json, os, shutil, subprocess
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HF_INSTALL = os.path.join(ROOT, "_work", "hf")
CHIP_PT, LEAD_PT, CHIP_H, CNT_PT, CNT_H = 26, 22, 48, 23, 42

def _f(cfg, kind, pt):
    return ImageFont.truetype(os.path.join(ROOT, cfg["graphics"]["font_bold" if kind == "bold" else "font_semibold"]), pt)

def bar_state(cfg, wh, lead, chips, active):
    p = cfg["graphics"]["palette"]; im = Image.new("RGBA", tuple(wh), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    fl, fc = _f(cfg, "bold", LEAD_PT), _f(cfg, "semi", CHIP_PT); cy = wh[1] // 2; x = 8; lead = lead.upper()
    d.text((x, cy), lead, font=fl, fill=p["cyan"], anchor="lm"); x += int(d.textlength(lead, font=fl)) + 24
    for i, c in enumerate(chips):
        cw = int(d.textlength(c, font=fc)) + 44; on = i == active
        d.rounded_rectangle([x, cy - CHIP_H // 2, x + cw, cy + CHIP_H // 2], CHIP_H // 2, fill=p["lime"] if on else p["card"],
                            outline=None if on else p["border"], width=1)
        d.text((x + cw // 2, cy + 1), c, font=fc, fill=p["canvas"] if on else p["muted"], anchor="mm"); x += cw
        if i < len(chips) - 1:
            d.text((x + 18, cy), "→", font=fc, fill=p["muted"], anchor="mm"); x += 36
    if x >= wh[0]:
        raise ValueError(f"chip row '{lead}: {chips}' is {x}px, wider than the bar ({wh[0]}px): shorten the labels")
    return np.asarray(im).astype(np.float32)

def bar_video(cfg, g, timeline, fa, fb, path, fade=0.25):
    fps = cfg["output"]["fps"]; wh = (g["bar"][2], g["bar"][3]); n = int(np.ceil((fb - fa) * fps)) + 2; cache = {}
    def frame(st):
        k = (st[1], tuple(st[2]), st[3])
        if k not in cache: cache[k] = bar_state(cfg, wh, st[1], st[2], st[3])
        return cache[k]
    tl = sorted(timeline); p = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{wh[0]}x{wh[1]}",
                                                  "-r", str(fps), "-i", "-", "-c:v", "qtrle", "-pix_fmt", "argb", path], stdin=subprocess.PIPE)
    for k in range(n):
        t = fa + k / fps; idx = [j for j, s in enumerate(tl) if s[0] <= t + 1e-9]
        if not idx: cur = np.zeros((wh[1], wh[0], 4), np.float32)
        else:
            i = idx[-1]; cur = frame(tl[i])
            if i > 0 and t - tl[i][0] < fade and tl[i][0] > fa:
                u = (t - tl[i][0]) / fade; u = u * u * (3 - 2 * u); cur = frame(tl[i - 1]) * (1 - u) + cur * u
        p.stdin.write(cur.round().astype(np.uint8).tobytes())
    p.stdin.close(); p.wait()
    return path

def badge(cfg, n, total, path):
    p = cfg["graphics"]["palette"]; f = _f(cfg, "semi", CNT_PT); s = f"{n:02d} / {total}"
    w = int(ImageDraw.Draw(Image.new("L", (1, 1))).textlength(s, font=f)) + 36
    im = Image.new("RGBA", (w, CNT_H), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, w - 1, CNT_H - 1], CNT_H // 2, fill=p["card"], outline=p["border"], width=1)
    d.text((w // 2, CNT_H // 2 + 1), s, font=f, fill=p["muted"], anchor="mm"); im.save(path)
    return path, w

# ---------------------------------------------------------------- HyperFrames elements
HEAD = open(os.path.join(ROOT, "assets", "hyperframes", "element_head.html"), encoding="utf-8").read()   # %(cid)s %(dur)s %(body)s %(js)s

def _term(p):
    t = p["t"]; big = ' style="font-size:26px"' if len(t) > 10 else ""
    return (f'<div class="term" id="c"><div class="k">{p.get("label", "KEY TERM")}</div><div class="t"{big}>{t}</div><div class="bar"></div>'
            f'<div class="d">{p["d"]}</div></div>',
            '  tl.fromTo("#c", { opacity: 0, x: 14 }, { opacity: 1, x: 0, duration: 0.35 }, 0)\n'
            '    .from("#c .bar", { scaleX: 0, duration: 0.4 }, 0.15).to("#c", { opacity: 0, duration: 0.35, ease: "power1.in" }, D - 0.35);')

def _panel(p, where, kicker, body_html, kick_px=17):
    pos = "left:64px; top:56px; max-width:560px" if where == "top" else "left:64px; bottom:64px"
    return (f'<div class="panel" id="c" style="{pos}; padding:16px 26px 18px 30px"><div class="acc"></div>'
            f'<div class="label" style="font-size:{kick_px}px">{kicker}</div>{body_html}</div>',
            '  tl.fromTo("#c", { opacity: 0, x: -14 }, { opacity: 1, x: 0, duration: 0.35 }, 0)\n'
            '    .from("#c .acc", { scaleY: 0, duration: 0.4 }, 0.1).to("#c", { opacity: 0, duration: 0.35, ease: "power1.in" }, D - 0.35);')

def _rings(p):
    """p: circles [{cx, cy, r, color}] in canvas px, times [local s per circle], clear_at (local s, before first pen stroke)."""
    cs, T = p["circles"], p["times"]; svg = ['<svg width="1920" height="1080" viewBox="0 0 1920 1080" fill="none"><g stroke-width="4" stroke-linecap="round">']
    for i, c in enumerate(cs):
        svg.append(f'<circle class="halo" id="h{i}" cx="{c["cx"]}" cy="{c["cy"]}" r="{c["r"] + 12}" stroke="{c["color"]}" color="{c["color"]}" opacity="0"/>')
    for a, b in zip(cs, cs[1:]):
        x0, x1, y = a["cx"] + a["r"] + 20, b["cx"] - b["r"] - 20, (a["cy"] + b["cy"]) / 2
        svg.append(f'<path class="ar" d="M{x0} {y} H{x1} M{x1 - 12} {y - 10} L{x1 + 2} {y} L{x1 - 12} {y + 10}" stroke="#A3E635" opacity="0"/>')
    svg.append("</g></svg>")
    js = (f"  const T = {json.dumps(T)};\n"
          "  T.forEach((t, k) => { tl.fromTo('#h' + k, { opacity: 0, scale: 0.9, transformOrigin: '50% 50%' }, { opacity: 0.95, scale: 1, duration: 0.35 }, t);\n"
          "    if (k < T.length - 1) tl.to('#h' + k, { opacity: 0.45, duration: 0.4 }, T[k + 1]); });\n"
          "  document.querySelectorAll('.ar').forEach((a, k) => { const L = a.getTotalLength(); gsap.set(a, { strokeDasharray: L, strokeDashoffset: L, opacity: 0 });\n"
          "    tl.set(a, { opacity: 0.9 }, T[k + 1] - 0.3).to(a, { strokeDashoffset: 0, duration: 0.3, ease: 'power1.inOut' }, T[k + 1] - 0.3); });\n"
          f"  tl.to('svg g > *', {{ opacity: 0, duration: 0.6, ease: 'power1.in' }}, {p['clear_at'] - 0.6});")
    return "\n".join(svg), js

def _steps(p):
    names, T = p["steps"], p["times"]; ids = []
    body = f'<div class="term" id="topic"><div class="k">{p.get("label", "NEW TOPIC")}</div><div class="t" style="font-size:26px">{p["title"]}</div><div class="steps">'
    for i, n in enumerate(names):
        body += f'<div class="st" id="s{i}">{n}</div>' + (f'<div class="dn" id="d{i}"><i></i></div>' if i < len(names) - 1 else "")
    body += "</div></div>"
    js = (f"  const LIT = {{ backgroundColor: '#A3E635', color: '#101827', borderColor: '#A3E635', duration: 0.25 }}; const T = {json.dumps(T)};\n"
          "  tl.fromTo('#topic', { opacity: 0, x: 14 }, { opacity: 1, x: 0, duration: 0.35 }, 0);\n"
          "  T.forEach((t, k) => { if (k) tl.set('#d' + (k - 1), { opacity: 1 }, t - 0.25).to('#d' + (k - 1) + ' i', { scaleY: 1, duration: 0.25 }, t - 0.25);\n"
          "    tl.fromTo('#s' + k, { opacity: 0, y: -6 }, { opacity: 1, y: 0, duration: 0.25 }, t).to('#s' + k, LIT, t);\n"
          "    if (k) tl.to('#s' + (k - 1), { backgroundColor: '#1E293B', color: '#F8FAFC', borderColor: '#A3E635', duration: 0.3 }, t); });\n"
          "  tl.to('#topic', { opacity: 0, duration: 0.4, ease: 'power1.in' }, D - 0.4);")
    return body, js

def _code(p):
    """Code-line highlight (scaffold, untested in a lecture): a lime bar beside line boxes [{x, y, w, h, t}] in canvas px."""
    body = "".join(f'<div class="cl" id="l{i}" style="position:absolute; left:{b["x"]}px; top:{b["y"]}px; width:{b["w"]}px; height:{b["h"]}px;'
                   f' border-left:5px solid #A3E635; background:rgba(163,230,53,.10); opacity:0"></div>' for i, b in enumerate(p["lines"]))
    js = "".join(f"  tl.to('#l{i}', {{ opacity: 1, duration: 0.25 }}, {b['t']}).to('#l{i}', {{ opacity: 0, duration: 0.3 }}, {b.get('t_end', 'D - 0.3')});\n"
                 for i, b in enumerate(p["lines"]))
    return body, js

KINDS = {"term": _term, "rings": _rings, "ipo": _steps, "steps": _steps, "code": _code,
         "topic": lambda p: _panel(p, "top", p.get("label", "Topic"), f'<div style="font-weight:700; font-size:34px; line-height:1.15; margin-top:4px">{p["text"]}</div>'),
         "title": lambda p: _panel(p, "bottom", p["kicker"], '<div id="tt" style="font-weight:700; font-size:52px; line-height:1.08; margin-top:8px">'
                                   + "<br>".join(f"<span>{l}</span>" for l in p["lines"]) + "</div>", 20),
         "end": lambda p: _panel(p, "bottom", p.get("label", "Next lesson"), f'<div style="font-weight:700; font-size:44px; margin-top:6px">{p["text"]}</div>', 18)}

def element_html(el):
    cid = f"el_{el['kind']}_{el['start']:08.2f}".replace(".", "_"); body, js = KINDS[el["kind"]](el)
    return cid, HEAD % {"cid": cid, "dur": el["duration"], "body": body, "js": js}

def render_elements(cfg, elements, force=False):
    """Writes compositions to lessons/<id>/assets/hf and renders each to ProRes 4444 (alpha). Returns {start: mov}."""
    proj = os.path.join(cfg["paths"]["assets"], "hf"); out = os.path.join(proj, "out"); os.makedirs(out, exist_ok=True)
    for f in ("style.css", "hyperframes.json", "package.json"):
        shutil.copy(os.path.join(ROOT, "assets", "hyperframes", f), os.path.join(proj, f))
    res = {}
    for el in elements:
        cid, html = element_html(el); open(os.path.join(proj, cid + ".html"), "w", encoding="utf-8").write(html)
        mov = os.path.join(out, cid + ".mov"); res[el["start"]] = mov
        if os.path.exists(mov) and not force: continue
        r = subprocess.run(["npx.cmd" if os.name == "nt" else "npx", "hyperframes", "render", proj, "-c", cid + ".html", "--format", "mov",
                            "-o", mov, "--quiet"], cwd=HF_INSTALL, capture_output=True, text=True)
        if not (os.path.exists(mov) and os.path.getsize(mov)): raise RuntimeError(f"HyperFrames failed for {cid}: {r.stderr[-400:]}")
    return res
