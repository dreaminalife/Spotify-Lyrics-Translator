from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Dict, Any


@dataclass
class TrackMetadata:
    track_name: str
    artist_name: str
    album_name: str
    duration_ms: int
    # Every artist on the track; artist_name is the first one
    artist_names: List[str] = field(default_factory=list)
    # Identifies the track in caches (app.track_key)
    key: str = ""

    @property
    def all_artists(self) -> str:
        """All artists joined with ", ", as the Chinese sources are searched with."""
        return ", ".join(self.artist_names) if self.artist_names else self.artist_name


@dataclass
class LyricsLine:
    start_time_ms: int
    words: str
    # Translation shipped with the lyrics (NetEase, QQ Music, Kugou: Simplified Chinese); "" if none
    provided: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"startTimeMs": int(self.start_time_ms), "words": self.words, "provided": self.provided}


@dataclass
class LyricsPayload:
    language: str
    lines: List[LyricsLine]
    synced: bool
    source: str = "Unknown"

    def to_api_dict(self) -> Dict[str, Any]:
        return {
            "lyrics": {
                "language": self.language,
                "lines": [line.to_dict() for line in self.lines],
                "synced": self.synced,
            },
            "source": self.source,
        }
