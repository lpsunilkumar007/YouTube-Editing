# YouTube metadata guide

Implemented in `ytpipe\metadata.py`. Lesson 01 output is in `lessons\lesson01\metadata\`.

## Sources of truth
- **Chapters:** come from the **final edit** (`timelines\edl.json`), never from the raw recording.
  - Markers are entered in face-camera time (`timelines\chapter_markers.json`) and converted through the EDL.
  - Validated against YouTube's rules: the first at 0:00, at least 3 chapters, each at least 10 s, in ascending order.
- **Everything written comes from `metadata\content_brief.md`.** That is the transcript of what is actually in the final edit, grouped by chapter.
- **Credits** are inserted verbatim from `config\credits.json`. Attribution is required for CC BY and **does not guarantee that no Content ID claim will appear** (stated in the description).

## Files produced
| File | Content |
|---|---|
| `youtube_titles.md` | 5 options: beginner, search, problem-solving, curiosity, professional. A recommendation with reasons. Character counts (≤ 70) |
| `youtube_description.md` | Intro, what you'll learn, concepts, examples, chapters, prerequisites, resources, call to action, hashtags, music credit (≤ 5000 characters) |
| `youtube_chapters.txt` | The chapter list alone |
| `youtube_tags.txt` | ≤ 500 characters (multi-word tags counted with quotes) |
| `youtube_hashtags.txt` | ≤ 5 |
| `pinned_comment.md` | A question that checks understanding, plus a next-lesson note |
| `shorts\*.md` | Per approved clip: Shorts title (≤ 100), description, Instagram caption (≤ 2200), hashtags, cover-frame time, optional pinned comment, credit if the clip has music |

## Writing rules
- **Describe only what the video teaches.** No invented claims, links, courses or social accounts.
- **Placeholders** stand in for anything you haven't supplied: `{{CHANNEL_NAME}}`, `{{PLAYLIST_URL}}`, `{{NEXT_LESSON_URL}}`, `{{WEBSITE_URL}}`, `{{INSTAGRAM_URL}}`. Set real values in the config (`youtube.links`). The validator lists every unfilled placeholder.
- **No URLs** except configured links and licence URLs. The validator flags any other.
- **No search-volume or ranking claims** without real keyword data.
- **Titles:** concise and accurate. Use the main search phrase naturally. No clickbait that the video doesn't deliver.
- **Hinglish is fine** in the intro and pinned comment. Technical terms follow `config\glossary.json`.
