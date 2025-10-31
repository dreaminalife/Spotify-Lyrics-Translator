"""Floating lyrics window implementation."""
import tkinter as tk
from tkinter import ttk
from .translation_settings import read_translation_settings
from .font_manager import get_default_chinese_font


class FloatingLyricsWindow:
    """Always-on-top draggable window for displaying current lyrics."""

    def __init__(self, parent, font_name=None, font_size=None, font_bold=None):
        """Initialize the floating lyrics window.

        Args:
            parent: Parent Tkinter window
            font_name: Font name to use (optional, will use settings if not provided)
            font_size: Font size to use (optional, will use settings if not provided)
            font_bold: Whether to use bold font (optional, will use settings if not provided)
        """
        self.window = tk.Toplevel(parent)
        self.window.title("Floating Lyrics")
        self.window.overrideredirect(True)  # Remove window decorations

        # Set font settings - use provided values or get from settings
        if font_name is not None and font_size is not None and font_bold is not None:
            self.selected_font = font_name
            self.font_size = font_size
            self.font_bold = font_bold
        else:
            # Fallback to getting from settings (for backward compatibility)
            self.selected_font = self.get_selected_font()
            settings = read_translation_settings()
            self.font_size = settings.get("floating_font_size", 12)
            self.font_bold = settings.get("floating_font_bold", True)
        
        # Define Spotify-inspired color scheme
        SPOTIFY_BLACK = '#121212'
        SPOTIFY_DARK = '#181818'
        SPOTIFY_GRAY = '#282828'
        SPOTIFY_LIGHT_GRAY = '#B3B3B3'
        SPOTIFY_WHITE = '#FFFFFF'
        SPOTIFY_GREEN = '#1DB954'
        
        # Window configuration with glassmorphic effect
        self.window.attributes('-topmost', True)
        self.window.attributes('-alpha', 0.0)  # Start fully transparent for fade-in effect
        self.window.geometry("800x200+100+100")  # Increased height to prevent text clipping
        self.window.configure(bg=SPOTIFY_BLACK)
        
        # Add a subtle border
        self.window.configure(highlightbackground=SPOTIFY_GREEN, highlightthickness=1)
        
        # Make window draggable
        self.x = 0
        self.y = 0
        self.window.bind('<Button-1>', self.start_drag)
        self.window.bind('<B1-Motion>', self.on_drag)
        
        # Create main frame with glassmorphic effect
        main_frame = tk.Frame(self.window, bg=SPOTIFY_DARK, padx=25, pady=20)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=0, pady=0)
        
        # Add a subtle gradient effect using frames
        gradient_frame = tk.Frame(main_frame, bg=SPOTIFY_BLACK, height=2)
        gradient_frame.pack(fill=tk.X, pady=(0, 15))
        
        # Song title and artist container
        title_frame = tk.Frame(main_frame, bg=SPOTIFY_DARK)
        title_frame.pack(fill=tk.X, pady=(0, 8))

        # Calculate font styles based on settings
        song_font_style = 'bold' if self.font_bold else 'normal'
        artist_font_style = 'normal' if self.font_bold else 'normal'  # Artist stays normal
        original_font_style = 'normal'  # Original lyrics stay normal for readability
        translated_font_style = 'bold' if self.font_bold else 'normal'

        # Song title with modern typography
        self.song_label = tk.Label(
            title_frame,
            text="No song playing",
            font=(self.selected_font, self.font_size, 'bold'),  # Song title always bold
            bg=SPOTIFY_DARK,
            fg=SPOTIFY_GREEN,
            anchor='w'
        )
        self.song_label.pack(side=tk.LEFT)

        # Artist name with subtle styling (right-aligned)
        self.artist_label = tk.Label(
            title_frame,
            text="",
            font=(self.selected_font, max(8, self.font_size - 2), artist_font_style),
            bg=SPOTIFY_DARK,
            fg=SPOTIFY_LIGHT_GRAY,
            anchor='e'
        )
        self.artist_label.pack(side=tk.RIGHT)

        # Original lyrics with larger font
        self.original_label = tk.Label(
            main_frame,
            text="",
            font=(self.selected_font, self.font_size + 6, original_font_style),
            bg=SPOTIFY_DARK,
            fg=SPOTIFY_WHITE,
            anchor='w',
            wraplength=750,
            justify='left'
        )
        self.original_label.pack(fill=tk.X, pady=(0, 8))

        # Translated lyrics with styling
        self.translated_label = tk.Label(
            main_frame,
            text="",
            font=(self.selected_font, self.font_size + 2, translated_font_style),
            bg=SPOTIFY_DARK,
            fg=SPOTIFY_WHITE,
            anchor='w',
            wraplength=750,
            justify='left'
        )
        self.translated_label.pack(fill=tk.X, pady=(4, 10))  # Added padding top and bottom to prevent clipping

        # Current line data
        self.current_line = None
        
        # Start fade-in animation
        self.fade_in()
    
    def start_drag(self, event):
        """Start dragging the window.
        
        Args:
            event: Mouse event
        """
        self.x = event.x
        self.y = event.y
    
    def on_drag(self, event):
        """Handle window dragging.
        
        Args:
            event: Mouse event
        """
        deltax = event.x - self.x
        deltay = event.y - self.y
        x = self.window.winfo_x() + deltax
        y = self.window.winfo_y() + deltay
        self.window.geometry(f"+{x}+{y}")
    
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
        
        # Background color (dark)
        bg_r, bg_g, bg_b = 24, 24, 24  # SPOTIFY_DARK
        
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
        self.original_label.config(font=(font_name, font_size + 6, original_font_style))
        self.translated_label.config(font=(font_name, font_size + 2, translated_font_style))

