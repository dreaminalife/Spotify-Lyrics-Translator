from __future__ import annotations

from typing import Callable, Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor, TimeoutError
import time
import logging

from .lyrics_models import TrackMetadata, LyricsPayload
from .lyrics_providers import BaseLyricsProvider
from .native_names import NativeNameLookup

# The order sources are tried in unless the user changes it (same as the Android app)
DEFAULT_ORDER = ["NetEase", "QQ Music", "Kugou", "Spotify", "LRCLib", "Uta-Net"]

# Source name -> (attempts, timeout per attempt in seconds). Sources not listed get one attempt of
# CHINESE_SOURCE_TIMEOUT: NetEase, QQ Music and Kugou make up to 4 requests, each with its own HTTP timeout, and
# LRCLib up to 4 (with and without the album, by native names and by Spotify's).
ATTEMPT_POLICY = {
    "Spotify": (3, 0.5),
    # UtaNet handles its own retries internally for the search request
    "Uta-Net": (1, 18.0),
}
CHINESE_SOURCE_TIMEOUT = 15.0
# Delays between Spotify attempts
RETRY_DELAYS = [0.0, 0.15]


def resolve_order(order: Optional[List[str]], pinned: Optional[str], default_order: List[str] = DEFAULT_ORDER) -> List[str]:
    """The pinned source, then the user's order, then the rest of the default order; only known sources, each once."""
    resolved: List[str] = []
    for name in ([pinned] if pinned else []) + list(order or []) + list(default_order):
        if name in default_order and name not in resolved:
            resolved.append(name)
    return resolved


class LyricsService:
    """When a source first misses, the track's native names are looked up with native_names. If they differ from
    Spotify's, that source searches again with them, and every source after it searches them first, then Spotify's.
    Found lyrics tell native_names which artists sing in Japanese.
    """

    def __init__(self, providers: Dict[str, BaseLyricsProvider], native_names: Optional[NativeNameLookup] = None):
        self._providers = providers
        self._native_names = native_names

    def get_lyrics(
        self,
        track: TrackMetadata,
        spotify_track_id: Optional[str],
        order: List[str],
        cache_lookup: Optional[Callable[[str], Optional[dict]]] = None,
        is_stale: Optional[Callable[[], bool]] = None,
    ) -> Optional[dict]:
        """Lyrics from the first source in order that has them, checking each source's cache before asking it.

        Returns the payload dict with "cached" set when it came from the cache, or None. Stops early once
        is_stale() is true (the song changed or another source was picked).
        """
        track_info = f"'{track.track_name}' by '{track.artist_name}'"
        logging.info(f"Starting lyrics search for {track_info}, order: {', '.join(order)}")

        # A fresh executor per search, so a timed-out attempt of an abandoned search can't delay this one
        executor = ThreadPoolExecutor(max_workers=3)
        # The track under its native names (うっせぇわ for "Usseewa"), or itself if they are the same; None until known.
        native = self._native_names.cached(track) if self._native_names else None

        def native_for(name: str) -> Optional[TrackMetadata]:
            # Spotify finds the song by its id, so other names find nothing new.
            return native if native is not None and native != track and name != "Spotify" else None

        try:
            for name in order:
                if is_stale and is_stale():
                    logging.info(f"Lyrics search for {track_info} abandoned")
                    return None
                if cache_lookup:
                    cached = cache_lookup(name)
                    if cached:
                        logging.info(f"Using cached lyrics from {name} for {track_info}")
                        self._found(track, cached)
                        return {**cached, "cached": True}
                provider = self._providers.get(name)
                if provider is None:
                    continue
                tracks = [t for t in (native_for(name), track) if t is not None]
                payload = self._try_provider(executor, name, provider, tracks, spotify_track_id)
                if not payload and native is None and self._native_names:
                    native = self._native_names.look_up(track)
                    if is_stale and is_stale():
                        logging.info(f"Lyrics search for {track_info} abandoned")
                        return None
                    if native_for(name):
                        payload = self._try_provider(executor, name, provider, [native_for(name)], spotify_track_id)
                if payload:
                    logging.info(f"Successfully retrieved lyrics from {name} for {track_info} ({len(payload.lines)} lines)")
                    result = {**payload.to_api_dict(), "cached": False}
                    self._found(track, result)
                    return result
                logging.info(f"All attempts failed for provider {name}")
        finally:
            executor.shutdown(wait=False)

        logging.info(f"No lyrics found for {track_info} from any provider")
        return None

    def _found(self, track: TrackMetadata, result: dict):
        if self._native_names:
            self._native_names.found(track, [line.get("words") or "" for line in result["lyrics"]["lines"]])

    def _try_provider(self, executor, name, provider, tracks, spotify_track_id) -> Optional[LyricsPayload]:
        """Searches tracks (the same song under different names) in turn; an attempt's searches share its timeout."""
        def search() -> Optional[LyricsPayload]:
            for track in tracks:
                payload = provider.get_lyrics(track, spotify_track_id)
                if payload and payload.lines:
                    return payload
            return None

        attempts, timeout = ATTEMPT_POLICY.get(name, (1, CHINESE_SOURCE_TIMEOUT))
        for i in range(attempts):
            attempt_num = i + 1
            logging.debug(f"Provider {name} attempt {attempt_num}/{attempts} (timeout: {timeout}s)")
            fut = executor.submit(search)
            try:
                payload: Optional[LyricsPayload] = fut.result(timeout=timeout)
            except TimeoutError:
                logging.debug(f"Provider {name} attempt {attempt_num} timed out")
                payload = None
            except Exception as e:
                logging.info(f"Provider {name} attempt {attempt_num} failed: {e}")
                payload = None

            if payload and payload.lines:
                return payload

            if attempt_num < attempts and i < len(RETRY_DELAYS):
                logging.debug(f"Provider {name} attempt {attempt_num} failed, retrying in {RETRY_DELAYS[i]}s")
                time.sleep(RETRY_DELAYS[i])
        return None
