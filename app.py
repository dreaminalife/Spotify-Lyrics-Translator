import tkinter as tk
from tkinter import ttk
import threading
import time
import bisect
import sv_ttk

from src.spotify_client import SpotifyClient
from src.lyrics_manager import LyricsManager
from src.floating_window import FloatingLyricsWindow
from src.lyrics_models import TrackMetadata
from src.lyrics_providers import SyricsLyricsProvider, LRCLibLyricsProvider, UtaNetLyricsProvider
from src.chinese_lyrics_providers import NetEaseLyricsProvider, QQMusicLyricsProvider, KugouLyricsProvider
from src.lyrics_service import LyricsService, DEFAULT_ORDER, resolve_order
from src import lyrics_language
from src.settings_manager import read_secrets, validate_secrets
from src.translation_clients import GoogleTranslateClient, OpenRouterClient
from src.translation_settings import (
    read_translation_settings,
    save_translation_settings,
    read_models_config,
    get_theme_colors,
    TARGET_LANGUAGES,
)
from src.settings_window import SettingsWindow
from src.font_manager import get_default_chinese_font
from src.logging_config import setup_logging, get_logger

# Setup logging
setup_logging()
logger = get_logger(__name__)

# Initialize Spotify client via settings
spotify_client = None

# Initialize lyrics manager
lyrics_manager = LyricsManager()

# Lyrics providers and service (initialized after Spotify client)
lyrics_service = None

# Theme colors
theme_colors = get_theme_colors()

# Global state
current_song_id = None
current_lyrics = []
current_song_name = ""
language = ""
floating_window = None
lyrics_synced = True
current_lyrics_source = "Unknown"
current_translation_source = "Unknown"
selected_font = "Microsoft YaHei UI"  # Default font (will be updated after tkinter init)
current_highlighted_item = None
user_scroll_lock_until = 0.0
lyrics_tree_items = []
lyrics_timecodes = []
# Bumped on each lyrics load; results of an older load (another song, another source picked) are dropped
load_generation = 0
current_translated_title = None

# Playback polling cache/state
playback_cache = {
    'payload': None,
    'position_ms': 0,
    'last_update': 0.0,
}
playback_lock = threading.Lock()
playback_polling_thread = None
playback_polling_stop = threading.Event()


def _update_playback_cache(playback, position):
    """Store the latest playback payload and position with a timestamp."""
    now = time.monotonic()
    with playback_lock:
        playback_cache['payload'] = playback
        playback_cache['position_ms'] = int(position or 0)
        playback_cache['last_update'] = now


def _playback_polling_loop():
    """Continuously refresh cached playback state in the background."""
    while not playback_polling_stop.is_set():
        client = spotify_client
        if not client:
            playback_polling_stop.wait(1.5)
            continue

        try:
            playback, position = client.get_current_playback()
        except Exception as exc:
            logger.debug(f"Playback polling failed: {exc}")
            playback = None
            position = 0

        _update_playback_cache(playback, position)

        is_playing = playback.get('is_playing', False) if playback else False
        interval = 0.5 if is_playing else 3.0
        playback_polling_stop.wait(interval)


def start_playback_polling():
    """Start the playback polling thread if it is not already running."""
    global playback_polling_thread

    if playback_polling_thread and playback_polling_thread.is_alive():
        return

    playback_polling_stop.clear()
    playback_polling_thread = threading.Thread(
        target=_playback_polling_loop,
        name="PlaybackPoller",
        daemon=True,
    )
    playback_polling_thread.start()

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
            NetEaseLyricsProvider(),
            QQMusicLyricsProvider(),
            KugouLyricsProvider(),
            SyricsLyricsProvider(spotify_client.syrics_sp),
            LRCLibLyricsProvider("Lyrics-Translator/0.1 (https://github.com/)"),
            UtaNetLyricsProvider(),
        ]
        # Tried in the order from settings (see resolve_order)
        lyrics_service = LyricsService({p.NAME: p for p in providers})
        start_playback_polling()
    except Exception as e:
        logger.error(f"Error initializing Spotify client: {e}")
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
            logger.error(f"Error initializing OpenRouter client: {e}")
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
        # Refresh UI with new font and theme colors
        refresh_ui_font()
        refresh_theme_colors()
        # Update floating window if it exists
        if floating_window and floating_window.is_open():
            font_name, font_size, is_bold = get_floating_font_settings()
            floating_window.update_font_settings(font_name, font_size, is_bold)
            floating_window.apply_colors()
        update_source_picker()
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


def track_key(item):
    """Identifies a track in the cache: its Spotify ID, or for local files, which have none, its artists, title and length."""
    if item.get('id'):
        return item['id']
    artists = ", ".join(a.get('name') or '' for a in (item.get('artists') or []))
    return f"local:{artists}|{item.get('name') or ''}|{int(item.get('duration_ms') or 0) // 1000}".lower()

# Function to get the current song and playback position
def get_current_playback_position():
    with playback_lock:
        cached_payload = playback_cache['payload']
        base_position = playback_cache['position_ms']
        last_update = playback_cache['last_update']

    if not cached_payload:
        return None, 0

    position_ms = int(base_position or 0)
    is_playing = cached_payload.get('is_playing', False)

    if is_playing and last_update:
        elapsed_ms = int(max(0.0, (time.monotonic() - last_update)) * 1000)
        item = cached_payload.get('item') or {}
        duration_ms = int(item.get('duration_ms') or 0)

        if duration_ms:
            position_ms = min(position_ms + elapsed_ms, duration_ms)
        else:
            position_ms = max(0, position_ms + elapsed_ms)

    return cached_payload, position_ms

# Function to update the Treeview and the current time label
def update_display():
    global current_song_id, floating_window, lyrics_synced
    global current_highlighted_item, user_scroll_lock_until
    current_song, current_position = get_current_playback_position()

    # Get playback state to determine update behavior
    is_playing = current_song.get('is_playing', False) if current_song else False

    if current_song:
        song_id = track_key(current_song['item'])
        if song_id != current_song_id:
            current_song_id = song_id
            update_lyrics()
            current_highlighted_item = None

        # Update current time label with modern format
        current_time_label.config(text=lyrics_manager.ms_to_min_sec(current_position))
        
        # Update current song label
        song_name = current_song['item']['name']
        artist_name = current_song['item']['artists'][0]['name'] if current_song['item']['artists'] else "Unknown Artist"
        
        # Show the translated title once the song is translated
        if current_translated_title and current_translated_title != song_name:
            display_title = f"{song_name} ({current_translated_title})"
            current_song_var.set(f"{display_title} • {artist_name}")
        else:
            current_song_var.set(f"{song_name} • {artist_name}")

        # Update main window treeview selection and highlight current line
        last_index = None
        if lyrics_synced and lyrics_timecodes:
            idx = bisect.bisect_right(lyrics_timecodes, int(current_position)) - 1
            if idx >= 0 and idx < len(lyrics_tree_items):
                last_index = lyrics_tree_items[idx]

            if last_index:
                if current_highlighted_item and current_highlighted_item != last_index:
                    try:
                        prev_tags = list(tree.item(current_highlighted_item)['tags'])
                        if 'current' in prev_tags:
                            prev_tags.remove('current')
                            tree.item(current_highlighted_item, tags=prev_tags)
                    except Exception:
                        pass

                try:
                    tags = list(tree.item(last_index)['tags'])
                    if 'current' not in tags:
                        tags.append('current')
                        tree.item(last_index, tags=tags)
                except Exception:
                    pass

                current_highlighted_item = last_index

                if is_playing and time.monotonic() > user_scroll_lock_until:
                    try:
                        if last_index not in tree.selection():
                            tree.selection_set(last_index)
                        
                        # Position the current line in the middle of the visible area
                        # Get the total number of items in the tree
                        total_items = len(tree.get_children())
                        if total_items > 0:
                            # Get the index of the current item
                            current_index = 0
                            for i, item_id in enumerate(tree.get_children()):
                                if item_id == last_index:
                                    current_index = i
                                    break
                            
                            # Get the visible portion of the tree
                            top, bottom = tree.yview()
                            visible_height = bottom - top
                            
                            # Calculate the position of the current item in the visible area
                            # Convert the current index to a fraction of the total
                            current_fraction = current_index / total_items
                            
                            # Check if the current item is already in a comfortable position
                            # We define a "comfort zone" in the middle 60% of the visible area
                            comfort_zone_top = top + (visible_height * 0.1)
                            comfort_zone_bottom = top + (visible_height * 0.8)
                            
                            # Only reposition if the current item is outside the comfort zone
                            if current_fraction < comfort_zone_top or current_fraction > comfort_zone_bottom:
                                # Calculate the position to center the current item
                                center_fraction = current_fraction - (visible_height / 2)
                                
                                # Make sure the fraction is within valid bounds
                                center_fraction = max(0, min(1 - visible_height, center_fraction))
                                
                                # Scroll to the calculated position
                                tree.yview_moveto(center_fraction)
                        else:
                            # Fallback to the original behavior if we can't calculate the position
                            tree.see(last_index)
                    except Exception:
                        # If anything goes wrong, fall back to the original behavior
                        tree.see(last_index)
            elif current_highlighted_item:
                try:
                    prev_tags = list(tree.item(current_highlighted_item)['tags'])
                    if 'current' in prev_tags:
                        prev_tags.remove('current')
                        tree.item(current_highlighted_item, tags=prev_tags)
                except Exception:
                    pass
                current_highlighted_item = None
        elif current_highlighted_item:
            try:
                prev_tags = list(tree.item(current_highlighted_item)['tags'])
                if 'current' in prev_tags:
                    prev_tags.remove('current')
                    tree.item(current_highlighted_item, tags=prev_tags)
            except Exception:
                pass
            current_highlighted_item = None

        # Update floating window if it exists
        if floating_window and floating_window.is_open():
            song_duration = current_song['item']['duration_ms'] if current_song and 'item' in current_song else 0
            if lyrics_synced and current_lyrics:
                # The line playing now, and its neighbours when the floating window shows several
                idx = bisect.bisect_right(lyrics_timecodes, int(current_position)) - 1
                floating_window.update_lyrics(current_song_name, artist_name, current_lyrics, idx, current_position, song_duration, current_translated_title)
            else:
                # Unsynced or no lyrics: clear text and avoid progression
                floating_window.update_lyrics(current_song_name, artist_name, None, -1, 0, 0, current_translated_title)
            # Update play/pause button state without extra Spotify calls
            floating_window.update_play_pause_button(is_playing)

    else:
        # No song playing or not authenticated yet
        if current_highlighted_item:
            try:
                prev_tags = list(tree.item(current_highlighted_item)['tags'])
                if 'current' in prev_tags:
                    prev_tags.remove('current')
                    tree.item(current_highlighted_item, tags=prev_tags)
            except Exception:
                pass
            current_highlighted_item = None
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
    # Poll more frequently while playing, ease off when paused or idle
    if current_song:
        poll_interval = 400 if current_song.get('is_playing', False) else 1200
    else:
        poll_interval = 800
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

def update_lyrics(force_translate=False):
    """Load the playing song's lyrics on a worker thread; _show_lyrics displays them.

    Args:
        force_translate: Translate even when OpenRouter auto-translate is off for this song (Refresh Lyrics)
    """
    global current_lyrics, current_song_name, current_lyrics_source, current_translation_source
    global current_highlighted_item, lyrics_tree_items, lyrics_timecodes, load_generation, current_translated_title

    try:
        # Get current playback
        current_playback, _ = get_current_playback_position()
        if not current_playback or not current_playback['item']:
            logger.debug("update_lyrics: No current playback or item, returning")
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

        item = current_playback['item']
        song_id = track_key(item)
        song_name = item['name']
        artist_names = [a.get('name', '') for a in (item.get('artists') or []) if a.get('name')]
        artist_name = artist_names[0] if artist_names else "Unknown Artist"
        current_song_name = song_name
        logger.debug(f"update_lyrics: Processing song '{song_name}' with ID {song_id}")

        # Update window title with song info
        root.title(f"{song_name} • {artist_name} - Spotify Lyrics Translator")

        load_generation += 1
        generation = load_generation

        # Clear what the previous load showed
        tree.delete(*tree.get_children())
        current_lyrics = []
        lyrics_tree_items = []
        lyrics_timecodes = []
        current_highlighted_item = None
        current_lyrics_source = "Unknown"
        current_translation_source = "Unknown"
        current_translated_title = None
        set_banner_notes([])
        update_column_headers()
        update_source_picker()

        if not lyrics_service:
            status_label.config(text="No lyrics found")
            return
        status_label.config(text="Loading lyrics...")

        track_meta = TrackMetadata(
            track_name=song_name,
            artist_name=artist_names[0] if artist_names else '',
            album_name=(item.get('album') or {}).get('name') or '',
            duration_ms=int(item.get('duration_ms') or 0),
            artist_names=artist_names,
        )
        settings = read_translation_settings()
        pinned = settings.get("pinned_lyrics_source")
        order = resolve_order(settings.get("lyrics_source_order"), pinned)

        def load():
            try:
                result = lyrics_service.get_lyrics(
                    track_meta,
                    item.get('id'),
                    order,
                    cache_lookup=lambda name: lyrics_manager.get_cached(song_id, name),
                    is_stale=lambda: generation != load_generation,
                )
                if result and not result.get('cached'):
                    lyrics_manager.put_lyrics(song_id, result)
            except Exception as e:
                logger.error(f"Error loading lyrics: {e}")
                result = None
            root.after(0, lambda: _show_lyrics(generation, song_id, song_name, pinned, result, force_translate))

        threading.Thread(target=load, name="LyricsLoader", daemon=True).start()
    except Exception as e:
        logger.error(f"Error updating lyrics: {e}")
        status_label.config(text="Error loading lyrics")


def _show_lyrics(generation, song_id, song_name, pinned, result, force_translate):
    """Display lyrics loaded by update_lyrics, then start translating them. Runs on the UI thread."""
    global current_lyrics, language, lyrics_synced, current_lyrics_source, current_translation_source
    global lyrics_tree_items, lyrics_timecodes

    if generation != load_generation:
        return
    try:
        lyrics = (result or {}).get('lyrics') or {}
        lines = lyrics.get('lines') or []
        current_lyrics_source = result.get('source', 'Unknown') if lines else "Unknown"
        update_source_picker()
        notes = []
        if pinned and pinned != current_lyrics_source:
            notes.append(f"Couldn't get lyrics from {pinned}")

        if not lines:
            set_banner_notes(notes)
            status_label.config(text="No lyrics found")
            update_column_headers()
            return

        lyrics_synced = lyrics.get('synced', True)
        language = lyrics.get('language', '')
        if not lyrics_synced:
            notes.append("Lyrics are not time-synced.")
        set_banner_notes(notes)

        # current_lyrics is the single source of truth, one entry per tree row
        current_lyrics = [
            {'startTimeMs': line['startTimeMs'], 'words': line['words'], 'provided': line.get('provided', ''), 'translated': ''}
            for line in lines
        ]
        # A translation shipped with the lyrics shows at once
        provided = lyrics_manager.provided_translation(current_lyrics)
        if provided:
            for lyric, text in zip(current_lyrics, provided):
                lyric['translated'] = text
            current_translation_source = current_lyrics_source
        logger.debug(f"_show_lyrics: {len(current_lyrics)} lines from {current_lyrics_source}")

        # Populate Treeview from current_lyrics with alternating row colors
        lyrics_tree_items = []
        lyrics_timecodes = []
        for i, lyric in enumerate(current_lyrics):
            tag = 'evenrow' if i % 2 == 0 else 'oddrow'
            time_text = lyrics_manager.ms_to_min_sec(lyric['startTimeMs']) if lyrics_synced else ""
            item_id = tree.insert("", "end", values=(time_text, lyric['words'], lyric['translated']), tags=(tag,))
            lyrics_tree_items.append(item_id)
            try:
                lyrics_timecodes.append(int(lyric['startTimeMs']))
            except Exception:
                lyrics_timecodes.append(0)

        # Hide the Time heading for unsynced lyrics
        tree.heading("Time", text="  Time" if lyrics_synced else "")
        update_column_headers()
        adjust_column_widths()

        status_label.config(text="Ready")
        lyrics_data = [dict(lyric) for lyric in current_lyrics]
        threading.Thread(
            target=_translate_lyrics,
            args=(generation, song_id, song_name, current_lyrics_source, lyrics_data, language, force_translate),
            name="Translator",
            daemon=True,
        ).start()
    except Exception as e:
        logger.error(f"Error showing lyrics: {e}")
        status_label.config(text="Error loading lyrics")


def _translate_lyrics(generation, song_id, song_name, source, lyrics_data, language_tag, force):
    """Decide whether to translate, then translate. Runs on a worker thread; _on_translation shows the outcome.

    Already in the target language: not translated. OpenRouter without a key: not translated. A cached translation
    always shows. OpenRouter with auto-translate off, or for a skipped language: only when forced (Refresh Lyrics).
    """
    def post(state, data=None):
        root.after(0, lambda: _on_translation(generation, state, data))

    try:
        target = lyrics_manager.target_language
        detected = lyrics_language.detect_language([line['words'] for line in lyrics_data], language_tag)
        if detected == lyrics_language.base(target):
            logger.info(f"Translation skipped: '{song_name}' is already in {target}")
            post('same', target)
            return
        client = lyrics_manager.translation_client
        is_openrouter = lyrics_manager.translator_id().startswith("openrouter:")
        if is_openrouter and not getattr(client, 'api_key', ''):
            post('missing_key')
            return
        cached = lyrics_manager.get_translation(song_id, source, len(lyrics_data))
        if cached:
            post('done', (cached, True))
            return
        if is_openrouter and not force:
            settings = read_translation_settings()
            if not settings.get("openrouter_auto_translate", True):
                logger.info(f"Translation not requested: OpenRouter auto-translate is off for '{song_name}'")
                post('not_requested')
                return
            if detected and detected in (settings.get("openrouter_skip_languages") or []):
                logger.info(f"Translation not requested: OpenRouter auto-translate is off for {detected} ('{song_name}')")
                post('not_requested')
                return
        post('translating')
        post('done', (lyrics_manager.translate_lyrics(lyrics_data, song_id, source, song_name), False))
    except Exception as e:
        logger.error(f"Translation failed for '{song_name}': {e}")
        post('failed', str(e))


def _on_translation(generation, state, data=None):
    """Show a translation outcome from _translate_lyrics. Runs on the UI thread."""
    global current_translation_source, current_translated_title

    if generation != load_generation:
        return
    if state == 'translating':
        status_label.config(text="Translating lyrics...")
        return
    if state == 'done':
        translation, cached = data
        for lyric, text in zip(current_lyrics, translation['lines']):
            lyric['translated'] = text
        current_translation_source = translation.get('label', 'Unknown')
        current_translated_title = translation.get('title')
        update_column_headers()
        update_translations(highlight=not cached)
        status_label.config(text="Ready" if cached else "Translation complete")
        if not cached:
            # Reset status after a delay
            root.after(3000, lambda: generation == load_generation and status_label.config(text="Ready"))
        return
    if state == 'same':
        name = next((n for code, n in TARGET_LANGUAGES if code == data), data)
        if name.startswith("Chinese"):
            name = "Chinese"
        current_translation_source = f"Already in {name}"
        status_label.config(text=f"Already in {name}")
    elif state == 'missing_key':
        status_label.config(text="OpenRouter selected but API key missing. Please add it in Settings.")
    elif state == 'not_requested':
        status_label.config(text="Not translated. Press Refresh Lyrics to translate")
    elif state == 'failed':
        status_label.config(text=f"Translation failed: {data}. Press Refresh Lyrics to retry")
    update_column_headers()


def set_banner_notes(notes):
    """Show notes such as "Lyrics are not time-synced." next to the buttons; none hides the banner."""
    try:
        if notes:
            unsynced_banner_label.config(text="  ·  ".join(notes))
            if not getattr(unsynced_banner_label, '_packed', False):
                # Place banner to the right of the buttons
                unsynced_banner_label.pack(side=tk.LEFT, padx=(20, 0))
                unsynced_banner_label._packed = True
        elif getattr(unsynced_banner_label, '_packed', False):
            unsynced_banner_label.pack_forget()
            unsynced_banner_label._packed = False
    except Exception:
        pass


def update_source_picker():
    """Label the source picker with the shown source, and check the source tried first."""
    settings = read_translation_settings()
    pinned = settings.get("pinned_lyrics_source")
    first = resolve_order(settings.get("lyrics_source_order"), pinned)[0]
    source_choice_var.set(first)
    shown = current_lyrics_source if current_lyrics_source not in ("Unknown", "unknown") else "Lyrics source"
    source_button.config(text=f"{shown} ▾")


def pick_lyrics_source(name):
    """Try this source first, for this and later songs; picking the first source of the Settings order unpins."""
    settings = read_translation_settings()
    first = resolve_order(settings.get("lyrics_source_order"), None)[0]
    save_translation_settings({"pinned_lyrics_source": None if name == first else name})
    update_lyrics()


# Function to update the Treeview with translated lyrics from current_lyrics
def update_translations(highlight=True):
    # Rows and current_lyrics are 1:1
    updated_count = 0
    for item, lyric in zip(lyrics_tree_items, current_lyrics):
        if not tree.exists(item):
            continue
        current_values = list(tree.item(item)['values'])
        current_values[2] = lyric.get('translated', '')
        tree.item(item, values=current_values)
        if lyric.get('translated'):
            updated_count += 1
            if highlight:
                _highlight_translation(item)

    logger.debug(f"update_translations: Updated {updated_count} translated lyrics in Treeview")
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
        # FIXED: Time column gets a constant width of 100px
        time_width = 100  # Fixed width instead of percentage-based calculation
        # Original and translated lyrics split the remaining width equally
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
        floating_window = FloatingLyricsWindow(root, spotify_client, font_name, font_size, is_bold)
        floating_window.set_locked(floating_locked_var.get())
        toggle_button.config(text="Hide Floating Lyrics")


def toggle_floating_lock():
    """Lock: clicks pass through the floating window. Unlocked from here, as a locked window takes no clicks."""
    if floating_window and floating_window.is_open():
        floating_window.set_locked(floating_locked_var.get())

def update_song_title_wraplength():
    """Update the wraplength of the song title label based on window width."""
    try:
        # Get window width
        window_width = root.winfo_width()
        if window_width < 1:
            return
        
        # Estimate space taken by left side (icon + title + padding)
        # Icon: ~30px, "Lyrics Translator": ~200px, padding: ~60px
        left_side_width = 290
        
        # Right padding: 20px
        right_padding = 20
        
        # Calculate available width for song title
        available_width = window_width - left_side_width - right_padding
        
        # Ensure minimum width and update wraplength
        wraplength = max(200, available_width - 50)  # Leave some margin
        current_song_label.config(wraplength=wraplength)
    except Exception:
        pass

def refresh_ui_font():
    """Refresh all main window UI elements with the currently selected font settings."""
    font_name, font_size, is_bold = get_font_settings()
    font_style = 'bold' if is_bold else 'normal'

    refresh_theme_colors()

    # Update all UI elements with the new font settings
    unsynced_banner_label.config(font=(font_name, 11, font_style))
    icon_label.config(font=(font_name, 24, 'bold'))  # Icon stays bold
    app_title.config(font=(font_name, 20, 'bold'))  # Title stays bold
    current_song_label.config(font=(font_name, 14, font_style))
    current_time_label.config(font=(font_name, 12, font_style))
    toggle_button.config(font=(font_name, 12, font_style))
    refresh_button.config(font=(font_name, 12, font_style))
    source_button.config(font=(font_name, 12, font_style))
    status_label.config(font=(font_name, 11, font_style))
    
    # Update wraplength after font refresh
    root.after(100, update_song_title_wraplength)

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


def apply_theme_to_tree():
    """Apply theme colors to the Treeview styles, tags, headings, and scrollbar."""
    global theme_colors

    # Get current font settings
    font_name, font_size, is_bold = get_font_settings()
    font_style = 'bold' if is_bold else 'normal'

    # Configure Treeview style with theme colors
    style.configure(
        "Spotify.Treeview",
        background=theme_colors.get("lyrics_table_bg", SPOTIFY_DARK),
        foreground=theme_colors.get("lyrics_text_fg", SPOTIFY_WHITE),
        fieldbackground=theme_colors.get("lyrics_table_bg", SPOTIFY_DARK),
        borderwidth=0,
        font=(font_name, font_size, font_style),
        rowheight=max(35, font_size + 20)  # Adjust row height based on font size
    )

    # Configure Treeview heading style
    style.configure(
        "Spotify.Treeview.Heading",
        background=theme_colors.get("lyrics_heading_bg", SPOTIFY_GRAY),
        foreground=theme_colors.get("lyrics_heading_fg", SPOTIFY_WHITE),
        font=(font_name, font_size, font_style),
        borderwidth=0,
        relief=tk.FLAT
    )

    # Configure selected row style with better highlighting
    style.map(
        "Spotify.Treeview",
        background=[('selected', theme_colors.get("lyrics_selected_bg", SPOTIFY_GREEN))],
        foreground=[('selected', theme_colors.get("lyrics_selected_fg", SPOTIFY_WHITE))]
    )

    # Add alternating row colors for better readability
    tree.tag_configure('oddrow', background=theme_colors.get("lyrics_row_odd_bg", SPOTIFY_DARK))
    tree.tag_configure('evenrow', background=theme_colors.get("lyrics_row_even_bg", SPOTIFY_GRAY))

    # Add a special tag for the current playing line
    tree.tag_configure('current', background=SPOTIFY_GREEN, foreground=SPOTIFY_WHITE)

    # Add a tag for translated text to make it stand out
    tree.tag_configure('translated', foreground=theme_colors.get("lyrics_text_fg", SPOTIFY_WHITE))

    # Add a tag for highlighting newly translated lines
    tree.tag_configure('highlight', background=SPOTIFY_GREEN, foreground=SPOTIFY_WHITE)

    # Configure scrollbar style
    style.configure(
        "Spotify.Vertical.TScrollbar",
        background=theme_colors.get("scrollbar_bg", SPOTIFY_GRAY),
        troughcolor=theme_colors.get("scrollbar_trough", SPOTIFY_DARK),
        bordercolor=theme_colors.get("scrollbar_border", SPOTIFY_DARK),
        arrowcolor=theme_colors.get("scrollbar_arrow", SPOTIFY_LIGHT_GRAY),
        darkcolor=theme_colors.get("scrollbar_bg", SPOTIFY_GRAY),
        lightcolor=theme_colors.get("scrollbar_bg", SPOTIFY_GRAY)
    )


def refresh_theme_colors():
    """Reload theme colors from settings and apply them to the main window."""
    global theme_colors, MAIN_BG_COLOR

    theme_colors = get_theme_colors()
    MAIN_BG_COLOR = theme_colors.get("main_bg", SPOTIFY_BLACK)

    try:
        root.configure(bg=MAIN_BG_COLOR)
    except Exception:
        pass

    # Apply panel background to main frames
    panel_bg = theme_colors.get("panel_bg", SPOTIFY_DARK)
    for widget in [control_frame, frame, unsynced_banner_label, status_label]:
        try:
            widget.configure(bg=MAIN_BG_COLOR)
        except Exception:
            pass

    # Apply theme to header area
    try:
        header_frame.configure(bg=panel_bg)
        title_frame.configure(bg=panel_bg)
        song_info_frame.configure(bg=panel_bg)
    except Exception:
        pass

    # Apply theme to header labels
    accent_color = theme_colors.get("accent_primary", SPOTIFY_GREEN)
    text_muted = theme_colors.get("text_muted", SPOTIFY_LIGHT_GRAY)
    text_primary = theme_colors.get("text_primary", SPOTIFY_WHITE)

    try:
        icon_label.configure(fg=accent_color, bg=panel_bg)
        app_title.configure(fg=text_primary, bg=panel_bg)
        current_song_label.configure(fg=text_muted, bg=panel_bg)
        current_time_label.configure(fg=accent_color, bg=panel_bg)
    except Exception:
        pass

    # Apply theme to buttons
    button_primary_bg = theme_colors.get("button_primary_bg", SPOTIFY_GREEN)
    button_primary_fg = theme_colors.get("button_primary_fg", SPOTIFY_WHITE)
    button_primary_hover = theme_colors.get("button_primary_hover", SPOTIFY_GREEN_HOVER)
    button_secondary_bg = theme_colors.get("button_secondary_bg", SPOTIFY_GRAY)
    button_secondary_fg = theme_colors.get("button_secondary_fg", SPOTIFY_WHITE)
    button_secondary_hover = theme_colors.get("button_secondary_hover", SPOTIFY_LIGHT_GRAY)

    try:
        # Primary button (Show/Hide Floating Lyrics)
        toggle_button.configure(
            bg=button_primary_bg,
            fg=button_primary_fg,
            activebackground=theme_colors.get("button_primary_active", SPOTIFY_GREEN_ACTIVE)
        )
        # Update hover handlers
        toggle_button.bind("<Enter>", lambda e: toggle_button.config(bg=button_primary_hover))
        toggle_button.bind("<Leave>", lambda e: toggle_button.config(bg=button_primary_bg))

        # Secondary button (Refresh Lyrics)
        refresh_button.configure(
            bg=button_secondary_bg,
            fg=button_secondary_fg,
            activebackground=theme_colors.get("button_secondary_active", SPOTIFY_LIGHT_GRAY)
        )
        # Update hover handlers
        refresh_button.bind("<Enter>", lambda e: refresh_button.config(bg=button_secondary_hover))
        refresh_button.bind("<Leave>", lambda e: refresh_button.config(bg=button_secondary_bg))

        # Lyrics source picker
        source_button.configure(
            bg=button_secondary_bg,
            fg=button_secondary_fg,
            activebackground=theme_colors.get("button_secondary_active", SPOTIFY_LIGHT_GRAY)
        )
    except Exception:
        pass

    # Apply theme to Treeview and related styles
    apply_theme_to_tree()
# Create main application window
root = tk.Tk()
root.title("Spotify Lyrics Translator")
root.configure(bg=theme_colors.get("main_bg", "#121212"))  # Apply configurable background

# Menubar with Settings
menubar = tk.Menu(root)
file_menu = tk.Menu(menubar, tearoff=0)
file_menu.add_command(label="Settings...", command=lambda: open_settings_modal())
file_menu.add_separator()
file_menu.add_command(label="Exit", command=root.quit)
menubar.add_cascade(label="File", menu=file_menu)
view_menu = tk.Menu(menubar, tearoff=0)
# Not saved, like on Android: the floating window opens unlocked after a restart
floating_locked_var = tk.BooleanVar(value=False)
view_menu.add_checkbutton(label="Lock Floating Lyrics", variable=floating_locked_var, command=lambda: toggle_floating_lock())
menubar.add_cascade(label="View", menu=view_menu)
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

MAIN_BG_COLOR = theme_colors.get("main_bg", SPOTIFY_BLACK)

# Configure root background
root.configure(bg=MAIN_BG_COLOR)

# Create header frame with app branding
header_frame = tk.Frame(root, bg=theme_colors.get("panel_bg", SPOTIFY_DARK), height=80)
header_frame.pack(fill=tk.X, padx=0, pady=0)
header_frame.pack_propagate(False)  # Prevent frame from shrinking

# App title and logo area
title_frame = tk.Frame(header_frame, bg=theme_colors.get("panel_bg", SPOTIFY_DARK))
title_frame.pack(side=tk.LEFT, padx=20, pady=15)

# Spotify-like icon (using text representation)
icon_label = tk.Label(
    title_frame,
    text="♪",
    font=(get_selected_font(), 24, 'bold'),
    fg=theme_colors.get("accent_primary", SPOTIFY_GREEN),
    bg=theme_colors.get("panel_bg", SPOTIFY_DARK)
)
icon_label.pack(side=tk.LEFT, padx=(0, 10))

app_title = tk.Label(
    title_frame,
    text="Lyrics Translator",
    font=(get_selected_font(), 20, 'bold'),
    fg=theme_colors.get("text_primary", SPOTIFY_WHITE),
    bg=theme_colors.get("panel_bg", SPOTIFY_DARK)
)
app_title.pack(side=tk.LEFT)

# Current song info frame - positioned on the right side
song_info_frame = tk.Frame(header_frame, bg=theme_colors.get("panel_bg", SPOTIFY_DARK))
song_info_frame.pack(side=tk.RIGHT, padx=(0, 20), pady=15, anchor='e')

# Current song label as Label - right-aligned to stick to right border
# Wraplength will be updated dynamically based on window width
current_song_var = tk.StringVar(value="No song playing")
current_song_label = tk.Label(
    song_info_frame,
    textvariable=current_song_var,
    font=(get_selected_font(), 14, 'bold'),
    fg=theme_colors.get("text_muted", SPOTIFY_LIGHT_GRAY),
    bg=theme_colors.get("panel_bg", SPOTIFY_DARK),
    anchor='e',  # Right-align the text
    justify='right'
)
current_song_label.pack(anchor='e')

# Current time label with modern styling - right-aligned
current_time_label = tk.Label(
    song_info_frame,
    text="0:00",
    font=(get_selected_font(), 12, 'bold'),
    fg=theme_colors.get("accent_primary", SPOTIFY_GREEN),
    bg=theme_colors.get("panel_bg", SPOTIFY_DARK),
    anchor='e'  # Right-align the time as well
)
current_time_label.pack(anchor='e')

# Control panel frame
control_frame = tk.Frame(root, bg=MAIN_BG_COLOR, height=60)
control_frame.pack(fill=tk.X, padx=20, pady=10)

# Unsynced banner (initially hidden)
unsynced_banner_label = tk.Label(
    control_frame,
    text="Lyrics are not time-synced.",
    fg=SPOTIFY_LIGHT_GRAY,
    bg=MAIN_BG_COLOR,
    font=(get_selected_font(), 11, 'bold')
)
unsynced_banner_label._packed = False

# Toggle floating lyrics button with modern styling
toggle_button = tk.Button(
    control_frame,
    text="Show Floating Lyrics",
    font=(get_selected_font(), 12, 'bold'),
    fg=theme_colors.get("button_primary_fg", SPOTIFY_WHITE),
    bg=theme_colors.get("button_primary_bg", SPOTIFY_GREEN),
    activebackground=theme_colors.get("button_primary_active", SPOTIFY_GREEN_ACTIVE),
    activeforeground=theme_colors.get("button_primary_fg", SPOTIFY_WHITE),
    bd=0,
    padx=20,
    pady=8,
    relief=tk.FLAT,
    cursor="hand2",
    command=toggle_floating_window
)
toggle_button.pack(side=tk.LEFT, padx=(0, 10))

# Hover effects will be set by refresh_theme_colors()

# Add a refresh button to manually refresh lyrics
def refresh_lyrics():
    """Manually refresh the current song's lyrics, and translate them even if auto-translate is off."""
    # Clear the cache of the shown source for the currently playing song (if any); other sources' stay
    current_playback, _ = get_current_playback_position()
    song_id = None
    try:
        if current_playback and current_playback.get('item'):
            song_id = track_key(current_playback['item'])
    except Exception:
        song_id = None
    if song_id and song_id == current_song_id and current_lyrics_source not in ("Unknown", "unknown"):
        lyrics_manager.clear_cache(song_id, current_lyrics_source)
    update_lyrics(force_translate=True)

refresh_button = tk.Button(
    control_frame,
    text="Refresh Lyrics",
    font=(get_selected_font(), 12, 'bold'),
    fg=theme_colors.get("button_secondary_fg", SPOTIFY_WHITE),
    bg=theme_colors.get("button_secondary_bg", SPOTIFY_GRAY),
    activebackground=theme_colors.get("button_secondary_active", SPOTIFY_LIGHT_GRAY),
    activeforeground=theme_colors.get("button_secondary_fg", SPOTIFY_WHITE),
    bd=0,
    padx=20,
    pady=8,
    relief=tk.FLAT,
    cursor="hand2",
    command=refresh_lyrics
)
refresh_button.pack(side=tk.LEFT, padx=(0, 10))

# Lyrics source picker: shows the source of the lyrics shown; picking one tries it first from now on
source_choice_var = tk.StringVar()
source_button = tk.Menubutton(
    control_frame,
    text="Lyrics source ▾",
    font=(get_selected_font(), 12, 'bold'),
    fg=theme_colors.get("button_secondary_fg", SPOTIFY_WHITE),
    bg=theme_colors.get("button_secondary_bg", SPOTIFY_GRAY),
    activebackground=theme_colors.get("button_secondary_active", SPOTIFY_LIGHT_GRAY),
    activeforeground=theme_colors.get("button_secondary_fg", SPOTIFY_WHITE),
    bd=0,
    padx=16,
    pady=8,
    relief=tk.FLAT,
    cursor="hand2",
)
source_menu = tk.Menu(source_button, tearoff=0)
for _source_name in DEFAULT_ORDER:
    source_menu.add_radiobutton(
        label=_source_name,
        variable=source_choice_var,
        value=_source_name,
        command=lambda name=_source_name: pick_lyrics_source(name),
    )
source_button.config(menu=source_menu)
# fill=Y: a Menubutton is drawn shorter than a Button with the same padding
source_button.pack(side=tk.LEFT, padx=(0, 10), fill=tk.Y)

# Hover effects will be set by refresh_theme_colors()

# Add a status label to show translation status
status_label = tk.Label(
    control_frame,
    text="Ready",
    font=(get_selected_font(), 11, 'bold'),
    fg=SPOTIFY_LIGHT_GRAY,
    bg=MAIN_BG_COLOR
)
status_label.pack(side=tk.RIGHT, padx=(10, 0))

# Create a frame to hold the Treeview and Scrollbar with modern styling
frame = tk.Frame(root, bg=MAIN_BG_COLOR)
frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 20))

# Create and configure the treeview widget with modern styling
tree = ttk.Treeview(
    frame, 
    columns=("Time", "Original Lyrics", "Translated Lyrics"), 
    show="headings",
    style="Spotify.Treeview",
    selectmode="extended"
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

# Create custom scrollbar with modern styling
scrollbar = ttk.Scrollbar(
    frame,
    orient="vertical",
    command=tree.yview,
    style="Spotify.Vertical.TScrollbar"
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
        # Removed the "Jumped to" notification as requested
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


def _record_user_tree_interaction(event=None):
    """Temporarily disable auto-scroll while the user is interacting."""
    global user_scroll_lock_until
    user_scroll_lock_until = time.monotonic() + 2.0
    return None


tree.bind("<ButtonPress-1>", _record_user_tree_interaction, add="+")
tree.bind("<MouseWheel>", _record_user_tree_interaction, add="+")
tree.bind("<Shift-MouseWheel>", _record_user_tree_interaction, add="+")
tree.bind("<Control-MouseWheel>", _record_user_tree_interaction, add="+")
tree.bind("<KeyPress-Up>", _record_user_tree_interaction, add="+")
tree.bind("<KeyPress-Down>", _record_user_tree_interaction, add="+")

# Initialize settings and client
update_source_picker()
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
        logger.warning(f"Could not initialize font settings: {e}")

initialize_font_settings()

# Bind window resize event to update song title wraplength
def on_window_configure(event=None):
    """Handle window resize events."""
    # Only handle root window resize events
    if event and event.widget == root:
        update_song_title_wraplength()

root.bind('<Configure>', on_window_configure)

# Initialize wraplength after window is ready
root.after(100, update_song_title_wraplength)

# Start the update loop
root.after(500, update_display)

# Start the application
root.mainloop()
