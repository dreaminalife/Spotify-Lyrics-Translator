import threading

from src.lyrics_models import LyricsLine, LyricsPayload, TrackMetadata
from src.lyrics_service import DEFAULT_ORDER, LyricsService, resolve_order

TRACK = TrackMetadata("Song", "Artist", "Album", 200_000, ["Artist"])


class Provider:
    def __init__(self, name, found=True, error=None, block=None):
        self.name, self.found, self.error, self.block = name, found, error, block
        self.calls = 0

    def get_lyrics(self, track, spotify_track_id=None):
        self.calls += 1
        if self.block:
            self.block.wait(5)
        if self.error:
            raise self.error
        return LyricsPayload("unknown", [LyricsLine(0, self.name)], True, self.name) if self.found else None


def test_resolve_order_puts_the_pin_first_then_the_users_order_then_the_rest():
    assert resolve_order([], None) == DEFAULT_ORDER
    assert resolve_order(["LRCLib", "Spotify"], None) == ["LRCLib", "Spotify", "NetEase", "QQ Music", "Kugou", "Uta-Net"]
    assert resolve_order(["LRCLib"], "Kugou")[:2] == ["Kugou", "LRCLib"]
    assert resolve_order(["Gone", "LRCLib", "LRCLib"], "Gone") == ["LRCLib", "NetEase", "QQ Music", "Kugou", "Spotify", "Uta-Net"]


def test_first_source_with_lyrics_wins_and_failures_move_on():
    providers = {"NetEase": Provider("NetEase", error=IOError("refused")), "QQ Music": Provider("QQ Music", found=False),
                 "Kugou": Provider("Kugou"), "LRCLib": Provider("LRCLib")}
    result = LyricsService(providers).get_lyrics(TRACK, "id", ["NetEase", "QQ Music", "Kugou", "LRCLib"])
    assert result["source"] == "Kugou" and result["cached"] is False
    assert providers["LRCLib"].calls == 0


def test_a_sources_cache_is_checked_before_asking_it():
    providers = {"NetEase": Provider("NetEase", found=False), "Kugou": Provider("Kugou")}
    cached = {"lyrics": {"language": "unknown", "lines": [], "synced": True}, "source": "Kugou"}
    result = LyricsService(providers).get_lyrics(TRACK, "id", ["NetEase", "Kugou"], lambda name: cached if name == "Kugou" else None)
    assert result["cached"] is True and result["source"] == "Kugou"
    assert providers["NetEase"].calls == 1 and providers["Kugou"].calls == 0


def test_spotify_gets_three_attempts_others_one():
    providers = {"Spotify": Provider("Spotify", found=False), "NetEase": Provider("NetEase", found=False)}
    assert LyricsService(providers).get_lyrics(TRACK, "id", ["Spotify", "NetEase"]) is None
    assert providers["Spotify"].calls == 3 and providers["NetEase"].calls == 1


def test_a_stale_search_stops_before_the_next_source():
    providers = {"NetEase": Provider("NetEase", found=False), "Kugou": Provider("Kugou")}
    stale = threading.Event()
    providers["NetEase"].get_lyrics = lambda track, sid=None: stale.set()
    assert LyricsService(providers).get_lyrics(TRACK, "id", ["NetEase", "Kugou"], is_stale=stale.is_set) is None
    assert providers["Kugou"].calls == 0
