from src.lrc_parser import parse_lrc


def lines(lrc):
    return [(l.start_time_ms, l.words) for l in parse_lrc(lrc)]


def test_parses_two_and_three_digit_fractions():
    assert lines("[00:12.34]two\n[01:02.345]three\n[00:05]none\n[00:07.5]one") == [
        (5_000, "none"), (7_500, "one"), (12_340, "two"), (62_345, "three"),
    ]


def test_line_with_several_timestamps_produces_one_line_per_timestamp_sorted():
    assert lines("[00:30.00][00:10.00]chorus\n[00:20.00]verse") == [
        (10_000, "chorus"), (20_000, "verse"), (30_000, "chorus"),
    ]


def test_skips_metadata_and_blank_lines_keeps_tag_only_lines_as_empty_text():
    assert lines("[ar:Artist]\n[ti:Title]\n\n   \nuntimed\n[00:01.00]\n[00:02.00] hello ") == [
        (1_000, ""), (2_000, "hello"),
    ]


def test_positive_offset_shows_lyrics_sooner():
    assert lines("[offset:+500]\n[00:10.00]a\n[00:00.20]b") == [(0, "b"), (9_500, "a")]


def test_strips_word_level_timestamps():
    assert lines("[00:01.00]<00:01.00>Hello <00:01.50>world") == [(1_000, "Hello world")]
