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
            scope="user-read-playback-state user-read-currently-playing user-read-private user-read-email user-modify-playback-state"
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
            # Prefer full playback state, but do not require is_playing
            current_playback = self.sp.current_playback()
            if current_playback and current_playback.get('item'):
                return current_playback, int(current_playback.get('progress_ms') or 0)

            # Fallback: some environments only return from currently_playing
            currently_playing = self.sp.currently_playing()
            if currently_playing and currently_playing.get('item'):
                return currently_playing, int(currently_playing.get('progress_ms') or 0)

            # Log device info to help diagnose "no active device" cases
            try:
                devices_resp = self.sp.devices()
                devices = devices_resp.get('devices', []) if devices_resp else []
                all_names = [d.get('name') for d in devices]
                active_names = [d.get('name') for d in devices if d.get('is_active')]
            except Exception as de:
                print(f"Error fetching devices: {de}")

            return None, 0
        except Exception as e:
            print(f"Error fetching current song playback position: {e}")
            return None, 0

    # Legacy method removed: retry logic is now centralized in LyricsService
    def get_lyrics(self, song_id):
        try:
            return self.syrics_sp.get_lyrics(song_id)
        except Exception as e:
            print(f"Error fetching lyrics: {e}")
            return None

    def get_current_track_metadata(self):
        """Return current track metadata (for lyrics providers) and track id.
        
        Returns:
            tuple: (track_metadata_dict, spotify_track_id) or (None, None)
        """
        try:
            # Try current_playback first
            current_playback = self.sp.current_playback()
            payload = current_playback if (current_playback and current_playback.get('item')) else None
            # Fallback to currently_playing
            if not payload:
                cp = self.sp.currently_playing()
                payload = cp if (cp and cp.get('item')) else None
            if not payload:
                return None, None
            item = payload['item']
            track_id = item.get('id')
            track_name = item.get('name') or ''
            artists = item.get('artists') or []
            artist_name = artists[0]['name'] if artists else ''
            album = item.get('album') or {}
            album_name = album.get('name') or ''
            duration_ms = int(item.get('duration_ms') or 0)
            meta = {
                'track_name': track_name,
                'artist_name': artist_name,
                'album_name': album_name,
                'duration_ms': duration_ms,
            }
            return meta, track_id
        except Exception as e:
            print(f"Error building current track metadata: {e}")
            return None, None

    def get_device_status(self):
        """Return available devices and the name of the active device (if any).
        
        Returns:
            dict: { 'devices': list, 'active_device': Optional[str] }
        """
        try:
            resp = self.sp.devices()
            devices = resp.get('devices', []) if resp else []
            active = next((d for d in devices if d.get('is_active')), None)
            return {
                'devices': devices,
                'active_device': active.get('name') if active else None,
            }
        except Exception as e:
            print(f"Error fetching device status: {e}")
            return { 'devices': [], 'active_device': None }

    def seek_to_position(self, position_ms: int) -> bool:
        """Seek to a specific position in the current track.
        
        Args:
            position_ms: Position in milliseconds to seek to
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            self.sp.seek_track(int(position_ms))
            return True
        except Exception as e:
            print(f"Error seeking to {position_ms}: {e}")
            return False

    def ensure_playing(self) -> bool:
        """Ensure playback is active (start if paused).
        
        Returns:
            bool: True if playback is active or was started, False otherwise
        """
        try:
            pb = self.sp.current_playback()
            if not pb:
                # No active device
                return False
            if not pb.get('is_playing'):
                self.sp.start_playback()
            return True
        except Exception as e:
            print(f"Error ensuring playback: {e}")
            return False

    def seek_and_play(self, position_ms: int) -> bool:
        """Seek to a position and ensure playback is active.

        Args:
            position_ms: Position in milliseconds to seek to

        Returns:
            bool: True if successful, False otherwise
        """
        ok = self.seek_to_position(position_ms)
        if not ok:
            return False
        # If paused, start playback
        self.ensure_playing()
        return True

    def play_pause(self) -> bool:
        """Toggle play/pause for current playback.

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            pb = self.sp.current_playback()
            if not pb:
                return False
            if pb.get('is_playing'):
                self.sp.pause_playback()
            else:
                self.sp.start_playback()
            return True
        except Exception as e:
            print(f"Error toggling play/pause: {e}")
            return False

    def next_track(self) -> bool:
        """Skip to the next track.

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            self.sp.next_track()
            return True
        except Exception as e:
            print(f"Error skipping to next track: {e}")
            return False

    def previous_track(self) -> bool:
        """Go to the previous track.

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            self.sp.previous_track()
            return True
        except Exception as e:
            print(f"Error going to previous track: {e}")
            return False

    def seek_forward(self, seconds: int = 10) -> bool:
        """Seek forward by specified number of seconds.

        Args:
            seconds: Number of seconds to seek forward (default: 10)

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            pb = self.sp.current_playback()
            if not pb or not pb.get('item'):
                return False

            current_pos = pb.get('progress_ms', 0)
            duration = pb['item'].get('duration_ms', 0)
            new_pos = min(current_pos + (seconds * 1000), duration)

            return self.seek_to_position(int(new_pos))
        except Exception as e:
            print(f"Error seeking forward {seconds}s: {e}")
            return False

    def seek_backward(self, seconds: int = 10) -> bool:
        """Seek backward by specified number of seconds.

        Args:
            seconds: Number of seconds to seek backward (default: 10)

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            pb = self.sp.current_playback()
            if not pb:
                return False

            current_pos = pb.get('progress_ms', 0)
            new_pos = max(current_pos - (seconds * 1000), 0)

            return self.seek_to_position(int(new_pos))
        except Exception as e:
            print(f"Error seeking backward {seconds}s: {e}")
            return False

    def get_playback_state(self):
        """Get current playback state information.

        Returns:
            dict: Playback state info or None if no active playback
        """
        try:
            pb = self.sp.current_playback()
            if not pb:
                return None
            return {
                'is_playing': pb.get('is_playing', False),
                'progress_ms': pb.get('progress_ms', 0),
                'item': pb.get('item')
            }
        except Exception as e:
            print(f"Error getting playback state: {e}")
            return None

