"""Split text into heading-sized chunks for full-text search (ADR-0008)."""

import re
from dataclasses import dataclass

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})")
MAX_CHARS = 1500


@dataclass(frozen=True)
class ChunkText:
    heading: str | None
    text: str
    start_line: int | None


def _split(heading: str | None, body: str, start: int, max_chars: int) -> list[ChunkText]:
    """Keep a section whole if it fits; otherwise split at paragraphs, then hard-wrap."""
    if len(body) <= max_chars:
        return [ChunkText(heading, body, start)]
    pieces: list[str] = []
    current = ""
    for paragraph in body.split("\n\n"):
        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            pieces.append(current)
        while len(paragraph) > max_chars:
            pieces.append(paragraph[:max_chars])
            paragraph = paragraph[max_chars:]
        current = paragraph
    if current:
        pieces.append(current)
    return [ChunkText(heading, piece, start) for piece in pieces]


def chunk_markdown(
    text: str,
    *,
    default_heading: str | None = None,
    first_line: int = 1,
    max_chars: int = MAX_CHARS,
) -> list[ChunkText]:
    """One chunk per section; text before the first heading uses default_heading."""
    chunks: list[ChunkText] = []
    heading = default_heading
    buffer: list[str] = []
    start = first_line
    in_fence = False

    def flush() -> None:
        body = "\n".join(buffer).strip()
        if body:
            chunks.extend(_split(heading, body, start, max_chars))
        buffer.clear()

    for offset, line in enumerate(text.splitlines()):
        number = first_line + offset
        if FENCE_RE.match(line):
            in_fence = not in_fence
        match = None if in_fence else HEADING_RE.match(line)
        if match:
            flush()
            heading = match.group(2)
            start = number
            continue
        if not buffer and not line.strip():
            continue
        if not buffer and heading == default_heading and not chunks:
            start = number
        buffer.append(line)
    flush()
    return chunks
