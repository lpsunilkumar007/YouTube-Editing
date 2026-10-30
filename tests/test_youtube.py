"""YouTube uploader against a FAKE YouTube (no network): matching staged uploads, the plan and its approval hash,
apply order (public only at the end), resuming, playlists without duplicates, captions, refusals and quota errors."""
import datetime, json, urllib.parse
import pytest
from ytpipe import youtube as yt

SERIES = {"channel_handle": "@codwithsunil", "language": "hi", "captions_name": "Hinglish",
          "playlists": {"main": "Main List", "flow": "Flow List"}, "shorts_start": "2030-01-01", "shorts_time": "18:00", "utc_offset": "+05:30"}

def fake_items(tmp_path):
    f = tmp_path / "f.bin"; f.write_bytes(b"x"); srt = tmp_path / "a.srt"; srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nHi\n")
    png = tmp_path / "t.png"; png.write_bytes(b"\x89PNG")
    return [{"key": "V1", "lesson": "l1", "kind": "video", "file": str(f), "title": "If x <= 5", "description": "a > b", "tags": ["flowchart", "if else"],
             "thumbnail": str(png), "captions": str(srt), "playlists": ["main"]},
            {"key": "V2", "lesson": "l2", "kind": "video", "file": str(f), "title": "Two", "description": "d", "tags": [],
             "thumbnail": None, "captions": None, "playlists": ["main", "flow"]},
            {"key": "S01", "lesson": "l1", "kind": "short", "file": str(f), "title": "Short one", "description": "s", "tags": [],
             "thumbnail": None, "captions": None, "playlists": [], "day": 1}]

@pytest.fixture
def its(tmp_path, monkeypatch):
    it = fake_items(tmp_path); monkeypatch.setattr(yt, "items", lambda series, root=".": it); return it

class FakeYT:
    def __init__(self, handle="@codwithsunil"):
        self.handle, self.calls, self.fail = handle, [], []
        self.videos = {"id1": ("V1", "PT1M40S"), "id2": ("V2", "PT5M"), "id3": ("S01", "PT45S"), "old": ("Old video", "PT2M")}
        self.playlists = {"pl1": "Main List", "pl2": "Flow List"}; self.items = {"pl1": ["id2"], "pl2": []}
    def __call__(self, method, url, headers, body):
        u = urllib.parse.urlparse(url); q = dict(urllib.parse.parse_qsl(u.query)); path = u.path.split("/youtube/v3", 1)[-1]
        if url.startswith(yt.TOKEN_URL): return 200, {}, b'{"access_token": "AT"}'
        self.calls.append((method, path, q, body))
        if self.fail: return self.fail.pop(0)
        ok = lambda js: (200, {}, json.dumps(js).encode())
        if path == "/channels": return ok({"items": [{"id": "UC1", "snippet": {"title": "Sunil", "customUrl": self.handle}, "contentDetails": {"relatedPlaylists": {"uploads": "UU1"}}}]})
        if path == "/playlistItems" and method == "GET":
            ids = list(self.videos) if q["playlistId"] == "UU1" else self.items[q["playlistId"]]
            return ok({"items": [{"contentDetails": {"videoId": i}, "snippet": {"resourceId": {"videoId": i}}} for i in ids]})
        if path == "/playlistItems" and method == "POST":
            sn = json.loads(body)["snippet"]; self.items[sn["playlistId"]].insert(sn["position"], sn["resourceId"]["videoId"]); return ok({})
        if path == "/videos" and method == "GET":
            return ok({"items": [{"id": i, "snippet": {"title": t}, "contentDetails": {"duration": d}} for i, (t, d) in self.videos.items() if i in q["id"].split(",")]})
        if path == "/playlists": return ok({"items": [{"id": i, "snippet": {"title": t}} for i, t in self.playlists.items()]})
        if path == "/captions" and method == "GET": return ok({"items": [{"id": "c0", "snippet": {"name": "Hinglish", "language": "hi"}}]})
        return ok({})

def client(fake): return yt.Client({"client_id": "c", "client_secret": "s"}, "RT", fake)

def test_clean_and_publish_time():
    assert yt.clean("a <= b > c") == "a ＜= b ＞ c"
    assert yt.publish_at(SERIES, 3) == "2030-01-03T18:00:00+05:30"
    assert yt._iso_duration("PT1H2M3S") == 3723 and yt._iso_duration("PT45S") == 45

def test_match_by_title_and_duration(its):
    fake = FakeYT(); durations = {"V1": 100, "V2": 300, "S01": 30}
    found, problems, ch = yt.match(SERIES, client(fake), durations=durations)
    assert found == {"V1": "id1", "V2": "id2"} and ch["title"] == "Sunil"
    assert any("S01" in p and "duration" in p for p in problems)            # 45 s on YouTube, 30 s file: wrong file

def test_match_refuses_another_channel(its):
    with pytest.raises(yt.YTError, match="not @codwithsunil"):
        yt.match(SERIES, client(FakeYT(handle="@someoneelse")), durations={})

def test_plan_problems_and_hash(its):
    ids = {"V1": "id1", "V2": "id2", "S01": "id3"}
    p = yt.plan(SERIES, ids, now=datetime.datetime(2029, 1, 1, tzinfo=datetime.timezone.utc))
    assert not p["problems"]
    meta = {s["key"]: s for s in p["steps"] if s["op"] == "metadata"}
    assert meta["V1"]["snippet"]["title"] == "If x ＜= 5" and meta["V1"]["status"]["privacyStatus"] == "private"
    assert meta["S01"]["status"]["publishAt"] == "2030-01-01T18:00:00+05:30" and meta["S01"]["snippet"]["categoryId"] == "27"
    assert [s["op"] for s in p["steps"]][-2:] == ["go_public", "go_public"]
    late = yt.plan(SERIES, ids, now=datetime.datetime(2031, 1, 1, tzinfo=datetime.timezone.utc))
    assert any("in the past" in x for x in late["problems"]) and late["hash"] == p["hash"]
    assert any("not matched" in x for x in yt.plan(SERIES, {"V1": "id1"})["problems"])

def test_apply_needs_current_hash_and_no_problems(its, tmp_path):
    p = yt.plan(SERIES, {"V1": "id1", "V2": "id2", "S01": "id3"}, now=datetime.datetime(2029, 1, 1, tzinfo=datetime.timezone.utc))
    with pytest.raises(yt.YTError, match="approval names"): yt.apply(p, client(FakeYT()), str(tmp_path / "st.json"), "0" * 12)
    bad = yt.plan(SERIES, {"V1": "id1"})
    with pytest.raises(yt.YTError, match="problems"): yt.apply(bad, client(FakeYT()), str(tmp_path / "st.json"), bad["hash"])

def test_apply_order_playlists_captions_and_resume(its, tmp_path):
    fake = FakeYT(); st = str(tmp_path / "st.json")
    p = yt.plan(SERIES, {"V1": "id1", "V2": "id2", "S01": "id3"}, now=datetime.datetime(2029, 1, 1, tzinfo=datetime.timezone.utc))
    yt.apply(p, client(fake), st, p["hash"])
    puts = [json.loads(b) for m, path, q, b in fake.calls if m == "PUT"]
    assert [x["status"]["privacyStatus"] for x in puts] == ["private", "private", "private", "public", "public"]   # public only at the end
    assert fake.items["pl1"] == ["id1", "id2"] and fake.items["pl2"] == ["id2"]                                  # order kept, no duplicate
    assert any(m == "DELETE" and path == "/captions" for m, path, q, b in fake.calls)                            # our old track replaced
    up = [b for m, path, q, b in fake.calls if path == "/captions" and m == "POST"][0]
    assert b'"videoId": "id1"' in up and b"Hi" in up
    n = len(fake.calls); yt.apply(p, client(fake), st, p["hash"]); assert len(fake.calls) == n                   # all done: nothing resent

def test_quota_error_stops_and_resumes(its, tmp_path):
    fake = FakeYT(); st = str(tmp_path / "st.json")
    p = yt.plan(SERIES, {"V1": "id1", "V2": "id2", "S01": "id3"}, now=datetime.datetime(2029, 1, 1, tzinfo=datetime.timezone.utc))
    fake.fail = [(403, {}, b'{"error": {"message": "quota", "errors": [{"reason": "quotaExceeded"}]}}')]
    with pytest.raises(yt.YTError, match="tomorrow"): yt.apply(p, client(fake), st, p["hash"])
    yt.apply(p, client(fake), st, p["hash"])
    assert sum(1 for m, path, q, b in fake.calls if m == "PUT" and json.loads(b)["status"]["privacyStatus"] == "public") == 2

def test_client_file(tmp_path):
    f = tmp_path / "c.json"; f.write_text(json.dumps({"installed": {"client_id": "a", "client_secret": "b"}}))
    assert yt.client_from_file(str(f)) == {"client_id": "a", "client_secret": "b"}
    f.write_text("{}")
    with pytest.raises(yt.YTError): yt.client_from_file(str(f))
