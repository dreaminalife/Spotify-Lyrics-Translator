"""Lyrics translation and caching management."""
import pickle
import os
import threading
from typing import Optional, List

from .translation_clients import BaseTranslationClient, GoogleTranslateClient
from . import provided_translations
from .logging_config import get_logger

logger = get_logger(__name__)


class LyricsManager:
    """Manages lyrics translation and caching.

    The cache holds one entry per (song, lyrics source), as another source's lyrics can have the same line count
    but different lines. Each entry keeps the lyrics and their translations per (translator, target language).
    """

    def __init__(self, cache_file='lyrics_cache.pkl', max_cache_size=1000, translation_client: Optional[BaseTranslationClient] = None, target_language: str = 'en'):
        """Initialize the lyrics manager.

        Args:
            cache_file: Path to the cache file
            max_cache_size: Maximum number of (song, source) entries to cache
        """
        self.cache_file = cache_file
        self.max_cache_size = max_cache_size
        # The lyrics loader and translation threads both write the cache
        self._lock = threading.RLock()
        self.cache = self._load_cache()
        self.translation_client: BaseTranslationClient = translation_client or GoogleTranslateClient()
        self.target_language = target_language

    def _load_cache(self):
        """Load cache from file if it exists.

        Returns:
            dict: Cached lyrics translations
        """
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'rb') as f:
                    return pickle.load(f)
            except Exception as e:
                logger.error(f"Error loading cache: {e}")
                return {}
        return {}

    def save_cache(self):
        """Save cache to file."""
        with self._lock:
            try:
                with open(self.cache_file, 'wb') as f:
                    pickle.dump(self.cache, f)
            except Exception as e:
                logger.error(f"Error saving cache: {e}")

    @staticmethod
    def _key(song_id: str, source: str) -> str:
        # Entries from before per-source caching are keyed by the bare song id; they are never read and age out.
        return f"{song_id}|{source}"

    def translator_id(self) -> str:
        """Identifies the translator in cache keys: "google" or "openrouter:<model>"."""
        model = getattr(self.translation_client, 'model', None)
        return f"openrouter:{model}" if model else "google"

    def clear_cache(self, song_id: Optional[str] = None, source: Optional[str] = None):
        """Clear cached lyrics and translations.

        Args:
            song_id: If provided with source, only clear that source's lyrics for this track; otherwise clear all.
            source: Lyrics source name
        """
        with self._lock:
            try:
                if song_id and source:
                    self.cache.pop(self._key(song_id, source), None)
                else:
                    self.cache.clear()
                self.save_cache()
            except Exception as e:
                logger.error(f"Error clearing cache: {e}")

    def get_cached(self, song_id: str, source: str) -> Optional[dict]:
        """Cached lyrics of a source for a song, in the lyrics service's payload format, or None."""
        with self._lock:
            entry = self.cache.get(self._key(song_id, source))
            return entry.get('payload') if isinstance(entry, dict) else None

    def put_lyrics(self, song_id: str, payload: dict):
        """Cache lyrics (a lyrics service payload); drops translations of the lyrics they replace."""
        payload = {k: v for k, v in payload.items() if k != 'cached'}
        with self._lock:
            self.cache[self._key(song_id, payload.get('source', 'Unknown'))] = {'payload': payload, 'translations': {}}
            # Ensure cache size doesn't exceed limit
            while len(self.cache) > self.max_cache_size:
                self.cache.pop(next(iter(self.cache)))
            self.save_cache()

    def get_translation(self, song_id: str, source: str, line_count: int) -> Optional[dict]:
        """Cached translation by the current translator to the current target language, or None.

        Returns:
            dict: {'lines': [str], 'title': str, 'label': str}
        """
        with self._lock:
            entry = self.cache.get(self._key(song_id, source))
            if not isinstance(entry, dict):
                return None
            cached = entry.get('translations', {}).get(f"{self.translator_id()}|{self.target_language}")
        if cached and len(cached.get('lines', [])) == line_count:
            return cached
        return None

    def put_translation(self, song_id: str, source: str, translator_id: str, target_language: str, translation: dict):
        with self._lock:
            entry = self.cache.get(self._key(song_id, source))
            if not isinstance(entry, dict):
                return
            entry.setdefault('translations', {})[f"{translator_id}|{target_language}"] = translation
            self.save_cache()

    def provided_translation(self, lyrics_data: List[dict]) -> Optional[List[str]]:
        """The translation shipped with the lyrics, if it is in the target language."""
        if self.target_language != provided_translations.LANGUAGE:
            return None
        provided = [line.get('provided', '') for line in lyrics_data]
        return provided if any(p.strip() for p in provided) else None

    def translate_song_title(self, song_title: str) -> str:
        """Translate a song title using the current translation client.

        Args:
            song_title: Original song title

        Returns:
            str: Translated song title or original title if translation fails
        """
        if not song_title or not song_title.strip():
            return song_title

        try:
            # Use the translation client to translate the title
            translated_titles = self.translation_client.translate_lines(
                [song_title],
                source_lang=None,
                target_lang=self.target_language,
            )
            if translated_titles and len(translated_titles) > 0:
                return translated_titles[0]
        except Exception as e:
            logger.error(f"Error translating song title: {e}")

        # Return original title if translation fails
        return song_title

    def translate_lyrics(self, lyrics_data: List[dict], song_id: str, lyrics_source: str, song_title: str = None) -> dict:
        """Translate lyrics and cache the result. Runs on a worker thread; raises if translation fails.

        A translation shipped with the lyrics is used as is; the translator fills its gaps. Blank lines are not sent.

        Args:
            lyrics_data: List of lyric lines with startTimeMs, words and provided, in display order
            song_id: Spotify track ID for caching
            lyrics_source: Source name of the lyrics provider (e.g., "Spotify", "NetEase")
            song_title: Optional song title to translate

        Returns:
            dict: {'lines': [str] (one per lyrics line), 'title': str, 'label': str}
        """
        client = self.translation_client
        translator_id = self.translator_id()
        target_language = self.target_language

        provided = self.provided_translation(lyrics_data)
        missing = [
            i for i, line in enumerate(lyrics_data)
            if line['words'].strip() and not (provided and provided[i].strip())
        ]
        logger.info(f"Translating '{song_title}' with {translator_id} to {target_language}: {len(missing)} lines"
                    + (f" ({lyrics_source} provided the rest)" if provided else ""))

        lines = list(provided) if provided else [''] * len(lyrics_data)
        if missing:
            translated = client.translate_lines(
                [lyrics_data[i]['words'] for i in missing],
                source_lang=None,
                target_lang=target_language,
            )
            for i, text in zip(missing, translated):
                lines[i] = text

        name = client.get_source_name()
        translation = {
            'lines': lines,
            'title': self.translate_song_title(song_title) if song_title else song_title,
            'label': f"{lyrics_source} + {name}" if provided else name,
        }
        self.put_translation(song_id, lyrics_source, translator_id, target_language, translation)
        return translation

    @staticmethod
    def get_current_line(lyrics, position_ms):
        """Find the current lyric line based on playback position.

        Args:
            lyrics: List of lyric dictionaries with startTimeMs
            position_ms: Current playback position in milliseconds

        Returns:
            dict: Current lyric line or None if no lyrics
        """
        logger.debug(f"get_current_line: lyrics_length={len(lyrics) if lyrics else 0}, position_ms={position_ms}")
        if not lyrics:
            logger.debug("get_current_line: No lyrics available, returning None")
            return None

        current_line = None
        for lyric in lyrics:
            lyric_time = int(lyric['startTimeMs'])
            logger.debug(f"get_current_line: Checking lyric at {lyric_time}ms: '{lyric.get('words', '')[:50]}...'")
            if lyric_time <= position_ms:
                current_line = lyric
                logger.debug(f"get_current_line: Found current line at {lyric_time}ms")
            else:
                logger.debug(f"get_current_line: Lyric at {lyric_time}ms is in the future, breaking")
                break

        # If no current line found (we're before all lyrics), return the first lyric
        if current_line is None and lyrics:
            current_line = lyrics[0]
            logger.debug(f"get_current_line: No current line found, returning first upcoming lyric at {lyrics[0].get('startTimeMs')}ms")

        result = current_line
        if result is None:
            logger.debug("get_current_line: Returning None")
        else:
            logger.debug(f"get_current_line: Returning line at {result.get('startTimeMs')}ms: '{result.get('words', '')[:50]}...'")
        return current_line

    @staticmethod
    def ms_to_min_sec(ms):
        """Convert milliseconds to minutes:seconds format.

        Args:
            ms: Time in milliseconds

        Returns:
            str: Formatted time string (MM:SS)
        """
        ms = int(ms)
        minutes = ms // 60000
        seconds = (ms % 60000) // 1000
        return f"{minutes}:{seconds:02}"
