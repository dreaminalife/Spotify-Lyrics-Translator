"""Lyrics translation and caching management."""
import pickle
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, List

from .translation_clients import BaseTranslationClient, GoogleTranslateClient


class LyricsManager:
    """Manages lyrics translation and caching."""
    
    def __init__(self, cache_file='lyrics_cache.pkl', max_cache_size=1000, translation_client: Optional[BaseTranslationClient] = None, target_language: str = 'en'):
        """Initialize the lyrics manager.
        
        Args:
            cache_file: Path to the cache file
            max_cache_size: Maximum number of songs to cache
        """
        self.cache_file = cache_file
        self.max_cache_size = max_cache_size
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
                print(f"Error loading cache: {e}")
                return {}
        return {}
    
    def save_cache(self):
        """Save cache to file."""
        try:
            with open(self.cache_file, 'wb') as f:
                pickle.dump(self.cache, f)
        except Exception as e:
            print(f"Error saving cache: {e}")
    
    def clear_cache(self, song_id: Optional[str] = None):
        """Clear cached translations.
        
        Args:
            song_id: If provided, only clear this track's cache; otherwise clear all.
        """
        try:
            if song_id:
                if song_id in self.cache:
                    del self.cache[song_id]
            else:
                self.cache.clear()
            self.save_cache()
        except Exception as e:
            print(f"Error clearing cache: {e}")
    
    def get_cached_lyrics(self, song_id):
        """Get cached translated lyrics for a song.
        
        Args:
            song_id: Spotify track ID
            
        Returns:
            dict: Cache entry with 'lyrics', 'lyrics_source', 'translation_source', 
                  'original_title', and 'translated_title' keys,
                  or None if not in cache. For backward compatibility, old format (list) is
                  converted to new format with 'Unknown' sources.
        """
        cached = self.cache.get(song_id)
        if cached:
            # Handle backward compatibility: old cache format was just a list
            if isinstance(cached, list):
                # Convert old format to new format
                try:
                    cached.sort(key=lambda x: int(x['startTimeMs']))
                except Exception as e:
                    print(f"[DEBUG] get_cached_lyrics: Sort failed: {e}")
                return {
                    'lyrics': cached,
                    'lyrics_source': 'Unknown',
                    'translation_source': 'Unknown',
                    'original_title': None,
                    'translated_title': None,
                    'synced': True  # Default to True for backward compatibility
                }
            # New format: dict with lyrics, lyrics_source, translation_source, and title info
            elif isinstance(cached, dict):
                lyrics = cached.get('lyrics', [])
                try:
                    lyrics.sort(key=lambda x: int(x['startTimeMs']))
                except Exception as e:
                    print(f"[DEBUG] get_cached_lyrics: Sort failed: {e}")
                return {
                    'lyrics': lyrics,
                    'lyrics_source': cached.get('lyrics_source', 'Unknown'),
                    'translation_source': cached.get('translation_source', 'Unknown'),
                    'original_title': cached.get('original_title'),
                    'translated_title': cached.get('translated_title'),
                    'synced': cached.get('synced', True)  # Get synced status from cache
                }
        return None
    
    def translate_song_title(self, song_title: str, song_id: str) -> str:
        """Translate a song title using the current translation client.
        
        Args:
            song_title: Original song title
            song_id: Spotify track ID for caching
            
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
            print(f"Error translating song title: {e}")
            
        # Return original title if translation fails
        return song_title
    
    def update_cache_with_title(self, song_id: str, original_title: str, translated_title: str):
        """Update the cache entry for a song with translated title information.
        
        Args:
            song_id: Spotify track ID
            original_title: Original song title
            translated_title: Translated song title
        """
        if song_id in self.cache:
            self.cache[song_id]['original_title'] = original_title
            self.cache[song_id]['translated_title'] = translated_title
            self.save_cache()
        else:
            # Create a new cache entry with just title info if lyrics aren't cached yet
            self.cache[song_id] = {
                'original_title': original_title,
                'translated_title': translated_title,
                'lyrics': [],
                'lyrics_source': 'Unknown',
                'translation_source': 'Unknown',
                'synced': True  # Default to True for title-only entries
            }
            self.save_cache()
    
    def get_cached_title(self, song_id: str) -> tuple:
        """Get cached translated title for a song.
        
        Args:
            song_id: Spotify track ID
            
        Returns:
            tuple: (original_title, translated_title) or (None, None) if not in cache
        """
        cached = self.cache.get(song_id)
        if cached and 'original_title' in cached and 'translated_title' in cached:
            return cached.get('original_title'), cached.get('translated_title')
        return None, None

    def translate_lyrics(self, lyrics_data, song_id, lyrics_source: str = "Unknown", callback=None, song_title: str = None, synced: bool = True):
        """Translate lyrics using multithreading.
        
        Args:
            lyrics_data: List of lyric lines with startTimeMs and words
            song_id: Spotify track ID for caching
            lyrics_source: Source name of the lyrics provider (e.g., "Spotify", "LRCLib")
            callback: Optional callback function to call with results
            song_title: Optional song title to translate
            
        Returns:
            list: Translated lyrics with original and translated text
        """
        # Prepare ordered list of lines
        ordered = sorted(lyrics_data, key=lambda x: int(x['startTimeMs']))
        original_lines: List[str] = [line['words'] for line in ordered]

        try:
            translated_lines = self.translation_client.translate_lines(
                original_lines,
                source_lang=None,
                target_lang=self.target_language,
            )
        except Exception as e:
            print(f"Error translating lyrics via client: {e}")
            # Fallback: keep originals on error
            translated_lines = original_lines

        # Get translation source name
        translation_source = "Unknown"
        try:
            translation_source = self.translation_client.get_source_name()
        except Exception as e:
            print(f"Error getting translation source name: {e}")

        # Translate song title if provided
        translated_title = None
        if song_title:
            translated_title = self.translate_song_title(song_title, song_id)

        # Merge into lyric dicts
        translated_lyrics = []
        for src, translated_text in zip(ordered, translated_lines):
            translated_lyrics.append({
                'startTimeMs': src['startTimeMs'],
                'words': src['words'],
                'translated': translated_text,
            })
        
        # Already ordered
        
        # Store in cache with source info, title info, and synced status
        cache_entry = {
            'lyrics': translated_lyrics,
            'lyrics_source': lyrics_source,
            'translation_source': translation_source,
            'synced': synced
        }
        
        # Add title info if available
        if song_title and translated_title:
            cache_entry['original_title'] = song_title
            cache_entry['translated_title'] = translated_title
        
        self.cache[song_id] = cache_entry
        
        # Ensure cache size doesn't exceed limit
        if len(self.cache) > self.max_cache_size:
            self.cache.pop(next(iter(self.cache)))
        
        self.save_cache()
        
        # Call callback if provided
        if callback:
            callback(translated_lyrics)
        
        return translated_lyrics
    
    @staticmethod
    def get_current_line(lyrics, position_ms):
        """Find the current lyric line based on playback position.

        Args:
            lyrics: List of lyric dictionaries with startTimeMs
            position_ms: Current playback position in milliseconds

        Returns:
            dict: Current lyric line or None if no lyrics
        """
        print(f"[DEBUG] get_current_line: lyrics_length={len(lyrics) if lyrics else 0}, position_ms={position_ms}")
        if not lyrics:
            print(f"[DEBUG] get_current_line: No lyrics available, returning None")
            return None

        current_line = None
        for lyric in lyrics:
            lyric_time = int(lyric['startTimeMs'])
            print(f"[DEBUG] get_current_line: Checking lyric at {lyric_time}ms: '{lyric.get('words', '')[:50]}...'")
            if lyric_time <= position_ms:
                current_line = lyric
                print(f"[DEBUG] get_current_line: Found current line at {lyric_time}ms")
            else:
                print(f"[DEBUG] get_current_line: Lyric at {lyric_time}ms is in the future, breaking")
                break

        # If no current line found (we're before all lyrics), return the first lyric
        if current_line is None and lyrics:
            current_line = lyrics[0]
            print(f"[DEBUG] get_current_line: No current line found, returning first upcoming lyric at {lyrics[0].get('startTimeMs')}ms")

        result = current_line
        if result is None:
            print(f"[DEBUG] get_current_line: Returning None")
        else:
            print(f"[DEBUG] get_current_line: Returning line at {result.get('startTimeMs')}ms: '{result.get('words', '')[:50]}...'")
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

