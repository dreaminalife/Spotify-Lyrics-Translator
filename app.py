import tkinter as tk
from tkinter import ttk
import threading
import sv_ttk

from src.spotify_client import SpotifyClient
from src.lyrics_manager import LyricsManager
from src.floating_window import FloatingLyricsWindow
from src.settings_manager import read_secrets, validate_secrets
from src.translation_clients import GoogleTranslateClient, OpenRouterClient
from src.translation_settings import (
    read_translation_settings,
    save_translation_settings,
    read_models_config,
)
from src.settings_window import SettingsWindow

# Initialize Spotify client via settings
spotify_client = None

# Initialize lyrics manager
lyrics_manager = LyricsManager()

# Global state
current_song_id = None
current_lyrics = []
current_song_name = ""
language = ""
floating_window = None


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
    except Exception as e:
        print(f"Error initializing Spotify client: {e}")
        try:
            status_label.config(text="Authentication failed. Open Settings.")
        except Exception:
            pass


def init_translation_client():
    settings = read_translation_settings()
    models_body = read_models_config()
    secrets = read_secrets()

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
            try:
                status_label.config(text="Translation: OpenRouter ready")
            except Exception:
                pass
        except Exception as e:
            print(f"Error initializing OpenRouter client: {e}")
            lyrics_manager.translation_client = GoogleTranslateClient()
            try:
                status_label.config(text="Translation fallback: Google Translate")
            except Exception:
                pass
    else:
        lyrics_manager.translation_client = GoogleTranslateClient()
        try:
            status_label.config(text="Translation: Google Translate")
        except Exception:
            pass


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
        translated_lyrics: List of translated lyric dictionaries

    Returns:
        int: Number of lines updated
    """
    global current_lyrics

    # Create lookup dict for current_lyrics by (startTimeMs, words) for efficient merging
    current_lookup = {(lyric['startTimeMs'], lyric['words']): lyric for lyric in current_lyrics}

    updated_count = 0
    for translated in translated_lyrics:
        key = (translated['startTimeMs'], translated['words'])
        if key in current_lookup:
            current_lookup[key]['translated'] = translated['translated']
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
    global current_song_id, floating_window
    current_song, current_position = get_current_playback_position()

    print(f"[DEBUG] update_display: current_position={current_position}, current_lyrics_length={len(current_lyrics) if current_lyrics else 0}, floating_window_exists={floating_window is not None}")

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
            update_lyrics()

        # Update current time label with modern format
        current_time_label.config(text=lyrics_manager.ms_to_min_sec(current_position))
        
        # Update current song label
        song_name = current_song['item']['name']
        artist_name = current_song['item']['artists'][0]['name'] if current_song['item']['artists'] else "Unknown Artist"
        current_song_label.config(text=f"{song_name} • {artist_name}")

        # Update main window treeview selection and highlight current line
        last_index = None
        for item in tree.get_children():
            item_data = tree.item(item)
            start_time = int(item_data['values'][0].split(":")[0]) * 60000 + int(item_data['values'][0].split(":")[1]) * 1000
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
            print(f"[DEBUG] update_display: About to get current line for position {current_position}")
            current_line = lyrics_manager.get_current_line(current_lyrics, current_position)
            song_duration = current_song['item']['duration_ms'] if current_song and 'item' in current_song else 0
            print(f"[DEBUG] update_display: current_line={current_line}")
            floating_window.update_lyrics(current_song_name, current_line, current_position, song_duration)
        else:
            print(f"[DEBUG] update_display: Floating window not available - exists={floating_window is not None}, is_open={floating_window.is_open() if floating_window else False}")
    else:
        # No song playing or not authenticated yet
        current_time_label.config(text="0:00")
        current_song_label.config(text="No song playing")

    root.after(500, update_display)

# Function to update the lyrics in the Treeview
def update_lyrics():
    global current_song_id, current_lyrics, current_song_name, language

    try:
        # Get current playback
        current_playback, _ = get_current_playback_position()
        if not current_playback or not current_playback['item']:
            print("[DEBUG] update_lyrics: No current playback or item, returning")
            status_label.config(text="No song playing")
            return

        song_id = current_playback['item']['id']
        song_name = current_playback['item']['name']
        artist_name = current_playback['item']['artists'][0]['name'] if current_playback['item']['artists'] else "Unknown Artist"
        current_song_name = song_name
        print(f"[DEBUG] update_lyrics: Processing song '{song_name}' with ID {song_id}")
        
        # Update window title with song info
        root.title(f"{song_name} • {artist_name} - Spotify Lyrics Translator")
        
        # Update status
        status_label.config(text="Loading lyrics...")
        
        # Get lyrics
        lyrics = spotify_client.get_lyrics(song_id) if spotify_client else None
        lyrics_data = lyrics['lyrics']['lines'] if lyrics and 'lyrics' in lyrics and 'lines' in lyrics['lyrics'] else None
        print(f"[DEBUG] update_lyrics: Retrieved lyrics data, has_lyrics={lyrics_data is not None}, lyrics_count={len(lyrics_data) if lyrics_data else 0}")

        # Clear existing treeview items
        tree.delete(*tree.get_children())

        if lyrics_data:
            # Detect the language of the first line of lyrics
            detected_lang = lyrics['lyrics']['language']
            language = detected_lang
            tree.heading("Original Lyrics", text=f"  Original Lyrics ({detected_lang})")

            # Initialize current_lyrics as single source of truth with original lyrics
            current_lyrics = [
                {'startTimeMs': lyric['startTimeMs'], 'words': lyric['words'], 'translated': ''}
                for lyric in lyrics_data
            ]
            print(f"[DEBUG] update_lyrics: Initialized current_lyrics with {len(current_lyrics)} lines")

            # Populate Treeview from current_lyrics with alternating row colors
            for i, lyric in enumerate(current_lyrics):
                tag = 'evenrow' if i % 2 == 0 else 'oddrow'
                tree.insert("", "end", values=(
                    lyrics_manager.ms_to_min_sec(lyric['startTimeMs']), 
                    lyric['words'], 
                    lyric['translated']
                ), tags=(tag,))
            
            # Check cache first
            cached = lyrics_manager.get_cached_lyrics(song_id)
            if cached:
                print(f"[DEBUG] update_lyrics: Using cached lyrics for song {song_id}, length={len(cached)}")
                status_label.config(text="Using cached translations")
                merge_translations_into_current(cached)
                # Schedule UI update on main thread
                root.after(0, update_translations)
            else:
                print(f"[DEBUG] update_lyrics: No cached lyrics, starting translation for song {song_id}")
                status_label.config(text="Translating lyrics...")
                # Translate in background thread
                def translate_callback(translated):
                    print(f"[DEBUG] translate_callback: Translation completed for song {song_id}, received {len(translated)} lines")
                    status_label.config(text="Translation complete")
                    merge_translations_into_current(translated)
                    # Schedule UI update on main thread
                    root.after(0, update_translations)
                    # Reset status after a delay
                    root.after(3000, lambda: status_label.config(text="Ready"))

                threading.Thread(
                    target=lyrics_manager.translate_lyrics,
                    args=(lyrics_data, song_id, translate_callback)
                ).start()
        elif lyrics is None:
            # Could be an auth error or API error; handled elsewhere
            status_label.config(text="Error loading lyrics")
        else:
            print("[DEBUG] update_lyrics: No lyrics data available for this song")
            status_label.config(text="No lyrics available")
            tree.insert("", "end", values=("0:00", "(No lyrics)", ""), tags=('evenrow',))
            current_lyrics = []
        
        adjust_column_widths()
    except Exception as e:
        print(f"Error updating lyrics: {e}")
        status_label.config(text="Error loading lyrics")

# Function to update the Treeview with translated lyrics from current_lyrics
def update_translations():
    global current_lyrics

    # Rebuild the translated lyrics column from current_lyrics
    updated_count = 0
    for i, item in enumerate(tree.get_children()):
        item_data = tree.item(item)
        start_time = item_data['values'][0]
        original_lyrics = item_data['values'][1]

        # Find matching lyric in current_lyrics
        for lyric in current_lyrics:
            if lyrics_manager.ms_to_min_sec(lyric['startTimeMs']) == start_time and lyric['words'] == original_lyrics:
                # Update the translated lyrics in the treeview
                current_values = list(tree.item(item)['values'])
                current_values[2] = lyric['translated']  # Update the translated lyrics column
                tree.item(item, values=current_values)
                updated_count += 1
                # Add a subtle highlight animation for newly translated lines
                if lyric['translated']:
                    _highlight_translation(item)
                break

    print(f"[DEBUG] update_translations: Updated {updated_count} translated lyrics in Treeview")

    # Log first few updated lines for verification
    if current_lyrics and len(current_lyrics) > 0:
        first_few = current_lyrics[:3]
        for i, lyric in enumerate(first_few):
            translated = lyric.get('translated', '')[:50]
            print(f"[DEBUG] update_translations: Line {i+1}: translated='{translated}...'")

    adjust_column_widths()

def _highlight_translation(item, step=0):
    """Add a subtle highlight animation for newly translated lines.
    
    Args:
        item: Treeview item to highlight
        step: Current step in the animation
    """
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
        tags = list(tree.item(item)['tags'])
        if 'highlight' in tags:
            tags.remove('highlight')
            tree.item(item, tags=tags)

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
    min_time_width = 100
    max_original_length, max_translated_length, line_count = find_longest_line_lengths()

    root.update_idletasks()
    
    # Calculate widths based on content with better proportions
    orig_length = max(max_original_length * 12, 300)  # Minimum width for original lyrics
    trans_length = max(max_translated_length * 12, 300)  # Minimum width for translated lyrics

    # Adjust for different languages
    if language == "ja":
        orig_length = max(max_original_length * 18, 300)
    if language == "ru":
        orig_length = max(max_original_length * 14, 300)
        trans_length = max(max_translated_length * 15, 300)

    # Calculate window dimensions
    total_width = min_time_width + orig_length + trans_length + 60  # Extra padding
    height = min(line_count * 35 + 200, 800)  # Cap height at 800px

    # Get current window width
    current_width = root.winfo_width()
    if current_width < 1:  # Window not yet rendered
        current_width = 1200  # Default width

    # Update column widths
    tree.column("Time", width=min_time_width, minwidth=min_time_width)
    tree.column("Original Lyrics", width=orig_length, minwidth=250)
    tree.column("Translated Lyrics", width=trans_length, minwidth=250)
    
    # Update window geometry if needed
    if total_width > current_width:
        root.geometry(f"{total_width}x{height}")
    else:
        root.geometry(f"{current_width}x{height}")

# Function to toggle floating window
def toggle_floating_window():
    global floating_window
    
    if floating_window and floating_window.is_open():
        floating_window.close()
        floating_window = None
        toggle_button.config(text="Show Floating Lyrics")
    else:
        floating_window = FloatingLyricsWindow(root)
        toggle_button.config(text="Hide Floating Lyrics")

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
    font=('Circular Std', 24, 'bold'),
    fg=SPOTIFY_GREEN,
    bg=SPOTIFY_DARK
)
icon_label.pack(side=tk.LEFT, padx=(0, 10))

app_title = tk.Label(
    title_frame,
    text="Lyrics Translator",
    font=('Circular Std', 20, 'bold'),
    fg=SPOTIFY_WHITE,
    bg=SPOTIFY_DARK
)
app_title.pack(side=tk.LEFT)

# Current song info frame
song_info_frame = tk.Frame(header_frame, bg=SPOTIFY_DARK)
song_info_frame.pack(side=tk.RIGHT, padx=20, pady=15)

# Current song label (will be updated when song changes)
current_song_label = tk.Label(
    song_info_frame,
    text="No song playing",
    font=('Circular Std', 14),
    fg=SPOTIFY_LIGHT_GRAY,
    bg=SPOTIFY_DARK
)
current_song_label.pack()

# Current time label with modern styling
current_time_label = tk.Label(
    song_info_frame,
    text="0:00",
    font=('Circular Std', 12),
    fg=SPOTIFY_GREEN,
    bg=SPOTIFY_DARK
)
current_time_label.pack()

# Control panel frame
control_frame = tk.Frame(root, bg=SPOTIFY_BLACK, height=60)
control_frame.pack(fill=tk.X, padx=20, pady=10)

# Toggle floating lyrics button with modern styling
toggle_button = tk.Button(
    control_frame,
    text="Show Floating Lyrics",
    font=('Circular Std', 12, 'bold'),
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
    current_song_id = None  # Force refresh
    update_lyrics()

refresh_button = tk.Button(
    control_frame,
    text="Refresh Lyrics",
    font=('Circular Std', 12, 'bold'),
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
    font=('Circular Std', 11),
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
    style="Spotify.Treeview"
)

# Configure Treeview style with Spotify-inspired colors
style.configure(
    "Spotify.Treeview",
    background=SPOTIFY_DARK,
    foreground=SPOTIFY_WHITE,
    fieldbackground=SPOTIFY_DARK,
    borderwidth=0,
    font=('Circular Std', 11),
    rowheight=35
)

# Configure Treeview heading style
style.configure(
    "Spotify.Treeview.Heading",
    background=SPOTIFY_GRAY,
    foreground=SPOTIFY_WHITE,
    font=('Circular Std', 12, 'bold'),
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
tree.tag_configure('translated', foreground=SPOTIFY_LIGHT_GRAY)

# Add a tag for highlighting newly translated lines
tree.tag_configure('highlight', background=SPOTIFY_GREEN, foreground=SPOTIFY_WHITE)

# Create custom scrollbar with modern styling
scrollbar_frame = tk.Frame(frame, bg=SPOTIFY_BLACK, width=15)
scrollbar_frame.pack(side='right', fill='y')

scrollbar = ttk.Scrollbar(
    scrollbar_frame,
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

tree.configure(yscrollcommand=scrollbar.set)
tree.pack(side='left', fill=tk.BOTH, expand=True)
scrollbar.pack(fill='y')

# Initialize settings and client
ensure_settings_and_init()
init_translation_client()

# Start the update loop
root.after(500, update_display)

# Start the application
root.mainloop()
