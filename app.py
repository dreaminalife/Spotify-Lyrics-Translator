import tkinter as tk
from tkinter import ttk
import threading
import logging
import sv_ttk

from src.spotify_client import SpotifyClient
from src.lyrics_manager import LyricsManager
from src.floating_window import FloatingLyricsWindow
from src.lyrics_models import TrackMetadata
from src.lyrics_providers import SyricsLyricsProvider, LRCLibLyricsProvider, UtaNetLyricsProvider
from src.lyrics_service import LyricsService
from src.settings_manager import read_secrets, validate_secrets
from src.translation_clients import GoogleTranslateClient, OpenRouterClient
from src.translation_settings import (
    read_translation_settings,
    save_translation_settings,
    read_models_config,
)
from src.settings_window import SettingsWindow
from src.font_manager import get_default_chinese_font

# Configure logging to show INFO level and above
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

# Initialize Spotify client via settings
spotify_client = None

# Initialize lyrics manager
lyrics_manager = LyricsManager()

# Lyrics providers and service (initialized after Spotify client)
lyrics_service = None

# Global state
current_song_id = None
current_lyrics = []
current_song_name = ""
language = ""
floating_window = None
lyrics_synced = True
last_current_line = None
current_lyrics_source = "Unknown"
current_translation_source = "Unknown"
selected_font = "Microsoft YaHei UI"  # Default font (will be updated after tkinter init)

def get_selected_font():
    """Get the currently selected font from settings."""
    global selected_font
    settings = read_translation_settings()
    font_from_settings = settings.get("selected_font", "Microsoft YaHei UI")

    # Try to get the proper default font if tkinter is available
    try:
        # Check if tkinter root exists
        import tkinter
        if tkinter._default_root:
            from src.font_manager import get_default_chinese_font
            if not font_from_settings or font_from_settings == "Microsoft YaHei UI":
                font_from_settings = get_default_chinese_font()
    except:
        # If tkinter is not ready, use the safe fallback
        pass

    selected_font = font_from_settings
    return selected_font

def get_font_settings():
    """Get the current main window font settings (name, size, bold)."""
    settings = read_translation_settings()
    font_name = settings.get("selected_font", "Microsoft YaHei UI")
    font_size = settings.get("font_size", 12)
    font_bold = settings.get("font_bold", True)

    # Try to get the proper default font if tkinter is available
    try:
        import tkinter
        if tkinter._default_root:
            from src.font_manager import get_default_chinese_font
            if not font_name or font_name == "Microsoft YaHei UI":
                font_name = get_default_chinese_font()
    except:
        pass

    return font_name, font_size, font_bold

def get_floating_font_settings():
    """Get the current floating window font settings (name, size, bold)."""
    settings = read_translation_settings()
    font_name = settings.get("floating_font", "Microsoft YaHei UI")
    font_size = settings.get("floating_font_size", 12)
    font_bold = settings.get("floating_font_bold", True)

    # Try to get the proper default font if tkinter is available
    try:
        import tkinter
        if tkinter._default_root:
            from src.font_manager import get_default_chinese_font
            if not font_name or font_name == "Microsoft YaHei UI":
                font_name = get_default_chinese_font()
    except:
        pass

    return font_name, font_size, font_bold

def apply_font_to_widget(widget, font_size=None, font_style=None):
    """Apply the selected font to a widget."""
    font_name, default_size, is_bold = get_font_settings()
    size = font_size if font_size is not None else default_size
    style = font_style if font_style is not None else ('bold' if is_bold else 'normal')
    widget.config(font=(font_name, size, style))


def init_spotify_client(settings):
    """Initialize the global Spotify client from provided settings dict."""
    global spotify_client
    try:
        spotify_client = SpotifyClient(
            client_id=settings.get("client_id", ""),
            client_secret=settings.get("client_secret", ""),
            redirect_uri=settings.get("redirect_uri", "http://127.0.0.1:8080"),
            sp_dc_cookie=settings.get("sp_dc_cookie", "")
        )
        try:
            status_label.config(text="Authenticated with Spotify")
        except Exception:
            pass
        # Initialize lyrics service now that spotify client exists
        global lyrics_service
        providers = [
            SyricsLyricsProvider(spotify_client.syrics_sp),
            LRCLibLyricsProvider("Lyrics-Translator/0.1 (https://github.com/)")
        ]
        # Add UtaNet provider as last fallback (search + log only for now)
        providers.append(UtaNetLyricsProvider())
        lyrics_service = LyricsService(providers)
    except Exception as e:
        print(f"Error initializing Spotify client: {e}")
        try:
            status_label.config(text="Authentication failed. Open Settings.")
        except Exception:
            pass


def init_translation_client():
    global current_translation_source
    settings = read_translation_settings()
    models_body = read_models_config()
    secrets = read_secrets()

    # Update the selected font
    get_selected_font()

    provider = settings.get("provider", "Google Translate")
    target_language = settings.get("target_language", "en")
    lyrics_manager.target_language = target_language

    if provider == "OpenRouter":
        api_key = secrets.get("openrouter_api_key", "")
        model = settings.get("selected_model", "openrouter/auto")
        prompt = settings.get("global_prompt", "")
        body = models_body.get(model, {})
        try:
            lyrics_manager.translation_client = OpenRouterClient(
                api_key=api_key,
                model=model,
                prompt_template=prompt,
                model_body=body,
            )
            current_translation_source = lyrics_manager.translation_client.get_source_name()
            try:
                status_label.config(text="Translation: OpenRouter ready")
            except Exception:
                pass
        except Exception as e:
            print(f"Error initializing OpenRouter client: {e}")
            lyrics_manager.translation_client = GoogleTranslateClient()
            current_translation_source = lyrics_manager.translation_client.get_source_name()
            try:
                status_label.config(text="Translation fallback: Google Translate")
            except Exception:
                pass
    else:
        lyrics_manager.translation_client = GoogleTranslateClient()
        current_translation_source = lyrics_manager.translation_client.get_source_name()
        try:
            status_label.config(text="Translation: Google Translate")
        except Exception:
            pass
    update_column_headers()


def open_settings_modal(prefill=None):
    """Open settings window, save to secrets.txt, and reinit client on save."""
    theme = {
        "bg": '#121212',
        "panel": '#181818',
        "label_fg": '#B3B3B3',
        "entry_bg": '#282828',
        "entry_fg": '#FFFFFF',
        "accent": '#1DB954',
        "accent_hover": '#1ED760',
        "accent_active": '#1AA34A',
        "button_fg": '#FFFFFF',
        "button_bg": '#282828',
        "button_fg_alt": '#121212',
        "button_bg_alt": '#B3B3B3',
    }

    def on_saved(values):
        init_spotify_client(values)
        init_translation_client()
        # Refresh UI with new font
        refresh_ui_font()
        # Update floating window fonts if it exists
        if floating_window and floating_window.is_open():
            font_name, font_size, is_bold = get_floating_font_settings()
            floating_window.update_font_settings(font_name, font_size, is_bold)
        # Force refresh lyrics after auth
        global current_song_id
        current_song_id = None
        try:
            status_label.config(text="Settings saved. Ready.")
        except Exception:
            pass

    SettingsWindow(root, on_saved=on_saved, theme=theme)


def ensure_settings_and_init():
    settings = read_secrets()
    ok, missing = validate_secrets(settings)
    if not ok:
        try:
            status_label.config(text="Missing settings. Please configure.")
        except Exception:
            pass
        root.after(0, lambda: open_settings_modal())
        return
    init_spotify_client(settings)

# Helper function to merge translated lyrics into current_lyrics
def merge_translations_into_current(translated_lyrics):
    """Merge translated lyrics into current_lyrics in place.

    Args:
        translated_lyrics: List of translated lyric dictionaries (or dict with 'lyrics' key for cache format)

    Returns:
        int: Number of lines updated
    """
    global current_lyrics

    # Handle new cache format: dict with 'lyrics' key
    if isinstance(translated_lyrics, dict) and 'lyrics' in translated_lyrics:
        translated_lyrics = translated_lyrics['lyrics']

    # Create lookup dict for current_lyrics by (startTimeMs, words) for efficient merging
    current_lookup = {(lyric['startTimeMs'], lyric['words']): lyric for lyric in current_lyrics}

    updated_count = 0
    for translated in translated_lyrics:
        key = (translated['startTimeMs'], translated['words'])
        if key in current_lookup:
            current_lookup[key]['translated'] = translated['translated']
            updated_count += 1
        else:
            # Try with type conversion for startTimeMs (string vs int)
            alt_key = None
            if isinstance(translated['startTimeMs'], str):
                try:
                    alt_key = (int(translated['startTimeMs']), translated['words'])
                except ValueError:
                    pass
            elif isinstance(translated['startTimeMs'], int):
                alt_key = (str(translated['startTimeMs']), translated['words'])

            if alt_key and alt_key in current_lookup:
                current_lookup[alt_key]['translated'] = translated['translated']
                updated_count += 1

    print(f"[DEBUG] merge_translations_into_current: Merged {updated_count} translated lines into current_lyrics")
    return updated_count

# Function to get the current song and playback position
def get_current_playback_position():
    if not spotify_client:
        return None, 0
    return spotify_client.get_current_playback()

# Function to update the Treeview and the current time label
def update_display():
    global current_song_id, floating_window, lyrics_synced, last_current_line
    current_song, current_position = get_current_playback_position()

    # Get playback state to determine update behavior
    is_playing = current_song.get('is_playing', False) if current_song else False

    # Only clear and re-highlight current line when song is playing
    if is_playing:
        # Clear previous current line highlighting
        for item in tree.get_children():
            tags = list(tree.item(item)['tags'])
            if 'current' in tags:
                tags.remove('current')
                tree.item(item, tags=tags)

    if current_song:
        song_id = current_song['item']['id']
        if song_id != current_song_id:
            current_song_id = song_id
            global last_current_line
            last_current_line = None  # Clear last current line when switching songs
            update_lyrics()

        # Update current time label with modern format
        current_time_label.config(text=lyrics_manager.ms_to_min_sec(current_position))
        
        # Update current song label
        song_name = current_song['item']['name']
        artist_name = current_song['item']['artists'][0]['name'] if current_song['item']['artists'] else "Unknown Artist"
        
        # Check if we have a cached translation for this song title
        original_title, translated_title = lyrics_manager.get_cached_title(song_id)
        if original_title and translated_title and original_title != translated_title:
            display_title = f"{original_title} ({translated_title})"
            current_song_var.set(f"{display_title} • {artist_name}")
        else:
            current_song_var.set(f"{song_name} • {artist_name}")

        # Update main window treeview selection and highlight current line (only when synced and playing)
        last_index = None
        if lyrics_synced and is_playing:
            for item in tree.get_children():
                item_data = tree.item(item)
                time_str = item_data['values'][0]
                try:
                    start_time = int(time_str.split(":")[0]) * 60000 + int(time_str.split(":")[1]) * 1000
                except Exception:
                    start_time = -1
                if start_time <= current_position:
                    last_index = item
                else:
                    break

            if last_index:
                # Highlight the current line
                tags = list(tree.item(last_index)['tags'])
                if 'current' not in tags:
                    tags.append('current')
                    tree.item(last_index, tags=tags)

                tree.selection_set(last_index)
                tree.see(last_index)

        # Update floating window if it exists
        if floating_window and floating_window.is_open():
            if lyrics_synced and is_playing:
                # Use the same source as the main window (Treeview) for current line
                if last_index:
                    item_values = tree.item(last_index)['values']
                    current_line = {
                        'words': item_values[1],
                        'translated': item_values[2]
                    }
                    last_current_line = current_line  # Update last current line
                else:
                    current_line = None
                    last_current_line = None
                song_duration = current_song['item']['duration_ms'] if current_song and 'item' in current_song else 0
                
                # Get translated title for floating window
                original_title, translated_title = lyrics_manager.get_cached_title(song_id)
                floating_window.update_lyrics(current_song_name, artist_name, current_line, current_position, song_duration, translated_title)
            elif not is_playing and lyrics_synced:
                # When paused, keep displaying the last current line
                song_duration = current_song['item']['duration_ms'] if current_song and 'item' in current_song else 0
                
                # Get translated title for floating window
                original_title, translated_title = lyrics_manager.get_cached_title(song_id)
                floating_window.update_lyrics(current_song_name, artist_name, last_current_line, current_position, song_duration, translated_title)
            else:
                # Unsynced or no song: clear text and avoid progression
                last_current_line = None
                floating_window.update_lyrics(current_song_name, artist_name, None, 0, 0)
        
    else:
        # No song playing or not authenticated yet
        current_time_label.config(text="0:00")
        # Try to provide a more helpful hint based on device status
        hint_shown = False
        try:
            if spotify_client:
                status = spotify_client.get_device_status()
                devices = status.get('devices', []) if status else []
                active = status.get('active_device') if status else None
                if devices and not active:
                    current_song_var.set("No active device")
                    try:
                        status_label.config(text="Open Spotify and press Play, or select a device")
                    except Exception:
                        pass
                    hint_shown = True
                elif not devices:
                    current_song_var.set("No Spotify devices found")
                    try:
                        status_label.config(text="Open Spotify on any device and play a track")
                    except Exception:
                        pass
                    hint_shown = True
        except Exception:
            hint_shown = False
        if not hint_shown:
            current_song_var.set("No song playing")

    # Schedule next update with different intervals based on playback state
    # Poll more frequently when playing (500ms), less frequently when paused (3000ms)
    poll_interval = 500 if (current_song and current_song.get('is_playing', False)) else 3000
    root.after(poll_interval, update_display)

# Function to update the lyrics in the Treeview
def update_column_headers():
    """Update column headers to display source information."""
    try:
        lyrics_header = f"  Original Lyrics"
        if current_lyrics_source != "Unknown":
            lyrics_header += f" ({current_lyrics_source})"
        tree.heading("Original Lyrics", text=lyrics_header)

        translation_header = f"  Translated Lyrics"
        if current_translation_source != "Unknown":
            translation_header += f" ({current_translation_source})"
        tree.heading("Translated Lyrics", text=translation_header)
    except Exception:
        pass

def update_lyrics():
    global current_song_id, current_lyrics, current_song_name, language, lyrics_synced
    global current_lyrics_source, current_translation_source

    try:
        # Get current playback
        current_playback, _ = get_current_playback_position()
        if not current_playback or not current_playback['item']:
            print("[DEBUG] update_lyrics: No current playback or item, returning")
            # Show a friendly hint if possible
            try:
                if spotify_client:
                    status = spotify_client.get_device_status()
                    devices = status.get('devices', []) if status else []
                    active = status.get('active_device') if status else None
                    if devices and not active:
                        status_label.config(text="No active device. Press Play or select a device")
                    elif not devices:
                        status_label.config(text="No Spotify devices found. Open Spotify and play a track")
                    else:
                        status_label.config(text="No song playing")
                else:
                    status_label.config(text="No song playing")
            except Exception:
                status_label.config(text="No song playing")
            return

        song_id = current_playback['item']['id']
        song_name = current_playback['item']['name']
        artist_name = current_playback['item']['artists'][0]['name'] if current_playback['item']['artists'] else "Unknown Artist"
        current_song_name = song_name
        print(f"[DEBUG] update_lyrics: Processing song '{song_name}' with ID {song_id}")
        
        # Update window title with song info
        root.title(f"{song_name} • {artist_name} - Spotify Lyrics Translator")
        
        # Check cache first - avoid expensive API calls if we already have lyrics
        cached = lyrics_manager.get_cached_lyrics(song_id)
        if cached:
            print(f"[DEBUG] update_lyrics: Using cached lyrics for song {song_id}, length={len(cached.get('lyrics', []))}")
            # Update status
            status_label.config(text="Loading cached lyrics...")

            # Extract cached data
            lyrics_data = cached.get('lyrics', [])
            lyrics_synced = cached.get('synced', True)  # Get actual synced status from cache
            current_lyrics_source = cached.get('lyrics_source', 'Unknown')
            current_translation_source = cached.get('translation_source', 'Unknown')

            # Clear existing treeview items
            tree.delete(*tree.get_children())

            if lyrics_data:
                # Initialize current_lyrics from cached data (already includes translations)
                current_lyrics = [
                    {'startTimeMs': lyric['startTimeMs'], 'words': lyric['words'], 'translated': lyric.get('translated', '')}
                    for lyric in lyrics_data
                ]
                print(f"[DEBUG] update_lyrics: Loaded {len(current_lyrics)} cached lines")

                # Update column headers with source info
                update_column_headers()

                # Populate Treeview with cached lyrics (including translations)
                for i, lyric in enumerate(current_lyrics):
                    tag = 'evenrow' if i % 2 == 0 else 'oddrow'
                    time_text = lyrics_manager.ms_to_min_sec(lyric['startTimeMs']) if lyrics_synced else ""
                    tree.insert("", "end", values=(time_text, lyric['words'], lyric['translated']), tags=(tag,))

                # Toggle synced banner and Time heading/column
                try:
                    if lyrics_synced:
                        if getattr(unsynced_banner_label, '_packed', False):
                            unsynced_banner_label.pack_forget()
                            unsynced_banner_label._packed = False
                        tree.heading("Time", text="  Time")
                    else:
                        unsynced_banner_label.config(text="Lyrics are not time-synced.")
                        if not getattr(unsynced_banner_label, '_packed', False):
                            # Place banner to the right of refresh button
                            unsynced_banner_label.pack(side=tk.LEFT, padx=(20, 0))
                            unsynced_banner_label._packed = True
                        tree.heading("Time", text="")
                except Exception:
                    pass

                # Update song title with cached translation if available
                original_title, translated_title = lyrics_manager.get_cached_title(song_id)
                if original_title and translated_title and original_title != translated_title:
                    display_title = f"{original_title} ({translated_title})"
                    current_song_var.set(f"{display_title} • {artist_name}")
                    root.title(f"{display_title} • {artist_name} - Spotify Lyrics Translator")

                status_label.config(text="Ready")
                adjust_column_widths()
            else:
                print("[DEBUG] update_lyrics: Cached lyrics data is empty")
                status_label.config(text="Cached lyrics data corrupted")
        else:
            # No cached lyrics - fetch fresh lyrics
            print(f"[DEBUG] update_lyrics: No cached lyrics, fetching fresh lyrics for song {song_id}")

            # Update status
            status_label.config(text="Loading lyrics...")

            # Get lyrics via service with fast retries and fallback
            lyrics = None
            if spotify_client and lyrics_service:
                meta_dict, _ = spotify_client.get_current_track_metadata()
                if meta_dict:
                    track_meta = TrackMetadata(
                        track_name=meta_dict['track_name'],
                        artist_name=meta_dict['artist_name'],
                        album_name=meta_dict['album_name'],
                        duration_ms=meta_dict['duration_ms'],
                    )
                    lyrics = lyrics_service.get_lyrics(track_meta, song_id)
            lyrics_data = lyrics['lyrics']['lines'] if lyrics and 'lyrics' in lyrics and 'lines' in lyrics['lyrics'] else None
            lyrics_synced = (lyrics and lyrics.get('lyrics', {}).get('synced', True))
            # Extract lyrics source from response
            current_lyrics_source = lyrics.get('source', 'Unknown') if lyrics else 'Unknown'
            print(f"[DEBUG] update_lyrics: Retrieved lyrics data, has_lyrics={lyrics_data is not None}, lyrics_count={len(lyrics_data) if lyrics_data else 0}, source={current_lyrics_source}")

            # Clear existing treeview items
            tree.delete(*tree.get_children())

            if lyrics_data:
                # Detect the language of the first line of lyrics
                detected_lang = lyrics['lyrics']['language']
                language = detected_lang
                # Update column headers with source info
                update_column_headers()

                # Initialize current_lyrics as single source of truth with original lyrics
                current_lyrics = [
                    {'startTimeMs': lyric['startTimeMs'], 'words': lyric['words'], 'translated': ''}
                    for lyric in lyrics_data
                ]
                print(f"[DEBUG] update_lyrics: Initialized current_lyrics with {len(current_lyrics)} lines")

                # Populate Treeview from current_lyrics with alternating row colors
                for i, lyric in enumerate(current_lyrics):
                    tag = 'evenrow' if i % 2 == 0 else 'oddrow'
                    time_text = lyrics_manager.ms_to_min_sec(lyric['startTimeMs']) if lyrics_synced else ""
                    tree.insert("", "end", values=(time_text, lyric['words'], lyric['translated']), tags=(tag,))

                # Ensure the UI renders original lyrics immediately before translation starts
                try:
                    root.update_idletasks()
                except Exception:
                    pass

                # Toggle unsynced banner and Time heading/column
                try:
                    if lyrics_synced:
                        if getattr(unsynced_banner_label, '_packed', False):
                            unsynced_banner_label.pack_forget()
                            unsynced_banner_label._packed = False
                        tree.heading("Time", text="  Time")
                    else:
                        unsynced_banner_label.config(text="Lyrics are not time-synced.")
                        if not getattr(unsynced_banner_label, '_packed', False):
                            # Place banner to the right of refresh button
                            unsynced_banner_label.pack(side=tk.LEFT, padx=(20, 0))
                            unsynced_banner_label._packed = True
                        tree.heading("Time", text="")
                except Exception:
                    pass

                print(f"[DEBUG] update_lyrics: Starting translation for song {song_id}")
                status_label.config(text="Translating lyrics...")
                # Translate in background thread
                def translate_callback(translated):
                    print(f"[DEBUG] translate_callback: Translation completed for song {song_id}, received {len(translated)} lines")
                    # Update translation source from current client
                    global current_translation_source
                    try:
                        current_translation_source = lyrics_manager.translation_client.get_source_name()
                    except Exception:
                        current_translation_source = "Unknown"
                    update_column_headers()
                    status_label.config(text="Translation complete")
                    merge_translations_into_current(translated)

                    # Update song title with translation if available
                    original_title, translated_title = lyrics_manager.get_cached_title(song_id)
                    if original_title and translated_title and original_title != translated_title:
                        display_title = f"{original_title} ({translated_title})"
                        current_song_var.set(f"{display_title} • {artist_name}")
                        root.title(f"{display_title} • {artist_name} - Spotify Lyrics Translator")

                    # Schedule UI update on main thread
                    root.after(0, update_translations)
                    # Reset status after a delay
                    root.after(3000, lambda: status_label.config(text="Ready"))

                threading.Thread(
                    target=lyrics_manager.translate_lyrics,
                    args=(lyrics_data, song_id, current_lyrics_source, translate_callback, song_name, lyrics_synced)
                ).start()
            elif lyrics is None:
                # Could be an auth error or API error; handled elsewhere
                current_lyrics_source = "unknown"
                current_translation_source = "unknown"
                status_label.config(text="No lyrics found")
                update_column_headers()
            else:
                print("[DEBUG] update_lyrics: No lyrics data available for this song")
                status_label.config(text="No lyrics available")
                tree.insert("", "end", values=("0:00", "(No lyrics found)", ""), tags=('evenrow',))
                current_lyrics = []
        
        adjust_column_widths()
    except Exception as e:
        print(f"Error updating lyrics: {e}")
        status_label.config(text="Error loading lyrics")

# Function to update the Treeview with translated lyrics from current_lyrics
def update_translations():
    global current_lyrics, lyrics_synced

    # Rebuild the translated lyrics column from current_lyrics
    updated_count = 0
    for i, item in enumerate(tree.get_children()):
        item_data = tree.item(item)
        if lyrics_synced:
            start_time = item_data['values'][0]
            original_lyrics = item_data['values'][1]
            # Find matching lyric in current_lyrics
            for lyric in current_lyrics:
                if lyrics_manager.ms_to_min_sec(lyric['startTimeMs']) == start_time and lyric['words'] == original_lyrics:
                    current_values = list(tree.item(item)['values'])
                    current_values[2] = lyric['translated']
                    tree.item(item, values=current_values)
                    updated_count += 1
                    if lyric['translated']:
                        _highlight_translation(item)
                    break
        else:
            # Unsynced: update by row index
            if i < len(current_lyrics):
                lyric = current_lyrics[i]
                current_values = list(tree.item(item)['values'])
                current_values[2] = lyric.get('translated', '')
                tree.item(item, values=current_values)
                if lyric.get('translated'):
                    updated_count += 1
                    _highlight_translation(item)

    print(f"[DEBUG] update_translations: Updated {updated_count} translated lyrics in Treeview")

    # Log first few updated lines for verification
    if current_lyrics and len(current_lyrics) > 0:
        first_few = current_lyrics[:3]
        for i, lyric in enumerate(first_few):
            translated = (lyric.get('translated') or '')[:50]

    adjust_column_widths()

def _highlight_translation(item, step=0):
    """Add a subtle highlight animation for newly translated lines.

    Args:
        item: Treeview item to highlight
        step: Current step in the animation
    """
    try:
        # Check if item still exists
        tree.item(item)
    except:
        # Item no longer exists, stop the animation
        return

    if step < 5:
        # Get current values
        current_values = list(tree.item(item)['values'])
        
        # Alternate between normal and highlighted color by temporarily changing the tag
        if step % 2 == 0:
            # Add highlight tag
            tags = list(tree.item(item)['tags'])
            if 'highlight' not in tags:
                tags.append('highlight')
                tree.item(item, tags=tags)
        else:
            # Remove highlight tag
            tags = list(tree.item(item)['tags'])
            if 'highlight' in tags:
                tags.remove('highlight')
                tree.item(item, tags=tags)
        
        root.after(100, lambda: _highlight_translation(item, step + 1))
    else:
        # Ensure highlight tag is removed
        try:
            tags = list(tree.item(item)['tags'])
            if 'highlight' in tags:
                tags.remove('highlight')
                tree.item(item, tags=tags)
        except:
            # Item no longer exists, skip cleanup
            pass

# Function to find the longest line length in original and translated lyrics
def find_longest_line_lengths():
    max_original_length = 0
    max_translated_length = 0
    line_count = 0

    for item in tree.get_children():
        line_count += 1
        original_length = len(tree.item(item)['values'][1])
        translated_length = len(tree.item(item)['values'][2])
        if original_length > max_original_length:
            max_original_length = original_length
        if translated_length > max_translated_length:
            max_translated_length = translated_length

    return max_original_length, max_translated_length, line_count

# Function to adjust the column widths based on the content
def adjust_column_widths():
    max_original_length, max_translated_length, line_count = find_longest_line_lengths()

    root.update_idletasks()

    # Get current window width and available content area
    current_width = root.winfo_width()
    if current_width < 1:  # Window not yet rendered
        current_width = 1200  # Default width

    # Account for padding and scrollbar
    available_width = current_width - 60  # Remove padding

    # Use proportional sizing for consistent column spacing
    if lyrics_synced:
        # Time column gets 15% of available width, min 80px, max 120px
        time_width = max(80, min(120, int(available_width * 0.15)))
        # Original and translated lyrics split the remaining 85% equally
        lyrics_width = int((available_width - time_width) * 0.5)
    else:
        # No time column for unsynced lyrics
        time_width = 0
        # Split available width equally between original and translated columns
        lyrics_width = int(available_width * 0.5)

    # Ensure minimum widths for readability
    min_lyrics_width = 200
    lyrics_width = max(lyrics_width, min_lyrics_width)

    # Calculate content-based preferred widths for comparison
    orig_content_width = max(max_original_length * 12, 250)
    trans_content_width = max(max_translated_length * 12, 250)

    # Adjust for different languages (character width multipliers)
    if language == "ja":
        orig_content_width = max(max_original_length * 18, 250)
    elif language == "ru":
        orig_content_width = max(max_original_length * 14, 250)
        trans_content_width = max(max_translated_length * 15, 250)
    else:
        # Default multiplier for other languages
        orig_content_width = max(max_original_length * 12, 250)
        trans_content_width = max(max_translated_length * 12, 250)

    # Use the larger of proportional width or content width, but cap at reasonable maximums
    orig_length = max(lyrics_width, min(orig_content_width, 600))
    trans_length = max(lyrics_width, min(trans_content_width, 600))

    # Calculate required total width
    total_content_width = time_width + orig_length + trans_length + 60

    # Calculate height based on line count
    height = min(line_count * 35 + 200, 800)  # Cap height at 800px

    # Update column widths with consistent proportions
    tree.column("Time", width=time_width, minwidth=time_width)
    tree.column("Original Lyrics", width=orig_length, minwidth=min_lyrics_width)
    tree.column("Translated Lyrics", width=trans_length, minwidth=min_lyrics_width)

    # Only resize window if content genuinely requires more space
    if total_content_width > current_width:
        root.geometry(f"{total_content_width}x{height}")
    else:
        # Keep current width but update height if needed
        root.geometry(f"{current_width}x{height}")

# Function to toggle floating window
def toggle_floating_window():
    global floating_window

    if floating_window and floating_window.is_open():
        floating_window.close()
        floating_window = None
        toggle_button.config(text="Show Floating Lyrics")
    else:
        # Get floating window font settings
        font_name, font_size, is_bold = get_floating_font_settings()
        floating_window = FloatingLyricsWindow(root, font_name, font_size, is_bold)
        toggle_button.config(text="Hide Floating Lyrics")

def refresh_ui_font():
    """Refresh all main window UI elements with the currently selected font settings."""
    font_name, font_size, is_bold = get_font_settings()
    font_style = 'bold' if is_bold else 'normal'

    # Update all UI elements with the new font settings
    unsynced_banner_label.config(font=(font_name, 11, font_style))
    icon_label.config(font=(font_name, 24, 'bold'))  # Icon stays bold
    app_title.config(font=(font_name, 20, 'bold'))  # Title stays bold
    current_song_label.config(font=(font_name, 14, font_style))
    current_time_label.config(font=(font_name, 12, font_style))
    toggle_button.config(font=(font_name, 12, font_style))
    refresh_button.config(font=(font_name, 12, font_style))
    status_label.config(font=(font_name, 11, font_style))

    # Update Treeview styles
    style.configure(
        "Spotify.Treeview",
        background=SPOTIFY_DARK,
        foreground=SPOTIFY_WHITE,
        fieldbackground=SPOTIFY_DARK,
        borderwidth=0,
        font=(font_name, font_size, font_style),
        rowheight=max(35, font_size + 20)  # Adjust row height based on font size
    )

    style.configure(
        "Spotify.Treeview.Heading",
        background=SPOTIFY_GRAY,
        foreground=SPOTIFY_WHITE,
        font=(font_name, font_size, font_style),
        borderwidth=0,
        relief=tk.FLAT
    )

    # Note: Floating window fonts are handled separately and not updated here

# Create main application window
root = tk.Tk()
root.title("Spotify Lyrics Translator")
root.configure(bg='#121212')  # Spotify's dark background

# Menubar with Settings
menubar = tk.Menu(root)
file_menu = tk.Menu(menubar, tearoff=0)
file_menu.add_command(label="Settings...", command=lambda: open_settings_modal())
file_menu.add_separator()
file_menu.add_command(label="Exit", command=root.quit)
menubar.add_cascade(label="File", menu=file_menu)
root.config(menu=menubar)

# Set window icon and initial size
root.geometry("1200x700")
root.minsize(800, 600)

# Apply theme
style = ttk.Style(root)
style.theme_use("default")

# Define Spotify-inspired color scheme
SPOTIFY_BLACK = '#121212'
SPOTIFY_DARKER = '#000000'
SPOTIFY_DARK = '#181818'
SPOTIFY_GRAY = '#282828'
SPOTIFY_LIGHT_GRAY = '#B3B3B3'
SPOTIFY_WHITE = '#FFFFFF'
SPOTIFY_GREEN = '#1DB954'
SPOTIFY_GREEN_HOVER = '#1ED760'
SPOTIFY_GREEN_ACTIVE = '#1AA34A'

# Configure root background
root.configure(bg=SPOTIFY_BLACK)

# Create header frame with app branding
header_frame = tk.Frame(root, bg=SPOTIFY_DARK, height=80)
header_frame.pack(fill=tk.X, padx=0, pady=0)
header_frame.pack_propagate(False)  # Prevent frame from shrinking

# App title and logo area
title_frame = tk.Frame(header_frame, bg=SPOTIFY_DARK)
title_frame.pack(side=tk.LEFT, padx=20, pady=15)

# Spotify-like icon (using text representation)
icon_label = tk.Label(
    title_frame,
    text="♪",
    font=(get_selected_font(), 24, 'bold'),
    fg=SPOTIFY_GREEN,
    bg=SPOTIFY_DARK
)
icon_label.pack(side=tk.LEFT, padx=(0, 10))

app_title = tk.Label(
    title_frame,
    text="Lyrics Translator",
    font=(get_selected_font(), 20, 'bold'),
    fg=SPOTIFY_WHITE,
    bg=SPOTIFY_DARK
)
app_title.pack(side=tk.LEFT)

# Current song info frame
song_info_frame = tk.Frame(header_frame, bg=SPOTIFY_DARK)
song_info_frame.pack(side=tk.RIGHT, padx=20, pady=15)

# Current song label as read-only Entry to allow selection/copy
current_song_var = tk.StringVar(value="No song playing")
current_song_label = tk.Entry(
    song_info_frame,
    textvariable=current_song_var,
    font=(get_selected_font(), 14, 'bold'),
    fg=SPOTIFY_LIGHT_GRAY,
    bg=SPOTIFY_DARK,
    readonlybackground=SPOTIFY_DARK,
    relief=tk.FLAT,
    state="readonly",
    borderwidth=0,
    highlightthickness=0,
    insertbackground=SPOTIFY_LIGHT_GRAY
)
current_song_label.pack()

# Current time label with modern styling
current_time_label = tk.Label(
    song_info_frame,
    text="0:00",
    font=(get_selected_font(), 12, 'bold'),
    fg=SPOTIFY_GREEN,
    bg=SPOTIFY_DARK
)
current_time_label.pack()

# Control panel frame
control_frame = tk.Frame(root, bg=SPOTIFY_BLACK, height=60)
control_frame.pack(fill=tk.X, padx=20, pady=10)

# Unsynced banner (initially hidden)
unsynced_banner_label = tk.Label(
    control_frame,
    text="Lyrics are not time-synced.",
    fg=SPOTIFY_LIGHT_GRAY,
    bg=SPOTIFY_BLACK,
    font=(get_selected_font(), 11, 'bold')
)
unsynced_banner_label._packed = False

# Toggle floating lyrics button with modern styling
toggle_button = tk.Button(
    control_frame,
    text="Show Floating Lyrics",
    font=(get_selected_font(), 12, 'bold'),
    fg=SPOTIFY_WHITE,
    bg=SPOTIFY_GREEN,
    activebackground=SPOTIFY_GREEN_ACTIVE,
    activeforeground=SPOTIFY_WHITE,
    bd=0,
    padx=20,
    pady=8,
    relief=tk.FLAT,
    cursor="hand2",
    command=toggle_floating_window
)
toggle_button.pack(side=tk.LEFT, padx=(0, 10))

# Add hover effect for button
def on_button_enter(e):
    toggle_button.config(bg=SPOTIFY_GREEN_HOVER)

def on_button_leave(e):
    toggle_button.config(bg=SPOTIFY_GREEN)

toggle_button.bind("<Enter>", on_button_enter)
toggle_button.bind("<Leave>", on_button_leave)

# Add a refresh button to manually refresh lyrics
def refresh_lyrics():
    """Manually refresh the current song's lyrics."""
    global current_song_id
    # Clear cache for the currently playing song (if any)
    current_playback, _ = get_current_playback_position()
    song_id = None
    try:
        if current_playback and current_playback.get('item'):
            song_id = current_playback['item']['id']
    except Exception:
        song_id = None
    if song_id:
        lyrics_manager.clear_cache(song_id)
        try:
            status_label.config(text="Cache cleared. Refreshing lyrics...")
        except Exception:
            pass
    update_lyrics()

refresh_button = tk.Button(
    control_frame,
    text="Refresh Lyrics",
    font=(get_selected_font(), 12, 'bold'),
    fg=SPOTIFY_WHITE,
    bg=SPOTIFY_GRAY,
    activebackground=SPOTIFY_LIGHT_GRAY,
    activeforeground=SPOTIFY_BLACK,
    bd=0,
    padx=20,
    pady=8,
    relief=tk.FLAT,
    cursor="hand2",
    command=refresh_lyrics
)
refresh_button.pack(side=tk.LEFT, padx=(0, 10))

# Add hover effect for refresh button
def on_refresh_enter(e):
    refresh_button.config(bg=SPOTIFY_LIGHT_GRAY, fg=SPOTIFY_BLACK)

def on_refresh_leave(e):
    refresh_button.config(bg=SPOTIFY_GRAY, fg=SPOTIFY_WHITE)

refresh_button.bind("<Enter>", on_refresh_enter)
refresh_button.bind("<Leave>", on_refresh_leave)

# Add a status label to show translation status
status_label = tk.Label(
    control_frame,
    text="Ready",
    font=(get_selected_font(), 11, 'bold'),
    fg=SPOTIFY_LIGHT_GRAY,
    bg=SPOTIFY_BLACK
)
status_label.pack(side=tk.RIGHT, padx=(10, 0))

# Create a frame to hold the Treeview and Scrollbar with modern styling
frame = tk.Frame(root, bg=SPOTIFY_BLACK)
frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 20))

# Create and configure the treeview widget with modern styling
tree = ttk.Treeview(
    frame, 
    columns=("Time", "Original Lyrics", "Translated Lyrics"), 
    show="headings",
    style="Spotify.Treeview",
    selectmode="extended"
)

# Configure Treeview style with Spotify-inspired colors
style.configure(
    "Spotify.Treeview",
    background=SPOTIFY_DARK,
    foreground=SPOTIFY_WHITE,
    fieldbackground=SPOTIFY_DARK,
    borderwidth=0,
    font=(get_selected_font(), 12, 'bold'),
    rowheight=35
)

# Configure Treeview heading style
style.configure(
    "Spotify.Treeview.Heading",
    background=SPOTIFY_GRAY,
    foreground=SPOTIFY_WHITE,
    font=(get_selected_font(), 12, 'bold'),
    borderwidth=0,
    relief=tk.FLAT
)

# Configure selected row style with better highlighting
style.map(
    "Spotify.Treeview",
    background=[('selected', SPOTIFY_GREEN)],
    foreground=[('selected', SPOTIFY_WHITE)]
)

# Configure headings with proper padding
tree.heading("Time", text="  Time", anchor='w')
tree.heading("Original Lyrics", text="  Original Lyrics", anchor='w')
tree.heading("Translated Lyrics", text="  Translated Lyrics", anchor='w')
# Initial column headers will be updated by update_column_headers() when sources are known

# Configure columns with better proportions
tree.column("Time", width=100, minwidth=80, anchor='w')
tree.column("Original Lyrics", width=450, minwidth=200, anchor='w')
tree.column("Translated Lyrics", width=450, minwidth=200, anchor='w')

# Add alternating row colors for better readability
tree.tag_configure('oddrow', background=SPOTIFY_DARK)
tree.tag_configure('evenrow', background=SPOTIFY_GRAY)

# Add a special tag for the current playing line
tree.tag_configure('current', background=SPOTIFY_GREEN, foreground=SPOTIFY_WHITE)

# Add a tag for translated text to make it stand out
tree.tag_configure('translated', foreground=SPOTIFY_WHITE)

# Add a tag for highlighting newly translated lines
tree.tag_configure('highlight', background=SPOTIFY_GREEN, foreground=SPOTIFY_WHITE)

# Create custom scrollbar with modern styling
scrollbar = ttk.Scrollbar(
    frame,
    orient="vertical",
    command=tree.yview,
    style="Spotify.Vertical.TScrollbar"
)

# Configure scrollbar style
style.configure(
    "Spotify.Vertical.TScrollbar",
    background=SPOTIFY_GRAY,
    troughcolor=SPOTIFY_DARK,
    bordercolor=SPOTIFY_DARK,
    arrowcolor=SPOTIFY_LIGHT_GRAY,
    darkcolor=SPOTIFY_GRAY,
    lightcolor=SPOTIFY_GRAY
)

# Connect the scrollbar to the treeview
tree.configure(yscrollcommand=scrollbar.set)

# Pack the treeview and scrollbar correctly
tree.pack(side='left', fill=tk.BOTH, expand=True)
scrollbar.pack(side='right', fill='y')

# Enable Ctrl+C to copy selected Treeview rows to clipboard (tab-separated)
def _copy_tree_selection(event=None):
    items = tree.selection()
    if not items:
        return "break"
    lines = []
    for iid in items:
        vals = tree.item(iid).get('values', [])
        lines.append("\t".join(str(v) for v in vals if v is not None))
    try:
        root.clipboard_clear()
        root.clipboard_append("\n".join(lines))
    except Exception:
        pass
    return "break"

tree.bind("<Control-c>", _copy_tree_selection)
tree.bind("<Control-Insert>", _copy_tree_selection)

# Enable double-click to seek to lyric timestamp (only for synced lyrics)
def _on_lyric_double_click(event=None):
    """Handle clicking on a lyric line to seek to that timestamp."""
    global lyrics_synced
    if not lyrics_synced:
        try:
            status_label.config(text="Click-to-seek works only with synced lyrics")
        except Exception:
            pass
        return
    item_id = tree.identify_row(event.y)
    if not item_id:
        return
    vals = tree.item(item_id).get('values', [])
    if not vals or not vals[0]:  # Time column empty on unsynced
        return
    try:
        mm, ss = map(int, str(vals[0]).split(':'))
        pos_ms = (mm * 60 + ss) * 1000
    except Exception:
        return
    # Attempt seek + play
    if spotify_client and spotify_client.seek_and_play(pos_ms):
        try:
            status_label.config(text=f"Jumped to {vals[0]}")
        except Exception:
            pass
    else:
        # Optional: check device status for better hint
        try:
            ds = spotify_client.get_device_status() if spotify_client else None
            if ds and ds.get('devices') and not ds.get('active_device'):
                status_label.config(text="No active device. Open Spotify and press Play once.")
            else:
                status_label.config(text="Could not seek. Check Spotify device and permissions.")
        except Exception:
            pass

tree.bind("<Double-Button-1>", _on_lyric_double_click)

# Initialize settings and client
ensure_settings_and_init()
init_translation_client()

# Update font after tkinter is initialized
selected_font = get_selected_font()
refresh_ui_font()

# Ensure we have the proper default font now that tkinter is ready
def initialize_font_settings():
    """Initialize font settings after tkinter is ready."""
    try:
        from src.font_manager import get_default_chinese_font
        settings = read_translation_settings()
        current_font = settings.get("selected_font", "Microsoft YaHei UI")

        # If we have the fallback font, update to the proper default
        if current_font == "Microsoft YaHei UI":
            proper_default = get_default_chinese_font()
            if proper_default != current_font:
                settings["selected_font"] = proper_default
                from src.translation_settings import save_translation_settings
                save_translation_settings(settings)
                global selected_font
                selected_font = proper_default
                refresh_ui_font()
    except Exception as e:
        print(f"Warning: Could not initialize font settings: {e}")

initialize_font_settings()

# Start the update loop
root.after(500, update_display)

# Start the application
root.mainloop()
