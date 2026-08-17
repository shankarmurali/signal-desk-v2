# Contributing

The easiest way to contribute is a PR to `config/sources.yml`:

- **Add a feed** to `rss_feeds` (name, url, weight 1–3).
- **Tune keywords** in `boost_keywords`.
- **Add HN queries or subreddits** to the discussion sources.

Guidelines: sources must be free and keyless, on-topic for AI security /
fraud / trust & safety, and reasonably signal-dense. Run
`python scripts/build_issue.py --sample` before submitting to confirm the
site still builds.
