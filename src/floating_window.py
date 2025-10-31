"""Floating lyrics window implementation."""
import tkinter as tk
from tkinter import ttk
import threading
from .translation_settings import read_translation_settings, save_translation_settings, get_theme_colors
from .font_manager import get_default_chinese_font


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
        original_font_style = 'normal'  # Original lyrics stay normal for readability
        translated_font_style = 'bold' if self.font_bold else 'normal'

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

        # Original lyrics with larger font
        self.original_label = tk.Label(
            self.main_frame,
            text="",
            font=(self.selected_font, self.font_size + 6, original_font_style),
            bg=self.background_color,
            fg=self.theme_colors.get("floating_original_fg", SPOTIFY_WHITE),
            anchor='w',
            wraplength=750,
            justify='left'
        )
        self.original_label.pack(fill=tk.X, pady=(0, 8))
        # Bind Motion to label for cursor updates
        self.original_label.bind('<Motion>', self.on_motion)
        self.original_label.bind('<Button-1>', self.start_drag)

        # Translated lyrics with styling
        self.translated_label = tk.Label(
            self.main_frame,
            text="",
            font=(self.selected_font, self.font_size + 2, translated_font_style),
            bg=self.background_color,
            fg=self.theme_colors.get("floating_translated_fg", SPOTIFY_WHITE),
            anchor='w',
            wraplength=750,
            justify='left'
        )
        self.translated_label.pack(fill=tk.X, pady=(4, 10))  # Added padding top and bottom to prevent clipping
        # Bind Motion to label for cursor updates
        self.translated_label.bind('<Motion>', self.on_motion)
        self.translated_label.bind('<Button-1>', self.start_drag)

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
        seek_back_frame = tk.Frame(self.controls_center, bg=self.background_color)
        seek_back_frame.pack(side=tk.LEFT, padx=(0, 6))
        self.seek_back_button = tk.Button(
            seek_back_frame,
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
            text="⏮",
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
            text="⏭",
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
        seek_forward_frame = tk.Frame(self.controls_center, bg=self.background_color)
        seek_forward_frame.pack(side=tk.LEFT)
        self.seek_forward_button = tk.Button(
            seek_forward_frame,
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

        # Current line data
        self.current_line = None

        # Set initial wraplength based on window width
        self._update_wraplength(_init_w)

        # Apply theme colors to all widgets
        self.apply_colors()

        # Start fade-in animation
        self.fade_in()
    
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
        self.original_label.config(wraplength=available_width)
        self.translated_label.config(wraplength=available_width)

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

    def update_lyrics(self, song_name, artist_name=None, current_line=None, position_ms=0, duration_ms=0, translated_title=None):
        """Update the displayed lyrics.

        Args:
            song_name: Name of the current song
            artist_name: Name of the artist (optional)
            current_line: Dictionary with 'words' and 'translated' keys, or None
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

        if current_line:
            original_text = current_line.get('words', '')
            translated_text = current_line.get('translated', '')

            # Add text transition effect
            self._transition_text(self.original_label, original_text)
            self._transition_text(self.translated_label, translated_text)
            self.current_line = current_line
        else:
            self._transition_text(self.original_label, "")
            self._transition_text(self.translated_label, "")
            self.current_line = None
    
    def _transition_text(self, label, new_text, steps=3):
        """Smoothly transition text in a label.
        
        Args:
            label: The label to update
            new_text: The new text to display
            steps: Number of steps for the transition
        """
        current_text = label.cget("text")
        if current_text == new_text:
            return
            
        # Fade out
        def fade_out(step=0):
            if step < steps:
                alpha = 1.0 - (step / steps)
                label.config(fg=self._adjust_color_alpha(label.cget("fg"), alpha))
                label.after(0, lambda: fade_out(step + 1))
            else:
                # Change text
                label.config(text=new_text)
                # Fade in
                fade_in(0)

        # Fade in
        def fade_in(step=0):
            if step < steps:
                alpha = step / steps
                label.config(fg=self._adjust_color_alpha(label.cget("fg"), alpha))
                label.after(0, lambda: fade_in(step + 1))
            else:
                # Reset to full color and correct font
                if label == self.original_label:
                    label.config(fg='#FFFFFF')
                else:
                    translated_font_style = 'bold' if self.font_bold else 'normal'
                    label.config(fg='#FFFFFF', font=(self.selected_font, self.font_size + 2, translated_font_style))
        
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
        bg_color = self.theme_colors.get("floating_bg", "#181818").lstrip('#')
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
        original_font_style = 'normal'  # Original lyrics stay normal for readability
        translated_font_style = 'bold' if is_bold else 'normal'

        # Apply font settings with appropriate scaling
        self.song_label.config(font=(font_name, font_size, song_font_style))
        self.artist_label.config(font=(font_name, max(8, font_size - 2), artist_font_style))
        if hasattr(self, 'close_button') and self.close_button:
            self.close_button.config(font=(font_name, max(10, font_size - 2), 'normal'))
        self.original_label.config(font=(font_name, font_size + 6, original_font_style))
        self.translated_label.config(font=(font_name, font_size + 2, translated_font_style))

    def apply_colors(self):
        """Apply all theme colors to the floating window."""
        # Reload theme colors
        self.theme_colors = get_theme_colors()
        self.background_color = self.theme_colors.get("floating_bg", "#181818")

        # Update window background and border
        try:
            self.window.configure(bg=self.background_color)
            self.window.configure(highlightbackground=self.theme_colors.get("floating_border", "#1DB954"))
        except Exception:
            pass

        # Update all widget backgrounds
        background_widgets = [
            getattr(self, 'main_frame', None),
            getattr(self, 'gradient_frame', None),
            getattr(self, 'title_frame', None),
            getattr(self, 'controls_frame', None),
            getattr(self, 'controls_center', None),
            getattr(self, 'bottom_spacer', None),
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
                self.song_label.configure(
                    bg=self.background_color,
                    fg=self.theme_colors.get("floating_title_fg", "#1DB954")
                )
            if hasattr(self, 'artist_label') and self.artist_label:
                self.artist_label.configure(
                    bg=self.background_color,
                    fg=self.theme_colors.get("floating_artist_fg", "#B3B3B3")
                )
            if hasattr(self, 'original_label') and self.original_label:
                self.original_label.configure(
                    bg=self.background_color,
                    fg=self.theme_colors.get("floating_original_fg", "#FFFFFF")
                )
            if hasattr(self, 'translated_label') and self.translated_label:
                self.translated_label.configure(
                    bg=self.background_color,
                    fg=self.theme_colors.get("floating_translated_fg", "#FFFFFF")
                )
            if hasattr(self, 'close_button') and self.close_button:
                self.close_button.configure(
                    bg=self.theme_colors.get("floating_close_bg", self.background_color),
                    fg=self.theme_colors.get("floating_close_fg", "#B3B3B3"),
                    activebackground=self.theme_colors.get("floating_close_bg", "#282828"),
                    activeforeground=self.theme_colors.get("floating_close_fg", "#FFFFFF")
                )
            # Update playback control buttons
            button_bg = self.theme_colors.get("floating_button_bg", self.theme_colors.get("floating_bg", "#181818"))
            button_fg = self.theme_colors.get("floating_button_fg", self.theme_colors.get("floating_original_fg", "#FFFFFF"))
            # Use same background for active state to remove green flash
            button_active_bg = button_bg

            if hasattr(self, 'seek_back_button') and self.seek_back_button:
                self.seek_back_button.configure(
                    bg=button_bg,
                    fg=button_fg,
                    activebackground=button_active_bg,
                    activeforeground=button_fg
                )
            if hasattr(self, 'prev_button') and self.prev_button:
                self.prev_button.configure(
                    bg=button_bg,
                    fg=button_fg,
                    activebackground=button_active_bg,
                    activeforeground=button_fg
                )
            if hasattr(self, 'play_pause_button') and self.play_pause_button:
                self.play_pause_button.configure(
                    bg=button_bg,
                    fg=button_fg,
                    activebackground=button_active_bg,
                    activeforeground=button_fg
                )
            if hasattr(self, 'next_button') and self.next_button:
                self.next_button.configure(
                    bg=button_bg,
                    fg=button_fg,
                    activebackground=button_active_bg,
                    activeforeground=button_fg
                )
            if hasattr(self, 'seek_forward_button') and self.seek_forward_button:
                self.seek_forward_button.configure(
                    bg=button_bg,
                    fg=button_fg,
                    activebackground=button_active_bg,
                    activeforeground=button_fg
                )
        except Exception:
            pass

    def play_pause(self):
        """Toggle play/pause for Spotify playback."""
        if self.spotify_client:
            # Optimistic update: immediately toggle the button icon
            current_text = self.play_pause_button.cget("text")
            self.play_pause_button.config(text="⏸" if current_text == "▶" else "▶")

            # Make the API call asynchronously to avoid blocking UI
            def toggle_playback():
                try:
                    success = self.spotify_client.play_pause()
                    if success:
                        # Update button to reflect actual state after a brief delay
                        self.window.after(50, self.update_play_pause_button)
                    else:
                        # Revert on failure
                        self.play_pause_button.config(text=current_text)
                except Exception as e:
                    print(f"Error toggling playback: {e}")
                    # Revert on error
                    self.play_pause_button.config(text=current_text)

            # Execute API call in background thread
            threading.Thread(target=toggle_playback, daemon=True).start()
        else:
            print("No Spotify client available for playback control")

    def next_track(self):
        """Skip to the next track."""
        if self.spotify_client:
            self._execute_with_feedback(self.next_button, self.spotify_client.next_track)
        else:
            print("No Spotify client available for playback control")

    def previous_track(self):
        """Go to the previous track."""
        if self.spotify_client:
            self._execute_with_feedback(self.prev_button, self.spotify_client.previous_track)
        else:
            print("No Spotify client available for playback control")

    def seek_forward(self):
        """Seek forward 10 seconds."""
        if self.spotify_client:
            self._execute_with_feedback(self.seek_forward_button, lambda: self.spotify_client.seek_forward(10))
        else:
            print("No Spotify client available for playback control")

    def seek_backward(self):
        """Seek backward 10 seconds."""
        if self.spotify_client:
            self._execute_with_feedback(self.seek_back_button, lambda: self.spotify_client.seek_backward(10))
        else:
            print("No Spotify client available for playback control")

    def _execute_with_feedback(self, button, action_func):
        """Execute an action with immediate visual feedback."""
        if not button:
            return

        # Execute the action asynchronously
        def execute_action():
            try:
                action_func()
            except Exception as e:
                print(f"Error executing action: {e}")

        # Run in background thread
        threading.Thread(target=execute_action, daemon=True).start()

    def update_play_pause_button(self):
        """Update the play/pause button icon based on current playback state."""
        if self.spotify_client and hasattr(self, 'play_pause_button'):
            try:
                state = self.spotify_client.get_playback_state()
                if state:
                    is_playing = state.get('is_playing', False)
                    self.play_pause_button.config(text="⏸" if is_playing else "▶")
                else:
                    self.play_pause_button.config(text="▶")
            except Exception as e:
                print(f"Error updating play/pause button: {e}")
                self.play_pause_button.config(text="▶")

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

