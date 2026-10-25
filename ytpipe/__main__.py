"""python -m ytpipe <stage> --config <lesson config.json> [options]

Stages (in workflow order; each is restartable and records a checkpoint in <lesson>/state.json):
  init        validate config, create the lesson folders
  inspect     ffprobe facts -> analysis/metadata.json
  sync        offset/drift -> analysis/sync.json + reports/synchronization_report.md (stops with 'needs_input' if unsure)
  transcribe  faster-whisper words (once) -> transcripts/words.json + transcript_draft.txt (to be corrected)
  analyze     slide area, slide changes, counter, ink, content masks, speech map, face track
  retakes     spoken cut instructions + repeated starts -> timelines/content_cuts.json, reports/content_cuts.md
              (review: apply true/false per cut); the timeline proposal removes the applied ones
  timeline    proposal -> timelines/timeline.json (review/edit, then: approve timeline)
  sample      ~15 s review clip (presenter, slide, cut; --at 30,95 picks final-video seconds, --len 5) with the final
              settings -> full_video/sample/sample.mp4, after 'timeline' approval (review it, then: approve preview)
  preview     render selected segments (--segments 0,3,7) after 'timeline' approval
  render      full video after 'full_render' approval -> full_video/<lesson>.mp4 (+ QA)
  captions    transcripts/<lesson>_hinglish.srt from transcripts/transcript.txt (+ review list)
  metadata    chapters/description/tags/hashtags/pinned comment from metadata/description_input.json
  blog        Medium-style SEO article from metadata/blog_input.json -> blog/<slug>.md, .html, SEO.txt (+ cover)
  wp-publish  WordPress DRAFT of the blog post: dry run by default (blog/wordpress/dry_run.md: everything that would be
              sent, internal-link suggestions, outreach.md); --check-links verifies external references; --send uploads
              after 'blog_publish' approval of the dry run's payload hash. Never publishes; public posts are never changed
  wp-check    read-only connection test of the configured WordPress site (user, rights, SEO plugin, categories)
  thumbnails  3 options from thumbnails/thumbnail_input.json (choose, then: approve thumbnail)
  shorts      candidate report (no rendering) -> shorts/shorts_candidate_report.md
  shorts-render  render approved clips (--clips 1,3) after 'shorts' approval
  qa          captions / thumbnails checks -> reports/qa_*.json; --final <video> also re-runs the full-video checks
              (decode, loudness, joints, sync, music) on a finished video, read only, with the stems in <its folder>/work
  package     publishing_package/ with INDEX.md
  approve     record an approval:  approve <gate> [--note "..."]   gates: timeline preview full_render thumbnail shorts paid_assets
  status      show checkpoints and approvals"""
import argparse, json, os, sys
import numpy as np
from . import config, state, sources, sync, analyze, transcript, timeline, captions, metadata, thumbnails, shorts, qa, pipeline, publish

def _j(p):
    return json.load(open(p, encoding="utf-8"))

def main(argv=None):
    ap = argparse.ArgumentParser(prog="ytpipe", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stage"); ap.add_argument("gate", nargs="?"); ap.add_argument("--config", required=True)
    ap.add_argument("--segments"); ap.add_argument("--clips"); ap.add_argument("--at"); ap.add_argument("--len", type=float, default=5.0)
    ap.add_argument("--note", default=""); ap.add_argument("--force", action="store_true")
    ap.add_argument("--send", action="store_true"); ap.add_argument("--check-links", action="store_true")
    ap.add_argument("--final", help="package / shorts-render / qa: an existing final video (read only, never modified)")
    ap.add_argument("--style", default="v3", help="shorts-render: v3 (lecture audio, line captions) or v4 (tightened pauses, chunk captions, music)")
    ap.add_argument("--music", help="shorts-render v4: licensed music file (record it in config/credits.json)"); ap.add_argument("--bpm", type=float)
    ap.add_argument("--music-db", type=float, default=None, help="shorts-render v4: music level under speech (dB below the voice)")
    a = ap.parse_args(argv)
    cfg = config.load(a.config); P = config.ensure_dirs(cfg); A = P["analysis"]
    meta = lambda: _j(os.path.join(A, "metadata.json"))
    an = lambda: _j(os.path.join(A, "analysis.json"))
    off = lambda: _j(os.path.join(A, "sync.json"))["result"]["offset_s"]
    edl = lambda: _j(os.path.join(P["timelines"], "edl.json"))
    s = a.stage
    if s == "init": print("ok:", P["root"])
    elif s == "inspect": m = sources.run(cfg); print(json.dumps({"pipeline": m["face_color_pipeline"], "desktop_audio": m["desktop_has_audio"], "warnings": m["warnings"]}, indent=1))
    elif s == "sync":
        r = sync.run(cfg, meta())["result"]; print(json.dumps(r, indent=1))
        if r["status"] != "ok": sys.exit("sync needs your input: see reports/synchronization_report.md, then set sync.manual_offset_s")
    elif s == "transcribe":
        ep = os.path.join(A, "speech_env.npy")              # after 'analyze': decode only the speech, in chunks
        wj = os.path.join(P["transcripts"], "words.json")
        w = transcript.transcribe(cfg, cfg["sources"]["face_camera"], wj, np.load(ep) if os.path.exists(ep) else None)
        if transcript.drop_hallucinations(w): json.dump(w, open(wj, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
        if "repaired" not in w:                              # garbled ASR stretches: decoded again on their own, or marked unclear
            w = transcript.repair(cfg, cfg["sources"]["face_camera"], w); json.dump(w, open(wj, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
        dr = os.path.join(P["transcripts"], "transcript_draft.txt"); transcript.draft_from_words(w, off(), dr)
        print("draft:", dr, "-> correct it (glossary, Hinglish) and save as transcripts/transcript.txt")
    elif s == "analyze": r = analyze.run(cfg, meta()); print(json.dumps({k: r[k] for k in ("slide_area", "slide_changes", "counter_box")}, indent=1), len(r["ink"]), "ink events")
    elif s == "timeline":
        lines = transcript.parse(os.path.join(P["transcripts"], "transcript.txt")) if os.path.exists(os.path.join(P["transcripts"], "transcript.txt")) else []
        cc = os.path.join(P["timelines"], "content_cuts.json")
        rm = [(c["face_in"], c["face_out"], {k: c[k] for k in ("reason", "confidence")}) for c in (_j(cc) if os.path.exists(cc) else []) if c["apply"]]
        t = timeline.propose(cfg, an(), lines, off(), os.path.join(P["timelines"], "timeline.json"), rm)
        if rm: print(len(rm), "content cuts applied,", round(sum(b - a for a, b, _ in rm), 1), "s removed (timelines/content_cuts.json)")
        print(len(t["segments"]), "segments,", len(t["restart_flags"]), "restart flags,", t["removed_dead_air_s"], "s dead air removed (proposal)")
    elif s == "retakes":
        from . import retakes
        cuts, out, rp = retakes.run(cfg, _j(os.path.join(P["transcripts"], "words.json")))
        print(len(cuts), "proposed cuts,", sum(c["apply"] for c in cuts), "applied,", round(sum(c["face_out"] - c["face_in"] for c in cuts if c["apply"]), 1), "s:", rp)
    elif s == "sample":
        from . import sample
        r = sample.build(cfg, _j(os.path.join(P["timelines"], "timeline.json")), an(), meta(), a.len, [float(x) for x in a.at.split(",")] if a.at else None)
        print(r["file"], f"{r['duration']:.1f} s")
        for p in r["pieces"]: print(f"  {p['label']}: {p['final_video']} in the final video ({'/'.join(p['layouts'])})")
        print("watch it, then: python -m ytpipe approve preview (or tell Claude what to change)")
    elif s in ("preview", "render"):
        plan = _j(os.path.join(P["timelines"], "timeline.json")); only = [int(x) for x in a.segments.split(",")] if a.segments else None
        out = os.path.join(P["full_video"], f"{cfg['project']['lesson_id']}.mp4")
        r = pipeline.build(cfg, plan, an(), meta(), out, only=only if s == "preview" else None, gate="timeline" if s == "preview" else "full_render")
        if s == "render":
            res = qa.run_full(cfg, r["file"], r["edl"], off(), an(), r["geometry"], os.path.join(P["full_video"], "work"))
            print(json.dumps(res["findings"], indent=1))
        else: print(r)
    elif s == "captions":
        env = np.load(os.path.join(A, "speech_env.npy")) if os.path.exists(os.path.join(A, "speech_env.npy")) else None
        srt, cues, rev = captions.build(cfg, transcript.parse(os.path.join(P["transcripts"], "transcript.txt")), edl()["segments"], env)
        print(srt, len(cues), "cues;", len(rev), "lines to review; QA:", qa.captions(srt, edl()["duration"], cfg) or "pass")
    elif s == "metadata":
        E = edl(); ch = metadata.chapters(_j(os.path.join(P["timelines"], "chapter_markers.json"))["markers"], E["segments"], E["duration"])
        metadata.content_brief(transcript.parse(os.path.join(P["transcripts"], "transcript.txt")), E["segments"], ch, os.path.join(P["metadata"], "content_brief.md"))
        inp = os.path.join(P["metadata"], "description_input.json")
        if not os.path.exists(inp): sys.exit(f"content brief written; now write {inp} (titles, description parts, tags) and rerun")
        paths, probs = metadata.build(cfg, ch, _j(inp)); print("\n".join(paths)); print("problems:", probs or "none")
    elif s == "blog":
        from . import blog
        inp = os.path.join(P["metadata"], "blog_input.json")
        if not os.path.exists(inp): sys.exit(f"write {inp} from metadata/content_brief.md first (fields: see ytpipe/blog.py)")
        th = publish._thumbnails(cfg, state.load(cfg))
        if os.path.exists(os.path.join(A, "analysis.json")) and os.path.exists(os.path.join(P["timelines"], "edl.json")):
            sc = blog.screens(cfg, an(), edl(), os.path.join(P["root"], "blog", "screens"))   # slide stills for "images"
            print(len(sc), "slide stills in blog/screens (pick them in blog_input images)")
        r = blog.build(cfg, _j(inp), th[0] if th else None)
        print(r["dir"], r["files"], f"{r['words']} words, {r['minutes']} min read"); print("checks:", r["problems"] or "pass")
        for m in r["todo"]: print("to do:", m)
    elif s in ("wp-publish", "wp-check"):
        from . import blog, wordpress
        W = cfg["wordpress"]; client = None
        if s == "wp-check": print(json.dumps(wordpress.check(wordpress.connect(cfg)), indent=1, ensure_ascii=False)); return
        inp = _j(os.path.join(P["metadata"], "blog_input.json")); th = publish._thumbnails(cfg, state.load(cfg))
        blog.build(cfg, inp, th[0] if th else None); D = blog.document(cfg, inp, th[0] if th else None)
        if W.get("site_url"):
            try: client = wordpress.connect(cfg)
            except wordpress.WPError as e:
                if a.send: sys.exit(str(e))
                print("offline dry run:", e)
        if not a.send:
            r = wordpress.dry_run(cfg, inp, D, client, a.check_links)
            print(os.path.join(r["dir"], "dry_run.md")); print("payload", r["hash"], "|", len(r["suggestions"]), "internal link suggestions")
            for w in r["warnings"]: print("warning:", w)
            print(f"review it, then: python -m ytpipe approve blog_publish --note payload:{r['hash']}  (and rerun with --send)")
        else:
            if client is None: sys.exit("wordpress.site_url is not set")
            state.require(cfg, "blog_publish")
            r = wordpress.send(cfg, inp, D, client, state.load(cfg)["approvals"]["blog_publish"].get("note", ""), a.force)
            print(json.dumps(r, indent=1, ensure_ascii=False)); print("open the draft, check it, and press Publish in WordPress yourself")
    elif s == "thumbnails":                                   # v2: face analysis (cached) + HTML/CSS premium layouts
        from . import faces, thumbs_v2
        E = edl(); fa = os.path.join(P["thumbnails"], "face_analysis.json")
        rows = _j(fa) if os.path.exists(fa) else faces.analyse(cfg, [(x["face_in"], x["face_out"]) for x in E["segments"] if x["layout"] == "A"]
                                                                or [(x["face_in"], x["face_out"]) for x in E["segments"]], meta()["face_color_pipeline"],
                                                                cfg["thumbnails"]["face_analysis_fps"], fa)
        print("face frames:", faces.rejection_summary(rows))
        for r in thumbs_v2.run(cfg, rows, os.path.join(P["thumbnails"], "thumbnail_input_v2.json"), P["thumbnails"]):
            print(os.path.basename(r["file"]), r["layout"], "frame", r["frame_t"], "QA:", r["qa"] or "pass")
        print("choose one, then: python -m ytpipe approve thumbnail --note option_N")
    elif s == "shorts":
        E = edl(); ch = metadata.chapters(_j(os.path.join(P["timelines"], "chapter_markers.json"))["markers"], E["segments"], E["duration"])
        terms = [k for k in _j(os.path.join(config.ROOT, cfg["captions"]["glossary"])) if not k.startswith("_")]
        c = shorts.candidates(cfg, transcript.parse(os.path.join(P["transcripts"], "transcript.txt")), E["segments"], terms, ch)
        json.dump(c, open(os.path.join(P["shorts"], "candidates.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        shorts.report(cfg, c, ch, os.path.join(P["shorts"], "shorts_candidate_report.md")); print(len(c), "candidates -> shorts_candidate_report.md (curate, then approve shorts)")
    elif s == "shorts-render":
        state.require(cfg, "shorts"); E = edl(); cands = _j(os.path.join(P["shorts"], "candidates_curated.json") if os.path.exists(os.path.join(P["shorts"], "candidates_curated.json")) else os.path.join(P["shorts"], "candidates.json"))
        srt = os.path.join(P["transcripts"], f"{cfg['project']['lesson_id']}_hinglish.srt"); cues = []
        if os.path.exists(srt):
            for b in open(srt, encoding="utf-8").read().strip().split("\n\n"):
                l = b.split("\n"); t = [sum(float(v) * m for v, m in zip(x.replace(",", ".").split(":"), (3600, 60, 1))) for x in l[1].split(" --> ")]
                cues.append((t[0], t[1], "\n".join(l[2:])))
        final = a.final or os.path.join(P["full_video"], f"{cfg['project']['lesson_id']}.mp4"); g = _j(os.path.join(P["timelines"], "geometry.json")) if os.path.exists(os.path.join(P["timelines"], "geometry.json")) else None
        ft = np.load(os.path.join(A, "face_track.npy")) if os.path.exists(os.path.join(A, "face_track.npy")) else None
        from . import shorts_v3, shorts_v2, transcript as tr_          # v3: rectangular split / full-frame / desktop focus (no circles)
        an_ = an() if os.path.exists(os.path.join(A, "analysis.json")) else {}
        area = an_.get("slide_area") or [0, 0, 1890, 1080]; cb = an_.get("counter_box")
        env = np.load(os.path.join(A, "speech_env.npy")); off_ = E["offset_s"]
        lines = tr_.parse(os.path.join(P["transcripts"], "transcript.txt"))
        terms = [k for k in _j(os.path.join(config.ROOT, cfg["captions"]["glossary"])) if not k.startswith("_") and len(k) > 2]
        etime = lambda F: metadata.edit_time(F, E["segments"])
        for k in [int(x) for x in a.clips.split(",")]:
            c = cands[k - 1]; F0, F1 = c.get("face_start"), c.get("face_end")
            if F0 is None:                                   # map the clip's final-video times back to face time
                seg0 = next(x for x in E["segments"] if x["edit_start"] <= c["start"] < x["edit_start"] + x["frames"] / 30)
                seg1 = next(x for x in E["segments"] if x["edit_start"] < c["end"] <= x["edit_start"] + x["frames"] / 30)
                F0, F1 = seg0["face_in"] + c["start"] - seg0["edit_start"], seg1["face_in"] + c["end"] - seg1["edit_start"]
            ink = shorts_v3.ink_runs(cfg["sources"]["desktop_recording"], F0 + off_, F1 + off_, off_)
            parts = shorts_v3.plan(F0, F1, [l["face"] for l in lines if F0 <= l["face"] <= F1], env, ink)
            pipe = meta()["face_color_pipeline"] if os.path.exists(os.path.join(A, "metadata.json")) else "libplacebo"
            if a.style == "v4":                              # approved 2026-10-22: tightened pauses, 2-4 word captions, music, guided split
                from . import shorts_audio, shorts_focus
                V4 = cfg["shorts"].get("v4", {}); music = a.music or (os.path.join(config.ROOT, V4["music"]) if V4.get("music") else None)
                bpm = a.bpm or V4.get("music_bpm"); mdb = a.music_db if a.music_db is not None else V4.get("music_db_under_voice", 20.0)
                crops, gparts, glog = {}, [], []
                for f0_, f1_, l_ in parts:                   # A parts: the desktop follows what is being explained
                    if l_ == "C" and V4.get("guided_split", {}).get("enabled", True):   # desktop focus: widened so no word is cut at an edge
                        fr_ = shorts_focus.ocr(cfg["sources"]["desktop_recording"], [round(f0_ + off_ + 0.2, 2), round(f1_ + off_ - 0.2, 2)], os.path.join(P["shorts"], "ocr_cache.json"))
                        c0 = shorts_v3.focus_crop(cfg["sources"]["desktop_recording"], f0_ + off_, f1_ + off_, area, 1080 / 1260) or shorts_v2.content_crop(cfg["sources"]["desktop_recording"], f0_ + off_, f1_ + off_, area, cb, aspect=1080 / 1260, min_w=700)
                        crops[(f0_, f1_)] = {"desk": shorts_focus.unclip(c0, area, 1080 / 1260, shorts_focus.text_boxes(cfg["sources"]["desktop_recording"], list(fr_), os.path.join(P["shorts"], "ocr_cache.json"), area), 700,
                                                                         shorts_focus.ink_box(cfg["sources"]["desktop_recording"], f0_ + off_, f1_ + off_))}
                    if l_ != "A" or not V4.get("guided_split", {}).get("enabled", True): gparts.append((f0_, f1_, l_)); continue
                    ov = shorts_v2.content_crop(cfg["sources"]["desktop_recording"], f0_ + off_, f1_ + off_, area, cb, aspect=1080 / 900, min_w=900)
                    for s0, s1, c_ in shorts_focus.guided(f0_, f1_, [l["face"] for l in lines], [l["text"] for l in lines], cfg["sources"]["desktop_recording"],
                                                          off_, area, 1080 / 900, shorts_v3.pauses(env, f0_, f1_), ov, os.path.join(P["shorts"], "ocr_cache.json"),
                                                          V4.get("guided_split", {}).get("min_shot_s", 4.0), glog):
                        gparts.append((s0, s1, "A")); crops[(s0, s1)] = {"desk": c_, "parent": (f0_, f1_)}
                parts = gparts
                cut = shorts_v3.tighten(F0, F1, env, V4.get("pause_keep_s", 0.25), V4.get("pause_min_s", 0.35)); pcs = shorts_v3.pieces_of(parts, E["segments"], cut)
                def env_at(t):                               # edit time -> narration level (dB) at that face time
                    g = next((x for x in E["segments"] if x["edit_start"] <= t < x["edit_start"] + x["frames"] / 30), None)
                    return env[int((g["face_in"] + t - g["edit_start"]) * 100)] if g else 0.0
                ccues = shorts_v3.chunk_cues(cues, env_at); T, bounds, sp = 0.0, [], []
                for i, p_ in enumerate(pcs):
                    if i and (abs(pcs[i - 1][1] - p_[0]) > 1e-3 or pcs[i - 1][3:] != p_[3:]): bounds.append(round(T, 3))   # jump cuts, layout switches, reframes
                    T += round((p_[1] - p_[0]) * 30) / 30; sp.append((p_[0], p_[1]))
                vdir = os.path.join(P["shorts"], "v4"); out = os.path.join(vdir, f"short_{k:02d}.mp4")      # earlier previews are kept
                mdir = os.path.join(vdir, "music_mix"); os.makedirs(mdir, exist_ok=True); wav = os.path.join(mdir, f"short_{k:02d}.wav")
                mi = shorts_audio.mix(cfg, sp, music, bpm, bounds, wav, speech_db=mdb)
                info = shorts_v3.render(cfg, final, ccues, parts, off_, ft, pipe, out, terms, etime, area, cb, E["segments"], cut, wav, "chunk", crops)
                sparts, t_ = [], F0
                for f0_, f1_, l_ in parts:
                    d_ = sum(round((p_[1] - p_[0]) * 30) / 30 for p_ in pcs if f0_ <= p_[0] < f1_); sparts.append((t_, t_ + d_, l_)); t_ += d_
                json.dump({"parts": parts, "short_parts": sparts, "cut_out": cut, "cuts_short_time": bounds, "mix": mi, "render": info, "guided_split": glog},
                          open(wav.replace(".wav", ".json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
                print(out, f"{len(cut)} pauses tightened, {len(ccues)} caption chunks, {T:.2f} s, mix {mi['final']}", "QA:", qa.short(out, cfg, parts=sparts) or "pass")
                continue
            out = os.path.join(P["shorts"], f"short_{k:02d}.mp4")
            info = shorts_v3.render(cfg, final, cues, parts, off_, ft, pipe, out, terms, etime, area, cb, E["segments"])
            print(out, parts, "QA:", qa.short(out, cfg, parts=parts) or "pass")
    elif s == "qa":
        E = edl(); srt = os.path.join(P["transcripts"], f"{cfg['project']['lesson_id']}_hinglish.srt")
        res = {"captions": qa.captions(srt, E["duration"], cfg) if os.path.exists(srt) else "no SRT"}
        tj = os.path.join(P["thumbnails"], "thumbnails.json")
        if os.path.exists(tj): res["thumbnails"] = {os.path.basename(r["file"]): r["qa"] for r in _j(tj)}
        qa._save(cfg, "deliverables", res); print(json.dumps(res, indent=1))
        if a.final:                                          # re-check a finished video (read only) with its render's stems
            g = _j(os.path.join(P["timelines"], "geometry.json"))
            r = qa.run_full(cfg, a.final, E["segments"], E["offset_s"], an(), g, os.path.join(os.path.dirname(os.path.abspath(a.final)), "work"))
            print("full video:", json.dumps(r["findings"], indent=1))
    elif s == "package":
        fv = a.final or os.path.join(P["full_video"], f"{cfg['project']['lesson_id']}.mp4")
        print(publish.build(cfg, fv if os.path.exists(fv) else None))
    elif s == "approve": state.approve(cfg, a.gate, a.note); print("approved:", a.gate)
    elif s == "status": print(json.dumps(state.load(cfg), indent=1))
    else: sys.exit(f"unknown stage {s}")
    if s not in ("approve", "status"):
        state.mark(cfg, s, state.fingerprint(a.config, cfg["sources"]["face_camera"], cfg["sources"]["desktop_recording"]))

if __name__ == "__main__":
    main()
