"""Stage 'blog': a Medium-style, SEO-checked article for each lesson video, ready to paste into Medium or a website CMS.

Creative text lives in metadata/blog_input.json (written by Claude from content_brief.md and the transcript, reviewed by
the user; it says only what the video says, plus clearly general explanations). Deterministic here: the article layout
(kicker, title, subtitle, cover, video, sections, chapters with timestamp links, takeaways, FAQ, call to action), SEO
checks, and the files in <lesson>/blog/:
  <slug>.md        Markdown (WordPress, Ghost, dev.to, Hashnode; Medium: paste the HTML version instead)
  <slug>.html      the article rendered: open it in a browser, select the article and paste it into Medium or any editor
                   (headings, lists, links, quotes and code blocks survive the paste); its <head> carries the SEO tags
                   and JSON-LD (BlogPosting, VideoObject, FAQPage) for your own website
  <slug>-cover.png the approved thumbnail, as the cover image
  SEO.txt          the fields a CMS asks for: SEO title, meta description, slug, focus keyword, tags, cover alt text

blog_input.json: title, subtitle, kicker, slug, focus_keyword, seo_title, meta_description, tags (<= 5, Medium's limit),
cover_alt, author, site_url, video_url (empty until the video is uploaded), intro [blocks], sections [{heading, body}],
takeaways [str], faq [{q, a}], cta [blocks], related [{title, url}], shorts_urls [str] (optional, after upload: one per
Short, in the order listed). The "Watch the short versions" section is built from the Shorts metadata files, not typed. A block is a paragraph string; a block may also be
"- item" lines (list), "1. item" lines (numbered), "> quote", or a ``` fenced code block. Inline: **bold**, *italic*,
`code`, [text](url)."""
import glob, html, json, os, re, shutil, time

WPM = 230                                             # reading speed for the "N min read" line

def _inline_html(s):
    s = html.escape(s, quote=False)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<![*\w])\*(?!\s)(.+?)(?<!\s)\*(?![*\w])", r"<em>\1</em>", s)
    return re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2">\1</a>', s)

def _block_html(b):
    lines = b.split("\n")
    if b.startswith("```"):
        return "<pre><code>" + html.escape("\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])) + "</code></pre>"
    if all(l.startswith("- ") for l in lines):
        return "<ul>" + "".join(f"<li>{_inline_html(l[2:])}</li>" for l in lines) + "</ul>"
    if all(re.match(r"\d+\. ", l) for l in lines):
        return "<ol>" + "".join(f"<li>{_inline_html(l.split('. ', 1)[1])}</li>" for l in lines) + "</ol>"
    if b.startswith("> "):
        return "<blockquote>" + "<br>".join(_inline_html(l[2:] if l.startswith("> ") else l) for l in lines) + "</blockquote>"
    return f"<p>{_inline_html(b)}</p>"

def _text(b):
    """Plain words of a block (for word counts and keyword checks)."""
    b = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", b)
    return re.sub(r"[*`>#]|^\d+\. |^- ", " ", b, flags=re.M)

def video_id(url):
    m = re.search(r"(?:youtu\.be/|v=|/shorts/|/embed/)([\w-]{11})", url or "")
    return m.group(1) if m else None

def chapters_from(path):
    """youtube_chapters.txt -> [(seconds, title)]."""
    out = []
    for l in open(path, encoding="utf-8") if os.path.exists(path) else []:
        m = re.match(r"((?:\d+:)?\d+:\d\d)\s+(.+)", l.strip())
        if m: out.append((sum(int(x) * 60 ** k for k, x in enumerate(reversed(m.group(1).split(":")))), m.group(2)))
    return out

def shorts_from(P):
    """The lesson's Shorts from their metadata files (same order as UPLOAD_COPY) -> [(title, clip_start_s, seconds)]."""
    out = []
    dirs = [os.path.join(P["metadata"], "shorts")] + ([os.path.join(P["shorts"], "metadata")] if P.get("shorts") else [])
    for f in sorted(f for d in dirs for f in glob.glob(os.path.join(d, "*.md"))):
        md = open(f, encoding="utf-8").read(); t = re.search(r"\*\*Title:\*\* (.+)", md)
        c = re.search(r"\*\*Clip:\*\* (\d+):(\d\d)\D+\d+:\d\d of the final video \(([\d.]+) s\)", md)
        if t: out.append((t.group(1).strip(), int(c.group(1)) * 60 + int(c.group(2)) if c else None, round(float(c.group(3))) if c else None))
    return out

def check(inp, words):
    """SEO and honesty checks -> list of problems (empty = pass). Lengths follow common search-result truncation."""
    p, kw = [], inp["focus_keyword"].lower(); has = lambda s: kw in (s or "").lower()
    if not 30 <= len(inp["seo_title"]) <= 60: p.append(f"SEO title is {len(inp['seo_title'])} chars (30-60)")
    if not has(inp["seo_title"]): p.append("focus keyword missing from the SEO title")
    if not 120 <= len(inp["meta_description"]) <= 160: p.append(f"meta description is {len(inp['meta_description'])} chars (120-160)")
    if not has(inp["meta_description"]): p.append("focus keyword missing from the meta description")
    if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", inp["slug"]) or len(inp["slug"]) > 60: p.append("slug: lowercase words joined by hyphens, <= 60 chars")
    if not all(w in inp["slug"].split("-") for w in re.findall(r"[a-z0-9]+", kw) if len(w) > 2): p.append("slug lacks the focus keyword's words")
    if not has(_text(inp["intro"][0])): p.append("focus keyword missing from the first paragraph")
    if not any(has(s["heading"]) for s in inp["sections"]): p.append("focus keyword in no section heading")
    if len(inp["tags"]) > 5: p.append("more than 5 tags (Medium allows 5)")
    if words < 800: p.append(f"{words} words; aim for 800+ for a search-friendly article")
    if not inp.get("cover_alt"): p.append("cover image alt text missing")
    blob = json.dumps(inp, ensure_ascii=False)
    for bad in ("≈", "[unclear", "{{"):
        if bad in blob: p.append(f"unresolved marker {bad!r} in the text")
    return p

def todo(inp, shorts=()):
    """Fields that can only be filled later or by the user: reported, not failures."""
    out = [m for k, m in (("video_url", "add video_url after uploading the video (then rerun): enables the embed, timestamp links and VideoObject schema"),
                          ("author", "add the author name as it should appear on the blog"),
                          ("site_url", "add site_url (your blog's address) for the canonical link")) if not inp.get(k)]
    if len([u for u in inp.get("shorts_urls", []) if u]) < len(shorts):
        out.append(f"add shorts_urls (one per Short, in the order of the 'Watch the short versions' list) after uploading the {len(shorts)} Shorts")
    return out

def build(cfg, inp, cover=None):
    P = cfg["paths"]; out = os.path.join(P["root"], "blog"); os.makedirs(out, exist_ok=True); slug = inp["slug"]
    url, vid = inp.get("video_url", ""), video_id(inp.get("video_url", ""))
    ch = chapters_from(os.path.join(P["metadata"], "youtube_chapters.txt"))
    at = lambda t: f"https://www.youtube.com/watch?v={vid}&t={t}s" if vid else None
    mm = lambda t: f"{t // 60}:{t % 60:02d}"
    img = None
    if cover and os.path.exists(cover):
        img = f"{slug}-cover.png"; shutil.copy2(cover, os.path.join(out, img))
    # ---- one ordered list of (kind, payload): both renderers walk it
    doc = [("kicker", inp.get("kicker", "")), ("title", inp["title"]), ("subtitle", inp.get("subtitle", ""))]
    if img: doc.append(("image", (img, inp.get("cover_alt", ""))))
    doc += [("block", b) for b in inp["intro"]]
    doc.append(("video", url))
    for s in inp["sections"]:
        doc.append(("h2", s["heading"])); doc += [("block", b) for b in s["body"]]
    if ch:
        doc.append(("h2", "Video chapters")); doc.append(("chapters", ch))
    shorts = shorts_from(P); su = inp.get("shorts_urls", [])
    if shorts:                                        # the lesson's Shorts: link once uploaded, and where each sits in the full video
        def line(k, title, t0, sec):
            u = su[k] if k < len(su) and su[k] else ""; name = f"[{title}]({u})" if u else f"**{title}**"
            info = ", ".join(x for x in ((f"{sec} s Short" if sec else "Short") + ("" if u else ", link after upload"),
                                         (f"from [{mm(t0)}]({at(t0)}) in the full video" if vid else f"from {mm(t0)} in the full video") if t0 is not None else "") if x)
            return f"- {name} ({info})"
        doc.append(("h2", "Watch the short versions"))
        doc.append(("block", "Short on time? These Shorts from this lesson each make one point in under a minute."))
        doc.append(("block", "\n".join(line(k, *s) for k, s in enumerate(shorts))))
    if inp.get("takeaways"):
        doc.append(("h2", "Key takeaways")); doc.append(("block", "\n".join(f"- {t}" for t in inp["takeaways"])))
    if inp.get("faq"):
        doc.append(("h2", "Frequently asked questions"))
        for f in inp["faq"]: doc += [("h3", f["q"]), ("block", f["a"])]
    if inp.get("cta"):
        doc.append(("hr", None)); doc += [("block", b) for b in inp["cta"]]
    if inp.get("related"):
        doc.append(("h2", "More in this series")); doc.append(("block", "\n".join(f"- [{r['title']}]({r['url']})" for r in inp["related"])))
    words = sum(len(_text(x).split()) for k, x in doc if k in ("block", "h2", "h3", "title", "subtitle"))
    words += sum(len(t.split()) for k, x in doc if k == "chapters" for _, t in x)
    mins = max(1, round(words / WPM))
    # ---- Markdown
    md = []
    for k, x in doc:
        if k == "kicker" and x: md.append(f"*{x}*")
        elif k == "title": md.append(f"# {x}")
        elif k == "subtitle" and x: md.append(f"### {x}\n\n*{mins} min read*")
        elif k == "image": md.append(f"![{x[1]}]({x[0]})")
        elif k == "video": md.append(f"**Watch the video:**\n\n{x}" if x else "**Watch the video:** _(YouTube link goes here after upload)_")
        elif k == "h2": md.append(f"## {x}")
        elif k == "h3": md.append(f"### {x}")
        elif k == "chapters": md.append("\n".join(f"- [{mm(t)}]({at(t)}) {n}" if vid else f"- {mm(t)} {n}" for t, n in x))
        elif k == "hr": md.append("---")
        elif k == "block": md.append(x)
    open(os.path.join(out, f"{slug}.md"), "w", encoding="utf-8").write("\n\n".join(md) + "\n")
    # ---- HTML (article for pasting + head for your own site)
    body = []
    for k, x in doc:
        if k == "kicker" and x: body.append(f'<p class="kicker">{html.escape(x)}</p>')
        elif k == "title": body.append(f"<h1>{html.escape(x)}</h1>")
        elif k == "subtitle" and x: body.append(f'<p class="subtitle">{html.escape(x)}</p><p class="meta">{mins} min read</p>')
        elif k == "image": body.append(f'<figure><img src="{x[0]}" alt="{html.escape(x[1], quote=True)}"></figure>')
        elif k == "video":
            body.append(f'<figure class="video"><iframe src="https://www.youtube.com/embed/{vid}" title="{html.escape(inp["title"], quote=True)}" '
                        f'allowfullscreen loading="lazy"></iframe><figcaption><a href="{html.escape(x, quote=True)}">Watch on YouTube</a></figcaption></figure>'
                        if vid else '<p class="todo">[Video embed: add video_url after uploading]</p>')
        elif k in ("h2", "h3"): body.append(f'<{k} id="{re.sub(r"[^a-z0-9]+", "-", x.lower()).strip("-")}">{_inline_html(x)}</{k}>')
        elif k == "chapters":
            body.append("<ul>" + "".join(f'<li><a href="{at(t)}">{mm(t)}</a> {html.escape(n)}</li>' if vid else f"<li>{mm(t)} {html.escape(n)}</li>"
                                         for t, n in x) + "</ul>")
        elif k == "hr": body.append("<hr>")
        elif k == "block": body.append(_block_html(x))
    canon = f"{inp['site_url'].rstrip('/')}/{slug}" if inp.get("site_url") else ""
    ld = [{"@context": "https://schema.org", "@type": "BlogPosting", "headline": inp["seo_title"], "description": inp["meta_description"],
           "keywords": ", ".join(inp["tags"]), "wordCount": words, "inLanguage": "en",
           **({"author": {"@type": "Person", "name": inp["author"]}} if inp.get("author") else {}),
           **({"image": f"{inp['site_url'].rstrip('/')}/{img}" if inp.get("site_url") else img} if img else {}),
           **({"mainEntityOfPage": canon} if canon else {})}]
    if vid:
        ld.append({"@context": "https://schema.org", "@type": "VideoObject", "name": inp["title"], "description": inp["meta_description"],
                   "thumbnailUrl": f"https://i.ytimg.com/vi/{vid}/maxresdefault.jpg", "embedUrl": f"https://www.youtube.com/embed/{vid}",
                   "contentUrl": url, "uploadDate": inp.get("upload_date") or time.strftime("%Y-%m-%d")})
    if inp.get("faq"):
        ld.append({"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
            {"@type": "Question", "name": f["q"], "acceptedAnswer": {"@type": "Answer", "text": _text(f["a"]).strip()}} for f in inp["faq"]]})
    esc = lambda s: html.escape(s, quote=True)
    head = (f"<title>{esc(inp['seo_title'])}</title>\n<meta name=\"description\" content=\"{esc(inp['meta_description'])}\">\n"
            + (f"<link rel=\"canonical\" href=\"{esc(canon)}\">\n" if canon else "")
            + f"<meta property=\"og:type\" content=\"article\">\n<meta property=\"og:title\" content=\"{esc(inp['title'])}\">\n"
            f"<meta property=\"og:description\" content=\"{esc(inp['meta_description'])}\">\n"
            + (f"<meta property=\"og:image\" content=\"{esc(img)}\">\n<meta name=\"twitter:card\" content=\"summary_large_image\">\n" if img else "")
            + "".join(f'<script type="application/ld+json">{json.dumps(x, ensure_ascii=False)}</script>\n' for x in ld))
    css = ("body{margin:0;background:#fff;color:#242424}article{max-width:680px;margin:0 auto;padding:48px 20px 96px;"
           "font:20px/1.6 Charter,Georgia,'Times New Roman',serif}h1,h2,h3,.kicker,.subtitle,.meta,figcaption{font-family:"
           "-apple-system,'Segoe UI',Helvetica,Arial,sans-serif}h1{font-size:42px;line-height:1.2;margin:.2em 0}h2{font-size:26px;"
           "margin:1.8em 0 .4em}h3{font-size:21px;margin:1.4em 0 .3em}.kicker{color:#6b6b6b;text-transform:uppercase;font-size:14px;"
           "letter-spacing:.06em;margin:0}.subtitle{color:#6b6b6b;font-size:22px;margin:.2em 0}.meta{color:#6b6b6b;font-size:14px}"
           "figure{margin:32px 0}img{max-width:100%;height:auto}.video iframe{width:100%;aspect-ratio:16/9;border:0}figcaption{font-size:14px;"
           "color:#6b6b6b;text-align:center}blockquote{border-left:3px solid #242424;margin:1.2em 0;padding-left:20px;font-style:italic}"
           "pre{background:#f2f2f2;padding:16px;overflow-x:auto;font-size:15px}code{font-family:Menlo,Consolas,monospace;font-size:.85em}"
           "hr{border:0;text-align:center;margin:2em 0}hr:after{content:'. . .';letter-spacing:.6em;color:#6b6b6b}.todo{background:#fff4ce;padding:8px}"
           "a{color:inherit}")
    page = (f"<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
            f"{head}<style>{css}</style>\n</head>\n<body>\n<!-- ARTICLE START: select from here when pasting into Medium or a CMS -->\n<article>\n"
            + "\n".join(body) + "\n</article>\n<!-- ARTICLE END -->\n</body>\n</html>\n")
    open(os.path.join(out, f"{slug}.html"), "w", encoding="utf-8").write(page)
    probs = check(inp, words); later = todo(inp, shorts)
    seo = ["SEO FIELDS (paste into your CMS / Medium story settings)", "",
           f"SEO title ({len(inp['seo_title'])} chars):", inp["seo_title"], "",
           f"Meta description ({len(inp['meta_description'])} chars):", inp["meta_description"], "",
           "Slug / URL:", slug, "", "Focus keyword:", inp["focus_keyword"], "",
           "Tags (Medium: up to 5):", ", ".join(inp["tags"]), "",
           "Cover image:", img or "(none)", "", "Cover alt text:", inp.get("cover_alt", ""), "",
           "Medium: Story settings -> SEO title / SEO description; if the article is on your site first, use Medium's",
           "'Import a story' with your post's URL so Medium sets the canonical link back to your site.", "",
           f"Reading time: {mins} min ({words} words)", "", "Checks: " + ("pass" if not probs else "; ".join(probs))]
    if later: seo += ["", "To do:"] + [f"- {m}" for m in later]
    open(os.path.join(out, "SEO.txt"), "w", encoding="utf-8").write("\n".join(seo) + "\n")
    return {"dir": out, "files": [f"{slug}.md", f"{slug}.html", "SEO.txt"] + ([img] if img else []), "words": words, "minutes": mins,
            "problems": probs, "todo": later}
