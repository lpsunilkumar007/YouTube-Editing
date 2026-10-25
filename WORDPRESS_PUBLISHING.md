# WordPress publishing (`wp-publish`)

This puts each lesson's blog article on your WordPress site **as a draft**. You check it and press Publish yourself.

It works with self-hosted WordPress and with WordPress.com. It is a separate stage (`ytpipe/wordpress.py`), tested against a fake WordPress (`tests/test_wordpress.py`), and it never touches videos.

## Workflow

| Step | Command | What happens |
|---|---|---|
| 1. Article | `blog` | Builds the article from `metadata/blog_input.json` (Markdown, HTML and `SEO.txt`). It also pulls one still per slide shown in the video into `blog/screens/`; you pick which to show in `images`. |
| 2. Dry run | `wp-publish` (add `--check-links` to verify the external references) | Writes `blog/wordpress/dry_run.md`: title, slug, category, tags, featured image, excerpt, SEO fields, structured data, internal links (applied and suggested), reference checks, warnings and the full post content. Nothing is sent. |
| 3. Approve | `approve blog_publish --note payload:<hash>` | Approves **exactly** the payload in the dry run. Any later change gives a new hash, which must be approved again. |
| 4. Draft | `wp-publish --send` | Uploads new or changed images, then creates this lesson's draft or updates it. Afterwards it reads the draft back to check it. |
| 5. Publish | in WordPress | Open the edit link it prints, check the draft in your theme, and press Publish yourself. |

Rerunning step 4 after a change updates the same draft and never makes a duplicate. The draft's ID is kept in `blog/wordpress/state.json`.

## Safety rules (enforced in code)

- **Drafts only.** The status sent is always `draft`.
- **Public content is never changed.** A post that is published, scheduled or private is never updated.
- **Edits made in WordPress are protected.** If the draft was changed in WordPress after the last send, it stops. Copy those edits into `blog_input.json`, or use `--force` to overwrite them.
- **Other drafts are left alone.** A draft with the same slug that ytpipe didn't create isn't taken over without `--force`.
- **Categories are never created.** The configured category must already exist. Missing tags are created, and the dry run lists them first.
- **Credentials:**
  - read from the macOS Keychain (or the `YTPIPE_WP_APP_PASSWORD` / `YTPIPE_WP_TOKEN` environment variables)
  - never stored in config files, never logged
  - sent over HTTPS only
- **Nothing is contacted** except your own site's REST API, and the reference URLs when you pass `--check-links` (read-only page loads).

## Setup (once you give the site details)

Add these to the lesson config's `overrides`, or to `config/defaults.json` for every lesson:

```json
"wordpress": {"site_url": "https://<your site>", "kind": "self_hosted", "username": "<WordPress user>", "category": "<existing category>"}
```

- `kind`: `self_hosted` or `wpcom`.
- `seo_plugin`: `auto` detects Yoast or Rank Math from the site's REST namespaces. You can also set it to `yoast`, `rankmath` or `none`.
- `structured_data`: `auto` adds VideoObject and FAQPage, plus BlogPosting when there is no SEO plugin. The other values are `all` or `off`.
- `author_id`: optional.

**Self-hosted credentials:**
1. In WordPress, open Users → Profile → Application Passwords and create one named "ytpipe". You can revoke it any time.
2. Store it in the Keychain yourself. The `-w` at the end makes it prompt, so the password never appears in a command line:
   ```
   security add-generic-password -U -s ytpipe-wordpress -a <username>@<site host> -w
   ```

**WordPress.com credentials:** store an OAuth2 token with `-a token@<site host>` instead.

**Connection test (read-only):** `wp-check` shows the user, whether it can write drafts and upload images, the SEO plugin found and the categories that exist.

## SEO plugin fields

- **Fields sent:** the SEO title, meta description and focus keyword, as the plugin's post meta keys (`ytpipe/wordpress.py` `SEO_PLUGINS`).
- **Check after sending:** `--send` reads the draft back and reports `stored`, or `NOT stored over REST`. In the second case, enter them from `SEO.txt`.
- Whether a plugin accepts these fields over REST depends on the plugin and its version. The mapping is checked against the installed plugin's documentation when the real site is connected; nothing is assumed.

## Structured data

The JSON-LD goes in a Custom HTML block. WordPress keeps `<script>` only for users with the `unfiltered_html` capability (Administrators and Editors on a single site). `--send` reports whether it survived.

## Internal links, references, outreach

- **Internal links:**
  - The dry run suggests published posts whose title phrase (2–5 words) appears in this article. That phrase becomes the anchor.
  - Approved links go into `blog_input.json` `internal_links` (`[{"anchor", "url"}]`). Each anchor is linked once, at its first plain-text occurrence.
  - An anchor that is no longer in the text is reported, never guessed.
- **References:** `references` (`[{"title", "url", "note"}]`) become a "Further reading" section. `--check-links` confirms HTTPS, HTTP 200 and the page's real title.
- **Outreach:** `blog/wordpress/outreach.md` lists backlink opportunities to work through by hand, and what never to do. ytpipe never posts, comments or emails.
