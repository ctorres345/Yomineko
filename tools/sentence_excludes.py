#!/usr/bin/env python3
"""Turn your own text filters into a list of line ids for a game's review file.

Sentence selection cannot hold game text, so a game's unwanted lines (debug strings, system
menus, sleep-talk) are kept in the review as line ids (``sentences.exclude``). This tool makes
that list: it matches your patterns against an extracted script and writes the ids.

    python tools/sentence_excludes.py script.json patterns.txt --review pmd-red-jp.yaml

``patterns.txt`` has one regular expression per line (``#`` starts a comment). It contains game
text, so keep it under ``yomineko-out/`` and never commit it. Only distinct dialogue lines are
matched. The review's other content is left as it is, except that its ``sentences.exclude`` list
is replaced by the new ids; ``sentences.pin`` is kept. Prints counts, never text.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

from yomineko.analyze.review import ReviewError, parse_review
from yomineko.script_io import read_script

LF = chr(10)


def read_patterns(path: Path) -> list[re.Pattern[str]]:
    patterns = []
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        try:
            patterns.append(re.compile(raw))
        except re.error as e:
            raise SystemExit(f"{path}: line {number} is not a valid regular expression: {e}") from e
    return patterns


def matching_ids(lines: list[tuple[str, str]], patterns: list[re.Pattern[str]]) -> list[str]:
    """Ids of the (id, text) lines any pattern matches, sorted."""
    return sorted({line_id for line_id, text in lines if any(p.search(text) for p in patterns)})


def drop_sentences_block(text: str) -> str:
    """The review text without its top-level ``sentences:`` block (and its comments)."""
    out: list[str] = []
    skipping = False
    for line in text.split(LF):
        if re.match(r"^sentences\s*:", line):
            skipping = True
            continue
        if skipping and (not line.strip() or line[0] in " \t-#"):
            continue
        skipping = False
        out.append(line)
    return LF.join(out).rstrip(LF) + LF


def render_sentences_block(exclude: list[str], pin: list[str]) -> str:
    out = ["sentences:"]
    for name, ids in (("exclude", exclude), ("pin", pin)):
        if ids:
            out.append(f"  {name}:")
            out.extend(f'    - "{i}"' for i in ids)
    return LF.join(out) + LF


def update_review(review_text: str, ids: list[str]) -> str:
    """The review with ``sentences.exclude`` set to ``ids``. Raises ``ReviewError`` if the
    result would be invalid (an id both excluded and pinned, say)."""
    current = parse_review(yaml.safe_load(review_text) or {}, "review")
    pins = list(current.sentences.pin)
    new = drop_sentences_block(review_text) + LF + render_sentences_block(ids, pins)
    parse_review(yaml.safe_load(new), "updated review")
    return new


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("script", type=Path, help="script.json from yomineko extract")
    ap.add_argument("patterns", type=Path, help="regular expressions, one per line (local only)")
    ap.add_argument("--review", type=Path, required=True, help="review file to update")
    args = ap.parse_args(argv)
    script = read_script(args.script)
    lines = [
        (x.id, x.text)
        for x in script.lines
        if x.kind == "dialogue" and x.text and x.duplicate_of is None
    ]
    ids = matching_ids(lines, read_patterns(args.patterns))
    try:
        updated = update_review(args.review.read_text(encoding="utf-8"), ids)
    except ReviewError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    args.review.write_text(updated, encoding="utf-8", newline=LF)
    print(f"{len(ids)} of {len(lines)} distinct dialogue lines excluded; wrote {args.review}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
