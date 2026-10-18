"""NetEase Cloud Music, QQ Music and Kugou lyrics, through their unofficial APIs.

All three often ship a Chinese (Simplified) translation with the lyrics; it is stored on each line's `provided`.
A refused request raises, so the lyrics service logs it and moves on to the next source.
"""
from __future__ import annotations

import base64
import json
import re
import zlib
from typing import Any, Dict, List, Optional

import requests

from . import provided_translations, song_matcher
from .chinese_script import to_simplified
from .logging_config import get_logger
from .lrc_parser import parse_lrc
from .lyrics_models import LyricsLine, LyricsPayload, TrackMetadata

logger = get_logger(__name__)

# Per request; a source makes up to 4 requests
HTTP_TIMEOUT = 5.0
USER_AGENT = "LyricsTranslator-Desktop/1.0"


def _get(url: str, params: Dict[str, Any], headers: Optional[Dict[str, str]] = None) -> Any:
    resp = requests.get(url, params=params, headers={"User-Agent": USER_AGENT, **(headers or {})}, timeout=HTTP_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def _post_json(url: str, body: Dict[str, Any], headers: Optional[Dict[str, str]] = None) -> Any:
    resp = requests.post(
        url,
        data=json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        headers={"User-Agent": USER_AGENT, "Content-Type": "application/json", **(headers or {})},
        timeout=HTTP_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def _payload(lines: List[LyricsLine], translation: Optional[List[str]], source: str) -> LyricsPayload:
    provided_translations.attach(lines, translation)
    translated = sum(1 for line in lines if line.provided.strip())
    logger.debug(f"{source}: {len(lines)} lines, {translated} translated")
    return LyricsPayload(language="unknown", lines=lines, synced=True, source=source)


class NetEaseLyricsProvider:
    """Search, then fetch the LRC by song id."""

    NAME = "NetEase"

    def get_lyrics(self, track: TrackMetadata, spotify_track_id: Optional[str] = None) -> Optional[LyricsPayload]:
        # The catalog spells Chinese titles in Simplified characters, and a Traditional query ("乾杯 Mayday") can miss
        # the song (干杯) entirely, so a miss is retried with the Simplified title. The original goes first because
        # folding also rewrites Japanese kanji (夢 to 梦).
        song = self._search(track, track.track_name)
        if song is None:
            simplified = to_simplified(track.track_name)
            if simplified != track.track_name:
                song = self._search(track, simplified)
        if song is None:
            return None
        logger.debug(f"NetEase: match id={song.get('id')} '{song.get('name')}' ({song.get('dt')} ms)")
        data = _get("https://music.163.com/api/song/lyric", {"id": song["id"], "lv": 1, "tv": -1})
        return self.parse_lyrics(data)

    def _search(self, track: TrackMetadata, title: str) -> Optional[dict]:
        data = _get(
            "https://music.163.com/api/cloudsearch/pc",
            {"s": f"{title} {track.all_artists}", "type": 1, "limit": 10},
        )
        songs = self.parse_search(data)
        song = self.pick_song(track, songs)
        if song is None:
            logger.debug(f"NetEase: no match for '{title}' among {len(songs)} results")
        return song

    @staticmethod
    def parse_search(data: dict) -> List[dict]:
        # NetEase answers HTTP 200 even when it refuses a request; the refusal is in the body's code (e.g. -462).
        if data.get("code") != 200:
            raise IOError(f"NetEase search returned code {data.get('code')}")
        return ((data.get("result") or {}).get("songs")) or []

    @staticmethod
    def pick_song(track: TrackMetadata, songs: List[dict]) -> Optional[dict]:
        def artists(song: dict) -> List[str]:
            names: List[str] = []
            for ar in song.get("ar") or []:
                if ar.get("name"):
                    names.append(ar["name"])
                names.extend(ar.get("alia") or [])
            return names

        return song_matcher.pick(track, songs, lambda s: s.get("name") or "", lambda s: s.get("dt"), artists)

    @classmethod
    def parse_lyrics(cls, data: dict) -> Optional[LyricsPayload]:
        """Returns None if NetEase has no timed lyrics. Credit lines (作词 : ...) are kept as lyrics."""
        if data.get("nolyric") or data.get("uncollected"):
            return None
        lines = parse_lrc((data.get("lrc") or {}).get("lyric") or "")
        if not lines:
            return None
        translation = provided_translations.pair_by_timestamp(lines, (data.get("tlyric") or {}).get("lyric") or "")
        return _payload(lines, translation, cls.NAME)


class QQMusicLyricsProvider:
    """Search with the web search, then fetch the LRC by song id posing as the desktop client."""

    NAME = "QQ Music"
    URL = "https://u.y.qq.com/cgi-bin/musicu.fcg"
    # The desktop client's search on musicu.fcg refuses every search from an address (code 2001) after a few
    # dozen in a short time, for minutes, while this search and the lyrics request keep working.
    SEARCH_URL = "https://c.y.qq.com/soso/fcgi-bin/client_search_cp"
    HEADERS = {"Referer": "https://y.qq.com/"}
    # Without the desktop client's identity every musicu.fcg request is refused.
    COMM = {"ct": "19", "cv": "1859", "uin": "0"}

    def get_lyrics(self, track: TrackMetadata, spotify_track_id: Optional[str] = None) -> Optional[LyricsPayload]:
        data = _get(
            self.SEARCH_URL,
            {"w": f"{track.track_name} {track.all_artists}", "format": "json", "p": 1, "n": 10, "cr": 1, "new_json": 1},
            self.HEADERS,
        )
        songs = self.parse_search(data)
        song = self.pick_song(track, songs)
        if song is None:
            logger.debug(f"QQ Music: no match among {len(songs)} results")
            return None
        logger.debug(f"QQ Music: match id={song.get('id')} '{song.get('title')}' ({song.get('interval')} s)")
        body = {
            "comm": self.COMM,
            "req_1": {
                "module": "music.musichallSong.PlayLyricInfo",
                "method": "GetPlayLyricInfo",
                "param": {"songID": song["id"], "trans": 1, "roma": 0, "qrc": 0, "crypt": 0},
            },
        }
        return self.parse_lyrics(_post_json(self.URL, body, self.HEADERS))

    @staticmethod
    def parse_search(data: dict) -> List[dict]:
        if data.get("code") != 0:
            raise IOError(f"QQ Music search returned code {data.get('code')}")
        return (((data.get("data") or {}).get("song") or {}).get("list")) or []

    @staticmethod
    def pick_song(track: TrackMetadata, songs: List[dict]) -> Optional[dict]:
        # "name" is the bare title even for "Lemon (Live)"; "title" has the version.
        def duration(song: dict) -> Optional[int]:
            interval = song.get("interval")
            return interval * 1000 if interval is not None else None

        def artists(song: dict) -> List[str]:
            names: List[str] = []
            for singer in song.get("singer") or []:
                names.extend(n for n in (singer.get("name"), singer.get("title")) if n)
            return names

        return song_matcher.pick(track, songs, lambda s: s.get("title") or "", duration, artists)

    @classmethod
    def parse_lyrics(cls, data: dict) -> Optional[LyricsPayload]:
        """Returns None if QQ Music has no timed lyrics. Credit lines are kept as lyrics."""
        request = data.get("req_1") or {}
        if request.get("code") != 0:
            raise IOError(f"QQ Music lyrics returned code {request.get('code')}")
        lyric_data = request.get("data") or {}
        lines = parse_lrc(cls._decode_base64(lyric_data.get("lyric")))
        if not lines:
            return None
        translation = provided_translations.pair_by_timestamp(lines, cls._decode_base64(lyric_data.get("trans")))
        return _payload(lines, translation, cls.NAME)

    @staticmethod
    def _decode_base64(text: Optional[str]) -> str:
        return base64.b64decode(text).decode("utf-8") if text else ""


class KugouLyricsProvider:
    """Search by artist, title and duration, then download KRC, Kugou's scrambled word-timed format.

    KRC is used rather than plain LRC because only KRC carries the Chinese (Simplified) translation.
    The search knows artists by their native name and titles in Simplified Chinese only, so "Mayday - 乾杯" finds
    nothing although "五月天 - 干杯" does. On a miss, Kugou's song search, which knows more spellings, supplies the
    song's hash, and the lyrics search is repeated with it. That still finds nothing for "Kenshi Yonezu".
    """

    NAME = "Kugou"
    KEY = bytes([0x40, 0x47, 0x61, 0x77, 0x5E, 0x32, 0x74, 0x47, 0x51, 0x36, 0x31, 0x2D, 0xCE, 0xD2, 0x6E, 0x69])
    LINE = re.compile(r"^\[(\d+),\d+](.*)$")
    WORD_TAG = re.compile(r"<\d+,\d+,\d+>")
    LANGUAGE_PREFIX = "[language:"
    # In the [language:] JSON, type 0 is romanization (one entry per word), 1 is the translation (one per line)
    TRANSLATION_TYPE = 1

    def get_lyrics(self, track: TrackMetadata, spotify_track_id: Optional[str] = None) -> Optional[LyricsPayload]:
        candidate = self._search_lyrics(track, "")
        if candidate is None:
            song_hash = self._find_song_hash(track)
            if song_hash:
                candidate = self._search_lyrics(track, song_hash)
        if candidate is None:
            return None
        logger.debug(f"Kugou: match id={candidate.get('id')} '{candidate.get('song')}' ({candidate.get('duration')} ms)")
        data = _get(
            "https://krcs.kugou.com/download",
            {"ver": 1, "client": "pc", "id": candidate["id"], "accesskey": candidate["accesskey"], "fmt": "krc", "charset": "utf8"},
        )
        content = data.get("content")
        if not content or not content.strip():
            return None
        return self.parse_krc(self.decode_krc(content))

    def _search_lyrics(self, track: TrackMetadata, song_hash: str) -> Optional[dict]:
        data = _get(
            "https://krcs.kugou.com/search",
            {
                "ver": 1, "man": "yes", "client": "mobi",
                "keyword": f"{track.all_artists} - {track.track_name}",
                "duration": track.duration_ms,
                "hash": song_hash,
            },
        )
        candidates = data.get("candidates") or []
        candidate = self.pick_candidate(track, candidates)
        if candidate is None:
            logger.debug(f"Kugou: no match (hash '{song_hash}') among {len(candidates)} results")
        return candidate

    def _find_song_hash(self, track: TrackMetadata) -> Optional[str]:
        data = _get(
            "https://mobileservice.kugou.com/api/v3/search/song",
            {"format": "json", "keyword": f"{to_simplified(track.track_name)} {track.all_artists}", "page": 1, "pagesize": 10},
        )
        songs = self.parse_song_search(data)
        song = self.pick_song(track, songs)
        if song is None:
            logger.debug(f"Kugou: no song search match among {len(songs)} results")
            return None
        return song.get("hash")

    @staticmethod
    def pick_candidate(track: TrackMetadata, candidates: List[dict]) -> Optional[dict]:
        return song_matcher.pick(
            track, candidates,
            lambda c: c.get("song") or "",
            lambda c: c.get("duration"),
            lambda c: [c["singer"]] if c.get("singer") else [],
        )

    @staticmethod
    def parse_song_search(data: dict) -> List[dict]:
        if data.get("status") != 1:
            raise IOError(f"Kugou song search returned status {data.get('status')}, errcode {data.get('errcode')}")
        return ((data.get("data") or {}).get("info")) or []

    @staticmethod
    def pick_song(track: TrackMetadata, songs: List[dict]) -> Optional[dict]:
        # Several singers come joined by "、"; duration is in seconds.
        def duration(song: dict) -> Optional[int]:
            seconds = song.get("duration")
            return seconds * 1000 if seconds is not None else None

        return song_matcher.pick(
            track, songs,
            lambda s: s.get("songname") or "",
            duration,
            lambda s: (s.get("singername") or "").split("、"),
        )

    @classmethod
    def decode_krc(cls, content: str) -> str:
        """Base64, then a 4-byte "krc1" header, a repeating XOR key and zlib."""
        raw = base64.b64decode(content)[4:]
        key = cls.KEY
        unscrambled = bytes(b ^ key[i % len(key)] for i, b in enumerate(raw))
        return zlib.decompress(unscrambled).decode("utf-8")

    @classmethod
    def parse_krc(cls, krc: str) -> Optional[LyricsPayload]:
        """KRC lines look like "[startMs,durationMs]<offset,duration,0>word<...>word". The translation sits in a
        "[language:<Base64 JSON>]" line, one row per lyrics line. Returns None if there are no lyrics lines.
        """
        raw_lines = [raw.strip() for raw in krc.splitlines()]
        lines: List[LyricsLine] = []
        for raw in raw_lines:
            match = cls.LINE.search(raw)
            if match:
                lines.append(LyricsLine(int(match.group(1)), cls.WORD_TAG.sub("", match.group(2)).strip()))
        if not lines:
            return None

        rows: List[str] = []
        language_line = next((l for l in raw_lines if l.startswith(cls.LANGUAGE_PREFIX)), None)
        if language_line:
            encoded = language_line[len(cls.LANGUAGE_PREFIX):]
            if encoded.endswith("]"):
                encoded = encoded[:-1]
            if encoded:
                content = json.loads(base64.b64decode(encoded).decode("utf-8")).get("content") or []
                item = next((c for c in content if c.get("type") == cls.TRANSLATION_TYPE), None)
                rows = [row[0] if row else "" for row in ((item or {}).get("lyricContent") or [])]
        if rows and len(rows) != len(lines):
            logger.warning(f"Kugou: ignoring translation, {len(rows)} rows vs {len(lines)} lines")
        translation = provided_translations.clean(rows) if len(rows) == len(lines) else None
        return _payload(lines, translation, cls.NAME)
