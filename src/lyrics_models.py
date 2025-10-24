from __future__ import annotations

from dataclasses import dataclass
from typing import List, Dict, Any


@dataclass
class TrackMetadata:
    track_name: str
    artist_name: str
    album_name: str
    duration_ms: int


@dataclass
class LyricsLine:
    start_time_ms: int
    words: str

    def to_dict(self) -> Dict[str, Any]:
        return {"startTimeMs": int(self.start_time_ms), "words": self.words}


@dataclass
class LyricsPayload:
    language: str
    lines: List[LyricsLine]
    synced: bool

    def to_api_dict(self) -> Dict[str, Any]:
        return {
            "lyrics": {
                "language": self.language,
                "lines": [line.to_dict() for line in self.lines],
                "synced": self.synced,
            }
        }


