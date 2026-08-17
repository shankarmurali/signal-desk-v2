#!/usr/bin/env python3
"""
Signal Desk v2 — newsletter builder.

Fetches AI-security / fraud / T&S signals from free, keyless sources,
ranks them, and renders a newsletter issue as a static web page.

Usage:
    python scripts/build_issue.py             # fetch live sources
    python scripts/build_issue.py --sample    # build from bundled sample data (offline demo)

Outputs (committed to the repo, served by GitHub Pages):
    site/issues/YYYY-MM-DD.html    the issue
    site/index.html                latest issue + archive
    site/feed.xml                  RSS feed of issues (this is how people "subscribe")
    issues_md/YYYY-MM-DD.md        markdown copy (nice for email tools like Buttondown)
"""

import argparse
import datetime as dt
import html
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlparse

import requests
import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).resolve().parent.parent
UA = {"User-Agent": "signal-desk-v2 newsletter builder (github.com; contact via repo issues)"}
TIMEOUT = 20


# ──────────────────────────────────────────────────────────────────
# helpers
# ──────────────────────────────────────────────────────────────────

def load_config():
    with open(ROOT / "config" / "sources.yml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def now_utc():
    return dt.datetime.now(dt.timezone.utc)


def hours_ago(ts):
    if ts is None:
        return 999
    return (now_utc() - ts).total_seconds() / 3600


def domain_of(url):
    try:
        return urlparse(url).netloc.replace("www.", "")
    except Exception:
        return ""


def clean_text(s, limit=280):
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = html.unescape(re.sub(r"\s+", " ", s)).strip()
    return (s[: limit - 1] + "…") if len(s) > limit else s


def score_item(item, cfg):
    """Simple transparent ranking: source weight + keyword hits + recency + engagement."""
    score = item.get("weight", 0)
    text = (item.get("title", "") + " " + item.get("summary", "")).lower()
    for kw in cfg.get("boost_keywords", []):
        if kw.lower() in text:
            score += 2
    age = hours_ago(item.get("published"))
    if age < 12:
        score += 3
    elif age < 24:
        score += 2
    elif age < 36:
        score += 1
    engagement = item.get("points", 0) or 0
    score += min(engagement // 50, 4)   # cap so one viral post can't drown everything
    item["score"] = score
    return score


def dedupe(items):
    seen, out = set(), []
    for it in items:
        key = it.get("url") or ""
        tkey = re.sub(r"[^a-z0-9]+", "", (it.get("title") or "").lower())[:60]
        if key in seen or (tkey and tkey in seen):
            continue
        seen.add(key)
        seen.add(tkey)
        out.append(it)
    return out


def safe(section_name):
    """Decorator: a broken source never kills the issue — it just logs and returns []."""
    def wrap(fn):
        def inner(*args, **kwargs):
            try:
                items = fn(*args, **kwargs)
                print(f"  [ok] {section_name}: {len(items)} items")
                return items
            except Exception as e:
                print(f"  [skip] {section_name}: {e}", file=sys.stderr)
                return []
        return inner
    return wrap


# ──────────────────────────────────────────────────────────────────
# fetchers — every one of these is keyless
# ──────────────────────────────────────────────────────────────────

@safe("rss")
def fetch_rss(cfg):
    import feedparser
    items = []
    for feed in cfg.get("rss_feeds", []):
        try:
            parsed = feedparser.parse(feed["url"], request_headers=UA)
        except Exception:
            continue
        for e in parsed.entries[:15]:
            published = None
            for attr in ("published_parsed", "updated_parsed"):
                t = getattr(e, attr, None)
                if t:
                    published = dt.datetime(*t[:6], tzinfo=dt.timezone.utc)
                    break
            items.append({
                "title": clean_text(getattr(e, "title", ""), 200),
                "url": getattr(e, "link", ""),
                "summary": clean_text(getattr(e, "summary", "")),
                "source": feed["name"],
                "weight": feed.get("weight", 1),
                "published": published,
            })
    lookback = cfg["newsletter"].get("lookback_hours", 36)
    return [i for i in items if hours_ago(i["published"]) <= lookback]


@safe("incident tracker")
def fetch_incidents(cfg):
    ic = cfg.get("incident_tracker", {})
    if not ic.get("enabled"):
        return []
    repo, path = ic["repo"], ic.get("incidents_path", "incidents")
    listing = requests.get(
        f"https://api.github.com/repos/{repo}/contents/{path}",
        headers=UA, timeout=TIMEOUT,
    )
    listing.raise_for_status()
    files = [f for f in listing.json() if f["name"].endswith((".yml", ".yaml"))]
    incidents = []
    for f in files:
        try:
            raw = requests.get(f["download_url"], headers=UA, timeout=TIMEOUT)
            data = yaml.safe_load(raw.text) or {}
            incidents.append({
                "title": data.get("title", f["name"]),
                "date": str(data.get("date", "")),
                "severity": str(data.get("severity", "unknown")).lower(),
                "summary": clean_text(str(data.get("summary", "")), 320),
                "url": data.get("source_url")
                       or f"https://github.com/{repo}/blob/main/{path}/{f['name']}",
            })
        except Exception:
            continue
    incidents.sort(key=lambda x: x["date"], reverse=True)
    return incidents[: ic.get("max_items", 5)]


@safe("hacker news")
def fetch_hackernews(cfg):
    hn = cfg.get("hackernews", {})
    if not hn.get("enabled"):
        return []
    items = []
    for q in hn.get("queries", []):
        r = requests.get(
            "https://hn.algolia.com/api/v1/search_by_date",
            params={"query": q, "tags": "story", "numericFilters": f"points>{hn.get('min_points', 40)}"},
            headers=UA, timeout=TIMEOUT,
        )
        r.raise_for_status()
        for hit in r.json().get("hits", [])[:5]:
            ts = dt.datetime.fromtimestamp(hit["created_at_i"], tz=dt.timezone.utc)
            items.append({
                "title": clean_text(hit.get("title", ""), 200),
                "url": hit.get("url") or f"https://news.ycombinator.com/item?id={hit['objectID']}",
                "discussion_url": f"https://news.ycombinator.com/item?id={hit['objectID']}",
                "summary": f"{hit.get('points', 0)} points · {hit.get('num_comments', 0)} comments on Hacker News",
                "source": "Hacker News",
                "points": hit.get("points", 0),
                "published": ts,
            })
    return [i for i in items if hours_ago(i["published"]) <= 72]


@safe("reddit")
def fetch_reddit(cfg):
    rd = cfg.get("reddit", {})
    if not rd.get("enabled"):
        return []
    items = []
    for sub in rd.get("subreddits", []):
        r = requests.get(
            f"https://www.reddit.com/r/{sub}/top.json",
            params={"t": "day", "limit": 10},
            headers=UA, timeout=TIMEOUT,
        )
        r.raise_for_status()
        for child in r.json().get("data", {}).get("children", []):
            p = child["data"]
            if p.get("score", 0) < rd.get("min_score", 60):
                continue
            items.append({
                "title": clean_text(p.get("title", ""), 200),
                "url": f"https://www.reddit.com{p.get('permalink', '')}",
                "discussion_url": f"https://www.reddit.com{p.get('permalink', '')}",
                "summary": f"{p.get('score', 0)} upvotes · {p.get('num_comments', 0)} comments in r/{sub}",
                "source": f"r/{sub}",
                "points": p.get("score", 0),
                "published": dt.datetime.fromtimestamp(p.get("created_utc", 0), tz=dt.timezone.utc),
            })
    return items


@safe("lobsters")
def fetch_lobsters(cfg):
    lb = cfg.get("lobsters", {})
    if not lb.get("enabled"):
        return []
    items = []
    for tag in lb.get("tags", []):
        r = requests.get(f"https://lobste.rs/t/{tag}.json", headers=UA, timeout=TIMEOUT)
        r.raise_for_status()
        for p in r.json()[:5]:
            items.append({
                "title": clean_text(p.get("title", ""), 200),
                "url": p.get("url") or p.get("comments_url", ""),
                "discussion_url": p.get("comments_url", ""),
                "summary": f"{p.get('score', 0)} points · {p.get('comment_count', 0)} comments on Lobsters",
                "source": "Lobsters",
                "points": p.get("score", 0),
                "published": None,
            })
    return items


@safe("arxiv")
def fetch_arxiv(cfg):
    ax = cfg.get("arxiv", {})
    if not ax.get("enabled"):
        return []
    ns = {"a": "http://www.w3.org/2005/Atom"}
    items = []
    for q in ax.get("queries", []):
        r = requests.get(
            "https://export.arxiv.org/api/query",
            params={"search_query": q, "sortBy": "submittedDate",
                    "sortOrder": "descending", "max_results": 5},
            headers=UA, timeout=TIMEOUT,
        )
        r.raise_for_status()
        root = ET.fromstring(r.text)
        for entry in root.findall("a:entry", ns):
            title = clean_text(entry.findtext("a:title", "", ns), 220)
            link = entry.findtext("a:id", "", ns)
            summary = clean_text(entry.findtext("a:summary", "", ns), 300)
            published = entry.findtext("a:published", "", ns)
            authors = [a.findtext("a:name", "", ns) for a in entry.findall("a:author", ns)]
            items.append({
                "title": title,
                "url": link,
                "summary": summary,
                "source": "arXiv",
                "authors": ", ".join(authors[:3]) + (" et al." if len(authors) > 3 else ""),
                "published_str": published[:10],
            })
    # newest first, unique by url
    return dedupe(sorted(items, key=lambda x: x.get("published_str", ""), reverse=True))[
        : ax.get("max_items", 5)
    ]


# ──────────────────────────────────────────────────────────────────
# assemble + render
# ──────────────────────────────────────────────────────────────────

def build_sections(cfg, sample=False):
    if sample:
        with open(ROOT / "sample_data" / "sample_issue.json", "r", encoding="utf-8") as f:
            raw = json.load(f)
        for it in raw.get("top_signals", []) + raw.get("discussions", []):
            it["published"] = None
        return raw

    max_items = cfg["newsletter"].get("max_items_per_section", 8)

    top = dedupe(fetch_rss(cfg))
    for it in top:
        score_item(it, cfg)
    top.sort(key=lambda x: x["score"], reverse=True)

    discussions = dedupe(fetch_hackernews(cfg) + fetch_reddit(cfg) + fetch_lobsters(cfg))
    for it in discussions:
        score_item(it, cfg)
    discussions.sort(key=lambda x: x["score"], reverse=True)

    return {
        "top_signals": top[:max_items],
        "incidents": fetch_incidents(cfg),
        "discussions": discussions[:max_items],
        "research": fetch_arxiv(cfg),
    }


def max_score(sections):
    scores = [i.get("score", 0) for i in sections.get("top_signals", [])] or [1]
    return max(scores) or 1


def render(cfg, sections):
    env = Environment(
        loader=FileSystemLoader(ROOT / "templates"),
        autoescape=select_autoescape(["html"]),
    )
    today = now_utc().strftime("%Y-%m-%d")
    display_date = now_utc().strftime("%A, %B %-d, %Y")

    issues_dir = ROOT / "site" / "issues"
    issues_dir.mkdir(parents=True, exist_ok=True)
    md_dir = ROOT / "issues_md"
    md_dir.mkdir(exist_ok=True)

    issue_no = len(list(issues_dir.glob("*.html")))
    if not (issues_dir / f"{today}.html").exists():
        issue_no += 1

    ctx = {
        "cfg": cfg["newsletter"],
        "date": today,
        "display_date": display_date,
        "issue_no": issue_no,
        "sections": sections,
        "max_score": max_score(sections),
        "domain_of": domain_of,
    }

    (issues_dir / f"{today}.html").write_text(
        env.get_template("issue.html.j2").render(**ctx), encoding="utf-8")

    # archive: newest first
    archive = sorted([p.stem for p in issues_dir.glob("*.html")], reverse=True)
    (ROOT / "site" / "index.html").write_text(
        env.get_template("index.html.j2").render(archive=archive, latest=archive[0], **ctx),
        encoding="utf-8")

    # markdown copy
    (md_dir / f"{today}.md").write_text(
        env.get_template("issue.md.j2").render(**ctx), encoding="utf-8")

    # RSS feed of issues
    write_feed(cfg, archive)
    print(f"Rendered issue #{issue_no} for {today} → site/issues/{today}.html")


def write_feed(cfg, archive):
    esc = lambda s: html.escape(s, quote=False)
    nl = {k: esc(str(v)) for k, v in cfg["newsletter"].items()}
    base = str(cfg["newsletter"]["site_url"]).rstrip("/")
    items = "\n".join(
        f"""  <item>
    <title>{nl['title']} — {d}</title>
    <link>{base}/issues/{d}.html</link>
    <guid>{base}/issues/{d}.html</guid>
    <pubDate>{dt.datetime.strptime(d, '%Y-%m-%d').strftime('%a, %d %b %Y 07:00:00 +0000')}</pubDate>
  </item>""" for d in archive[:30])
    feed = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
  <title>{nl['title']}</title>
  <link>{base}</link>
  <description>{nl['tagline']}</description>
{items}
</channel>
</rss>"""
    (ROOT / "site" / "feed.xml").write_text(feed, encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", action="store_true", help="build from bundled sample data (offline)")
    args = ap.parse_args()

    cfg = load_config()
    print("Building Signal Desk issue…")
    sections = build_sections(cfg, sample=args.sample)
    render(cfg, sections)


if __name__ == "__main__":
    main()
