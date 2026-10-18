"""The Chinese (Simplified) translations NetEase, QQ Music and Kugou ship with their lyrics."""
from __future__ import annotations

from collections import defaultdict, deque
from typing import Deque, Dict, List, Optional

from .lrc_parser import parse_lrc
from .lyrics_models import LyricsLine

# The language every provided translation is in
LANGUAGE = "zh-CN"


def _is_notice(text: str) -> bool:
    # "//" marks an untranslated QQ Music line; the others are copyright and "translated by an AI model" notices.
    return text == "//" or "享有本翻译作品的著作权" in text or text.startswith("以下歌词翻译由")


def clean(lines: List[str]) -> Optional[List[str]]:
    """One entry per lyrics line. Placeholder and notice lines are blanked; None if nothing is left."""
    cleaned = ["" if _is_notice(line.strip()) else line for line in lines]
    return cleaned if any(line.strip() for line in cleaned) else None


def pair_by_timestamp(lines: List[LyricsLine], translation_lrc: str) -> Optional[List[str]]:
    """Pairs an LRC translation with lines by timestamp, which may differ in precision ([00:19.43] vs [00:19.430])."""
    translated: Dict[int, Deque[str]] = defaultdict(deque)
    for line in parse_lrc(translation_lrc):
        translated[line.start_time_ms].append(line.words)
    paired = []
    for line in lines:
        queue = translated.get(line.start_time_ms)
        paired.append(queue.popleft() if queue else "")
    return clean(paired)


def attach(lines: List[LyricsLine], translation: Optional[List[str]]) -> None:
    """Stores a translation on its lines, so sorting never separates them."""
    if translation and len(translation) == len(lines):
        for line, text in zip(lines, translation):
            line.provided = text
