"""Tells whether lyrics are already in the target language, so translating them would be a wasted request."""
from __future__ import annotations

import re
from collections import Counter
from typing import Callable, List, Optional

from .logging_config import get_logger

logger = get_logger(__name__)

MIN_SHARE = 0.9
# langdetect's probability needed to trust it; strict, so a song it isn't sure about gets translated
MIN_PROBABILITY = 0.9

_HAN = (
    "⺀-⿟々〇〡-〩〸-〻㐀-䶿一-鿿豈-﫿"
    "\U00020000-\U0003134F"
)
# Code point ranges of the scripts that name a language. Python's re has no Unicode script classes.
_SCRIPTS = [
    # Kana, without the prolonged sound mark and middle dot, which are shared with Chinese text
    ("ja", re.compile("[ぁ-ゖゝ-ゟァ-ヺヽ-ヿㇰ-ㇿ㋐-㋾㌀-㍗ｦ-ｯｱ-ﾝ]")),
    ("ko", re.compile("[ᄀ-ᇿㄱ-ㆎꥠ-꥿가-힣ힰ-퟿ﾠ-ￜ]")),
    ("zh", re.compile(f"[{_HAN}]")),
    ("th", re.compile("[ก-ฺเ-๛]")),
    ("ar", re.compile("[ء-ي٠-٩ٮ-ۓە-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿]")),
    ("hi", re.compile("[ऀ-ॿ꣠-ꣿ]")),
]
# NetEase, QQ Music and Kugou add Chinese credit lines (作词 : Paul Simon) even to English songs.
_CREDIT = re.compile(f"^\\s*[{_HAN}]{{1,6}}\\s*[:：]")


def base(code: str) -> str:
    return code.split("-", 1)[0].lower()


def _line_language(line: str) -> Optional[str]:
    """Language of a line by its script; None for Latin and other scripts shared by many languages."""
    for language, pattern in _SCRIPTS:
        if pattern.search(line):
            return language
    return None


def identify(text: str) -> Optional[str]:
    """Language code of text in Latin and other shared scripts, or None if unsure."""
    try:
        from langdetect import DetectorFactory, detect_langs
        DetectorFactory.seed = 0
        best = detect_langs(text)[0]
    except Exception as e:
        logger.debug(f"Language identification failed: {e}")
        return None
    return best.lang if best.prob >= MIN_PROBABILITY else None


def detect_language(
    texts: List[str],
    source_tag: Optional[str],
    identifier: Callable[[str], Optional[str]] = identify,
) -> Optional[str]:
    """Base language code of the lyrics ("zh", "en", ...), or None if it can't be told.

    When some lines are in a script that names a language, nearly every line must be; a song mixing, say, Chinese
    and English is left to the translator. When none are, the source's tag (Spotify's) if any, else the identifier.
    """
    lettered = [t for t in texts if any(c.isalpha() for c in t) and not _CREDIT.search(t)]
    counts = Counter(lang for lang in map(_line_language, lettered) if lang)
    if not counts:
        if source_tag and source_tag.lower() != "unknown":
            return base(source_tag)
        if not lettered:
            return None
        found = identifier("\n".join(lettered))
        return base(found) if found else None
    best, count = counts.most_common(1)[0]
    # Kanji-only lines are normal in Japanese lyrics.
    if best == "ja":
        count += counts.get("zh", 0)
    return best if count >= len(lettered) * MIN_SHARE else None


def is_in(texts: List[str], source_tag: Optional[str], target_language: str) -> bool:
    """True only when the lyrics are clearly in the target language. zh-CN and zh-TW both count as Chinese."""
    return detect_language(texts, source_tag) == base(target_language)
