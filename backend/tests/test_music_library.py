import io

from fastapi.testclient import TestClient

from app.main import create_app


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIPCRAFT_MUSIC_DIR", str(tmp_path / "music"))
    return TestClient(create_app(data_dir=tmp_path))


def test_list_music_empty(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    response = client.get("/api/music")

    assert response.status_code == 200
    assert response.json() == {"tracks": []}


def test_upload_rejects_non_audio(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    response = client.post(
        "/api/music",
        files={"file": ("evil.txt", io.BytesIO(b"not audio"), "text/plain")},
    )

    assert response.status_code == 400


def test_upload_rejects_path_traversal(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    response = client.post(
        "/api/music",
        files={"file": ("../evil.mp3", io.BytesIO(b"ID3"), "audio/mpeg")},
    )

    assert response.status_code in (400, 422)
