"""FastAPI endpoint tests via TestClient."""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from webgui.app import app
    return TestClient(app)


def test_index_returns_html(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "Whisper" in r.text
    # implicit `request` from Starlette 1.0 TemplateResponse must reach the
    # template — Start nav-link should carry .is-active on /
    assert 'href="/" class="is-active"' in r.text


def test_healthz_returns_ok(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_static_css_served(client):
    r = client.get("/static/style.css")
    assert r.status_code == 200
    assert "text/css" in r.headers["content-type"]


def test_api_audio_probe_with_valid_file(client, fixtures_dir):
    r = client.post("/api/audio/probe", json={"path": str(fixtures_dir / "sample.m4a")})
    assert r.status_code == 200
    body = r.json()
    assert body["valid"] is True
    assert body["stem"] == "sample"


def test_api_audio_probe_with_missing_file(client, tmp_path):
    r = client.post("/api/audio/probe", json={"path": str(tmp_path / "nope.m4a")})
    assert r.status_code == 200
    assert r.json()["valid"] is False
    assert r.json()["error"] == "file_not_found"
