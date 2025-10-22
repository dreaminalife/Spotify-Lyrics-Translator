"""Lyrics translation and caching management."""
import pickle
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from deep_translator import GoogleTranslator


class LyricsManager:
    """Manages lyrics translation and caching."""
    
    def __init__(self, cache_file='lyrics_cache.pkl', max_cache_size=1000):
        """Initialize the lyrics manager.
        
        Args:
            cache_file: Path to the cache file
            max_cache_size: Maximum number of songs to cache
        """
        self.cache_file = cache_file
        self.max_cache_size = max_cache_size
        self.cache = self._load_cache()
    
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
    
    def get_cached_lyrics(self, song_id):
        """Get cached translated lyrics for a song.
        
        Args:
            song_id: Spotify track ID
            
        Returns:
            list: Cached translated lyrics or None if not in cache
        """
        cached = self.cache.get(song_id)
        if cached:
            try:
                cached.sort(key=lambda x: int(x['startTimeMs']))
            except Exception as e:
                print(f"[DEBUG] get_cached_lyrics: Sort failed: {e}")
        return cached
    
    def translate_lyrics(self, lyrics_data, song_id, callback=None):
        """Translate lyrics using multithreading.
        
        Args:
            lyrics_data: List of lyric lines with startTimeMs and words
            song_id: Spotify track ID for caching
            callback: Optional callback function to call with results
            
        Returns:
            list: Translated lyrics with original and translated text
        """
        translator = GoogleTranslator(source='auto', target='en')
        
        def translate_line(line):
            """Translate a single lyric line."""
            original_text = line['words']
            try:
                translated_text = translator.translate(original_text)
            except Exception as e:
                print(f"Error translating '{original_text}': {e}")
                translated_text = original_text
            return {
                'startTimeMs': line['startTimeMs'],
                'words': original_text,
                'translated': translated_text
            }
        
        # Translate lines in parallel
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(translate_line, line) for line in lyrics_data]
            translated_lyrics = [future.result() for future in as_completed(futures)]
        
        # Sort by start time to maintain order
        translated_lyrics.sort(key=lambda x: int(x['startTimeMs']))
        
        # Store in cache
        self.cache[song_id] = translated_lyrics
        
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

