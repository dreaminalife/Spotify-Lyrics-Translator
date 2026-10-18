"""Spotify's web login in a window; prints the sp_dc cookie to stdout once it appears.

Run as its own process (python -m src.spotify_login) because pywebview needs the main thread, which Tk owns in the app.
The window runs in private mode, so the login isn't kept once it closes. Google sign-in refuses to run in embedded
browsers; those users paste the cookie in Settings instead.
"""
import webview

LOGIN_URL = "https://accounts.spotify.com/login?continue=https%3A%2F%2Fopen.spotify.com%2F"


def read_sp_dc(window):
    for cookie in window.get_cookies():
        if "sp_dc" in cookie and cookie["sp_dc"].value:
            return cookie["sp_dc"].value
    return None


def main():
    window = webview.create_window("Log in to Spotify", LOGIN_URL, width=500, height=750)
    captured = []

    def on_loaded():
        if captured:
            return
        sp_dc = read_sp_dc(window)
        if sp_dc:
            captured.append(sp_dc)
            window.destroy()

    window.events.loaded += on_loaded
    webview.start(private_mode=True)
    if captured:
        print(captured[0], flush=True)


if __name__ == "__main__":
    main()
