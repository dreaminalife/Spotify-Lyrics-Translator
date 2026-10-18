from __future__ import annotations

from typing import Callable, Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor, TimeoutError
import time
import logging

from .lyrics_models import TrackMetadata, LyricsPayload
from .lyrics_providers import BaseLyricsProvider

# The order sources are tried in unless the user changes it (same as the Android app)
DEFAULT_ORDER = ["NetEase", "QQ Music", "Kugou", "Spotify", "LRCLib", "Uta-Net"]

# Source name -> (attempts, timeout per attempt in seconds). Sources not listed get one attempt of
# CHINESE_SOURCE_TIMEOUT: NetEase, QQ Music and Kugou make up to 4 requests, each with its own HTTP timeout.
ATTEMPT_POLICY = {
    "Spotify": (3, 0.5),
    "LRCLib": (1, 0.9),
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
    def __init__(self, providers: Dict[str, BaseLyricsProvider]):
        self._providers = providers

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
        try:
            for name in order:
                if is_stale and is_stale():
                    logging.info(f"Lyrics search for {track_info} abandoned")
                    return None
                if cache_lookup:
                    cached = cache_lookup(name)
                    if cached:
                        logging.info(f"Using cached lyrics from {name} for {track_info}")
                        return {**cached, "cached": True}
                provider = self._providers.get(name)
                if provider is None:
                    continue
                payload = self._try_provider(executor, name, provider, track, spotify_track_id)
                if payload and payload.lines:
                    logging.info(f"Successfully retrieved lyrics from {name} for {track_info} ({len(payload.lines)} lines)")
                    return {**payload.to_api_dict(), "cached": False}
                logging.info(f"All attempts failed for provider {name}")
        finally:
            executor.shutdown(wait=False)

        logging.info(f"No lyrics found for {track_info} from any provider")
        return None

    def _try_provider(self, executor, name, provider, track, spotify_track_id) -> Optional[LyricsPayload]:
        attempts, timeout = ATTEMPT_POLICY.get(name, (1, CHINESE_SOURCE_TIMEOUT))
        for i in range(attempts):
            attempt_num = i + 1
            logging.debug(f"Provider {name} attempt {attempt_num}/{attempts} (timeout: {timeout}s)")
            fut = executor.submit(provider.get_lyrics, track, spotify_track_id)
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
