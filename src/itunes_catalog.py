"""Apple's public iTunes Search API, used for names only: it has no lyrics.

The US and Japan stores share track ids but name songs differently ("Usseewa" and うっせぇわ, "Kenshi Yonezu" and
米津玄師), so the playing track is matched in the US store, then looked up in the Japan store. Apple allows about
20 calls a minute.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import requests

from . import song_matcher
from .logging_config import get_logger
from .lyrics_models import TrackMetadata
from .native_names import NativeNames

logger = get_logger(__name__)

HTTP_TIMEOUT = 5.0


def _get(url: str, params: Dict[str, Any]) -> Any:
    resp = requests.get(url, params=params, timeout=HTTP_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def native_names(track: TrackMetadata) -> Optional[NativeNames]:
    """Returns None if the US store has no matching song. Raises on network/parse errors."""
    songs = parse_results(_get(
        "https://itunes.apple.com/search",
        {"term": f"{track.track_name} {track.all_artists}", "entity": "song", "limit": 10, "country": "US"},
    ))
    song = pick_song(track, songs)
    if song is None:
        logger.debug(f"iTunes: no match among {len(songs)} results: "
                     + ", ".join(f"'{s.get('trackName')}' ({s.get('trackTimeMillis')} ms)" for s in songs))
        return None
    results = parse_results(_get("https://itunes.apple.com/lookup", {"id": song["trackId"], "country": "JP"}))
    if not results:
        return None
    names = names_of(results[0])
    logger.debug(f"iTunes: native names of '{track.track_name}' by '{track.all_artists}': '{names.title}' by '{names.artist}'")
    return names


def parse_results(data: dict) -> List[dict]:
    """Album and artist results come too; only songs are kept."""
    return [r for r in data.get("results") or [] if r.get("trackId") is not None and r.get("trackName") is not None]


def pick_song(track: TrackMetadata, songs: List[dict]) -> Optional[dict]:
    return song_matcher.pick(
        track, songs,
        lambda s: s.get("trackName") or "",
        lambda s: s.get("trackTimeMillis"),
        lambda s: [s["artistName"]] if s.get("artistName") else [],
    )


def names_of(song: dict) -> NativeNames:
    return NativeNames(song.get("trackName") or "", song.get("artistName") or "")
