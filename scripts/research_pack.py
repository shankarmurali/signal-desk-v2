#!/usr/bin/env python3
"""
Deep Research Pack — the zero-key research companion.

Instead of calling a paid LLM API, this script compiles everything the
newsletter gathered on a topic into a single, well-structured prompt file.
Paste it into Claude (or open the repo in Claude Code) to run the actual
deep research — you bring your own AI, the repo stays keyless.

Usage:
    python scripts/research_pack.py "prompt injection defenses"
    python scripts/research_pack.py "deepfake payment fraud" --days 14

Output:
    research_packs/YYYY-MM-DD-<slug>.md
"""

import argparse
import datetime as dt
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60]


def collect_matches(topic, days):
    """Scan recent markdown issues for lines mentioning the topic."""
    cutoff = dt.date.today() - dt.timedelta(days=days)
    matches = []
    md_dir = ROOT / "issues_md"
    if not md_dir.exists():
        return matches
    for f in sorted(md_dir.glob("*.md"), reverse=True):
        try:
            issue_date = dt.date.fromisoformat(f.stem)
        except ValueError:
            continue
        if issue_date < cutoff:
            break
        for line in f.read_text(encoding="utf-8").splitlines():
            if topic.lower() in line.lower() and "](" in line:
                matches.append(f"- ({f.stem}) {line.strip().lstrip('- ')}")
    return matches


TEMPLATE = """# Deep Research Pack: {topic}
Generated {today} by Signal Desk v2 (zero-key mode).

## How to use
Paste this entire file into Claude, or open this repo in Claude Code and ask it
to run the brief below. All source material was gathered by the newsletter
pipeline from public, keyless sources.

## Research brief
You are a senior trust-and-safety analyst. Produce a deep research report on:

> **{topic}**

Structure the report as:
1. Executive summary (5 bullets, decision-oriented)
2. What happened / current state — synthesize the collected sources below and
   search the web for anything newer
3. Threat model — who is affected, attack paths, and abuse economics
4. Defenses and detection — practical controls, ranked by effort vs. impact
5. Open questions and weak evidence — what we still don't know
6. Watchlist — 5 specific things to monitor over the next 30 days

Cite every claim with a link. Flag any source you consider low quality.

## Collected sources ({n_sources} items from the last {days} days of issues)
{sources}

## Standing context
- Reader works in trust & safety for payments/cloud at a large tech company.
- Prioritize fraud, account security, and AI-agent abuse angles.
- Prefer primary sources over aggregators.
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("topic")
    ap.add_argument("--days", type=int, default=30)
    args = ap.parse_args()

    matches = collect_matches(args.topic, args.days)
    out_dir = ROOT / "research_packs"
    out_dir.mkdir(exist_ok=True)
    today = dt.date.today().isoformat()
    out = out_dir / f"{today}-{slugify(args.topic)}.md"
    out.write_text(TEMPLATE.format(
        topic=args.topic, today=today, days=args.days,
        n_sources=len(matches),
        sources="\n".join(matches) if matches else
        "_No matching items in recent issues — ask Claude to research from scratch._",
    ), encoding="utf-8")
    print(f"Wrote {out} ({len(matches)} collected sources)")


if __name__ == "__main__":
    main()
