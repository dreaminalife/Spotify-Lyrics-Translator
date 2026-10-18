"""Parses LRC text ("[mm:ss.xx]words") into lines sorted by start time."""
from __future__ import annotations

import re
from typing import List

from .lyrics_models import LyricsLine

TIME_TAG = re.compile(r"\[(\d+):(\d{1,2})(?:[.:](\d{1,3}))?]")
WORD_TAG = re.compile(r"<\d+:\d{1,2}(?:[.:]\d{1,3})?>")
OFFSET_TAG = re.compile(r"^\[offset:\s*([+-]?\d+)\s*]$", re.IGNORECASE)


def _to_millis(match: re.Match) -> int:
    minutes, seconds, fraction = match.group(1), match.group(2), match.group(3) or ""
    # "5" = 500 ms, "45" = 450 ms, "456" = 456 ms
    fraction_ms = int(fraction.ljust(3, "0")) if fraction else 0
    return (int(minutes) * 60 + int(seconds)) * 1000 + fraction_ms


def parse_lrc(lrc: str) -> List[LyricsLine]:
    offset_ms = 0
    result: List[LyricsLine] = []
    for raw in (lrc or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        offset = OFFSET_TAG.search(line)
        if offset:
            offset_ms = int(offset.group(1))
            continue
        tags = list(TIME_TAG.finditer(line))
        if not tags:
            continue  # metadata such as [ar:...] or untimed text
        text = WORD_TAG.sub("", TIME_TAG.sub("", line)).strip()
        result.extend(LyricsLine(_to_millis(tag), text) for tag in tags)
    # A positive [offset:] makes lyrics appear sooner.
    for line in result:
        line.start_time_ms = max(0, line.start_time_ms - offset_ms)
    result.sort(key=lambda l: l.start_time_ms)
    return result
