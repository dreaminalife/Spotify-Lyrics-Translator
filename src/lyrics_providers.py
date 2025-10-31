from __future__ import annotations

import re
from typing import Optional, Protocol, List, Dict, Any
import requests
import logging
from bs4 import BeautifulSoup
import json
import time

from .settings_manager import read_secrets

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
        return LyricsPayload(language=language, lines=lines, synced=True, source="Spotify")


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
                return LyricsPayload(language=language, lines=lines, synced=True, source="LRCLib")
            else:
                logging.debug("LRCLibLyricsProvider: Failed to parse synced lyrics")

        if plain.strip():
            lines = self._plain_to_synthetic(plain, track.duration_ms)
            if lines:
                logging.info(f"LRCLibLyricsProvider: Successfully parsed {len(lines)} plain lyrics lines with synthetic timing")
                return LyricsPayload(language=language, lines=lines, synced=False, source="LRCLib")
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



class UtaNetLyricsProvider:
    SEARCH_URL = "https://www.uta-net.com/search/"

    def __init__(self, user_agent: str = "Mozilla/5.0 (Lyrics-Translator/0.1)"):
        self._ua = user_agent

    def get_lyrics(self, track: TrackMetadata, spotify_track_id: Optional[str] = None) -> Optional[LyricsPayload]:
        track_info = f"'{track.track_name}' by '{track.artist_name}'"
        logging.info(f"UtaNetLyricsProvider: Searching Uta-Net for {track_info}")

        params = {
            "Keyword": track.track_name,
            "Aselect": "2",
            "Bselect": "3",
        }
        headers = {"User-Agent": self._ua}

        # Retry policy: initial + 2 retries (total 3 attempts) for Uta-Net search
        delays = [0.0, 0.15]
        resp = None

        for attempt in range(len(delays) + 1):
            try:
                # Keep under service timeout budget to avoid hanging the caller
                resp = requests.get(self.SEARCH_URL, params=params, headers=headers, timeout=1.8)
                if resp.status_code == 200:
                    break  # Success, exit retry loop
                else:
                    logging.info(f"UtaNetLyricsProvider: HTTP {resp.status_code} response (attempt {attempt + 1})")
                    if attempt < len(delays):
                        time.sleep(delays[attempt])
                    else:
                        return None  # All attempts failed
            except Exception as e:
                logging.info(f"UtaNetLyricsProvider: Request failed (attempt {attempt + 1}): {e}")
                if attempt < len(delays):
                    time.sleep(delays[attempt])
                else:
                    return None  # All attempts failed

        if not resp or resp.status_code != 200:
            return None

        try:
            soup = BeautifulSoup(resp.text, "html.parser")
            container = soup.find(class_="songlist-table-body")
        except Exception as e:
            logging.info(f"UtaNetLyricsProvider: Failed to parse HTML: {e}")
            return None

        if not container:
            logging.info("UtaNetLyricsProvider: 'songlist-table-body' not found in search results")
            return None

        # Parse the song list
        rows = container.find_all('tr')
        logging.info(f"UtaNetLyricsProvider: Found {len(rows)} table rows in songlist-table-body")
        songs = []
        for row in rows:
            try:
                # Extract song info from the row
                cells = row.find_all('td')
                logging.debug(f"UtaNetLyricsProvider: Row has {len(cells)} cells")
                if len(cells) < 6:  # Need at least 6 columns
                    logging.debug("UtaNetLyricsProvider: Skipping row - not enough cells")
                    continue

                # First cell: song title and artist (mobile view)
                song_link = cells[0].find('a')
                if not song_link:
                    continue

                song_href = song_link.get('href', '')
                song_id = song_href.split('/song/')[-1].rstrip('/') if '/song/' in song_href else ''

                song_title_span = song_link.find('span', class_='songlist-title')
                song_title = song_title_span.get_text(strip=True) if song_title_span else ''

                # Second cell: artist link
                artist_link = cells[1].find('a')
                artist_href = artist_link.get('href', '') if artist_link else ''
                artist_id = artist_href.split('/artist/')[-1].rstrip('/') if '/artist/' in artist_href else ''
                artist_name = artist_link.get_text(strip=True) if artist_link else ''

                # Last cell: lyrics (pc-utaidashi)
                lyrics_span = cells[5].find('span', class_='pc-utaidashi')
                lyrics = lyrics_span.get_text(strip=True) if lyrics_span else ''
                # Convert Japanese full-width spaces to regular spaces for better readability
                lyrics = lyrics.replace('\u3000', ' ')

                if song_title and artist_id and artist_name and lyrics:
                    song_dict = {
                        'song_title': song_title,
                        'artist_id': artist_id,
                        'artist_name': artist_name,
                        'lyrics': lyrics,
                    }
                    songs.append(song_dict)

            except Exception as e:
                logging.debug(f"UtaNetLyricsProvider: Failed to parse row: {e}")
                continue

        logging.info(f"UtaNetLyricsProvider: Parsed {len(songs)} songs from search results")

        # Build slim list (no lyrics) for LLM if needed
        slim = [
            {
                'song_title': s['song_title'],
                'artist_id': s['artist_id'],
                'artist_name': s['artist_name'],
            }
            for s in songs
        ]

        # Try local artist match (normalize full-width spaces, case-insensitive)
        current_artist_norm = self._normalize_name(track.artist_name)
        logging.debug(f"UtaNetLyricsProvider: Normalized current artist='{current_artist_norm}'")
        selected_lyrics: Optional[str] = None
        for s in songs:
            candidate = self._normalize_name(s['artist_name'])
            if candidate == current_artist_norm:
                logging.info(f"UtaNetLyricsProvider: Local artist match found -> artist_id={s['artist_id']}")
                selected_lyrics = s['lyrics']
                break

        # If no local match, ask LLM to identify artist_id from slim list
        if selected_lyrics is None and slim:
            try:
                secrets = read_secrets()
                api_key = (secrets.get('openrouter_api_key') or '').strip()
            except Exception:
                api_key = ''

            if not api_key:
                logging.debug("UtaNetLyricsProvider: OpenRouter API key missing; skipping LLM fallback")
            else:
                prompt = (
                    "You are helping to match a song artist from Spotify with a Japanese artist from Uta-Net lyrics database.\n\n"
                    "Current Spotify artist name: '" + track.artist_name + "'\n\n"
                    "Available candidates from Uta-Net search results:\n"
                    + json.dumps(slim, ensure_ascii=False, indent=2) + "\n\n"
                    "TASK: Find which candidate artist matches the current Spotify artist. "
                    "Consider common variations: English vs Japanese names, romanized versions, "
                    "stage names, full names vs shortened names, or common alternative spellings.\n\n"
                    "RESPONSE FORMAT: Return ONLY a JSON object with exactly one key:\n"
                    "- {\"artist_id\": \"<matching_artist_id>\"} if you find a good match\n"
                    "- {\"artist_id\": null} if no good match is found\n\n"
                    "Examples:\n"
                    "- If current artist 'Kenshi Yonezu' matches candidate with artist_id '1234', return: {\"artist_id\": \"1234\"}\n"
                    "- If current artist 'Yoasobi' matches candidate with artist_id '5678', return: {\"artist_id\": \"5678\"}\n"
                    "- If no match is found, return: {\"artist_id\": null}\n\n"
                    "Do not include any other text, explanations, or formatting outside the JSON."
                )
                body = {
                    "model": "openai/gpt-5-chat",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.7,
                }
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "X-Title": "Spotify Lyrics Translator",
                }
                logging.info("UtaNetLyricsProvider: Calling OpenRouter for artist disambiguation")
                try:
                    resp = requests.post(
                        "https://openrouter.ai/api/v1/chat/completions",
                        headers=headers,
                        json=body,
                        timeout=15,
                    )
                except Exception as e:
                    logging.debug(f"UtaNetLyricsProvider: OpenRouter request failed: {e}")
                    resp = None

                if resp and resp.status_code < 400:
                    try:
                        data = resp.json()
                        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                        logging.info(f"UtaNetLyricsProvider: LLM raw response: {content}")
                        clean = self._extract_json_object(content)
                        result = json.loads(clean) if clean else {}
                        artist_id_llm = result.get("artist_id")
                    except Exception as e:
                        logging.debug(f"UtaNetLyricsProvider: Failed parsing LLM response: {e}")
                        artist_id_llm = None

                    if artist_id_llm:
                        logging.info(f"UtaNetLyricsProvider: LLM selected artist_id={artist_id_llm}")
                        for s in songs:
                            if s['artist_id'] == str(artist_id_llm):
                                selected_lyrics = s['lyrics']
                                break
                    else:
                        logging.info("UtaNetLyricsProvider: LLM returned no matching artist")
                else:
                    if resp is not None:
                        logging.debug(f"UtaNetLyricsProvider: OpenRouter HTTP {resp.status_code}")

        # If we selected lyrics (locally or via LLM), return unsynced payload with synthetic timing
        if selected_lyrics:
            lines = self._plain_to_synthetic(selected_lyrics, track.duration_ms)
            if lines:
                logging.info("UtaNetLyricsProvider: Returning lyrics from Uta-Net search result")
                return LyricsPayload(language='ja', lines=lines, synced=False, source="Uta-Net")

        logging.info("UtaNetLyricsProvider: No lyrics match from Uta-Net")
        return None

    @staticmethod
    def _normalize_name(name: str) -> str:
        base = (name or '').replace('\u3000', ' ')
        base = ' '.join(base.split())
        return base.lower()

    @staticmethod
    def _extract_json_object(text: str) -> Optional[str]:
        if not text:
            return None
        t = text.strip()
        if t.startswith("```"):
            # Strip fenced blocks like ```json ... ```
            try:
                t = t.strip('`')
                parts = t.split("\n", 1)
                t = parts[1] if len(parts) > 1 else t
                t = t.rsplit("```", 1)[0]
            except Exception:
                pass
        # Extract first JSON object
        start = t.find('{')
        end = t.rfind('}')
        if start != -1 and end != -1 and end > start:
            return t[start:end+1]
        return None

    @staticmethod
    def _plain_to_synthetic(plain_text: str, duration_ms: int) -> List[LyricsLine]:
        text = (plain_text or '').strip()
        if not text:
            return []
        # Split lyrics by single spaces to create individual word/phrase lines
        segments = [seg.strip() for seg in text.split() if seg.strip()]
        count = len(segments)
        spacing = 3000
        if duration_ms and duration_ms > 0:
            spacing = max(1000, duration_ms // max(1, count + 1))
        lines: List[LyricsLine] = []
        current = 0
        for seg in segments:
            lines.append(LyricsLine(start_time_ms=current, words=seg))
            current += spacing
        return lines

