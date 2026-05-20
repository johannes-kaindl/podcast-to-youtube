import json
from pathlib import Path


def test_load_settings_returns_defaults_when_file_missing(tmp_path):
    from webgui.settings import load_settings
    s = load_settings(tmp_path / "nope.json")
    assert s["theme"] == "dark"
    assert s["tail_default"] is True


def test_save_then_load_roundtrips(tmp_path):
    from webgui.settings import load_settings, save_settings
    p = tmp_path / "settings.json"
    save_settings(p, {"theme": "light"})
    loaded = load_settings(p)
    assert loaded["theme"] == "light"
    assert loaded["tail_default"] is True


def test_save_settings_partial_merges(tmp_path):
    from webgui.settings import save_settings, load_settings
    p = tmp_path / "settings.json"
    save_settings(p, {"theme": "dark", "tail_default": False})
    save_settings(p, {"theme": "light"})
    loaded = load_settings(p)
    assert loaded["theme"] == "light"
    assert loaded["tail_default"] is False
