import ast
from pathlib import Path


def _load_track_key():
    # app.py builds the whole UI on import, so only track_key is taken from it
    source = (Path(__file__).resolve().parent.parent / "app.py").read_text(encoding="utf-8")
    node = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == "track_key")
    namespace = {}
    exec(compile(ast.Module(body=[node], type_ignores=[]), "app.py", "exec"), namespace)
    return namespace["track_key"]


track_key = _load_track_key()


def test_spotify_tracks_are_keyed_by_id():
    assert track_key({"id": "abc", "name": "Song", "artists": [{"name": "A"}], "duration_ms": 1000}) == "abc"


def test_local_files_get_a_key_of_their_own():
    first = track_key({"id": None, "name": "Song", "artists": [{"name": "A"}, {"name": "B"}], "duration_ms": 200_400})
    other = track_key({"id": None, "name": "Other", "artists": [{"name": "A"}], "duration_ms": 200_400})
    assert first == "local:a, b|song|200"
    assert first != other
    assert track_key({"id": None, "name": None, "artists": None, "duration_ms": None}) == "local:||0"
