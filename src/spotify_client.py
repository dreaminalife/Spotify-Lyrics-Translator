"""Spotify API client wrapper for playback and lyrics."""
from spotipy import Spotify
from spotipy.oauth2 import SpotifyOAuth
from syrics.api import Spotify as SyricsSpotify
import time
import random


class SpotifyClient:
    """Manages Spotify API connections for playback and lyrics."""
    
    def __init__(self, client_id, client_secret, redirect_uri, sp_dc_cookie):
        """Initialize Spotify API clients.
        
        Args:
            client_id: Spotify API client ID
            client_secret: Spotify API client secret
            redirect_uri: OAuth redirect URI
            sp_dc_cookie: sp_dc cookie for Syrics API
        """
        # Initialize Spotify API for playback (Spotipy)
        self.sp = Spotify(auth_manager=SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scope="user-read-playback-state user-read-currently-playing user-read-private user-read-email"
        ))
        
        # Initialize Syrics API for lyrics
        self.syrics_sp = SyricsSpotify(sp_dc_cookie)
        
        # Authenticate and print user info
        user = self.sp.current_user()
        print("Spotify authentication successful!")
        print(f"Logged in as: {user['display_name']}")
    
    def get_current_playback(self):
        """Get current playback information.
        
        Returns:
            tuple: (playback_info, position_ms) or (None, 0) if nothing is playing
        """
        try:
            current_playback = self.sp.current_playback()
            if current_playback and current_playback['is_playing']:
                return current_playback, current_playback['progress_ms']
            else:
                return None, 0
        except Exception as e:
            print(f"Error fetching current song playback position: {e}")
            return None, 0
    
    def get_lyrics(self, song_id, max_retries=3, initial_backoff=1.0):
        """Get lyrics for a song with retry mechanism.
        
        Args:
            song_id: Spotify track ID
            max_retries: Maximum number of retry attempts (default: 3)
            initial_backoff: Initial backoff time in seconds (default: 1.0)
            
        Returns:
            dict: Lyrics data from Syrics API or None if not available
        """
        retry_count = 0
        backoff = initial_backoff
        
        while retry_count <= max_retries:
            try:
                lyrics = self.syrics_sp.get_lyrics(song_id)
                return lyrics
            except Exception as e:
                retry_count += 1
                if retry_count > max_retries:
                    print(f"Error fetching lyrics after {max_retries} retries: {e}")
                    return None
                
                # Calculate exponential backoff with jitter
                jitter = random.uniform(0.8, 1.2)
                sleep_time = backoff * jitter
                
                print(f"Error fetching lyrics (attempt {retry_count}/{max_retries}): {e}")
                print(f"Retrying in {sleep_time:.2f} seconds...")
                
                time.sleep(sleep_time)
                backoff *= 2  # Exponential backoff
        
        return None

