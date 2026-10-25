"""Stage 'wp-publish': the lesson's blog article as a WordPress DRAFT (self-hosted, or WordPress.com), never published.

Built from the blog stage's document (ytpipe/blog.py), so the WordPress post says exactly what the .md/.html say:
Gutenberg blocks (headings, lists, quotes, code, screenshots, the YouTube embed once video_url is set), the cover as the
featured image, category, tags, excerpt, SEO-plugin fields and schema.org JSON-LD.

  dry run (default)  blog/wordpress/dry_run.md + payload.json: everything that would be sent, internal-link suggestions
                     from the site's published posts, external-reference checks (--check-links), warnings. Prints the
                     payload hash to approve:  python -m ytpipe approve blog_publish --note payload:<hash>
  --send             uploads media and creates, or updates, the one draft for this lesson (blog/wordpress/state.json)

Safety rules (enforced here, not by convention):
  - status is always "draft"; a post that is already public, scheduled or private is never changed
  - --send needs the blog_publish approval naming the CURRENT payload hash: changed content must be approved again
  - edits made in WordPress since the last send are not overwritten (stops; --force to overwrite)
  - a draft with the same slug that ytpipe did not create is not taken over (stops; --force)
  - credentials come from the macOS Keychain (or env vars), never from config files or logs; HTTPS only
  - categories are never created (the configured one must exist); missing tags are created and listed in the dry run
The HTTP transport is injectable: tests run against a fake WordPress."""
import base64, hashlib, html, json, os, re, subprocess, time, urllib.error, urllib.parse, urllib.request
from . import blog

class WPError(RuntimeError):
    pass

# SEO plugins, recognised by their REST namespace. Fields are written as the plugin's post meta keys and read back after
# the upload: if the site does not expose them over REST, the report says so (enter them from SEO.txt) instead of
# assuming success. Verify the mapping against the installed plugin's documentation when connecting a real site.
SEO_PLUGINS = {
    "yoast": {"namespace": "yoast/v1", "meta": {"title": "_yoast_wpseo_title", "description": "_yoast_wpseo_metadesc", "focus_keyword": "_yoast_wpseo_focuskw"}},
    "rankmath": {"namespace": "rankmath/v1", "meta": {"title": "rank_math_title", "description": "rank_math_description", "focus_keyword": "rank_math_focus_keyword"}},
}
STOP = set("the a an and or of to in on for with is are was be by as at it this that from your you how what why can do my our".split())

# ---------------------------------------------------------------- credentials (macOS Keychain, env fallback)

def _keychain(service, account, run=subprocess.run):
    r = run(["security", "find-generic-password", "-s", service, "-a", account, "-w"], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else None

def keychain_account(W):
    host = urllib.parse.urlparse(W["site_url"]).netloc
    return f"token@{host}" if W["kind"] == "wpcom" else f"{W['username']}@{host}"

def credentials(W, env=None, run=subprocess.run):
    """Authorization header. Self-hosted: an Application Password (Users -> Profile) for W["username"]; WordPress.com:
    an OAuth2 token. Stored by you, once, with:  security add-generic-password -U -s <service> -a <account> -w"""
    env = os.environ if env is None else env; acct = keychain_account(W)
    hint = f"store it in the Keychain:  security add-generic-password -U -s {W['keychain_service']} -a {acct} -w"
    if W["kind"] == "wpcom":
        tok = env.get("YTPIPE_WP_TOKEN") or _keychain(W["keychain_service"], acct, run)
        if not tok: raise WPError("no WordPress.com token; " + hint)
        return {"Authorization": f"Bearer {tok}"}
    pw = env.get("YTPIPE_WP_APP_PASSWORD") or _keychain(W["keychain_service"], acct, run)
    if not pw: raise WPError(f"no Application Password for {W['username']}; " + hint)
    return {"Authorization": "Basic " + base64.b64encode(f"{W['username']}:{pw}".encode()).decode()}

# ---------------------------------------------------------------- REST client

def urllib_transport(method, url, headers, body, timeout=30):
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r: return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e: return e.code, dict(e.headers or {}), e.read()

class Client:
    def __init__(self, W, auth, transport=urllib_transport, sleep=time.sleep):
        site = W["site_url"].rstrip("/"); u = urllib.parse.urlparse(site)
        if u.scheme != "https" and u.hostname not in ("localhost", "127.0.0.1"):
            raise WPError("site_url must use https: the credentials go with every request")
        self.W, self.site, self.auth, self.t, self.sleep = W, site, auth, transport, sleep
        self.api = f"https://public-api.wordpress.com/wp/v2/sites/{u.netloc}" if W["kind"] == "wpcom" else f"{site}/wp-json/wp/v2"

    def call(self, method, path, params=None, body=None, data=None, headers=None, base=None, auth=True):
        url = (self.api if base is None else base) + path + ("?" + urllib.parse.urlencode(params, doseq=True) if params else "")
        h = {"Accept": "application/json", "User-Agent": "ytpipe-wp", **(self.auth if auth else {}), **(headers or {})}
        if body is not None: data = json.dumps(body).encode(); h["Content-Type"] = "application/json"
        for attempt in range(3):                                   # rate limits and gateway hiccups: back off, retry twice
            st, rh, raw = self.t(method, url, h, data)
            if st in (429, 502, 503, 504) and attempt < 2: self.sleep(2 * 2 ** attempt); continue
            break
        try: js = json.loads(raw or b"null")
        except ValueError: js = None
        if st >= 400:
            e = js if isinstance(js, dict) else {}
            raise WPError(f"{method} {path} -> HTTP {st} {e.get('code', '')}: {e.get('message') or (raw or b'')[:200]!r}")
        return js, {k.lower(): v for k, v in rh.items()}

    def all(self, path, params):
        out, p = [], 1
        while True:
            js, h = self.call("GET", path, {**params, "per_page": 100, "page": p}); out += js or []
            if p >= int(h.get("x-wp-totalpages", 1) or 1): return out
            p += 1

    def namespaces(self):
        try: return (self.call("GET", "/", base=f"{self.site}/wp-json", auth=False)[0] or {}).get("namespaces", [])
        except WPError: return []

    def me(self):
        return self.call("GET", "/users/me", {"context": "edit"})[0]

    def post(self, pid):
        try: return self.call("GET", f"/posts/{pid}", {"context": "edit"})[0]
        except WPError as e:
            if "HTTP 404" in str(e) or "HTTP 410" in str(e): return None
            raise

    def by_slug(self, slug):
        r = self.call("GET", "/posts", {"slug": slug, "status": "draft,pending,private,future,publish", "context": "edit"})[0]
        return r[0] if r else None

    def term(self, kind, name, create):
        """Id of the tag/category called name (case-insensitive exact match), created only if create."""
        for t in self.all(f"/{kind}", {"search": name}):
            if html.unescape(t["name"]).strip().lower() == name.strip().lower(): return t["id"]
        return self.call("POST", f"/{kind}", body={"name": name})[0]["id"] if create else None

    def upload(self, path, alt, caption=""):
        name = os.path.basename(path); ctype = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp"}[name.rsplit(".", 1)[-1].lower()]
        m = self.call("POST", "/media", data=open(path, "rb").read(), headers={"Content-Type": ctype, "Content-Disposition": f'attachment; filename="{name}"'})[0]
        self.call("POST", f"/media/{m['id']}", body={"alt_text": alt, "caption": caption})
        return {"id": m["id"], "url": m["source_url"]}

def connect(cfg, transport=urllib_transport, env=None, run=subprocess.run):
    W = cfg["wordpress"]
    missing = [k for k in ("site_url", "kind") if not W.get(k)] + (["username"] if W.get("kind") == "self_hosted" and not W.get("username") else [])
    if missing: raise WPError("wordpress settings missing in the lesson or defaults config: " + ", ".join(missing))
    if W["kind"] not in ("self_hosted", "wpcom"): raise WPError("wordpress.kind must be self_hosted or wpcom")
    return Client(W, credentials(W, env, run), transport)

def check(client):
    """Read-only connection test: who we are, can we write drafts, which SEO plugin, which categories exist."""
    me = client.me(); caps = me.get("capabilities", {}); ns = client.namespaces()
    cats = [html.unescape(c["name"]) for c in client.all("/categories", {"_fields": "id,name"})]
    return {"user": me.get("name"), "user_id": me.get("id"), "can_write_posts": bool(caps.get("edit_posts")),
            "can_upload": bool(caps.get("upload_files")), "unfiltered_html": bool(caps.get("unfiltered_html")),
            "seo_plugin": detect_seo(ns), "categories": cats}

def detect_seo(namespaces):
    return next((k for k, p in SEO_PLUGINS.items() if p["namespace"] in namespaces), "none")

# ---------------------------------------------------------------- Gutenberg blocks

def _wrap(name, inner, attrs=None):
    a = (" " + json.dumps(attrs, separators=(",", ":"))) if attrs else ""
    return f"<!-- wp:{name}{a} -->\n{inner}\n<!-- /wp:{name} -->"

def _list(items, ordered):
    li = "".join(_wrap("list-item", f"<li>{x}</li>") for x in items); tag = "ol" if ordered else "ul"
    return _wrap("list", f'<{tag} class="wp-block-list">{li}</{tag}>', {"ordered": True} if ordered else None)

def _block(b):
    lines = b.split("\n")
    if b.startswith("```"):
        return _wrap("code", '<pre class="wp-block-code"><code>' + html.escape("\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])) + "</code></pre>")
    if all(l.startswith("- ") for l in lines): return _list([blog._inline_html(l[2:]) for l in lines], False)
    if all(re.match(r"\d+\. ", l) for l in lines): return _list([blog._inline_html(l.split(". ", 1)[1]) for l in lines], True)
    if b.startswith("> "):
        p = "<br>".join(blog._inline_html(l[2:] if l.startswith("> ") else l) for l in lines)
        return _wrap("quote", '<blockquote class="wp-block-quote">' + _wrap("paragraph", f"<p>{p}</p>") + "</blockquote>")
    return _wrap("paragraph", f"<p>{blog._inline_html(b)}</p>")

def youtube_embed(url):
    return _wrap("embed", '<figure class="wp-block-embed is-type-video is-provider-youtube wp-block-embed-youtube wp-embed-aspect-16-9 '
                 f'wp-has-aspect-ratio"><div class="wp-block-embed__wrapper">\n{url}\n</div></figure>',
                 {"url": url, "type": "video", "providerNameSlug": "youtube", "responsive": True, "className": "wp-embed-aspect-16-9 wp-has-aspect-ratio"})

def blocks(D, ld=()):
    """Post content. Media appear as {{media:<file>}} / {{media_id:<file>}} until --send has uploaded them, so the
    approved payload does not depend on upload results. The title is the post title and the cover the featured image."""
    out = []
    for k, x in D["doc"]:
        if k == "subtitle" and x: out.append(_wrap("paragraph", f"<p><em>{html.escape(x)}</em></p>"))
        elif k == "video" and D["vid"]: out.append(youtube_embed(f"https://www.youtube.com/watch?v={D['vid']}"))
        elif k in ("h2", "h3"):
            out.append(_wrap("heading", f'<{k} class="wp-block-heading">{blog._inline_html(x)}</{k}>', {"level": 3} if k == "h3" else None))
        elif k == "figure":
            f, alt, cap = x; c = f'<figcaption class="wp-element-caption">{blog._inline_html(cap)}</figcaption>' if cap else ""
            out.append("<!-- wp:image {\"id\":{{media_id:" + f + "}},\"sizeSlug\":\"large\"} -->\n" f'<figure class="wp-block-image size-large"><img src="{{{{media:{f}}}}}" '
                       f'alt="{html.escape(alt, quote=True)}" class="wp-image-{{{{media_id:{f}}}}}"/>{c}</figure>\n<!-- /wp:image -->')
        elif k == "chapters":
            out.append(_list([f'<a href="{html.escape(D["at"](t), quote=True)}">{D["mm"](t)}</a> {html.escape(n)}' if D["vid"] else f"{D['mm'](t)} {html.escape(n)}" for t, n in x], False))
        elif k == "hr": out.append(_wrap("separator", '<hr class="wp-block-separator has-alpha-channel-opacity"/>'))
        elif k == "block": out.append(_block(x))
    if ld:
        out.append(_wrap("html", "".join(f'<script type="application/ld+json">{json.dumps(o, ensure_ascii=False)}</script>' for o in ld)))
    return "\n\n".join(out)

# ---------------------------------------------------------------- internal links, references, outreach

def _words(s):
    return [w for w in re.findall(r"[a-z0-9#+]+", html.unescape(re.sub(r"<[^>]+>", " ", s or "")).lower())]

def suggest_links(D, inp, posts, n=5):
    """Contextual internal links: a published post is suggested when 2-5 consecutive words of its title occur in a
    paragraph of this article (that phrase is the anchor) and they are not only stop words. Best (longest) first."""
    text = [(i, x) for i, (k, x) in enumerate(D["doc"]) if k == "block" and not x.startswith("```")]
    out = []
    for p in posts:
        if p.get("slug") == inp["slug"]: continue
        title = html.unescape(re.sub(r"<[^>]+>", "", (p.get("title") or {}).get("rendered", ""))); tw = _words(title); best = None
        for L in range(min(5, len(tw)), 1, -1):
            for j in range(len(tw) - L + 1):
                g = tw[j:j + L]
                if sum(w not in STOP for w in g) < 2: continue
                pat = re.compile(r"(?<![\w])" + r"\W+".join(map(re.escape, g)) + r"(?![\w])", re.I)
                hit = next(((i, m.group(0)) for i, x in text for m in [pat.search(blog._text(x))] if m), None)
                if hit: best = (L, hit); break
            if best: break
        if best: out.append({"title": title, "url": p["link"], "anchor": best[1][1], "block": best[1][0], "words": best[0]})
    return sorted(out, key=lambda s: -s["words"])[:n]

def check_references(refs, transport=urllib_transport):
    """Each external reference: HTTPS, reachable (HTTP 200 after redirects) and its page title, so a reviewer sees what
    the link really is. Read-only GETs; only run when asked (--check-links)."""
    out = []
    for r in refs:
        res = {"url": r["url"], "title": r["title"], "ok": False}
        if not r["url"].startswith("https://"): res["error"] = "not https"
        else:
            try:
                st, _, raw = transport("GET", r["url"], {"User-Agent": "Mozilla/5.0 (ytpipe link check)"}, None)
                m = re.search(rb"<title[^>]*>(.*?)</title>", raw or b"", re.S | re.I)
                res.update(status=st, ok=st == 200, page_title=html.unescape(m.group(1).decode("utf-8", "replace").strip()) if m else None)
            except Exception as e: res["error"] = str(e)[:120]
        out.append(res)
    return out

def outreach_report(inp, W, path):
    """Backlink OPPORTUNITIES to review by hand. Nothing here contacts anyone or posts anywhere."""
    kw, tags = inp["focus_keyword"], inp["tags"]; q = lambda s: f"`{s}`"
    lines = [f"# Backlink outreach opportunities: {inp['title']}", "",
             "A list to work through by hand. ytpipe never posts, comments or emails anyone. Earn links by being genuinely useful;",
             "Google's spam policies treat bought links, link exchanges, automated comments and link networks as link spam.", "",
             "## 1. Your own channels (do these first, after the post is public)", "",
             "- YouTube description of this lesson: add the article link near the top.",
             "- Pinned comment on the video: one line with the article link.",
             "- Each Short's description: \"Full explanation: <article link>\".",
             "- Instagram: link sticker in a story, or the bio link.",
             "- LinkedIn or other profiles you already use: a short post on the lesson's main point, with the link.", "",
             "## 2. Republish with a canonical link (no duplicate-content problem)", "",
             "- Medium: Import a story with the post's URL (sets the canonical link to your site).",
             "- dev.to / Hashnode: paste the article and set its canonical URL to your post.", "",
             "## 3. Places to help, where linking is allowed", "",
             f"Search for recent beginner questions this article answers ({q(kw)}). Answer in full in your own words, and add the",
             "link only where it saves the reader time. Read each community's self-promotion rules first; many allow it only rarely.", "",
             "## 4. Resource pages and educators", "",
             "Pages that list beginner programming resources may add a free course. Searches to find them:", "",
             *[f"- {q(s)}" for s in (f'"{kw}" "resources"', f'"{kw}" "useful links"', f'"learn to code" intitle:resources beginners',
                                      f'"{tags[0].lower() if tags else kw}" "for beginners" "resources"')],
             "", "Write to the page owner once, say what the lesson covers and why it fits their list, and accept a no.", "",
             "## 5. Guest articles", "",
             "Offer an original article (not this one) to education or programming blogs; link to this post only where relevant.", "",
             "## Never", "", "- Buy links, swap links in bulk, or use link networks.", "- Post automated or copy-paste comments.",
             "- Add links in forum signatures, unrelated threads or other people's comment sections.", ""]
    open(path, "w", encoding="utf-8").write("\n".join(lines))
    return path

# ---------------------------------------------------------------- payload, dry run, send

def _sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()[:16]

def payload(cfg, inp, D, seo_plugin="none"):
    """Everything --send will write, by name (no site ids), so its hash can be approved before any upload."""
    W = cfg["wordpress"]; sd = W["structured_data"]
    kinds = () if sd == "off" else ("BlogPosting", "VideoObject", "FAQPage") if sd == "all" or seo_plugin == "none" else ("VideoObject", "FAQPage")
    ld = blog.structured_data(inp, D, "{{media:" + D["img"] + "}}" if D["img"] else None, kinds=kinds)
    figs = [x[0] for k, x in D["doc"] if k == "figure"]
    media = ([{"file": D["img"], "alt": inp.get("cover_alt", ""), "role": "featured"}] if D["img"] else []) + \
            [{"file": f, "alt": next(x[1] for k, x in D["doc"] if k == "figure" and x[0] == f), "role": "content"} for f in figs]
    for m in media: m["sha"] = _sha(os.path.join(D["dir"], m["file"]))
    return {"title": inp["title"], "slug": inp["slug"], "status": "draft", "excerpt": inp["meta_description"],
            "category": W.get("category"), "tags": inp["tags"], "author_id": W.get("author_id"), "media": media,
            "seo": {"plugin": seo_plugin, "title": inp["seo_title"], "description": inp["meta_description"], "focus_keyword": inp["focus_keyword"]},
            "structured_data": [o["@type"] for o in ld], "content": blocks(D, ld)}

def payload_hash(p):
    return hashlib.sha256(json.dumps(p, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]

def _dir(D):
    d = os.path.join(D["dir"], "wordpress"); os.makedirs(d, exist_ok=True); return d

def _state(D):
    p = os.path.join(_dir(D), "state.json"); return (json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}), p

def dry_run(cfg, inp, D, client=None, check_links=False, transport=urllib_transport):
    """Writes blog/wordpress/payload.json, dry_run.md, link_suggestions.json, outreach.md. Read-only on the site."""
    W = cfg["wordpress"]; d = _dir(D); warn = []; site = {}
    if client:
        ns = client.namespaces(); site["seo_plugin"] = detect_seo(ns) if W["seo_plugin"] == "auto" else W["seo_plugin"]
        posts = client.all("/posts", {"status": "publish", "_fields": "id,link,slug,title"})
        site["suggestions"] = suggest_links(D, inp, posts, W["internal_links_max"])
        ex = client.by_slug(inp["slug"]); st, _ = _state(D)
        site["existing"] = ({"id": ex["id"], "status": ex["status"], "ours": ex["id"] == st.get("post_id")} if ex else None)
        if W.get("category") and client.term("categories", W["category"], create=False) is None:
            warn.append(f"category {W['category']!r} does not exist on the site (create it in WordPress; ytpipe never creates categories)")
        site["new_tags"] = [t for t in inp["tags"] if client.term("tags", t, create=False) is None]
        if ex and ex["status"] not in ("draft", "pending", "auto-draft"): warn.append(f"a {ex['status']} post already uses this slug: --send will refuse to change it")
        elif ex and not site["existing"]["ours"]: warn.append("a draft with this slug exists that ytpipe did not create: --send needs --force to update it")
    else:
        site["seo_plugin"] = W["seo_plugin"] if W["seo_plugin"] != "auto" else "none"
        warn.append("no site connection (wordpress settings or credentials missing): offline dry run, no link suggestions, SEO plugin not detected")
    p = payload(cfg, inp, D, site["seo_plugin"]); h = payload_hash(p)
    if not W.get("category"): warn.append("wordpress.category not set: required before --send")
    if not D["vid"]: warn.append("video_url not set: the post has no YouTube embed yet (add it after the upload, then rerun)")
    if D["links_missing"]: warn.append(f"approved internal link anchors not found in the text: {D['links_missing']}")
    refs = check_references(inp.get("references", []), transport) if check_links else None
    if refs: warn += [f"reference not verified: {r['url']} ({r.get('error') or r.get('status')})" for r in refs if not r["ok"]]
    elif inp.get("references"): warn.append("external references not checked yet: rerun with --check-links")
    json.dump(p, open(os.path.join(d, "payload.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(site.get("suggestions", []), open(os.path.join(d, "link_suggestions.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    outreach_report(inp, W, os.path.join(d, "outreach.md"))
    applied = [l for l in inp.get("internal_links", []) if l["anchor"] not in D["links_missing"]]
    md = [f"# WordPress dry run: {p['title']}", "", f"Payload hash **{h}**. Nothing has been sent. To approve exactly this:", "",
          f"    python -m ytpipe approve blog_publish --note payload:{h} --config <config>", "",
          "| Field | Value |", "|---|---|", f"| Site | {W.get('site_url') or '(not set)'} |", f"| Status | draft (publishing stays manual) |",
          f"| Title | {p['title']} |", f"| Slug | {p['slug']} |", f"| Category | {p['category'] or '(not set)'} |",
          f"| Tags | {', '.join(p['tags'])}" + (f" (new: {', '.join(site['new_tags'])})" if site.get("new_tags") else "") + " |",
          f"| Featured image | {D['img'] or '(none)'} (alt: {inp.get('cover_alt', '')}) |",
          f"| Excerpt | {p['excerpt']} |", f"| SEO plugin | {p['seo']['plugin']} |", f"| SEO title | {p['seo']['title']} ({len(p['seo']['title'])} chars) |",
          f"| Meta description | {p['seo']['description']} ({len(p['seo']['description'])} chars) |", f"| Focus keyword | {p['seo']['focus_keyword']} |",
          f"| Structured data | {', '.join(p['structured_data']) or 'none'} |", f"| YouTube embed | {D['url'] or '(after upload)'} |",
          f"| Screenshots | {', '.join(m['file'] for m in p['media'] if m['role'] == 'content') or 'none'} |",
          f"| Words | {D['words']} ({D['mins']} min read) |", ""]
    if site.get("existing"): md += [f"Existing post with this slug: id {site['existing']['id']}, {site['existing']['status']}" + (" (ytpipe's draft: will be updated)" if site['existing']['ours'] else ""), ""]
    md += ["## Internal links", "", "Applied (from blog_input internal_links):", ""] + ([f"- \"{l['anchor']}\" -> {l['url']}" for l in applied] or ["- none"])
    md += ["", "Suggested from the site's published posts (add the ones you want to blog_input internal_links):", ""]
    md += [f"- \"{s['anchor']}\" -> [{s['title']}]({s['url']})" for s in site.get("suggestions", [])] or ["- none" + ("" if client else " (no site connection)")]
    md += ["", "## External references", ""]
    md += [f"- {r['title']}: {r['url']} " + (f"(HTTP {r.get('status')}, page title: {r.get('page_title')!r})" if r["ok"] else f"(NOT verified: {r.get('error') or r.get('status')})") for r in refs] if refs else \
          [f"- {r['title']}: {r['url']} (not checked)" for r in inp.get("references", [])] or ["- none"]
    md += ["", "## Warnings", ""] + ([f"- {w}" for w in warn] or ["- none"])
    if "BlogPosting" in p["structured_data"] or p["structured_data"]:
        md += ["", "JSON-LD goes in a Custom HTML block. WordPress keeps <script> only for users with the unfiltered_html capability"
               " (Administrators and Editors on a single site); --send reads the draft back and reports whether it survived."]
    md += ["", "Backlink opportunities (manual): wordpress/outreach.md", "", "## Content (Gutenberg blocks)", "", "```html", p["content"], "```", ""]
    open(os.path.join(d, "dry_run.md"), "w", encoding="utf-8").write("\n".join(md))
    return {"hash": h, "payload": p, "warnings": warn, "suggestions": site.get("suggestions", []), "references": refs, "dir": d}

def _edit_url(client, pid):
    return f"https://wordpress.com/post/{urllib.parse.urlparse(client.site).netloc}/{pid}" if client.W["kind"] == "wpcom" else f"{client.site}/wp-admin/post.php?post={pid}&action=edit"

def send(cfg, inp, D, client, approval_note, force=False):
    """Create or update this lesson's draft. Refuses anything that would change public content or unreviewed content."""
    W = cfg["wordpress"]; seo = W["seo_plugin"] if W["seo_plugin"] != "auto" else detect_seo(client.namespaces())
    p = payload(cfg, inp, D, seo); h = payload_hash(p)
    if f"payload:{h}" not in (approval_note or ""):
        raise PermissionError(f"blog_publish approval does not name this payload ({h}): run the dry run, review it, then "
                              f"python -m ytpipe approve blog_publish --note payload:{h}")
    if not W.get("category"): raise WPError("wordpress.category not set")
    st, sp = _state(D); post = client.post(st["post_id"]) if st.get("post_id") else None
    if post is None:
        post = client.by_slug(inp["slug"])
        if post and not force: raise WPError(f"post {post['id']} ({post['status']}) already uses slug {inp['slug']!r} and was not created by ytpipe; --force to update it")
    if post and post["status"] not in ("draft", "pending", "auto-draft"):
        raise WPError(f"post {post['id']} is {post['status']}: ytpipe only writes drafts and never changes public content")
    if post and st.get("modified_gmt") and post.get("modified_gmt") != st["modified_gmt"] and not force:
        raise WPError(f"draft {post['id']} was edited in WordPress after the last send ({post.get('modified_gmt')}); "
                      "copy those edits into blog_input.json, or --force to overwrite them")
    cat = client.term("categories", W["category"], create=False)
    if cat is None: raise WPError(f"category {W['category']!r} does not exist on the site; create it in WordPress first")
    tags = [client.term("tags", t, create=True) for t in inp["tags"]]
    media = st.get("media", {})
    for m in p["media"]:                                           # upload new or changed files only
        if media.get(m["file"], {}).get("sha") != m["sha"]:
            media[m["file"]] = {**client.upload(os.path.join(D["dir"], m["file"]), m["alt"]), "sha": m["sha"]}
    content = p["content"]
    for f, m in media.items(): content = content.replace("{{media:" + f + "}}", m["url"]).replace("{{media_id:" + f + "}}", str(m["id"]))
    body = {"title": p["title"], "slug": p["slug"], "status": "draft", "excerpt": p["excerpt"], "content": content,
            "categories": [cat], "tags": tags, **({"featured_media": media[D["img"]]["id"]} if D["img"] else {}),
            **({"author": W["author_id"]} if W.get("author_id") else {})}
    keys = SEO_PLUGINS.get(seo, {}).get("meta", {})
    if keys: body["meta"] = {keys[k]: p["seo"][k] for k in keys}
    res = client.call("POST", f"/posts/{post['id']}" if post else "/posts", body=body)[0]
    back = client.post(res["id"]) or {}; raw = (back.get("content") or {}).get("raw", "")
    rep = {"post_id": res["id"], "action": "updated" if post else "created", "status": back.get("status"), "edit_url": _edit_url(client, res["id"]),
           "preview": back.get("link"), "payload": h, "seo_fields": "n/a (no SEO plugin)" if not keys else
           ("stored" if all((back.get("meta") or {}).get(v) == p["seo"][k] for k, v in keys.items()) else "NOT stored over REST: enter them from SEO.txt"),
           "structured_data": "n/a" if not p["structured_data"] else ("kept" if "application/ld+json" in raw else "removed by WordPress (user lacks unfiltered_html)")}
    if rep["status"] != "draft": rep["warning"] = f"WordPress reports status {rep['status']!r}: check the post now"
    json.dump({"post_id": res["id"], "modified_gmt": back.get("modified_gmt"), "media": media, "payload": h, "sent_at": time.strftime("%Y-%m-%d %H:%M:%S"),
               "edit_url": rep["edit_url"]}, open(sp, "w", encoding="utf-8"), indent=1)
    return rep
