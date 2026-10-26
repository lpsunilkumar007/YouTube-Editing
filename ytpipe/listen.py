"""Stage 'listen': a page for the presenter's caption listen-check. Every '≈' (reconstructed) transcript line with a play
button (the face-camera audio from that line to the next, no music), its final-video time and the current text; the
presenter marks it correct or types the fix. Claude publishes reports/listen_check.html as a private claude.ai Artifact
with the db capability (answers in collection "reviews", doc id = "<lesson>-<face time>"), reads the answers back with
read_db, fixes transcripts/transcript.txt and reruns captions. Ids use the face time, so they survive line inserts."""
import base64, json, os, subprocess
from . import config, transcript

def lines(cfg):
    """[{id, video, final, face, text, audio}] for every ≈ line of this lesson (audio as a data: URI, mono 40 kb/s mp3)."""
    P = cfg["paths"]; L = cfg["project"]["lesson_id"]; tl = transcript.parse(os.path.join(P["transcripts"], "transcript.txt"))
    E = json.load(open(os.path.join(P["timelines"], "edl.json"), encoding="utf-8"))["segments"]
    def fin(F):
        x = next((x for x in E if x["face_in"] - 0.05 <= F < x["face_out"] + 0.05), None)
        return round(x["edit_start"] + max(F, x["face_in"]) - x["face_in"], 2) if x else None
    out = []
    for i, l in enumerate(tl):
        if not l["text"].startswith("≈"): continue
        a = max(0, l["face"] - 0.3); b = min((tl[i + 1]["face"] if i + 1 < len(tl) else l["face"] + 8) + 0.2, a + 45)
        mp3 = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{a:.2f}", "-t", f"{b - a:.2f}", "-i", cfg["sources"]["face_camera"], "-vn", "-ac", "1",
                              "-ar", "22050", "-c:a", "libmp3lame", "-b:a", "40k", "-f", "mp3", "-"], capture_output=True, check=True).stdout
        out.append({"id": f"{L}-{l['face']:.2f}", "video": cfg["project"]["lecture_topic"], "final": fin(l["face"]), "face": round(l["face"], 2),
                    "text": l["text"].lstrip("≈ ").strip(), "audio": "data:audio/mpeg;base64," + base64.b64encode(mp3).decode()})
    return out

def run(cfg):
    ls = lines(cfg); t = open(os.path.join(config.ROOT, "assets", "listen", "listen_check.html"), encoding="utf-8").read()
    html = t.replace("__H1__", "Caption listen-check").replace("__DATA__", json.dumps(ls, ensure_ascii=False).replace("</", "<\\/"))
    out = os.path.join(cfg["paths"]["reports"], "listen_check.html"); open(out, "w", encoding="utf-8").write(html)
    return out, ls
