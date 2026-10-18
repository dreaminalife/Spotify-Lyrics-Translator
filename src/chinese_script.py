"""Folds Traditional Chinese characters to Simplified.

Spotify often has the Traditional title (乾杯) while NetEase, QQ Music and Kugou list the Simplified one (干杯).
Character by character, so it is for matching and searching, not for display.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

_TABLE_PATH = Path(__file__).resolve().parent / "data" / "traditional_to_simplified.txt"
_table: Optional[Dict[int, str]] = None


def _load() -> Dict[int, str]:
    global _table
    if _table is None:
        table: Dict[int, str] = {}
        with open(_TABLE_PATH, encoding="utf-8") as f:
            for raw in f:
                line = raw.rstrip("\r\n")
                if len(line) == 2 and not line.startswith("#"):
                    table[ord(line[0])] = line[1]
        _table = table
    return _table


def to_simplified(text: str) -> str:
    return text.translate(_load())
