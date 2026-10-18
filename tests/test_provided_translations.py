from src import provided_translations
from src.lyrics_models import LyricsLine


def test_placeholders_and_notices_are_blanked():
    assert provided_translations.clean([
        "//", "  //  ", "QQ音乐享有本翻译作品的著作权", "TME享有本翻译作品的著作权", " 以下歌词翻译由文曲大模型提供", "如果只是一场梦",
    ]) == ["", "", "", "", "", "如果只是一场梦"]
    assert provided_translations.clean(["你/我"]) == ["你/我"]


def test_nothing_left_after_cleaning_gives_none():
    assert provided_translations.clean([]) is None
    assert provided_translations.clean(["", " ", "//", "TME享有本翻译作品的著作权"]) is None


def test_pairing_matches_timestamps_across_precisions():
    lines = [LyricsLine(19_430, "a"), LyricsLine(20_000, "b")]
    assert provided_translations.pair_by_timestamp(lines, "[00:19.43]一\n[00:20.000]二") == ["一", "二"]


def test_repeated_timestamps_pair_in_order():
    lines = [LyricsLine(0, "a"), LyricsLine(0, "b"), LyricsLine(1_000, "c")]
    assert provided_translations.pair_by_timestamp(lines, "[00:00.00]一\n[00:00.00]二\n[00:01.00]三") == ["一", "二", "三"]


def test_untranslated_lines_stay_blank_and_extra_lines_are_ignored():
    lines = [LyricsLine(1_000, "a"), LyricsLine(2_000, "b")]
    assert provided_translations.pair_by_timestamp(lines, "[00:01.00]一\n[00:05.00]extra\n[00:00.50]early") == ["一", ""]


def test_empty_or_untimed_translation_gives_none():
    lines = [LyricsLine(1_000, "a")]
    assert provided_translations.pair_by_timestamp(lines, "") is None
    assert provided_translations.pair_by_timestamp(lines, "plain text") is None
    assert provided_translations.pair_by_timestamp(lines, "[00:01.00]") is None
