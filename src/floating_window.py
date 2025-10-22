"""Floating lyrics window implementation."""
import tkinter as tk
from tkinter import ttk


class FloatingLyricsWindow:
    """Always-on-top draggable window for displaying current lyrics."""
    
    def __init__(self, parent):
        """Initialize the floating lyrics window.
        
        Args:
            parent: Parent Tkinter window
        """
        self.window = tk.Toplevel(parent)
        self.window.title("Floating Lyrics")
        self.window.overrideredirect(True)  # Remove window decorations
        
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
        self.window.geometry("800x180+100+100")
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
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Add a subtle gradient effect using frames
        gradient_frame = tk.Frame(main_frame, bg=SPOTIFY_BLACK, height=2)
        gradient_frame.pack(fill=tk.X, pady=(0, 15))
        
        # Song title with modern typography
        self.song_label = tk.Label(
            main_frame,
            text="No song playing",
            font=('Circular Std', 12, 'normal'),
            bg=SPOTIFY_DARK,
            fg=SPOTIFY_GREEN,
            anchor='w'
        )
        self.song_label.pack(fill=tk.X, pady=(0, 12))
        
        # Original lyrics with larger, bolder font
        self.original_label = tk.Label(
            main_frame,
            text="",
            font=('Circular Std', 18, 'bold'),
            bg=SPOTIFY_DARK,
            fg=SPOTIFY_WHITE,
            anchor='w',
            wraplength=750,
            justify='left'
        )
        self.original_label.pack(fill=tk.X, pady=(0, 8))
        
        # Translated lyrics with subtle styling
        self.translated_label = tk.Label(
            main_frame,
            text="",
            font=('Circular Std', 14, 'normal'),
            bg=SPOTIFY_DARK,
            fg=SPOTIFY_LIGHT_GRAY,
            anchor='w',
            wraplength=750,
            justify='left'
        )
        self.translated_label.pack(fill=tk.X)
        
        # Progress bar frame with modern styling
        self.progress_frame = tk.Frame(main_frame, bg=SPOTIFY_DARK)
        self.progress_frame.pack(fill=tk.X, pady=(15, 0))
        
        # Create a custom progress bar with better styling
        self.progress_bg = tk.Frame(
            self.progress_frame,
            bg=SPOTIFY_GRAY,
            height=4
        )
        self.progress_bg.pack(fill=tk.X)
        
        self.progress_bar = tk.Frame(
            self.progress_bg,
            bg=SPOTIFY_GREEN,
            height=4
        )
        self.progress_bar.place(x=0, y=0, width=0, height=4)
        
        # Current line data
        self.current_line = None
        self.current_position = 0
        self.song_duration = 0
        
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
    
    def update_lyrics(self, song_name, current_line, position_ms=0, duration_ms=0):
        """Update the displayed lyrics and progress bar.

        Args:
            song_name: Name of the current song
            current_line: Dictionary with 'words' and 'translated' keys, or None
            position_ms: Current playback position in milliseconds
            duration_ms: Total song duration in milliseconds
        """
        print(f"[DEBUG] floating_window.update_lyrics: song_name='{song_name}', current_line={current_line is not None}, position_ms={position_ms}, duration_ms={duration_ms}")

        if song_name:
            self.song_label.config(text=song_name)
            print(f"[DEBUG] floating_window.update_lyrics: Set song name to '{song_name}'")
        else:
            self.song_label.config(text="No song playing")
            print(f"[DEBUG] floating_window.update_lyrics: Set song name to 'No song playing'")

        if current_line:
            original_text = current_line.get('words', '')
            translated_text = current_line.get('translated', '')

            # Add text transition effect
            self._transition_text(self.original_label, original_text)
            self._transition_text(self.translated_label, translated_text)
            self.current_line = current_line
        else:
            print(f"[DEBUG] floating_window.update_lyrics: No current line, clearing display")
            self._transition_text(self.original_label, "")
            self._transition_text(self.translated_label, "")
            self.current_line = None

        # Update progress bar
        self.current_position = position_ms
        self.song_duration = duration_ms
        if duration_ms > 0:
            # Update the progress bar after the frame has been rendered
            self.window.after(10, self._update_progress_bar)
        else:
            print(f"[DEBUG] floating_window.update_lyrics: No duration available for progress bar")
    
    def _transition_text(self, label, new_text, steps=5):
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
                label.after(20, lambda: fade_out(step + 1))
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
                label.after(20, lambda: fade_in(step + 1))
            else:
                # Reset to full color
                if label == self.original_label:
                    label.config(fg='#FFFFFF')
                else:
                    label.config(fg='#B3B3B3')
        
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
    
    def _update_progress_bar(self):
        """Update the progress bar width based on current position and duration."""
        if self.song_duration > 0:
            progress_width = int((self.current_position / self.song_duration) * self.progress_bg.winfo_width())
            self.progress_bar.place(x=0, y=0, width=progress_width, height=4)
            progress_value = (self.current_position / self.song_duration) * 100
            print(f"[DEBUG] _update_progress_bar: Set progress bar to {progress_value:.1f}%")
    
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

