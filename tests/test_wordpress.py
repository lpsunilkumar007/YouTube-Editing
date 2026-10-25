"""WordPress publishing against a FAKE WordPress (no network): credentials, Gutenberg blocks, dry run, the approval hash,
draft create/update without duplicates, and every refusal (public posts, edits made in WordPress, foreign drafts,
missing categories), SEO-plugin fields and JSON-LD read back, internal-link suggestions, reference checks, retries."""
import json, os, re, urllib.parse
import pytest
from PIL import Image
from ytpipe import blog, wordpress as wp
from tests.test_core import make_cfg

class FakeWP:
    """Enough of the WordPress REST API (wp/v2) for ytpipe, kept in memory."""
    def __init__(self, namespaces=("wp/v2",), writable_meta=(), unfiltered_html=True, categories=("Programming",)):
        self.ns, self.writable, self.unfiltered = list(namespaces), set(writable_meta), unfiltered_html
        self.posts, self.media, self.calls, self.n, self.fail = {}, {}, [], 100, []
        self.terms = {"categories": {i + 1: c for i, c in enumerate(categories)}, "tags": {50: "Programming"}}
    def __call__(self, method, url, headers, body):
        u = urllib.parse.urlparse(url); q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}; path = u.path
        self.calls.append((method, path, headers.get("Authorization")))
        if self.fail: return self.fail.pop(0), {}, b'{"code":"rate_limited","message":"slow down"}'
        if path == "/wp-json/": return 200, {}, json.dumps({"namespaces": self.ns}).encode()
        path = path.split("/wp-json/wp/v2", 1)[-1]
        ok = lambda js, h=None: (200, h or {"X-WP-TotalPages": "1"}, json.dumps(js).encode())
        if path == "/users/me": return ok({"id": 7, "name": "Fake Author", "capabilities": {"edit_posts": True, "upload_files": True, "unfiltered_html": self.unfiltered}})
        m = re.fullmatch(r"/(tags|categories)", path)
        if m and method == "GET": return ok([{"id": i, "name": n} for i, n in self.terms[m.group(1)].items() if q.get("search", "").lower() in n.lower()])
        if m and method == "POST": self.n += 1; self.terms[m.group(1)][self.n] = json.loads(body)["name"]; return 201, {}, json.dumps({"id": self.n}).encode()
        if path == "/media" and method == "POST":
            self.n += 1; name = re.search(r'filename="(.+)"', headers["Content-Disposition"]).group(1)
            self.media[self.n] = {"id": self.n, "source_url": f"https://example.test/uploads/{name}", "bytes": len(body)}
            return 201, {}, json.dumps(self.media[self.n]).encode()
        m = re.fullmatch(r"/media/(\d+)", path)
        if m: self.media[int(m.group(1))].update(json.loads(body)); return ok(self.media[int(m.group(1))])
        if path == "/posts" and method == "GET":
            if "slug" in q: return ok([self._view(p) for p in self.posts.values() if p["slug"] == q["slug"]])
            return ok([self._view(p) for p in self.posts.values() if p["status"] == "publish"])
        m = re.fullmatch(r"/posts(?:/(\d+))?", path)
        if m and method == "GET":
            p = self.posts.get(int(m.group(1))); return (404, {}, b'{"code":"rest_post_invalid_id"}') if p is None else ok(self._view(p))
        if m and method == "POST":
            b = json.loads(body); pid = int(m.group(1)) if m.group(1) else None
            if pid is None: self.n += 1; pid = self.n; self.posts[pid] = {"id": pid, "status": "draft", "meta": {}, "rev": 0}
            p = self.posts[pid]; meta = b.pop("meta", {})
            if not self.unfiltered: b["content"] = re.sub(r"<script.*?</script>", "", b.get("content", ""), flags=re.S)
            p.update(b); p["meta"].update({k: v for k, v in meta.items() if k in self.writable}); p["rev"] += 1
            p["modified_gmt"] = f"2026-10-25T10:00:{p['rev']:02d}"
            return ok(self._view(p))
        return 404, {}, b'{"code":"rest_no_route"}'
    def _view(self, p):
        return {**{k: v for k, v in p.items() if k != "content"}, "link": f"https://example.test/?p={p['id']}", "title": {"rendered": p.get("title", "")},
                "content": {"raw": p.get("content", "")}}

def setup(tmp_path, fake=None, **wpcfg):
    W = {"site_url": "https://example.test", "kind": "self_hosted", "username": "teacher", "category": "Programming", **wpcfg}
    cfg = make_cfg(tmp_path, wordpress=W); os.makedirs(cfg["paths"]["metadata"], exist_ok=True)
    open(os.path.join(cfg["paths"]["metadata"], "youtube_chapters.txt"), "w").write("0:00 Intro\n0:53 Problem solving first\n")
    cover = str(tmp_path / "cover.png"); Image.new("RGB", (64, 36), (10, 20, 30)).save(cover)
    os.makedirs(os.path.join(cfg["paths"]["root"], "blog", "screens"), exist_ok=True)
    Image.new("RGB", (64, 36), (200, 200, 200)).save(os.path.join(cfg["paths"]["root"], "blog", "screens", "slide_05.png"))
    para = "How to start programming: begin with problem solving on paper. " + "word " * 120
    inp = {"title": "How to Start Programming", "slug": "how-to-start-programming", "focus_keyword": "how to start programming",
           "seo_title": "How to Start Programming: Flowchart First", "meta_description": "How to start programming: " + "x" * 110,
           "tags": ["Programming", "Flowchart"], "cover_alt": "Roadmap", "video_url": "https://youtu.be/abcdefghijk", "intro": [para],
           "sections": [{"heading": "How to start programming on paper", "body": [para, "- one\n- two", "> A quote", "```\nSTART\nEND\n```"]}],
           "images": [{"file": "screens/slide_05.png", "after": "How to start programming on paper", "alt": "Slide: problem solving", "caption": "The slide"}],
           "faq": [{"q": "Q?", "a": "A."}], "author": "Teacher"}
    env = {"YTPIPE_WP_APP_PASSWORD": "abcd efgh ijkl mnop"}
    client = wp.connect(cfg, transport=fake, env=env, run=lambda *a, **k: None) if fake else None
    if client: client.sleep = lambda s: None
    return cfg, inp, cover, client

def approve(cfg, inp, cover, client):
    D = blog.document(cfg, inp, cover); r = wp.dry_run(cfg, inp, D, client); return D, f"payload:{r['hash']}"

def test_credentials_keychain_env_and_https(tmp_path):
    W = {"site_url": "https://example.test", "kind": "self_hosted", "username": "teacher", "keychain_service": "ytpipe-wordpress"}
    seen = []
    class R:
        returncode, stdout = 0, "app pass word\n"
    h = wp.credentials(W, env={}, run=lambda cmd, **k: seen.append(cmd) or R())
    assert seen[0][:2] == ["security", "find-generic-password"] and "teacher@example.test" in seen[0]
    assert h["Authorization"].startswith("Basic ") and "app pass word" not in h["Authorization"]
    class Missing:
        returncode, stdout = 44, ""
    with pytest.raises(wp.WPError) as e: wp.credentials(W, env={}, run=lambda *a, **k: Missing())
    assert "security add-generic-password -U -s ytpipe-wordpress -a teacher@example.test -w" in str(e.value)
    assert wp.credentials({**W, "kind": "wpcom"}, env={"YTPIPE_WP_TOKEN": "t0k"})["Authorization"] == "Bearer t0k"
    with pytest.raises(wp.WPError): wp.Client({**W, "site_url": "http://example.test"}, {})

def test_blocks_render_gutenberg(tmp_path):
    cfg, inp, cover, _ = setup(tmp_path); D = blog.document(cfg, inp, cover); c = wp.blocks(D)
    for b in ("<!-- wp:paragraph -->", "<!-- wp:heading -->", '<!-- wp:heading {"level":3} -->', "<!-- wp:list -->", "<!-- wp:quote -->", "<!-- wp:code -->"):
        assert b in c, b
    assert '"providerNameSlug":"youtube"' in c and "https://www.youtube.com/watch?v=abcdefghijk" in c
    assert "{{media:screens/slide_05.png}}" in c and "{{media_id:screens/slide_05.png}}" in c and "Slide: problem solving" in c
    assert c.count("<!-- wp:") == c.count("<!-- /wp:")                       # every block closed
    assert "wp:embed" not in wp.blocks(blog.document(cfg, {**inp, "video_url": ""}, cover))

def test_offline_dry_run_is_stable_and_complete(tmp_path):
    cfg, inp, cover, _ = setup(tmp_path, category=None)
    D = blog.document(cfg, inp, cover); r1 = wp.dry_run(cfg, inp, D); r2 = wp.dry_run(cfg, inp, blog.document(cfg, inp, cover))
    assert r1["hash"] == r2["hash"] and r1["payload"]["status"] == "draft"
    assert any("category not set" in w for w in r1["warnings"]) and any("offline" in w for w in r1["warnings"])
    md = open(os.path.join(r1["dir"], "dry_run.md")).read()
    assert f"payload:{r1['hash']}" in md and "| Slug | how-to-start-programming |" in md and "BlogPosting" in md
    out = open(os.path.join(r1["dir"], "outreach.md")).read()
    assert "never posts" in out and "Buy links" in out
    r3 = wp.dry_run(cfg, {**inp, "title": "Changed"}, blog.document(cfg, {**inp, "title": "Changed"}, cover))
    assert r3["hash"] != r1["hash"]

def test_send_needs_the_approved_hash_and_creates_one_draft(tmp_path):
    fake = FakeWP(); cfg, inp, cover, client = setup(tmp_path, fake)
    D, note = approve(cfg, inp, cover, client)
    with pytest.raises(PermissionError): wp.send(cfg, inp, D, client, "payload:000000000000")
    r = wp.send(cfg, inp, D, client, note)
    assert r["action"] == "created" and r["status"] == "draft" and len(fake.posts) == 1
    p = fake.posts[r["post_id"]]
    assert p["status"] == "draft" and p["categories"] == [1] and len(p["tags"]) == 2 and 50 in p["tags"]
    assert "{{media" not in p["content"] and "https://example.test/uploads/slide_05.png" in p["content"]
    assert p["featured_media"] in fake.media and fake.media[p["featured_media"]]["alt_text"] == "Roadmap"
    assert r["edit_url"] == f"https://example.test/wp-admin/post.php?post={r['post_id']}&action=edit"
    assert all(a and a.startswith("Basic ") for m, path, a in fake.calls if path != "/wp-json/")
    uploads = len(fake.media)
    r2 = wp.send(cfg, inp, D, client, note)                                    # rerun: same draft, no new uploads
    assert r2["action"] == "updated" and r2["post_id"] == r["post_id"] and len(fake.posts) == 1 and len(fake.media) == uploads
    inp2 = {**inp, "title": "How to Start Programming (updated)"}; D2 = blog.document(cfg, inp2, cover)
    with pytest.raises(PermissionError): wp.send(cfg, inp2, D2, client, note)  # changed content needs a new approval
    D2, note2 = approve(cfg, inp2, cover, client); assert wp.send(cfg, inp2, D2, client, note2)["post_id"] == r["post_id"]
    assert not any(m == "POST" and path.endswith("/categories") for m, path, a in fake.calls)   # categories never created

def test_send_refuses_public_edited_foreign_and_missing_category(tmp_path):
    fake = FakeWP(); cfg, inp, cover, client = setup(tmp_path, fake)
    D, note = approve(cfg, inp, cover, client); r = wp.send(cfg, inp, D, client, note)
    fake.posts[r["post_id"]]["modified_gmt"] = "2026-10-25T11:11:11"           # someone edited the draft in WordPress
    with pytest.raises(wp.WPError, match="edited in WordPress"): wp.send(cfg, inp, D, client, note)
    assert wp.send(cfg, inp, D, client, note, force=True)["action"] == "updated"
    fake.posts[r["post_id"]]["status"] = "publish"                             # now public: never changed
    with pytest.raises(wp.WPError, match="never changes public content"): wp.send(cfg, inp, D, client, note, force=True)
    fake2 = FakeWP(); cfg2, inp2, cover2, client2 = setup(tmp_path / "b", fake2)
    fake2.posts[300] = {"id": 300, "slug": inp2["slug"], "status": "draft", "meta": {}, "rev": 0}   # a draft ytpipe did not make
    D2, note2 = approve(cfg2, inp2, cover2, client2)
    with pytest.raises(wp.WPError, match="not created by ytpipe"): wp.send(cfg2, inp2, D2, client2, note2)
    fake3 = FakeWP(categories=()); cfg3, inp3, cover3, client3 = setup(tmp_path / "c", fake3)
    D3, note3 = approve(cfg3, inp3, cover3, client3)
    with pytest.raises(wp.WPError, match="does not exist"): wp.send(cfg3, inp3, D3, client3, note3)
    assert not fake3.posts

def test_seo_plugin_fields_and_json_ld_are_read_back(tmp_path):
    keys = wp.SEO_PLUGINS["rankmath"]["meta"]
    fake = FakeWP(namespaces=("wp/v2", "rankmath/v1"), writable_meta=keys.values()); cfg, inp, cover, client = setup(tmp_path, fake)
    D, note = approve(cfg, inp, cover, client); r = wp.send(cfg, inp, D, client, note)
    assert r["seo_fields"] == "stored" and r["structured_data"] == "kept"
    assert fake.posts[r["post_id"]]["meta"][keys["description"]] == inp["meta_description"]
    assert "BlogPosting" not in fake.posts[r["post_id"]]["content"]            # the SEO plugin already writes Article schema
    fake2 = FakeWP(namespaces=("wp/v2", "yoast/v1"), unfiltered_html=False); cfg2, inp2, cover2, client2 = setup(tmp_path / "b", fake2)
    D2, note2 = approve(cfg2, inp2, cover2, client2); r2 = wp.send(cfg2, inp2, D2, client2, note2)
    assert r2["seo_fields"].startswith("NOT stored") and r2["structured_data"].startswith("removed")

def test_internal_link_suggestions_and_applied_links(tmp_path):
    fake = FakeWP(); cfg, inp, cover, client = setup(tmp_path, fake)
    fake.posts[900] = {"id": 900, "slug": "problem-solving", "status": "publish", "title": "Problem Solving for Beginners", "meta": {}}
    fake.posts[901] = {"id": 901, "slug": "cooking", "status": "publish", "title": "The Best Pasta Recipe", "meta": {}}
    r = wp.dry_run(cfg, inp, blog.document(cfg, inp, cover), client)
    assert [s["url"] for s in r["suggestions"]] == ["https://example.test/?p=900"] and r["suggestions"][0]["anchor"].lower() == "problem solving"
    inp["internal_links"] = [{"anchor": r["suggestions"][0]["anchor"], "url": r["suggestions"][0]["url"]}, {"anchor": "not in the text", "url": "https://x.test"}]
    D = blog.document(cfg, inp, cover)
    assert "[problem solving](https://example.test/?p=900)" in json.dumps(D["doc"]) and D["links_missing"] == ["not in the text"]
    assert sum("](https://example.test/?p=900)" in x for k, x in D["doc"] if k == "block") == 1   # linked once

def test_reference_check_and_retry(tmp_path):
    pages = {"https://ok.test/a": (200, b"<html><title>Flowchart - Docs</title></html>"), "https://gone.test/b": (404, b"")}
    t = lambda m, url, h, b: (pages[url][0], {}, pages[url][1])
    res = wp.check_references([{"title": "A", "url": "https://ok.test/a"}, {"title": "B", "url": "https://gone.test/b"}, {"title": "C", "url": "http://plain.test"}], t)
    assert [r["ok"] for r in res] == [True, False, False] and res[0]["page_title"] == "Flowchart - Docs" and res[2]["error"] == "not https"
    fake = FakeWP(); cfg, inp, cover, client = setup(tmp_path, fake); fake.fail = [429, 503]
    assert client.me()["id"] == 7                                              # two retries, then success
    fake.fail = [500]
    with pytest.raises(wp.WPError, match="HTTP 500"): client.me()

def test_package_keeps_blog_screens_and_wordpress_reports(tmp_path):
    from ytpipe import publish
    d = tmp_path / "blog"; (d / "screens").mkdir(parents=True); (d / "wordpress").mkdir()
    (d / "a.md").write_text("![x](screens/slide_05.png)"); (d / "screens" / "slide_05.png").write_bytes(b"png"); (d / "screens" / "slide_06.png").write_bytes(b"png")
    (d / "wordpress" / "dry_run.md").write_text("x"); (d / "wordpress" / "state.json").write_text("{}")
    names = [os.path.relpath(f, d) for f in publish._blog(str(d))]
    assert names == ["a.md", "screens/slide_05.png", "wordpress/dry_run.md"]          # unused stills and state stay out
