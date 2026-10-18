"""Picks the search result that is the playing track, for sources whose search is fuzzy (NetEase, QQ Music, Kugou)."""
from __future__ import annotations

import re
from typing import Callable, Iterable, List, Optional, Sequence, TypeVar

from .chinese_script import to_simplified
from .lyrics_models import TrackMetadata

T = TypeVar("T")

DURATION_TOLERANCE_MS = 3000
_NON_WORD = re.compile(r"[\W_]+")
_SPACES = re.compile(r"\s+")


def normalize(name: str) -> str:
    return " ".join(_SPACES.split(name.replace("　", " ").strip())).lower()


def _normalize_title(title: str) -> str:
    # Traditional and Simplified spellings are the same title (乾杯 and 干杯).
    return normalize(to_simplified(title).replace("（", "(").replace("）", ")"))


def _words(name: str) -> List[str]:
    # Whole words, so "BTS" matches "BTS (防弹少年团)" but "IU" does not match "Julius".
    return [w for w in _NON_WORD.split(normalize(name)) if w]


def _contains_words(name: Sequence[str], part: Sequence[str]) -> bool:
    n = len(part)
    return any(list(name[i:i + n]) == list(part) for i in range(len(name) - n + 1))


def _has_latin(name: str) -> bool:
    return any("a" <= c <= "z" or "A" <= c <= "Z" for c in name)


def _written_differently(a: str, b: str) -> bool:
    return bool(a.strip()) and _has_latin(a) != _has_latin(b)


def pick(
    track: TrackMetadata,
    songs: Iterable[T],
    title: Callable[[T], str],
    duration_ms: Callable[[T], Optional[int]],
    artists: Callable[[T], List[str]],
) -> Optional[T]:
    """Searches also return live versions, remixes and covers, some within seconds of the original's length,
    so both the title and the duration must match. A matching artist is preferred. Artists are often listed under
    their native name (米津玄師 for "Kenshi Yonezu"), so a non-matching artist is still accepted, in search order,
    if it is written in a different script; a different name in the same script is another artist's song.
    """
    wanted_title = _normalize_title(track.track_name)
    candidates = [
        s for s in songs
        if _normalize_title(title(s)) == wanted_title
        and abs((duration_ms(s) or 0) - track.duration_ms) <= DURATION_TOLERANCE_MS
    ]
    artist_text = track.all_artists
    wanted_artists = [w for w in (_words(a) for a in artist_text.split(",")) if w]
    for song in candidates:
        for name in (_words(a) for a in artists(song)):
            if name and any(_contains_words(name, w) or _contains_words(w, name) for w in wanted_artists):
                return song
    for song in candidates:
        if any(_written_differently(a, artist_text) for a in artists(song)):
            return song
    return None
