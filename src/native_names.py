"""Finds the names a song has in its own language, for sources that don't know Spotify's.

Spotify shows many Japanese songs under English or romanized names ("Usseewa" by Ado), while NetEase, QQ Music,
Kugou and Uta-Net know them only by their native ones (うっせぇわ). NativeNameLookup finds the native names and
caches them per track, also when they are Spotify's own, so each track is looked up once. Failed lookups are not
cached, so they are retried the next time the track plays.

The Japan store writes foreign artists in katakana (テイラー・スウィフト for Taylor Swift), a name the other
sources don't use, so a katakana-only artist counts only for a Japanese song: one with a kana title, or by an
artist whose lyrics were found in Japanese before, such as ヨルシカ (Yorushika).
"""
from __future__ import annotations

import dataclasses
import json
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from typing import Callable, List, NamedTuple, Optional

from .logging_config import get_logger
from .lyrics_language import _HAN
from .lyrics_models import TrackMetadata
from .song_matcher import normalize

logger = get_logger(__name__)

TIME_LIMIT_S = 10.0
# A quarter of the lines: J-pop mixes in a lot of English, while Chinese and English lyrics have no kana.
MIN_KANA_SHARE = 0.25

_HIRAGANA = "ぁ-ゖゝ-ゟ"
# Without the prolonged sound mark and middle dot, which are shared with Chinese text
_KANA_CHARS = f"{_HIRAGANA}ァ-ヺヽ-ヿㇰ-ㇿ㋐-㋾㌀-㍗ｦ-ｯｱ-ﾝ"
_KANA = re.compile(f"[{_KANA_CHARS}]")
_KANJI_OR_HIRAGANA = re.compile(f"[{_HAN}{_HIRAGANA}]")
_NATIVE_SCRIPT = re.compile(f"[{_HAN}{_KANA_CHARS}ᄀ-ᇿㄱ-ㆎ가-힣]")


class NativeNames(NamedTuple):
    """A song's title and artist as written in its own language."""
    title: str
    artist: str


def _same(a: str, b: str) -> bool:
    return normalize(a) == normalize(b)


def _in_japanese(lines: List[str]) -> bool:
    lettered = [line for line in lines if any(c.isalpha() for c in line)]
    return bool(lettered) and sum(1 for line in lettered if _KANA.search(line)) >= len(lettered) * MIN_KANA_SHARE


class NativeNameLookup:
    def __init__(
        self,
        find: Callable[[TrackMetadata], Optional[NativeNames]],
        cache_file: str = 'native_names_cache.json',
        max_cache_size: int = 10000,
    ):
        """find returns None if the song isn't found and raises if the lookup fails."""
        self._find = find
        self._cache_file = cache_file
        self._max_cache_size = max_cache_size
        # Lyrics loader threads of earlier songs may still be running
        self._lock = threading.Lock()
        data = self._load()
        self._names = data.get('names', {})
        self._japanese_artists = set(data.get('japanese_artists', []))

    def _load(self) -> dict:
        if os.path.exists(self._cache_file):
            try:
                with open(self._cache_file, encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading native names: {e}")
        return {}

    def _save(self):
        try:
            with open(self._cache_file, 'w', encoding='utf-8') as f:
                json.dump({'names': self._names, 'japanese_artists': sorted(self._japanese_artists)}, f, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error saving native names: {e}")

    def cached(self, track: TrackMetadata) -> Optional[TrackMetadata]:
        """track under its native names, or track itself if they are the same; None if it was never looked up."""
        names = self._names.get(track.key)
        return self._renamed(track, NativeNames(*names)) if names else None

    def look_up(self, track: TrackMetadata) -> TrackMetadata:
        """track under its native names, or track itself if they are the same or can't be found."""
        if _NATIVE_SCRIPT.search(track.track_name) and _NATIVE_SCRIPT.search(track.all_artists):
            return track
        # Songs are matched by length too: without it nothing matches, and that would be cached as "same names".
        if track.duration_ms <= 0:
            return track
        executor = ThreadPoolExecutor(max_workers=1)
        try:
            names = executor.submit(self._find, track).result(timeout=TIME_LIMIT_S)
            names = names or NativeNames(track.track_name, track.all_artists)
        except TimeoutError:
            logger.warning(f"Native names: no answer within {TIME_LIMIT_S:.0f} s")
            return track
        except Exception as e:
            logger.warning(f"Native names lookup failed for '{track.track_name}': {e}")
            return track
        finally:
            executor.shutdown(wait=False)
        with self._lock:
            self._names[track.key] = list(names)
            while len(self._names) > self._max_cache_size:
                self._names.pop(next(iter(self._names)))
            self._save()
        return self._renamed(track, names)

    def found(self, track: TrackMetadata, lines: List[str]):
        """Notes track's artists as Japanese if the lyrics lines found for it are in Japanese."""
        artist = normalize(track.all_artists)
        if artist in self._japanese_artists or not _in_japanese(lines):
            return
        logger.debug(f"'{track.all_artists}' sings in Japanese")
        with self._lock:
            self._japanese_artists.add(artist)
            self._save()

    def _renamed(self, track: TrackMetadata, names: NativeNames) -> TrackMetadata:
        new_artist = not _same(names.artist, track.all_artists) and bool(
            _KANJI_OR_HIRAGANA.search(names.artist)
            or _KANA.search(track.track_name)
            or normalize(track.all_artists) in self._japanese_artists
        )
        if _same(names.title, track.track_name) and not new_artist:
            return track
        # Spotify's album is dropped: it is in Spotify's language too, and LRCLib would require it to match.
        return dataclasses.replace(
            track, track_name=names.title, artist_name=names.artist, album_name="", artist_names=[names.artist],
        )
