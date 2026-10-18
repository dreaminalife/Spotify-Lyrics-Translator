from src.lyrics_manager import LyricsManager


class Client:
    def __init__(self, model=None):
        self.requests = []
        if model:
            self.model = model

    def translate_lines(self, lines, source_lang, target_lang):
        self.requests.append(list(lines))
        return [f"T({l})" for l in lines]

    def get_source_name(self):
        return "Fake"


def payload(source, words):
    return {"lyrics": {"language": "unknown", "lines": [{"startTimeMs": i, "words": w, "provided": p} for i, (w, p) in enumerate(words)],
                       "synced": True}, "source": source, "cached": False}


def manager(tmp_path, client, target="zh-CN"):
    return LyricsManager(cache_file=str(tmp_path / "cache.pkl"), translation_client=client, target_language=target)


def test_provided_translation_fills_lines_and_only_gaps_go_to_the_translator(tmp_path):
    client = Client()
    m = manager(tmp_path, client)
    data = payload("NetEase", [("作词 : x", ""), ("one", "一"), ("", ""), ("two", "")])
    m.put_lyrics("song", data)
    result = m.translate_lyrics(data["lyrics"]["lines"], "song", "NetEase", "Title")
    assert result["lines"] == ["T(作词 : x)", "一", "", "T(two)"]
    assert result["label"] == "NetEase + Fake"
    assert result["title"] == "T(Title)"
    assert client.requests[0] == ["作词 : x", "two"]


def test_provided_translation_is_ignored_for_another_target(tmp_path):
    client = Client()
    m = manager(tmp_path, client, target="en")
    data = payload("NetEase", [("one", "一")])
    m.put_lyrics("song", data)
    result = m.translate_lyrics(data["lyrics"]["lines"], "song", "NetEase")
    assert result["lines"] == ["T(one)"] and result["label"] == "Fake"


def test_cache_is_per_source_and_translations_per_translator_and_language(tmp_path):
    client = Client()
    m = manager(tmp_path, client, target="en")
    data = payload("Kugou", [("one", "")])
    m.put_lyrics("song", data)
    assert m.get_cached("song", "Kugou")["source"] == "Kugou"
    assert "cached" not in m.get_cached("song", "Kugou")
    assert m.get_cached("song", "NetEase") is None

    m.translate_lyrics(data["lyrics"]["lines"], "song", "Kugou")
    assert m.get_translation("song", "Kugou", 1)["lines"] == ["T(one)"]
    assert m.get_translation("song", "Kugou", 2) is None
    m.target_language = "ja"
    assert m.get_translation("song", "Kugou", 1) is None
    m.target_language = "en"
    m.translation_client = Client(model="vendor/model")
    assert m.translator_id() == "openrouter:vendor/model"
    assert m.get_translation("song", "Kugou", 1) is None

    reloaded = manager(tmp_path, client, target="en")
    assert reloaded.get_translation("song", "Kugou", 1)["lines"] == ["T(one)"]
    reloaded.clear_cache("song", "Kugou")
    assert reloaded.get_cached("song", "Kugou") is None
