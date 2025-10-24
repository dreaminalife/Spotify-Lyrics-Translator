from __future__ import annotations

import re
from typing import Optional, Protocol, List, Dict, Any
import requests
import logging

from .lyrics_models import TrackMetadata, LyricsPayload, LyricsLine


class BaseLyricsProvider(Protocol):
    def get_lyrics(self, track: TrackMetadata, spotify_track_id: Optional[str] = None) -> Optional[LyricsPayload]:
        ...


class SyricsLyricsProvider:
    def __init__(self, syrics_client):
        self._client = syrics_client

    def get_lyrics(self, track: TrackMetadata, spotify_track_id: Optional[str] = None) -> Optional[LyricsPayload]:
        if not spotify_track_id:
            logging.debug("SyricsLyricsProvider: No Spotify track ID provided")
            return None

        track_info = f"'{track.track_name}' by '{track.artist_name}'"
        logging.debug(f"SyricsLyricsProvider: Fetching lyrics for {track_info} (ID: {spotify_track_id})")

        try:
            data = self._client.get_lyrics(spotify_track_id)
        except Exception as e:
            logging.debug(f"SyricsLyricsProvider: Failed to fetch lyrics: {e}")
            return None

        if not data or 'lyrics' not in data:
            logging.debug("SyricsLyricsProvider: No lyrics data in response")
            return None

        lyrics = data.get('lyrics') or {}
        language = lyrics.get('language') or 'unknown'
        lines_raw = lyrics.get('lines') or []
        lines: List[LyricsLine] = []

        for item in lines_raw:
            try:
                start_ms = int(item.get('startTimeMs', 0))
                words = item.get('words', '')
                if words is None:
                    words = ''
                lines.append(LyricsLine(start_time_ms=start_ms, words=words))
            except Exception as e:
                logging.debug(f"SyricsLyricsProvider: Failed to parse line: {e}")
                continue

        if not lines:
            logging.debug("SyricsLyricsProvider: No valid lyrics lines found")
            return None

        logging.info(f"SyricsLyricsProvider: Lyrics source - Spotify (Syrics API)")
        logging.debug(f"SyricsLyricsProvider: Successfully parsed {len(lines)} lyrics lines")
        return LyricsPayload(language=language, lines=lines, synced=True)


class LRCLibLyricsProvider:
    BASE_URL = "https://lrclib.net/api/get"

    def __init__(self, user_agent: str = "Spotify-Lyrics-Translator (https://github.com/)"):
        self._ua = user_agent

    def get_lyrics(self, track: TrackMetadata, spotify_track_id: Optional[str] = None) -> Optional[LyricsPayload]:
        track_info = f"'{track.track_name}' by '{track.artist_name}'"
        logging.info(f"LRCLibLyricsProvider: Fetching lyrics for {track_info}")

        params = {
            "track_name": track.track_name,
            "artist_name": track.artist_name,
            "album_name": track.album_name,
            "duration": max(0, int(round(track.duration_ms / 1000)))
        }
        headers = {"User-Agent": self._ua}

        try:
            resp = requests.get(self.BASE_URL, params=params, headers=headers, timeout=0.9)
        except Exception as e:
            logging.debug(f"LRCLibLyricsProvider: Request failed: {e}")
            return None

        if resp.status_code != 200:
            logging.debug(f"LRCLibLyricsProvider: HTTP {resp.status_code} response")
            return None

        try:
            payload = resp.json()
        except Exception as e:
            logging.debug(f"LRCLibLyricsProvider: Failed to parse JSON response: {e}")
            return None

        # Log the raw response for debugging
        raw_response = str(payload)
        if len(raw_response) > 500:
            raw_response = raw_response[:497] + "..."
        logging.info(f"LRCLibLyricsProvider: Raw LRCLIB response: {raw_response}")

        # Log lyrics source metadata
        lrclib_id = payload.get('id')
        instrumental = payload.get('instrumental', False)
        source_info = f"LRCLIB ID: {lrclib_id}"
        if instrumental:
            source_info += " (instrumental)"
        logging.info(f"LRCLibLyricsProvider: Lyrics source - {source_info}")

        language = 'unknown'
        synced = payload.get('syncedLyrics') or ''
        plain = payload.get('plainLyrics') or ''

        if synced.strip():
            lines = self._parse_lrc(synced)
            if lines:
                logging.info(f"LRCLibLyricsProvider: Successfully parsed {len(lines)} synced lyrics lines")
                return LyricsPayload(language=language, lines=lines, synced=True)
            else:
                logging.debug("LRCLibLyricsProvider: Failed to parse synced lyrics")

        if plain.strip():
            lines = self._plain_to_synthetic(plain, track.duration_ms)
            if lines:
                logging.info(f"LRCLibLyricsProvider: Successfully parsed {len(lines)} plain lyrics lines with synthetic timing")
                return LyricsPayload(language=language, lines=lines, synced=False)
            else:
                logging.debug("LRCLibLyricsProvider: Failed to parse plain lyrics")

        logging.debug("LRCLibLyricsProvider: No usable lyrics found in response")
        return None

    TIME_TAG = re.compile(r"\[(\d{2}):(\d{2})(?:[\.:](\d{2}))?\]")

    def _parse_lrc(self, lrc_text: str) -> List[LyricsLine]:
        lines: List[LyricsLine] = []
        for raw in lrc_text.splitlines():
            if not raw.strip():
                continue
            matches = list(self.TIME_TAG.finditer(raw))
            if not matches:
                continue
            text = self.TIME_TAG.sub("", raw).strip()
            for m in matches:
                mm = int(m.group(1) or 0)
                ss = int(m.group(2) or 0)
                cs = int(m.group(3) or 0)
                # cs is centiseconds if provided
                start_ms = (mm * 60 + ss) * 1000 + (cs * 10)
                lines.append(LyricsLine(start_time_ms=start_ms, words=text))
        lines.sort(key=lambda x: x.start_time_ms)
        return lines

    def _plain_to_synthetic(self, plain_text: str, duration_ms: int) -> List[LyricsLine]:
        raw_lines = [ln.strip() for ln in plain_text.splitlines() if ln.strip()]
        if not raw_lines:
            return []
        # Spread lines across duration or use 3000ms default spacing
        count = len(raw_lines)
        spacing = 3000
        if duration_ms > 0:
            spacing = max(1000, duration_ms // max(1, count + 1))
        lines: List[LyricsLine] = []
        current = 0
        for text in raw_lines:
            lines.append(LyricsLine(start_time_ms=current, words=text))
            current += spacing
        return lines


