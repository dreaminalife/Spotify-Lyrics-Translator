from src import song_matcher
from src.lyrics_models import TrackMetadata


def track(title, artist, duration_ms=200_000):
    return TrackMetadata(title, artist.split(",")[0].strip(), "", duration_ms, [a.strip() for a in artist.split(",")])


def song(id, title, duration_ms, artists):
    return {"id": id, "title": title, "duration": duration_ms, "artists": artists}


def pick(t, *songs):
    picked = song_matcher.pick(t, list(songs), lambda s: s["title"], lambda s: s["duration"], lambda s: s["artists"])
    return picked["id"] if picked else None


def test_title_ignores_case_repeated_and_full_width_spaces():
    t = track("Hype Boy", "NewJeans")
    assert pick(t, song(1, "HYPE BOY", 200_000, ["NewJeans"])) == 1
    assert pick(t, song(1, "  Hype   Boy ", 200_000, ["NewJeans"])) == 1
    assert pick(t, song(1, "Hype　Boy", 200_000, ["NewJeans"])) == 1


def test_full_width_parentheses_equal_ascii_ones():
    assert pick(track("Song(Live)", "Artist"), song(1, "Song（Live）", 200_000, ["Artist"])) == 1


def test_traditional_and_simplified_spellings_are_the_same_title():
    assert pick(track("乾杯", "Mayday", 289_000), song(1, "干杯", 289_050, ["五月天"])) == 1
    assert pick(track("後來的我們", "Mayday", 346_000), song(1, "后来的我们", 346_000, ["五月天"])) == 1
    assert pick(track("乾杯", "Mayday", 289_000), song(1, "干杯 (Live)", 289_050, ["五月天"])) is None


def test_versions_with_another_title_are_rejected():
    t = track("Dynamite", "BTS")
    assert pick(
        t,
        song(1, "Dynamite (Live)", 200_000, ["BTS"]),
        song(2, "Dynamite - Remix", 200_000, ["BTS"]),
        song(3, "BTS-Dynamite", 200_000, ["BTS"]),
    ) is None


def test_duration_may_differ_by_up_to_3_s_either_way():
    t = track("Song", "Artist", 200_000)
    assert pick(t, song(1, "Song", 203_000, ["Artist"])) == 1
    assert pick(t, song(1, "Song", 197_000, ["Artist"])) == 1
    assert pick(t, song(1, "Song", 203_001, ["Artist"])) is None
    assert pick(t, song(1, "Song", 196_999, ["Artist"])) is None
    assert pick(t, song(1, "Song", None, ["Artist"])) is None


def test_a_matching_artist_wins_over_search_order():
    t = track("Lemon", "Kenshi Yonezu")
    assert pick(t, song(1, "Lemon", 200_000, ["米津玄師"]), song(2, "Lemon", 200_000, ["Kenshi Yonezu"])) == 2


def test_artist_matching_ignores_case_and_accepts_containment_either_way():
    assert pick(track("Song", "newjeans"), song(1, "Song", 200_000, ["NewJeans"])) == 1
    assert pick(track("Dynamite", "BTS"), song(1, "Dynamite", 200_000, ["BTS (防弹少年团)"])) == 1
    assert pick(track("Dynamite", "BTS (방탄소년단)"), song(1, "Dynamite", 200_000, ["BTS"])) == 1


def test_artist_names_match_on_whole_words():
    for spotify, source in [("IU", "Julius"), ("Ado", "Shadow"), ("Sia", "Asia"), ("Asia", "Sia"), ("Eve", "Steve"), ("Rain", "Rainbow")]:
        assert pick(track("Song", spotify), song(1, "Song", 200_000, [source])) is None, (spotify, source)


def test_whole_word_matches_still_work_with_decorations_and_extra_artists():
    assert pick(track("Song", "IU"), song(1, "Song", 200_000, ["IU (아이유)"])) == 1
    assert pick(track("Song", "Kenshi Yonezu"), song(1, "Song", 200_000, ["Kenshi Yonezu & Someone"])) == 1
    assert pick(track("Song", "Jay-Z"), song(1, "Song", 200_000, ["JAY Z"])) == 1
    assert pick(track("Song", "米津玄師"), song(1, "Song", 200_000, ["米津玄師"])) == 1


def test_any_of_several_spotify_artists_can_match():
    assert pick(track("Song", "YOASOBI, Ikura"), song(1, "Song", 200_000, ["幾田りら", "ikura"])) == 1


def test_blank_source_artist_names_never_match():
    assert pick(track("Song", "Artist"), song(1, "Song", 200_000, [""])) is None
    assert pick(track("Song", "Artist"), song(1, "Song", 200_000, [])) is None


def test_an_artist_written_in_another_script_is_accepted_in_both_directions():
    assert pick(track("Lemon", "Kenshi Yonezu"), song(1, "Lemon", 200_000, ["米津玄師"])) == 1
    assert pick(track("Lemon", "米津玄師"), song(1, "Lemon", 200_000, ["Kenshi Yonezu"])) == 1
    assert pick(track("Song", "IU"), song(1, "Song", 200_000, ["아이유"])) == 1
    assert pick(track("Idol", "YOASOBI"), song(1, "Idol", 200_000, ["ＹＯＡＳＯＢＩ"])) == 1


def test_a_different_artist_in_the_same_script_is_rejected():
    assert pick(track("Home", "Artist X"), song(1, "Home", 200_000, ["Artist Y"])) is None
    assert pick(track("Lemon", "米津玄師"), song(1, "Lemon", 200_000, ["秋绘"])) is None
    assert pick(track("Song", "아이유"), song(1, "Song", 200_000, ["태연"])) is None
    # A name mixing scripts counts as Latin
    assert pick(track("Lemon", "Kenshi Yonezu"), song(1, "Lemon", 200_000, ["安亚尔Anyar"])) is None
    assert pick(track("Song", "Beyoncé"), song(1, "Song", 200_000, ["Beyonce"])) is None


def test_a_same_script_fallback_is_skipped_for_a_later_other_script_one():
    t = track("Lemon", "Kenshi Yonezu")
    assert pick(t, song(1, "Lemon", 200_000, ["Someone Else"]), song(2, "Lemon", 200_000, ["米津玄師"])) == 2
