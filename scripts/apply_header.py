#!/usr/bin/env python3
"""Apply the shared research-site header to this project's pages.

Uses the programme's banner module (repos/grounded/tools/banner.py). Until this
project is listed in banner.PROJECTS it is registered here for these pages
only, so the header shows the project name and its page tabs without changing
any other site.

Usage: python3 scripts/apply_header.py docs/index.html [docs/story.html ...]
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT.parent / "grounded" / "tools"
SLUG = "ehs-chemical-peers"
TITLE = "Chemical plant peers"
PAGES = [("index.html", "Plant explorer"), ("story.html", "Story"), ("method.html", "Data & method")]


def main(paths):
    sys.path.insert(0, str(TOOLS))
    import banner  # noqa: E402
    if SLUG not in {k for k, _t, _n in banner.PROJECTS}:
        banner.PROJECTS = banner.PROJECTS + [(SLUG, TITLE, "peer explorer")]
    banner.PROJECT_PAGES.setdefault(SLUG, PAGES)
    for p in paths:
        path = Path(p)
        html = path.read_text(encoding="utf-8")
        out = banner.apply_banner(html, current=SLUG, sections=[], page=path.name)
        if out != html:
            path.write_text(out, encoding="utf-8")
            print("header applied:", path)


if __name__ == "__main__":
    main(sys.argv[1:])
