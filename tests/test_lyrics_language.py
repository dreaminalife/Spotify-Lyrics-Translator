from src.lyrics_language import detect_language


class Identifier:
    def __init__(self, answer=None):
        self.answer = answer
        self.texts = []

    def __call__(self, text):
        self.texts.append(text)
        return self.answer


def test_chinese_lyrics_are_chinese_without_asking_the_identifier():
    identifier = Identifier()
    assert detect_language(["作词 : 周杰伦", "", "故事的小黄花", "從出生那年就飄著", "..."], None, identifier) == "zh"
    assert identifier.texts == []


def test_japanese_lyrics_with_kanji_only_lines_are_japanese():
    assert detect_language(["君の名前を", "永遠", "呼んでいた"], None, Identifier()) == "ja"


def test_korean_lyrics_are_korean():
    assert detect_language(["사랑해", "보고 싶어"], None, Identifier()) == "ko"


def test_a_mixed_song_is_left_to_the_translator():
    identifier = Identifier("zh")
    assert detect_language(["我爱你", "你爱我", "baby I love you", "every night"], None, identifier) is None
    assert identifier.texts == []
    assert detect_language(["사랑해", "보고 싶어", "baby I love you", "every night"], "ko", Identifier()) is None


def test_chinese_credit_lines_dont_hide_an_english_song():
    identifier = Identifier("en")
    lines = ["作词 : Paul Simon", "作曲：Paul Simon", "词：Paul Simon", "Hello darkness", "my old friend"]
    assert detect_language(lines, None, identifier) == "en"
    assert identifier.texts == ["Hello darkness\nmy old friend"]


def test_latin_lyrics_use_the_source_tag_first():
    identifier = Identifier("es")
    assert detect_language(["Hello darkness"], "en", identifier) == "en"
    assert identifier.texts == []


def test_untagged_latin_lyrics_go_to_the_identifier():
    assert detect_language(["Hello darkness", "", "my old friend"], "unknown", Identifier("en")) == "en"
    assert detect_language(["Hello darkness"], None, Identifier(None)) is None


def test_the_script_beats_a_wrong_tag():
    assert detect_language(["故事的小黄花"], "en", Identifier()) == "zh"
