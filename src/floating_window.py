"""Floating lyrics window implementation."""
import ctypes
import sys
import tkinter as tk
from tkinter import ttk
import threading
from .translation_settings import (
    read_translation_settings,
    save_translation_settings,
    get_theme_colors,
    FLOATING_LINE_COUNTS,
    FLOATING_STYLES,
    FLOATING_MIN_OPACITY,
)
from .font_manager import get_default_chinese_font
from .logging_config import get_logger
import time

logger = get_logger(__name__)

# Light style background
LIGHT_BG = "#FFFFFF"
# Clear style: the see-through color
CLEAR_KEY = "#010101"
# Clear style: buttons and the window edge, which must stay clickable; see-through pixels pass clicks through
CLEAR_HANDLE = "#1A1A1A"
# Win32 extended window styles used to let clicks pass through a locked window
GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x80000
WS_EX_TRANSPARENT = 0x20
LWA_ALPHA = 0x2


class FloatingLyricsWindow:
    """Always-on-top draggable window for displaying current lyrics."""

    def __init__(self, parent, spotify_client=None, font_name=None, font_size=None, font_bold=None):
        """Initialize the floating lyrics window.

        Args:
            parent: Parent Tkinter window
            spotify_client: SpotifyClient instance for playback controls (optional)
            font_name: Font name to use (optional, will use settings if not provided)
            font_size: Font size to use (optional, will use settings if not provided)
            font_bold: Whether to use bold font (optional, will use settings if not provided)
        """
        self.window = tk.Toplevel(parent)
        self.window.title("Floating Lyrics")
        self.window.overrideredirect(True)  # Remove window decorations

        # Store Spotify client for playback controls
        self.spotify_client = spotify_client
        
        # Timestamp for preventing polling override after play/pause clicks
        self._last_play_pause_click = 0
        # Timestamp for debouncing after grace period
        self._last_update_time = 0

        settings = read_translation_settings()
        self.theme_colors = get_theme_colors()

        # Set font settings - use provided values or get from settings
        if font_name is not None and font_size is not None and font_bold is not None:
            self.selected_font = font_name
            self.font_size = font_size
            self.font_bold = font_bold
        else:
            # Fallback to getting from settings (for backward compatibility)
            self.selected_font = self.get_selected_font()
            self.font_size = settings.get("floating_font_size", 12)
            self.font_bold = settings.get("floating_font_bold", True)

        # Floating window background color (use theme color)
        self.background_color = self.theme_colors.get("floating_bg", "#181818")

        # Define Spotify-inspired color scheme as fallbacks
        SPOTIFY_BLACK = '#121212'
        SPOTIFY_DARK = '#181818'
        SPOTIFY_GRAY = '#282828'
        SPOTIFY_LIGHT_GRAY = '#B3B3B3'
        SPOTIFY_WHITE = '#FFFFFF'
        SPOTIFY_GREEN = '#1DB954'
        
        # Window configuration with glassmorphic effect
        self.window.attributes('-topmost', True)
        self.window.attributes('-alpha', 0.0)  # Start fully transparent for fade-in effect
        # Load persisted window size (fallback to defaults)
        _init_w = int(settings.get("floating_window_width", 800))
        _init_h = int(settings.get("floating_window_height", 200))
        self.window.geometry(f"{_init_w}x{_init_h}+100+100")  # Increased height to prevent text clipping
        self.window.configure(bg=self.background_color)

        # Add a subtle border
        self.window.configure(highlightbackground=self.theme_colors.get("floating_border", SPOTIFY_GREEN), highlightthickness=1)
        
        # Make window draggable and resizable
        self.x = 0
        self.y = 0
        self.resize_edge = None  # Track which edge/corner is being resized
        self.resize_margin = 8  # Pixels from edge to trigger resize
        # Track starting geometry/position at mouse down for stable calculations
        self.start_x_root = 0
        self.start_y_root = 0
        self.start_win_x = 0
        self.start_win_y = 0
        self.start_width = 0
        self.start_height = 0

        # Create main frame with glassmorphic effect
        self.main_frame = tk.Frame(self.window, bg=self.background_color)
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=25, pady=(20, 10))
        
        # Bind mouse events for dragging and resizing
        # Bind to toplevel window and main frame to ensure events are captured
        self.window.bind('<Button-1>', self.start_drag)
        self.window.bind('<B1-Motion>', self.on_drag)
        self.window.bind('<ButtonRelease-1>', self.on_release)
        self.window.bind('<Motion>', self.on_motion)
        self.window.bind('<Leave>', lambda e: self.window.config(cursor=""))

        # Also bind Motion to main frame and window to ensure cursor updates work over all widgets
        self.main_frame.bind('<Motion>', self.on_motion)
        self.main_frame.bind('<Button-1>', self.start_drag)
        
        # Update wraplength when geometry changes (e.g., OS-driven resizes)
        self.window.bind('<Configure>', lambda e: self._update_wraplength(self.window.winfo_width()))
        
        # Add a subtle gradient effect using frames
        self.gradient_frame = tk.Frame(self.main_frame, bg=self.background_color, height=2)
        self.gradient_frame.pack(fill=tk.X, pady=(0, 15))
        
        # Song title and artist container
        self.title_frame = tk.Frame(self.main_frame, bg=self.background_color)
        self.title_frame.pack(fill=tk.X, pady=(0, 8))
        # Bind Motion to title frame for cursor updates
        self.title_frame.bind('<Motion>', self.on_motion)
        self.title_frame.bind('<Button-1>', self.start_drag)

        # Close button positioned near the top-right corner of the floating window
        self.close_button = tk.Button(
            self.window,
            text="✕",
            font=(self.selected_font, max(10, self.font_size - 2), 'normal'),
            bg=self.theme_colors.get("floating_close_bg", self.background_color),
            fg=self.theme_colors.get("floating_close_fg", SPOTIFY_LIGHT_GRAY),
            activebackground=self.theme_colors.get("floating_close_bg", SPOTIFY_GRAY),
            activeforeground=self.theme_colors.get("floating_close_fg", SPOTIFY_WHITE),
            bd=0,
            highlightthickness=0,
            padx=8,
            pady=2,
            relief=tk.FLAT,
            cursor="hand2",
            command=self.close
        )
        self.close_button.place(relx=1.0, rely=0.0, x=-2, y=2, anchor='ne')
        self.close_button.lift()

        # Calculate font styles based on settings
        song_font_style = 'bold' if self.font_bold else 'normal'
        artist_font_style = 'normal' if self.font_bold else 'normal'  # Artist stays normal

        # Song title with modern typography
        self.song_label = tk.Label(
            self.title_frame,
            text="No song playing",
            font=(self.selected_font, self.font_size, 'bold'),  # Song title always bold
            bg=self.background_color,
            fg=self.theme_colors.get("floating_title_fg", SPOTIFY_GREEN),
            anchor='w'
        )
        self.song_label.pack(side=tk.LEFT)
        # Bind Motion to label for cursor updates
        self.song_label.bind('<Motion>', self.on_motion)
        self.song_label.bind('<Button-1>', self.start_drag)

        # Artist name with subtle styling (right-aligned)
        self.artist_label = tk.Label(
            self.title_frame,
            text="",
            font=(self.selected_font, max(8, self.font_size - 2), artist_font_style),
            bg=self.background_color,
            fg=self.theme_colors.get("floating_artist_fg", SPOTIFY_LIGHT_GRAY),
            anchor='e'
        )
        self.artist_label.pack(side=tk.RIGHT)
        # Bind Motion to label for cursor updates
        self.artist_label.bind('<Motion>', self.on_motion)
        self.artist_label.bind('<Button-1>', self.start_drag)

        # Lyric rows: the line playing now in the middle, with neighbours above and below when showing 3 or 5.
        # Each row is (main label, second label); the middle row's labels are original_label/translated_label.
        self.lines_frame = tk.Frame(self.main_frame, bg=self.background_color)
        self.lines_frame.pack(fill=tk.X)
        self.lines_frame.bind('<Motion>', self.on_motion)
        self.lines_frame.bind('<Button-1>', self.start_drag)
        self.rows = []
        self.locked = False
        self._load_options(settings)
        self._build_rows()

        # Playback controls container (below lyrics, centered)
        self.controls_frame = tk.Frame(self.main_frame, bg=self.background_color)
        self.controls_frame.pack(fill=tk.X, pady=(8, 2))  # Reduced bottom padding
        # Bind Motion to controls frame for cursor updates
        self.controls_frame.bind('<Motion>', self.on_motion)
        self.controls_frame.bind('<Button-1>', self.start_drag)

        # Add a small invisible spacer at the bottom to ensure resize area is accessible
        self.bottom_spacer = tk.Frame(self.main_frame, bg=self.background_color, height=3)
        self.bottom_spacer.pack(fill=tk.X, side=tk.BOTTOM)
        self.bottom_spacer.bind('<Motion>', self.on_motion)
        self.bottom_spacer.bind('<Button-1>', self.start_drag)
        self.bottom_spacer.bind('<B1-Motion>', self.on_drag)
        self.bottom_spacer.bind('<ButtonRelease-1>', self.on_release)

        # Centering container for controls
        self.controls_center = tk.Frame(self.controls_frame, bg=self.background_color)
        self.controls_center.pack(expand=True)
        # Bind Motion to controls center for cursor updates
        self.controls_center.bind('<Motion>', self.on_motion)
        self.controls_center.bind('<Button-1>', self.start_drag)

        # Button styling - smaller icons, no green flash
        button_bg = self.theme_colors.get("floating_button_bg", self.theme_colors.get("floating_bg", "#181818"))
        button_fg = self.theme_colors.get("floating_button_fg", self.theme_colors.get("floating_original_fg", "#FFFFFF"))
        # Use same background for active state to remove green flash
        button_active_bg = button_bg
        button_font = (self.selected_font, max(8, self.font_size - 4), 'normal')
        icon_font = (self.selected_font, max(10, self.font_size - 2), 'bold')

        # Left side: Seek backward button (with text label)
        self.seek_back_frame = tk.Frame(self.controls_center, bg=self.background_color)
        self.seek_back_frame.pack(side=tk.LEFT, padx=(0, 6))
        self.seek_back_button = tk.Button(
            self.seek_back_frame,
            text="−10s",
            font=button_font,
            bg=button_bg,
            fg=button_fg,
            activebackground=button_active_bg,
            activeforeground=button_fg,
            bd=0,
            relief=tk.FLAT,
            cursor="hand2",
            padx=6,
            pady=3,
            command=self.seek_backward
        )
        self.seek_back_button.pack()

        # Previous track button
        self.prev_button = tk.Button(
            self.controls_center,
            text="◀◀",  # Changed from ⏮ to ◀◀
            font=icon_font,
            bg=button_bg,
            fg=button_fg,
            activebackground=button_active_bg,
            activeforeground=button_fg,
            bd=0,
            relief=tk.FLAT,
            cursor="hand2",
            padx=8,
            pady=3,
            command=self.previous_track
        )
        self.prev_button.pack(side=tk.LEFT, padx=(0, 3))

        # Play/Pause button (slightly larger but still reduced, fixed width to prevent shifting)
        self.play_pause_button = tk.Button(
            self.controls_center,
            text="▶",  # Will be updated to ⏸ when playing
            font=(self.selected_font, max(12, self.font_size), 'bold'),
            bg=button_bg,
            fg=button_fg,
            activebackground=button_active_bg,
            activeforeground=button_fg,
            bd=0,
            relief=tk.FLAT,
            cursor="hand2",
            padx=10,
            pady=3,
            width=3,  # Fixed width to prevent icon shifting
            anchor='center',
            command=self.play_pause
        )
        self.play_pause_button.pack(side=tk.LEFT, padx=(3, 3))

        # Next track button
        self.next_button = tk.Button(
            self.controls_center,
            text="▶▶",  # Changed from ⏭ to ▶▶
            font=icon_font,
            bg=button_bg,
            fg=button_fg,
            activebackground=button_active_bg,
            activeforeground=button_fg,
            bd=0,
            relief=tk.FLAT,
            cursor="hand2",
            padx=8,
            pady=3,
            command=self.next_track
        )
        self.next_button.pack(side=tk.LEFT, padx=(3, 6))

        # Right side: Seek forward button (with text label)
        self.seek_forward_frame = tk.Frame(self.controls_center, bg=self.background_color)
        self.seek_forward_frame.pack(side=tk.LEFT)
        self.seek_forward_button = tk.Button(
            self.seek_forward_frame,
            text="+10s",
            font=button_font,
            bg=button_bg,
            fg=button_fg,
            activebackground=button_active_bg,
            activeforeground=button_fg,
            bd=0,
            relief=tk.FLAT,
            cursor="hand2",
            padx=6,
            pady=3,
            command=self.seek_forward
        )
        self.seek_forward_button.pack()

        # Set initial wraplength based on window width
        self._update_wraplength(_init_w)

        # Apply theme colors to all widgets
        self.apply_colors()

        # Start fade-in animation
        self.fade_in(target_alpha=self.target_alpha)
    
    def start_drag(self, event):
        """Start dragging or resizing the window.

        Args:
            event: Mouse event
        """
        # Capture starting positions and geometry in screen coordinates
        self.start_x_root = event.x_root
        self.start_y_root = event.y_root
        self.start_win_x = self.window.winfo_x()
        self.start_win_y = self.window.winfo_y()
        self.start_width = self.window.winfo_width()
        self.start_height = self.window.winfo_height()

        # Get consistent relative coordinates using the same method as on_motion
        x_rel, y_rel = self._get_relative_coordinates(event)

        width = self.start_width
        height = self.start_height
        margin = self.resize_margin

        # Determine which edge/corner is being grabbed (using coordinates relative to window)
        left = x_rel < margin
        right = x_rel > width - margin
        top = y_rel < margin
        bottom = y_rel > height - margin

        # Check if over close button - but only if not on an edge
        if not (left or right or top or bottom) and self._pointer_over_close_button(event.x_root, event.y_root):
            self.resize_edge = None
            return

        # Priority: corners first, then edges
        if left and top:
            self.resize_edge = "nw"
        elif right and top:
            self.resize_edge = "ne"
        elif left and bottom:
            self.resize_edge = "sw"
        elif right and bottom:
            self.resize_edge = "se"
        elif left:
            self.resize_edge = "w"
        elif right:
            self.resize_edge = "e"
        elif top:
            self.resize_edge = "n"
        elif bottom:
            self.resize_edge = "s"
        else:
            self.resize_edge = None  # Regular drag
    
    def on_drag(self, event):
        """Handle window dragging or resizing.

        Args:
            event: Mouse event
        """
        if self.resize_edge:
            # Handle resizing
            self.on_resize(event)
        else:
            # Handle dragging using root (screen) coordinates for stability
            dx = event.x_root - self.start_x_root
            dy = event.y_root - self.start_y_root
            x = self.start_win_x + dx
            y = self.start_win_y + dy
            self.window.geometry(f"+{x}+{y}")

    def on_release(self, event):
        """Reset resize state on mouse release."""
        self.resize_edge = None

    def on_resize(self, event):
        """Handle window resizing using stable starting geometry.

        Args:
            event: Mouse event
        """
        # Calculate deltas in screen coordinates from the initial press
        dx = event.x_root - self.start_x_root
        dy = event.y_root - self.start_y_root

        x = self.start_win_x
        y = self.start_win_y
        width = self.start_width
        height = self.start_height

        # Minimum constraints
        min_width = 400
        min_height = 150

        if "w" in self.resize_edge:  # Left edge
            new_x = self.start_win_x + dx
            new_width = self.start_width - dx
            if new_width < min_width:
                # Clamp so width does not go below minimum
                new_x = self.start_win_x + (self.start_width - min_width)
                new_width = min_width
            x = new_x
            width = new_width

        if "e" in self.resize_edge:  # Right edge
            new_width = self.start_width + dx
            if new_width < min_width:
                new_width = min_width
            width = new_width

        if "n" in self.resize_edge:  # Top edge
            new_y = self.start_win_y + dy
            new_height = self.start_height - dy
            if new_height < min_height:
                new_y = self.start_win_y + (self.start_height - min_height)
                new_height = min_height
            y = new_y
            height = new_height

        if "s" in self.resize_edge:  # Bottom edge
            new_height = self.start_height + dy
            if new_height < min_height:
                new_height = min_height
            height = new_height

        # Apply new geometry
        self.window.geometry(f"{int(width)}x{int(height)}+{int(x)}+{int(y)}")

        # Update label wraplength based on new width
        self._update_wraplength(int(width))

    def on_motion(self, event):
        """Update cursor based on mouse position for resize feedback.

        Args:
            event: Mouse event
        """
        pointer_x = self.window.winfo_pointerx()
        pointer_y = self.window.winfo_pointery()
        if self._pointer_over_close_button(pointer_x, pointer_y):
            self.window.config(cursor="")
            return

        # Get consistent relative coordinates
        x_rel, y_rel = self._get_relative_coordinates(event)

        width = self.window.winfo_width()
        height = self.window.winfo_height()
        margin = self.resize_margin

        # Determine cursor based on position relative to window
        left = x_rel < margin
        right = x_rel > width - margin
        top = y_rel < margin
        bottom = y_rel > height - margin

        # Use Tk-supported cursor names for cross-platform compatibility
        if left and top:
            cursor = "top_left_corner"
        elif right and top:
            cursor = "top_right_corner"
        elif left and bottom:
            cursor = "bottom_left_corner"
        elif right and bottom:
            cursor = "bottom_right_corner"
        elif left:
            cursor = "left_side"
        elif right:
            cursor = "right_side"
        elif top:
            cursor = "top_side"
        elif bottom:
            cursor = "bottom_side"
        else:
            cursor = ""

        self.window.config(cursor=cursor)

    def _update_wraplength(self, window_width):
        """Update the wraplength of labels based on window width.

        Args:
            window_width: Current window width
        """
        # Account for padding (25px on each side from main_frame)
        available_width = window_width - 50
        for main, second in self.rows:
            main.config(wraplength=available_width)
            second.config(wraplength=available_width)

    def _get_relative_coordinates(self, event):
        """Get mouse coordinates relative to the toplevel window.

        Args:
            event: Mouse event

        Returns:
            tuple: (x_rel, y_rel) coordinates relative to window
        """
        # Primary method: use pointer position relative to window root
        try:
            x_rel = self.window.winfo_pointerx() - self.window.winfo_rootx()
            y_rel = self.window.winfo_pointery() - self.window.winfo_rooty()
            return x_rel, y_rel
        except Exception:
            pass

        # Fallback: convert widget coordinates to toplevel coordinates
        try:
            widget_x = event.widget.winfo_rootx() - self.window.winfo_rootx()
            widget_y = event.widget.winfo_rooty() - self.window.winfo_rooty()
            x_rel = widget_x + event.x
            y_rel = widget_y + event.y
            return x_rel, y_rel
        except Exception:
            pass

        # Last resort: use event coordinates directly (may not be accurate)
        return getattr(event, 'x', 0), getattr(event, 'y', 0)

    def _pointer_over_close_button(self, x_root, y_root):
        """Check if the current pointer position overlaps the close button."""
        if not hasattr(self, 'close_button') or not self.close_button:
            return False
        try:
            btn_x = self.close_button.winfo_rootx()
            btn_y = self.close_button.winfo_rooty()
            btn_w = self.close_button.winfo_width()
            btn_h = self.close_button.winfo_height()
        except Exception:
            return False

        return btn_x <= x_root <= btn_x + btn_w and btn_y <= y_root <= btn_y + btn_h

    def _load_options(self, settings):
        """Read the floating window options (lines, translation only, style, opacity) from settings."""
        count = settings.get("floating_lines", 1)
        self.line_count = count if count in FLOATING_LINE_COUNTS else 1
        self.translation_only = bool(settings.get("floating_translation_only", False))
        style = settings.get("floating_style", "Dark")
        self.style = style if style in FLOATING_STYLES else "Dark"
        try:
            opacity = float(settings.get("floating_opacity", 0.9))
        except (TypeError, ValueError):
            opacity = 0.9
        # Clear has no background to make translucent
        self.target_alpha = 1.0 if self.style == "Clear" else max(FLOATING_MIN_OPACITY, min(1.0, opacity))

    def _style_colors(self):
        """Background and text colors for the current style. Dark uses the Appearance settings."""
        theme = self.theme_colors
        if self.style == "Light":
            return {
                "bg": LIGHT_BG, "border": "#DDDDDD", "title_fg": "#121212", "artist_fg": "#555555",
                "original_fg": "#121212", "translated_fg": "#333333", "close_bg": LIGHT_BG, "close_fg": "#555555",
                "button_bg": LIGHT_BG, "button_fg": "#121212",
            }
        colors = {
            "bg": theme.get("floating_bg", "#181818"),
            "border": theme.get("floating_border", "#1DB954"),
            "title_fg": theme.get("floating_title_fg", "#1DB954"),
            "artist_fg": theme.get("floating_artist_fg", "#B3B3B3"),
            "original_fg": theme.get("floating_original_fg", "#FFFFFF"),
            "translated_fg": theme.get("floating_translated_fg", "#FFFFFF"),
            "close_bg": theme.get("floating_close_bg", theme.get("floating_bg", "#181818")),
            "close_fg": theme.get("floating_close_fg", "#B3B3B3"),
            "button_bg": theme.get("floating_button_bg", theme.get("floating_bg", "#181818")),
            "button_fg": theme.get("floating_button_fg", theme.get("floating_original_fg", "#FFFFFF")),
        }
        if self.style == "Clear":
            # Every pixel in this color is see-through (Windows); near black, so anti-aliased edges read as a shadow
            colors.update({"bg": CLEAR_KEY, "border": CLEAR_HANDLE, "close_bg": CLEAR_HANDLE, "button_bg": CLEAR_HANDLE})
        return colors

    def _row_fonts(self, is_current):
        """Fonts of a row's main and second label."""
        second_style = 'bold' if self.font_bold else 'normal'
        if is_current:
            return (self.selected_font, self.font_size + 6, 'normal'), (self.selected_font, self.font_size + 2, second_style)
        return (self.selected_font, self.font_size + 2, 'normal'), (self.selected_font, self.font_size, second_style)

    def _build_rows(self):
        """(Re)create one row per shown line; the middle row is the line playing now."""
        for main, second in self.rows:
            main.destroy()
            second.destroy()
        self.rows = []
        # Every row has room for a translation when showing several, so the window keeps its height from line to line
        show_second = not self.translation_only
        for i in range(self.line_count):
            is_current = i == self.line_count // 2
            main_font, second_font = self._row_fonts(is_current)
            main = tk.Label(self.lines_frame, text="", font=main_font, bg=self.background_color, anchor='w', justify='left')
            second = tk.Label(self.lines_frame, text="", font=second_font, bg=self.background_color, anchor='w', justify='left')
            main.pack(fill=tk.X, pady=(0, 2) if show_second else (0, 6))
            if show_second:
                second.pack(fill=tk.X, pady=(0, 8))
            for label in (main, second):
                label.bind('<Motion>', self.on_motion)
                label.bind('<Button-1>', self.start_drag)
            self.rows.append((main, second))
        self.original_label, self.translated_label = self.rows[self.line_count // 2]
        self._built_layout = (self.line_count, self.translation_only)
        try:
            self._update_wraplength(self.window.winfo_width())
        except Exception:
            pass

    def _row_texts(self, lyrics, index):
        """(main, second) texts of the rows around line index, that line in the middle; rows off the lyrics are blank."""
        half = self.line_count // 2
        texts = []
        for i in range(index - half, index + half + 1):
            if not lyrics or not 0 <= i < len(lyrics):
                texts.append(("", ""))
                continue
            original = lyrics[i].get('words', '')
            translation = (lyrics[i].get('translated') or '').strip()
            if self.translation_only:
                # No translation (yet, or the song is already in the target language): the original beats an empty row
                texts.append((translation or original, ""))
            else:
                texts.append((original, translation))
        return texts

    def update_lyrics(self, song_name, artist_name=None, lyrics=None, index=-1, position_ms=0, duration_ms=0, translated_title=None):
        """Update the displayed lyrics.

        Args:
            song_name: Name of the current song
            artist_name: Name of the artist (optional)
            lyrics: List of dicts with 'words' and 'translated' keys, or None to show no lyrics
            index: Index of the line playing now in lyrics; -1 before the first line
            position_ms: Current playback position in milliseconds
            duration_ms: Total song duration in milliseconds
            translated_title: Optional translated song title
        """

        if song_name:
            # Display both original and translated titles if available
            if translated_title and translated_title != song_name:
                display_title = f"{song_name} ({translated_title})"
                self.song_label.config(text=display_title)
            else:
                self.song_label.config(text=song_name)

            # Display artist name if available
            if artist_name:
                self.artist_label.config(text=f"By {artist_name}")
            else:
                self.artist_label.config(text="")
        else:
            self.song_label.config(text="No song playing")
            self.artist_label.config(text="")

        current = self.line_count // 2
        for i, ((main_label, second_label), (main_text, second_text)) in enumerate(zip(self.rows, self._row_texts(lyrics, index))):
            if i == current:
                # Add text transition effect
                self._transition_text(main_label, main_text, self.colors["original_fg"])
                self._transition_text(second_label, second_text, self.colors["translated_fg"])
            else:
                main_label.config(text=main_text)
                second_label.config(text=second_text)

    def _transition_text(self, label, new_text, color, steps=3):
        """Smoothly transition text in a label.

        Args:
            label: The label to update
            new_text: The new text to display
            color: The label's text color once the transition ends
            steps: Number of steps for the transition
        """
        current_text = label.cget("text")
        if current_text == new_text:
            return
        if self.style == "Clear":
            # Blending toward the see-through color would flash dark text
            label.config(text=new_text, fg=color)
            return

        # Fade out
        def fade_out(step=0):
            if step < steps:
                label.config(fg=self._adjust_color_alpha(color, 1.0 - (step / steps)))
                label.after(0, lambda: fade_out(step + 1))
            else:
                # Change text
                label.config(text=new_text)
                # Fade in
                fade_in(0)

        # Fade in
        def fade_in(step=0):
            if step < steps:
                label.config(fg=self._adjust_color_alpha(color, step / steps))
                label.after(0, lambda: fade_in(step + 1))
            else:
                # Reset to full color
                label.config(fg=color)

        fade_out()

    def _adjust_color_alpha(self, hex_color, alpha):
        """Adjust the alpha of a hex color by blending with background.

        Args:
            hex_color: Hex color code
            alpha: Alpha value (0.0 to 1.0)

        Returns:
            str: Adjusted hex color
        """
        # Convert hex to RGB
        hex_color = hex_color.lstrip('#')
        r, g, b = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

        # Use actual floating background color for blending
        bg_color = self.colors["bg"].lstrip('#')
        bg_r, bg_g, bg_b = tuple(int(bg_color[i:i+2], 16) for i in (0, 2, 4))

        # Blend with background based on alpha
        r = int(r * alpha + bg_r * (1 - alpha))
        g = int(g * alpha + bg_g * (1 - alpha))
        b = int(b * alpha + bg_b * (1 - alpha))

        # Convert back to hex
        return f'#{r:02x}{g:02x}{b:02x}'

    def fade_in(self, step=0.05, target_alpha=0.9):
        """Fade in the window with a smooth animation.

        Args:
            step: Increment for alpha value in each step
            target_alpha: Target alpha value for the window
        """
        current_alpha = self.window.attributes('-alpha')
        if current_alpha < target_alpha:
            new_alpha = min(current_alpha + step, target_alpha)
            self.window.attributes('-alpha', new_alpha)
            self.window.after(20, lambda: self.fade_in(step, target_alpha))
        else:
            # Changing the alpha can drop the click-through style
            self._apply_lock()

    def set_locked(self, locked):
        """Lock: clicks pass through the window to whatever is underneath (Windows only)."""
        self.locked = locked
        self._apply_lock()

    def _apply_lock(self):
        if sys.platform != "win32" or not self.is_open():
            return
        try:
            user32 = ctypes.windll.user32
            hwnd = int(self.window.wm_frame(), 16)
            style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            if self.locked:
                if not style & WS_EX_LAYERED:
                    # Tk drops the layered style at full opacity; a layered window stays hidden until given an alpha
                    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED)
                    user32.SetLayeredWindowAttributes(hwnd, 0, 255, LWA_ALPHA)
                    style |= WS_EX_LAYERED
                user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_TRANSPARENT)
            else:
                user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style & ~WS_EX_TRANSPARENT)
        except Exception as e:
            logger.warning(f"Could not change floating window lock: {e}")

    def fade_out(self, step=0.05, callback=None):
        """Fade out the window with a smooth animation.
        
        Args:
            step: Decrement for alpha value in each step
            callback: Function to call after fade out completes
        """
        current_alpha = self.window.attributes('-alpha')
        if current_alpha > 0:
            new_alpha = max(current_alpha - step, 0)
            self.window.attributes('-alpha', new_alpha)
            self.window.after(20, lambda: self.fade_out(step, callback))
        elif callback:
            callback()
    
    def close(self):
        """Close the floating window with fade-out animation."""
        self.fade_out(callback=self._destroy_window)
    
    def _destroy_window(self):
        """Actually destroy the window after fade out."""
        if self.window:
            # Persist current size before destroying
            try:
                self._save_window_size()
            except Exception:
                pass
            self.window.destroy()
            self.window = None
    
    def is_open(self):
        """Check if the window is still open.
        
        Returns:
            bool: True if window exists and is open
        """
        try:
            return self.window and self.window.winfo_exists()
        except:
            return False

    def get_selected_font(self):
        """Get the currently selected floating window font from settings."""
        settings = read_translation_settings()
        return settings.get("floating_font", get_default_chinese_font())
    
    def update_font(self, font_name):
        """Update the font used by all labels in the floating window.

        Args:
            font_name: The new font name to use
        """
        # Legacy method for backward compatibility
        self.update_font_settings(font_name, 12, True)

    def update_font_settings(self, font_name, font_size, is_bold):
        """Update the font settings used by all labels in the floating window.

        Args:
            font_name: The new font name to use
            font_size: The base font size
            is_bold: Whether to use bold text
        """
        # Update instance variables
        self.selected_font = font_name
        self.font_size = font_size
        self.font_bold = is_bold

        # Calculate font styles based on settings
        song_font_style = 'bold'  # Song title always bold
        artist_font_style = 'normal'  # Artist stays normal for subtlety

        # Apply font settings with appropriate scaling
        self.song_label.config(font=(font_name, font_size, song_font_style))
        self.artist_label.config(font=(font_name, max(8, font_size - 2), artist_font_style))
        if hasattr(self, 'close_button') and self.close_button:
            self.close_button.config(font=(font_name, max(10, font_size - 2), 'normal'))
        current = len(self.rows) // 2
        for i, (main, second) in enumerate(self.rows):
            main_font, second_font = self._row_fonts(i == current)
            main.config(font=main_font)
            second.config(font=second_font)

    def apply_colors(self):
        """Apply the floating window options (lines, style, opacity) and theme colors to the window."""
        # Reload options and theme colors
        self._load_options(read_translation_settings())
        self.theme_colors = get_theme_colors()
        self.colors = self._style_colors()
        self.background_color = self.colors["bg"]

        if getattr(self, '_built_layout', None) != (self.line_count, self.translation_only):
            self._build_rows()
            # Grow the window to fit more rows; never shrink what the user sized
            try:
                self.window.update_idletasks()
                needed = self.window.winfo_reqheight()
                if needed > self.window.winfo_height():
                    self.window.geometry(f"{self.window.winfo_width()}x{needed}")
            except Exception:
                pass

        # Update window background, border and see-through color
        try:
            self.window.configure(bg=self.background_color)
            # In Clear, the border is what can be grabbed to resize, so it spans the whole resize margin
            self.window.configure(
                highlightbackground=self.colors["border"],
                highlightthickness=self.resize_margin if self.style == "Clear" else 1,
            )
            self.window.attributes('-transparentcolor', CLEAR_KEY if self.style == "Clear" else '')
        except Exception:
            pass

        # Update all widget backgrounds
        background_widgets = [
            getattr(self, 'main_frame', None),
            getattr(self, 'gradient_frame', None),
            getattr(self, 'title_frame', None),
            getattr(self, 'lines_frame', None),
            getattr(self, 'controls_frame', None),
            getattr(self, 'controls_center', None),
            getattr(self, 'bottom_spacer', None),
            getattr(self, 'seek_back_frame', None),
            getattr(self, 'seek_forward_frame', None),
        ]

        for widget in background_widgets:
            if widget is None:
                continue
            try:
                widget.configure(bg=self.background_color)
            except Exception:
                pass

        # Update foreground colors for labels
        try:
            if hasattr(self, 'song_label') and self.song_label:
                self.song_label.configure(bg=self.background_color, fg=self.colors["title_fg"])
            if hasattr(self, 'artist_label') and self.artist_label:
                self.artist_label.configure(bg=self.background_color, fg=self.colors["artist_fg"])
            # Lines other than the one playing now are dimmed
            current = len(self.rows) // 2
            for i, (main, second) in enumerate(self.rows):
                alpha = 1.0 if i == current else 0.45
                main.configure(bg=self.background_color, fg=self._adjust_color_alpha(self.colors["original_fg"], alpha))
                second.configure(bg=self.background_color, fg=self._adjust_color_alpha(self.colors["translated_fg"], alpha))
            if hasattr(self, 'close_button') and self.close_button:
                self.close_button.configure(
                    bg=self.colors["close_bg"],
                    fg=self.colors["close_fg"],
                    activebackground=self.colors["close_bg"],
                    activeforeground=self.colors["close_fg"]
                )
            # Update playback control buttons
            button_bg = self.colors["button_bg"]
            button_fg = self.colors["button_fg"]
            # Use same background for active state to remove green flash
            button_active_bg = button_bg

            for button in (
                getattr(self, 'seek_back_button', None),
                getattr(self, 'prev_button', None),
                getattr(self, 'play_pause_button', None),
                getattr(self, 'next_button', None),
                getattr(self, 'seek_forward_button', None),
            ):
                if button:
                    button.configure(
                        bg=button_bg,
                        fg=button_fg,
                        activebackground=button_active_bg,
                        activeforeground=button_fg
                    )
        except Exception:
            pass

        # Apply the opacity; while the window is still invisible, the fade-in runs to target_alpha itself
        try:
            if self.window.attributes('-alpha') > 0:
                self.window.attributes('-alpha', self.target_alpha)
        except Exception:
            pass
        self._apply_lock()

    def play_pause(self):
        """Toggle play/pause for Spotify playback."""
        if self.spotify_client:
            # Optimistic update: immediately toggle the button icon
            current_text = self.play_pause_button.cget("text")
            self.play_pause_button.config(text="⏸" if current_text == "▶" else "▶")
            
            # Record the timestamp to prevent polling from overriding our update
            self._last_play_pause_click = time.monotonic()
            logger.debug(f"Set click timestamp: {self._last_play_pause_click}")

            # Make the API call asynchronously to avoid blocking UI
            def toggle_playback():
                try:
                    success = self.spotify_client.play_pause()
                    # No need to update button here - let polling handle it
                except Exception as e:
                    logger.error(f"Error toggling playback: {e}")

            # Execute API call in background thread
            threading.Thread(target=toggle_playback, daemon=True).start()
        else:
            logger.warning("No Spotify client available for playback control")

    def next_track(self):
        """Skip to the next track."""
        if self.spotify_client:
            self._execute_with_feedback(self.next_button, self.spotify_client.next_track)
        else:
            logger.warning("No Spotify client available for playback control")

    def previous_track(self):
        """Go to the previous track."""
        if self.spotify_client:
            self._execute_with_feedback(self.prev_button, self.spotify_client.previous_track)
        else:
            logger.warning("No Spotify client available for playback control")

    def seek_forward(self):
        """Seek forward 10 seconds."""
        if self.spotify_client:
            self._execute_with_feedback(self.seek_forward_button, lambda: self.spotify_client.seek_forward(10))
        else:
            logger.warning("No Spotify client available for playback control")

    def seek_backward(self):
        """Seek backward 10 seconds."""
        if self.spotify_client:
            self._execute_with_feedback(self.seek_back_button, lambda: self.spotify_client.seek_backward(10))
        else:
            logger.warning("No Spotify client available for playback control")

    def _execute_with_feedback(self, button, action_func):
        """Execute an action with immediate visual feedback."""
        if not button:
            return

        # Execute the action asynchronously
        def execute_action():
            try:
                action_func()
            except Exception as e:
                logger.error(f"Error executing action: {e}")

        # Run in background thread
        threading.Thread(target=execute_action, daemon=True).start()

    def update_play_pause_button(self, is_playing=None):
        """Update the play/pause button icon.

        Args:
            is_playing: Optional bool indicating current playback state. When
                provided, avoids querying Spotify from the UI thread.
        """
        if not hasattr(self, 'play_pause_button'):
            return

        current_time = time.monotonic()
        
        # Check if we recently clicked the button
        if hasattr(self, '_last_play_pause_click') and self._last_play_pause_click > 0:
            time_since_click = current_time - self._last_play_pause_click
            logger.debug(f"Time since click: {time_since_click}s")
            
            # During grace period (3 seconds), completely skip updates
            if time_since_click < 3.0:
                logger.debug("Skipping button update due to recent click")
                return
            else:
                # Grace period expired, but add a short debounce to prevent rapid updates
                time_since_grace = time_since_click - 3.0
                if time_since_grace < 0.5:  # 500ms debounce after grace period
                    logger.debug(f"Debouncing after grace period: {time_since_grace}s")
                    return
                else:
                    # Clear the timestamp after debounce period
                    self._last_play_pause_click = 0

        # Debounce rapid successive updates (only update if 200ms have passed since last update)
        if hasattr(self, '_last_update_time') and current_time - self._last_update_time < 0.2:
            logger.debug("Debouncing rapid update")
            return

        state_known = is_playing is not None

        if not state_known and self.spotify_client:
            try:
                state = self.spotify_client.get_playback_state()
                if state:
                    is_playing = state.get('is_playing', False)
                    state_known = True
            except Exception as e:
                logger.error(f"Error updating play_pause_button: {e}")

        if state_known:
            new_text = "⏸" if is_playing else "▶"
            current_text = self.play_pause_button.cget("text")
            
            # Only update if the state actually changed
            if current_text != new_text:
                logger.debug(f"Updating button to: {new_text}")
                self.play_pause_button.config(text=new_text)
                self._last_update_time = current_time
            else:
                logger.debug(f"Button already shows correct state: {new_text}")
        else:
            logger.debug("Updating button to play (unknown state)")
            self.play_pause_button.config(text="▶")
            self._last_update_time = current_time

    def update_background_color(self, color: str):
        """Update the floating window background color."""
        # For backward compatibility, accept a direct color parameter
        if color:
            # If a specific color is provided, override the theme color temporarily
            self.background_color = color
        else:
            # Otherwise reload from theme
            self.apply_colors()
            return

        try:
            self.window.configure(bg=self.background_color)
        except Exception:
            pass

        widgets = [
            getattr(self, 'main_frame', None),
            getattr(self, 'gradient_frame', None),
            getattr(self, 'title_frame', None),
            getattr(self, 'controls_frame', None),
            getattr(self, 'controls_center', None),
            getattr(self, 'bottom_spacer', None),
            getattr(self, 'song_label', None),
            getattr(self, 'artist_label', None),
            getattr(self, 'original_label', None),
            getattr(self, 'translated_label', None),
            getattr(self, 'close_button', None),
        ]

        for widget in widgets:
            if widget is None:
                continue
            try:
                widget.configure(bg=self.background_color)
            except Exception:
                pass

    def _save_window_size(self):
        """Persist the current floating window size to translation settings."""
        try:
            cur_w = self.window.winfo_width()
            cur_h = self.window.winfo_height()
            settings = read_translation_settings()
            settings["floating_window_width"] = int(cur_w)
            settings["floating_window_height"] = int(cur_h)
            save_translation_settings(settings)
        except Exception:
            # Best-effort; ignore persistence failures
            return

