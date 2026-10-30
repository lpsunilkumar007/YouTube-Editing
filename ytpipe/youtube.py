"""YouTube: fills in videos you uploaded in YouTube Studio (title, description, tags, thumbnail, subtitles, playlists,
publish / schedule) from the lessons' validated metadata, over the YouTube Data API.

It never uploads video files: uploads from an unaudited API project are locked to Private (YouTube Data API,
videos.insert). You drag the staged files into Studio; everything after that is done here.

  python -m ytpipe.youtube auth --client <client_secret.json>   one-time sign-in; tokens go to the macOS Keychain
  python -m ytpipe.youtube stage     hard links with unique names (V1.mp4, S01.mp4 ...) in lessons/_series/upload/
  python -m ytpipe.youtube match     finds those uploads on the channel (title = file name, duration checked)
  python -m ytpipe.youtube plan      youtube_plan.md: everything that would be set, and the hash to approve
  python -m ytpipe.youtube apply --approve <hash>   applies the approved plan (resumable; quota errors stop cleanly)
  python -m ytpipe.youtube links     youtube_links.md + video_url in each lesson's blog_input.json

Safety rules (enforced here):
  - only videos matched from the staged files are touched, and only on the channel named in the series file
  - apply needs the hash of the CURRENT plan: any change to the text, files or dates must be approved again
  - videos stay Private until every other step has succeeded, then the long videos go public together;
    Shorts are scheduled (private + publishAt); a publish time in the past stops the plan
  - credentials come from the macOS Keychain, never from files in the project or from logs
The HTTP transport is injectable: tests run against a fake YouTube."""
import argparse, base64, datetime, hashlib, http.server, json, os, re, secrets, subprocess, sys, urllib.parse
from . import config, publish, state
from .wordpress import urllib_transport

API = "https://www.googleapis.com/youtube/v3"
UPLOAD = "https://www.googleapis.com/upload/youtube/v3"
TOKEN_URL = "https://oauth2.googleapis.com/token"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
SCOPE = "https://www.googleapis.com/auth/youtube.force-ssl"       # update videos, captions, thumbnails, playlists
SERVICE = "ytpipe-youtube"
EDUCATION = "27"
SERIES = "lessons/_series/youtube_series.json"

class YTError(RuntimeError):
    pass

# ---------------------------------------------------------------- credentials (macOS Keychain)

def _keychain_get(account, run=subprocess.run):
    r = run(["security", "find-generic-password", "-s", SERVICE, "-a", account, "-w"], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else None

def _keychain_set(account, value, run=subprocess.run):
    r = run(["security", "add-generic-password", "-U", "-s", SERVICE, "-a", account, "-w", value], capture_output=True, text=True)
    if r.returncode != 0: raise YTError(f"could not store {account} in the Keychain: {r.stderr.strip()}")

def client_from_file(path):
    """Google's 'Desktop app' OAuth client JSON -> {client_id, client_secret}."""
    js = json.load(open(path, encoding="utf-8")); c = js.get("installed") or js.get("web") or {}
    if not c.get("client_id") or not c.get("client_secret"): raise YTError(f"{path} is not an OAuth client file (Desktop app)")
    return {"client_id": c["client_id"], "client_secret": c["client_secret"]}

def authorize(client, open_browser=True, transport=urllib_transport):
    """Loopback sign-in with PKCE: opens Google's consent page, receives the code on 127.0.0.1, returns the refresh token."""
    verifier = secrets.token_urlsafe(64); st = secrets.token_urlsafe(16)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    got = {}
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(self.path).query)); got.update(q)
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.end_headers()
            self.wfile.write("<p>Signed in. You can close this tab and go back to the terminal.</p>".encode())
        def log_message(self, *a): pass
    srv = http.server.HTTPServer(("127.0.0.1", 0), H); redirect = f"http://127.0.0.1:{srv.server_port}"
    url = AUTH_URL + "?" + urllib.parse.urlencode({"client_id": client["client_id"], "redirect_uri": redirect, "response_type": "code",
        "scope": SCOPE, "access_type": "offline", "prompt": "consent", "state": st, "code_challenge": challenge, "code_challenge_method": "S256"})
    print("Sign in with the Google account that owns the channel (pick the channel if Google asks):\n" + url)
    if open_browser: subprocess.run(["open", url])
    while "code" not in got and "error" not in got: srv.handle_request()
    srv.server_close()
    if got.get("state") != st: raise YTError("sign-in answer did not match this request (state); try again")
    if "error" in got: raise YTError(f"sign-in refused: {got['error']}")
    tok = _token(transport, {"code": got["code"], "client_id": client["client_id"], "client_secret": client["client_secret"],
                             "redirect_uri": redirect, "grant_type": "authorization_code", "code_verifier": verifier})
    if not tok.get("refresh_token"): raise YTError("Google returned no refresh token; remove the app's access in your Google account and sign in again")
    return tok["refresh_token"]

def _token(transport, form):
    s, _, b = transport("POST", TOKEN_URL, {"Content-Type": "application/x-www-form-urlencoded"}, urllib.parse.urlencode(form).encode())
    js = json.loads(b or b"{}")
    if s != 200: raise YTError(f"token request failed ({s}): {js.get('error_description') or js.get('error')}"
                               + (" — sign in again: python -m ytpipe.youtube auth --client <file>" if js.get("error") == "invalid_grant" else ""))
    return js

# ---------------------------------------------------------------- REST client

class Client:
    def __init__(self, client, refresh_token, transport=urllib_transport):
        self.c, self.rt, self.t, self.access = client, refresh_token, transport, None
        self.units = 0                                           # quota spent by this run (YouTube's published costs)

    @classmethod
    def from_keychain(cls, transport=urllib_transport, run=subprocess.run):
        c, rt = _keychain_get("client", run), _keychain_get("refresh_token", run)
        if not c or not rt: raise YTError("not signed in: python -m ytpipe.youtube auth --client <client_secret.json>")
        return cls(json.loads(c), rt, transport)

    def _auth(self):
        if not self.access:
            self.access = _token(self.t, {"client_id": self.c["client_id"], "client_secret": self.c["client_secret"],
                                          "refresh_token": self.rt, "grant_type": "refresh_token"})["access_token"]
        return {"Authorization": f"Bearer {self.access}"}

    def call(self, method, path, params=None, body=None, cost=1, base=API, ctype="application/json", raw=None):
        url = base + path + ("?" + urllib.parse.urlencode(params) if params else "")
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        for attempt in (0, 1):
            h = {**self._auth(), **({"Content-Type": ctype} if data is not None else {})}
            s, _, b = self.t(method, url, h, data)
            if s == 401 and attempt == 0: self.access = None; continue
            break
        js = json.loads(b) if b else {}
        if s >= 400:
            err = js.get("error", {}); reason = ((err.get("errors") or [{}])[0]).get("reason", "")
            if reason in ("quotaExceeded", "dailyLimitExceeded"):
                raise YTError("today's free API quota is used up; run the same command again tomorrow (finished steps are skipped)")
            raise YTError(f"{method} {path} failed ({s} {reason}): {err.get('message', b[:200])}")
        self.units += cost
        return js

    def pages(self, path, params, cost=1):
        out, tok = [], None
        while True:
            js = self.call("GET", path, {**params, **({"pageToken": tok} if tok else {})}, cost=cost)
            out += js.get("items", []); tok = js.get("nextPageToken")
            if not tok: return out

    def channel(self):
        it = self.call("GET", "/channels", {"part": "snippet,contentDetails", "mine": "true"}).get("items", [])
        if not it: raise YTError("this Google account has no YouTube channel (pick the channel when signing in)")
        c = it[0]; return {"id": c["id"], "title": c["snippet"]["title"], "handle": c["snippet"].get("customUrl", ""),
                           "uploads": c["contentDetails"]["relatedPlaylists"]["uploads"]}

# ---------------------------------------------------------------- the series: what goes where

def _iso_duration(d):
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", d or "")
    if not m: return None
    dd, h, mi, s = (int(x or 0) for x in m.groups()); return ((dd * 24 + h) * 60 + mi) * 60 + s

def probe_duration(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path], capture_output=True, text=True)
    return float(r.stdout.strip())

def clean(text):
    """YouTube rejects '<' and '>' in titles, descriptions and tags: full-width look-alikes keep '<=' readable."""
    return text.replace("<", "＜").replace(">", "＞")

def load_series(path=SERIES):
    return json.load(open(path, encoding="utf-8"))

def items(series, root="."):
    """Every video and Short of the series with its files and text, in playlist order. Long videos: the lesson's final,
    approved thumbnail, the reviewed .srt; Shorts: the v4 render and its metadata .md (paired by number, checked)."""
    out = []
    for les in series["lessons"]:
        cfg = config.load(os.path.join(root, "lessons", les["id"], "video_project_config.json"), check_files=False); P = cfg["paths"]
        L = publish.long_copy(P["metadata"]); thumbs = publish._thumbnails(cfg, state.load(cfg))
        srt = sorted(f for f in os.listdir(P["transcripts"]) if f.endswith(".srt"))
        out.append({"key": les["video_key"], "lesson": les["id"], "kind": "video", "file": os.path.join(P["full_video"], f"{les['id']}.mp4"),
                    "title": L["title"], "description": L["description"], "tags": [t.strip() for t in L["tags"].split(",") if t.strip()],
                    "thumbnail": thumbs[0] if thumbs else None, "captions": os.path.join(P["transcripts"], srt[0]) if srt else None,
                    "playlists": les["playlists"]})
        files = publish._shorts(P["shorts"])
        for s in les["shorts"]:
            md = os.path.join(P["metadata"], "shorts", s["metadata"]); S = publish.short_copy(open(md, encoding="utf-8").read())
            f = [x for x in files if os.path.basename(x) == s["file"]]
            if not f: raise YTError(f"{les['id']}: no rendered {s['file']}")
            out.append({"key": s["key"], "lesson": les["id"], "kind": "short", "file": f[0], "metadata": md, "title": S["title"],
                        "description": S["description"], "tags": [], "thumbnail": None, "captions": None, "playlists": [], "day": s["day"]})
    return out

def publish_at(series, day):
    d = datetime.date.fromisoformat(series["shorts_start"]) + datetime.timedelta(days=day - 1)
    return f"{d.isoformat()}T{series['shorts_time']}:00{series['utc_offset']}"

# ---------------------------------------------------------------- stage / match

def stage(series, out_dir, root="."):
    """Hard links (no copies, finals untouched) named <key>.mp4: Studio uses the file name as the first title, which is
    how 'match' finds each upload again."""
    os.makedirs(out_dir, exist_ok=True); done = []
    for it in items(series, root):
        dst = os.path.join(out_dir, f"{it['key']}.mp4")
        if os.path.exists(dst): os.remove(dst)                    # only ever a link this command made
        os.link(it["file"], dst); done.append(dst)
    return done

def match(series, yt, root=".", durations=None):
    """{key: videoId} for the staged uploads: title == key and duration within 2 s of the file. Refuses another channel."""
    ch = yt.channel()
    if ch["handle"].lower().lstrip("@") != series["channel_handle"].lower().lstrip("@"):
        raise YTError(f"signed in to {ch['title']} ({ch['handle']}), not {series['channel_handle']}: sign in again and pick that channel")
    ups = yt.pages("/playlistItems", {"part": "contentDetails", "playlistId": ch["uploads"], "maxResults": 50})
    ids = [u["contentDetails"]["videoId"] for u in ups]
    vids = {}
    for i in range(0, len(ids), 50):
        for v in yt.call("GET", "/videos", {"part": "snippet,contentDetails", "id": ",".join(ids[i:i + 50])}).get("items", []): vids[v["id"]] = v
    found, problems = {}, []
    for it in items(series, root):
        cand = [v for v in vids.values() if v["snippet"]["title"].strip() == it["key"]]
        if not cand: problems.append(f"{it['key']}: not uploaded yet (or renamed in Studio)"); continue
        if len(cand) > 1: problems.append(f"{it['key']}: {len(cand)} uploads with this title; delete the extra one in Studio"); continue
        want = (durations or {}).get(it["key"]) or probe_duration(it["file"]); got = _iso_duration(cand[0]["contentDetails"].get("duration"))
        if got is None or abs(got - want) > 2: problems.append(f"{it['key']}: duration {got} s on YouTube, file is {want:.0f} s (still processing, or the wrong file)"); continue
        found[it["key"]] = cand[0]["id"]
    return found, problems, ch

# ---------------------------------------------------------------- plan / apply

def _status(privacy, at=None):
    s = {"privacyStatus": privacy, "selfDeclaredMadeForKids": False, "embeddable": True, "license": "youtube",
         "publicStatsViewable": True, "containsSyntheticMedia": False}
    if at: s["publishAt"] = at
    return s

def plan(series, ids, root=".", now=None):
    """Every API change, in order, plus problems that block it. Hash = what 'apply --approve' must name."""
    now = now or datetime.datetime.now(datetime.timezone.utc); steps, problems = [], []
    its = items(series, root)
    for it in its:
        if it["key"] not in ids: problems.append(f"{it['key']}: not matched yet (run match)"); continue
        title, desc, tags = clean(it["title"]), clean(it["description"]), [clean(t) for t in it["tags"]]
        if not title or len(title) > 100: problems.append(f"{it['key']}: title missing or over 100 characters")
        if len(desc) > 5000: problems.append(f"{it['key']}: description over 5000 characters")
        if sum(len(t) + (2 if " " in t else 0) for t in tags) + max(len(tags) - 1, 0) > 500: problems.append(f"{it['key']}: tags over 500 characters")
        at = publish_at(series, it["day"]) if it["kind"] == "short" else None
        if at and datetime.datetime.fromisoformat(at) <= now: problems.append(f"{it['key']}: publish time {at} is in the past; move shorts_start")
        snippet = {"title": title, "description": desc, "tags": tags, "categoryId": EDUCATION,
                   "defaultLanguage": series["language"], "defaultAudioLanguage": series["language"]}
        steps.append({"op": "metadata", "key": it["key"], "id": ids[it["key"]], "snippet": snippet, "status": _status("private", at)})
        if it["thumbnail"]: steps.append({"op": "thumbnail", "key": it["key"], "id": ids[it["key"]], "file": it["thumbnail"], "sha": _sha(it["thumbnail"])})
        if it["captions"]: steps.append({"op": "captions", "key": it["key"], "id": ids[it["key"]], "file": it["captions"], "sha": _sha(it["captions"]),
                                         "language": series["language"], "name": series["captions_name"]})
    for pk, title in series["playlists"].items():
        members = [it["key"] for it in its if pk in it["playlists"]]
        steps.append({"op": "playlist", "playlist": title, "keys": members, "ids": [ids.get(k) for k in members]})
    for it in its:
        if it["kind"] == "video" and it["key"] in ids:
            steps.append({"op": "go_public", "key": it["key"], "id": ids[it["key"]], "status": _status("public")})
    h = hashlib.sha256(json.dumps(steps, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]
    return {"hash": h, "steps": steps, "problems": problems}

def _sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()[:16]

def plan_md(series, p, its):
    by = {it["key"]: it for it in its}; L = [f"# YouTube plan {p['hash']}", ""]
    L += ["## Problems (must be fixed first)", ""] + [f"- {x}" for x in p["problems"]] + [""] if p["problems"] else ["No problems found.", ""]
    for s in p["steps"]:
        if s["op"] == "metadata":
            it = by[s["key"]]; st = s["status"]
            when = f"scheduled {st['publishAt']}" if st.get("publishAt") else "private until the last step, then public"
            L += [f"## {s['key']} ({it['kind']}, {it['lesson']}): {s['snippet']['title']}", "", f"- video id: {s['id']}  ·  {when}",
                  f"- file: `{it['file']}`", f"- tags: {', '.join(s['snippet']['tags']) or '(none)'}",
                  f"- category Education, language {s['snippet']['defaultLanguage']}, not made for kids", "", "```", s["snippet"]["description"], "```", ""]
        elif s["op"] in ("thumbnail", "captions"): L += [f"- {s['key']}: {s['op']} `{s['file']}`"]
        elif s["op"] == "playlist": L += ["", f"## Playlist: {s['playlist']}", "", *[f"{i + 1}. {k}" for i, k in enumerate(s["keys"])], ""]
        elif s["op"] == "go_public": L += [f"- {s['key']}: made **public** (all long videos together, after every step above)"]
    return "\n".join(L) + "\n"

def apply(p, yt, state_path, approve):
    if approve != p["hash"]: raise YTError(f"approval names {approve}, the current plan is {p['hash']}: review youtube_plan.md again")
    if p["problems"]: raise YTError("the plan has problems; fix them first:\n- " + "\n- ".join(p["problems"]))
    st = json.load(open(state_path, encoding="utf-8")) if os.path.exists(state_path) else {}
    done = st.setdefault("done", {}); save = lambda: json.dump(st, open(state_path, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    sig = lambda s: hashlib.sha256(json.dumps(s, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]
    pls = None
    for s in p["steps"]:
        k = f"{s['op']}:{s.get('key') or s.get('playlist')}"
        if done.get(k) == sig(s): continue
        if s["op"] == "metadata":
            yt.call("PUT", "/videos", {"part": "snippet,status"}, {"id": s["id"], "snippet": s["snippet"], "status": s["status"]}, cost=50)
        elif s["op"] == "thumbnail":
            try:
                yt.call("POST", "/thumbnails/set", {"videoId": s["id"], "uploadType": "media"}, base=UPLOAD, ctype="image/png" if s["file"].endswith(".png") else "image/jpeg",
                        raw=open(s["file"], "rb").read(), cost=50)
            except YTError as e:
                if "(403" in str(e): raise YTError(f"{e}\ncustom thumbnails need a verified channel: verify your phone number at https://www.youtube.com/verify, then run apply again")
                raise
        elif s["op"] == "captions":
            have = yt.call("GET", "/captions", {"part": "snippet", "videoId": s["id"]}, cost=50).get("items", [])
            for c in have:                                         # ours from an earlier run (same name and language): replaced
                if c["snippet"].get("name") == s["name"] and c["snippet"].get("language") == s["language"]: yt.call("DELETE", "/captions", {"id": c["id"]}, cost=50)
            b = "ytpipe" + secrets.token_hex(8)
            meta = json.dumps({"snippet": {"videoId": s["id"], "language": s["language"], "name": s["name"], "isDraft": False}})
            body = (f"--{b}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{meta}\r\n--{b}\r\nContent-Type: application/octet-stream\r\n\r\n").encode() \
                   + open(s["file"], "rb").read() + f"\r\n--{b}--\r\n".encode()
            yt.call("POST", "/captions", {"part": "snippet", "uploadType": "multipart"}, base=UPLOAD, ctype=f"multipart/related; boundary={b}", raw=body, cost=400)
        elif s["op"] == "playlist":
            if pls is None: pls = {x["snippet"]["title"]: x["id"] for x in yt.pages("/playlists", {"part": "snippet", "mine": "true", "maxResults": 50})}
            if s["playlist"] not in pls: raise YTError(f"playlist '{s['playlist']}' not found on the channel (create it in Studio with exactly this title)")
            pid = pls[s["playlist"]]
            cur = [x["snippet"]["resourceId"]["videoId"] for x in yt.pages("/playlistItems", {"part": "snippet", "playlistId": pid, "maxResults": 50})]
            for pos, vid in enumerate(s["ids"]):
                if vid in cur: continue                          # already added in Studio: left where it is
                yt.call("POST", "/playlistItems", {"part": "snippet"}, {"snippet": {"playlistId": pid, "position": min(pos, len(cur)),
                        "resourceId": {"kind": "youtube#video", "videoId": vid}}}, cost=50); cur.insert(min(pos, len(cur)), vid)
        elif s["op"] == "go_public":                             # reached only when every earlier step succeeded
            yt.call("PUT", "/videos", {"part": "status"}, {"id": s["id"], "status": s["status"]}, cost=50)
        done[k] = sig(s); save()
    return yt.units

def links(series, ids, root="."):
    """youtube_links.md for you, and video_url in each lesson's blog_input.json (Shorts are added after their dates)."""
    rows, its = [], items(series, root)
    for it in its:
        vid = ids.get(it["key"]); url = (f"https://youtube.com/shorts/{vid}" if it["kind"] == "short" else f"https://youtu.be/{vid}") if vid else "(not matched)"
        rows.append(f"- {it['key']} {it['title']}: {url}" + (f"  (public {publish_at(series, it['day'])})" if it["kind"] == "short" else ""))
        if it["kind"] == "video" and vid:
            bi = os.path.join(root, "lessons", it["lesson"], "metadata", "blog_input.json"); js = json.load(open(bi, encoding="utf-8"))
            if js.get("video_url") != f"https://youtu.be/{vid}":
                js["video_url"] = f"https://youtu.be/{vid}"; json.dump(js, open(bi, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    return "\n".join(["# YouTube links", "", *rows]) + "\n"

# ---------------------------------------------------------------- CLI

def main(argv=None):
    ap = argparse.ArgumentParser(prog="ytpipe.youtube", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["auth", "stage", "match", "plan", "apply", "links"])
    ap.add_argument("--series", default=SERIES); ap.add_argument("--client"); ap.add_argument("--approve")
    a = ap.parse_args(argv); d = os.path.dirname(a.series); S = load_series(a.series)
    ids_path, state_path = os.path.join(d, "youtube_ids.json"), os.path.join(d, "youtube_state.json")
    ids = lambda: json.load(open(ids_path, encoding="utf-8")) if os.path.exists(ids_path) else {}
    try:
        if a.cmd == "auth":
            if not a.client: raise YTError("--client <client_secret.json> (Google Cloud → Credentials → OAuth client, Desktop app)")
            c = client_from_file(a.client); rt = authorize(c)
            _keychain_set("client", json.dumps(c)); _keychain_set("refresh_token", rt)
            ch = Client(c, rt).channel(); print(f"signed in: {ch['title']} ({ch['handle']}); keys stored in the Keychain ({SERVICE})")
            print(f"you can now delete {a.client}")
        elif a.cmd == "stage":
            out = stage(S, os.path.join(d, "upload")); print(f"{len(out)} files in {os.path.join(d, 'upload')}: drag them into YouTube Studio → Create → Upload videos"
                                                            " (up to 15 at once), then close the dialog without editing")
        elif a.cmd == "match":
            found, problems, ch = match(S, Client.from_keychain())
            json.dump({**ids(), **found}, open(ids_path, "w", encoding="utf-8"), indent=1)
            print(f"{ch['title']} ({ch['handle']}): {len(found)} matched"); [print(" -", x) for x in problems]
        elif a.cmd == "plan":
            p = plan(S, ids()); its = items(S)
            open(os.path.join(d, "youtube_plan.md"), "w", encoding="utf-8").write(plan_md(S, p, its))
            json.dump(p, open(os.path.join(d, "youtube_plan.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
            print(f"plan {p['hash']}: {len(p['steps'])} steps, {len(p['problems'])} problem(s) -> {os.path.join(d, 'youtube_plan.md')}")
            [print(" -", x) for x in p["problems"]]
        elif a.cmd == "apply":
            yt = Client.from_keychain(); units = apply(plan(S, ids()), yt, state_path, a.approve); print(f"done ({units} quota units used)")
        elif a.cmd == "links":
            out = os.path.join(d, "youtube_links.md"); open(out, "w", encoding="utf-8").write(links(S, ids())); print(out)
    except YTError as e:
        sys.exit(f"youtube: {e}")

if __name__ == "__main__":
    main()
