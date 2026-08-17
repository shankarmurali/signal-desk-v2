# Signal Desk v2

A self-publishing **AI security & fraud newsletter**. Every day, a GitHub Action
gathers signals from free public sources, renders a newsletter issue, and
publishes it as a web page on GitHub Pages — **no API keys, no server, no cost**.

**Sections in every issue:**

| # | Section | Source |
|---|---------|--------|
| 01 | Top Signals | Curated RSS feeds (Krebs, Schneier, CISA, vendor blogs…) |
| 02 | Incident Watch | Auto-pulled from the [AI Agent Incident Tracker](https://github.com/shankarmurali/ai-agent-incident-tracker) |
| 03 | Interesting Discussions | Hacker News (Algolia), Reddit, Lobsters |
| 04 | Research Corner | New arXiv papers |

Plus a **zero-key deep research mode**: `research_pack.py` compiles everything
the newsletter has collected on a topic into a structured prompt you run in
Claude or Claude Code yourself.

## Quick start

```bash
pip install -r requirements.txt
python scripts/build_issue.py --sample   # offline demo issue
open site/index.html
```

Build a real issue (fetches live sources, still keyless):

```bash
python scripts/build_issue.py
```

## Deploy (one-time setup)

1. Push this repo to GitHub.
2. In **Settings → Pages**, set *Source* to **GitHub Actions**.
3. In **Settings → Actions → General**, allow workflows **read and write permissions**.
4. Edit `config/sources.yml`: set `site_url` and your `incident_tracker.repo`.
5. Trigger the **Build & publish daily issue** workflow manually once from the
   Actions tab. After that it runs daily at 07:00 IST.

Your newsletter is now live at `https://<you>.github.io/signal-desk-v2`, with
an archive and an RSS feed at `/feed.xml` that anyone can subscribe to.
(Optional email later: point Buttondown's free RSS-to-email at that feed.)

## Deep research packs

```bash
python scripts/research_pack.py "prompt injection defenses"
```

Writes `research_packs/<date>-prompt-injection-defenses.md` containing a
research brief plus every matching link from the last 30 days of issues.
Paste it into Claude — the repo itself never calls an LLM.

## Customize

- **Sources & keywords:** everything lives in `config/sources.yml`.
- **Cadence:** edit the cron line in `.github/workflows/publish.yml`
  (e.g. `30 1 * * 1` for a weekly Monday issue).
- **Ranking:** `score_item()` in `scripts/build_issue.py` — source weight +
  keyword boosts + recency + capped engagement. Transparent on the page as the
  ▮▮▮▯▯ signal-strength meter.
- **Design:** `templates/issue.html.j2` — a single self-contained stylesheet.

## Design principles

- **Keyless by construction.** Every fetcher uses public, unauthenticated
  endpoints. There is nowhere to put an API key.
- **Fail-soft.** A broken source logs a warning and its section shrinks;
  the issue still ships.
- **Everything is a file.** Issues are committed markdown + HTML, so the full
  archive is versioned and greppable.

## License

MIT
