from __future__ import annotations

from typing import List, Optional, Callable
from concurrent.futures import ThreadPoolExecutor, TimeoutError
import time
import logging

from .lyrics_models import TrackMetadata, LyricsPayload
from .lyrics_providers import BaseLyricsProvider


class LyricsService:
    def __init__(self, providers: List[BaseLyricsProvider]):
        self._providers = providers
        self._executor = ThreadPoolExecutor(max_workers=2)

    def get_lyrics(
        self,
        track: TrackMetadata,
        spotify_track_id: Optional[str] = None,
        per_attempt_timeout_syrics: float = 0.5,
        per_attempt_timeout_lrclib: float = 0.9,
    ) -> Optional[dict]:
        # Retry policy: initial + 2 retries (total 3 attempts) per provider
        delays = [0.0, 0.15]  # between attempts

        track_info = f"'{track.track_name}' by '{track.artist_name}'"
        logging.info(f"Starting lyrics search for {track_info}")

        for provider in self._providers:
            provider_name = provider.__class__.__name__
            logging.info(f"Trying provider: {provider_name} for {track_info}")

            attempts = 1 + len(delays)
            for i in range(attempts):
                attempt_num = i + 1
                timeout = per_attempt_timeout_syrics if 'Syrics' in provider.__class__.__name__ else per_attempt_timeout_lrclib
                logging.debug(f"Provider {provider_name} attempt {attempt_num}/{attempts} (timeout: {timeout}s)")

                fut = self._executor.submit(provider.get_lyrics, track, spotify_track_id)
                try:
                    payload: Optional[LyricsPayload] = fut.result(timeout=timeout)
                except TimeoutError:
                    logging.debug(f"Provider {provider_name} attempt {attempt_num} timed out")
                    payload = None
                except Exception as e:
                    logging.debug(f"Provider {provider_name} attempt {attempt_num} failed: {e}")
                    payload = None

                if payload and payload.lines:
                    logging.info(f"Successfully retrieved lyrics from {provider_name} for {track_info} ({len(payload.lines)} lines)")
                    return payload.to_api_dict()

                if i < len(delays):
                    logging.debug(f"Provider {provider_name} attempt {attempt_num} failed, retrying in {delays[i]}s")
                    time.sleep(delays[i])

            logging.info(f"All attempts failed for provider {provider_name}")

        logging.info(f"No lyrics found for {track_info} from any provider")
        return None


