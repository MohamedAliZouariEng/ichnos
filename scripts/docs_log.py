#!/usr/bin/env python3
"""Add an entry to docs/log.md under today's UTC date heading, newest first.

Usage: scripts/docs_log.py "**Creation**: Added [Title](/path/to/concept.md)."
"""
import datetime as dt
import sys
from pathlib import Path

entry = " ".join(sys.argv[1:]).strip()
if not entry:
    sys.exit(__doc__)

log = Path(__file__).resolve().parent.parent / "docs" / "log.md"
lines = log.read_text(encoding="utf-8").splitlines()
heading = f"## {dt.datetime.now(dt.timezone.utc).date().isoformat()}"
item = f"* {entry}"

if heading in lines:
    lines.insert(lines.index(heading) + 1, item)
else:
    first = next((i for i, line in enumerate(lines) if line.startswith("## ")), len(lines))
    lines[first:first] = [heading, item, ""]

log.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"{heading}: {item}")
