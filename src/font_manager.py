import tkinter as tk
import tkinter.font as tkFont
from typing import List, Dict, Optional
import platform

def get_available_fonts() -> List[str]:
    """Get a list of available fonts on the system, prioritizing Chinese fonts."""
    system = platform.system()
    available_fonts = []

    # Get all available fonts
    all_fonts = tkFont.families()

    # Common Chinese font names to look for (prioritized first)
    chinese_font_patterns = [
        # Simplified Chinese
        "SimSun", "NSimSun", "FangSong", "KaiTi", "SimHei", "Microsoft YaHei",
        "Microsoft YaHei UI", "DengXian", "FangSong_GB2312", "KaiTi_GB2312",
        "STSong", "STKaiti", "STFangsong", "STXihei", "STZhongsong",
        "Noto Sans SC", "Noto Serif SC", "Source Han Sans SC", "Source Han Serif SC",
        # Traditional Chinese
        "MingLiU", "PMingLiU", "DFKai-SB", "DFMing-Bd", "Microsoft JhengHei",
        "Microsoft JhengHei UI", "LiSong Pro", "LiHei Pro", "BiauKai", "BiauKai TC",
        "Noto Sans TC", "Noto Serif TC", "Source Han Sans TC", "Source Han Serif TC",
        # Generic Chinese patterns
        "Chinese", "Han", "Hanzi", "Zhongwen"
    ]

    # Common English font names to look for
    english_font_patterns = [
        # Serif fonts
        "Times New Roman", "Georgia", "Garamond", "Book Antiqua", "Bookman Old Style",
        "Century", "Century Gothic", "Century Schoolbook", "Constantia", "Corbel",
        # Sans-serif fonts
        "Arial", "Helvetica", "Calibri", "Cambria", "Candara", "Consolas",
        "Segoe UI", "Tahoma", "Trebuchet MS", "Verdana",
        # Monospace fonts
        "Courier New", "Lucida Console", "Monaco", "Menlo", "Fira Code",
        # Script/Decorative fonts
        "Comic Sans MS", "Impact", "Lucida Handwriting", "Mistral",
        # System fonts
        "MS Sans Serif", "MS Serif", "System"
    ]

    # Add Chinese fonts first (prioritized)
    # Check for exact matches first, but exclude vertical fonts (@ prefix)
    for font in all_fonts:
        if font in chinese_font_patterns and not font.startswith('@'):
            available_fonts.append(font)

    # Then check for partial matches (fonts that contain Chinese-related keywords)
    # Exclude vertical fonts (@ prefix) and system fonts that might cause issues
    for font in all_fonts:
        if font not in available_fonts and not font.startswith('@'):
            font_lower = font.lower()
            for pattern in chinese_font_patterns:
                if pattern.lower() in font_lower or font_lower in pattern.lower():
                    # Skip fonts that might cause orientation issues
                    if not any(problematic in font_lower for problematic in ['extb', 'extg', '_hkscs']):
                        available_fonts.append(font)
                        break

    # Add English fonts
    for font in all_fonts:
        if font not in available_fonts and not font.startswith('@'):
            # Add exact English font matches
            if font in english_font_patterns:
                available_fonts.append(font)
            # Add other fonts that don't look like system/technical fonts
            elif not any(skip in font.lower() for skip in ['extb', 'extg', '_hkscs', 'marlett', 'symbol', 'webdings', 'wingdings']):
                # Skip fonts that are clearly not UI fonts
                available_fonts.append(font)

    # Remove duplicates and sort the fonts alphabetically
    available_fonts = list(set(available_fonts))
    available_fonts.sort()

    return available_fonts


def get_default_chinese_font() -> str:
    """Get a default Chinese font based on the system."""
    system = platform.system()

    # First try to get available fonts to choose the best one
    available_fonts = get_available_fonts()

    # System-specific defaults (prefer the most reliable fonts)
    if system == "Windows":
        # Try Microsoft YaHei UI first (most reliable for Chinese), then Microsoft JhengHei UI, then Noto Sans SC
        preferred_fonts = ["Microsoft YaHei UI", "Microsoft JhengHei UI", "Noto Sans SC", "Noto Serif SC"]
        for font in preferred_fonts:
            if font in available_fonts:
                return font
        # Fallback to first available font
        return available_fonts[0] if available_fonts else "Arial"
    elif system == "Darwin":  # macOS
        return "PingFang SC"  # Default for macOS
    else:  # Linux and others
        return "Noto Sans CJK SC"  # Common on Linux
    
