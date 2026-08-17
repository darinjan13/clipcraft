from pathlib import Path
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from app.clients import DatabaseClient
from app.config import Settings
from app.main import create_app


class CheckpointDatabase:
    url = "http://database.test"

    def __init__(self):
        self.rows = []

    def list_jobs(self):
        return self.rows

    def insert_job(self, data):
        row = {"id": str(uuid4()), **data}
        self.rows.append(row)
        return row

    def get_job(self, job_id):
        return next((row for row in self.rows if row["id"] == str(job_id)), None)


class CheckpointWorkflow:
    def get_status(self, job_id):
        return {"found": True, "status": "queued", "progress": 0}

    def get_result(self, job_id):
        return None


def make_client(tmp_path: Path, database: CheckpointDatabase) -> TestClient:
    return TestClient(
        create_app(
            workflow_client=CheckpointWorkflow(),
            database_client=database,
            data_dir=tmp_path,
        )
    )


def test_current_health_and_user_routes_are_local_only(tmp_path):
    database = CheckpointDatabase()
    client = make_client(tmp_path, database)

    assert client.get("/api/health").status_code == 200
    assert client.get("/api/videos").status_code == 200
    response = client.post(
        "/api/videos",
        json={
            "prompt": "Checkpoint flow",
            "duration": 30,
            "style": "Educational",
            "voice": "Neutral",
            "captions": "Clean",
        },
    )

    assert response.status_code == 202
    assert database.rows[0].get("user_id") is None


def test_frontend_request_helper_currently_omits_authorization_header():
    import pytest
    source = Path(__file__).parents[2] / "frontend/src/features/videos/api/videoService.ts"
    if not source.exists():
        pytest.skip(f"Frontend source not found: {source}")
    text = source.read_text(encoding="utf-8")

    assert "Authorization" not in text
    assert "supabase" not in text.lower()


def test_database_client_currently_uses_service_role_headers(monkeypatch):
    settings = Settings(
        n8n_base_url="http://n8n.test",
        n8n_api_key="",
        supabase_url="http://supabase.test",
        supabase_service_role_key="service-role-test-secret",
        data_dir="/tmp/jobs",
        gemini_api_key="",
        gemini_text_model="gemini-test",
        gemini_image_enabled=False,
        gemini_image_model="",
    )
    captured = {}

    def fake_get(url, **kwargs):
        captured.update(url=url, kwargs=kwargs)

        class Response:
            status_code = 200

            def json(self):
                return []

        return Response()

    monkeypatch.setattr("httpx.get", fake_get)

    DatabaseClient(settings).list_jobs()

    assert captured["kwargs"]["headers"] == {
        "apikey": "service-role-test-secret",
        "Authorization": "Bearer service-role-test-secret",
    }
    assert "user_id" not in captured["kwargs"]["params"]
    assert captured["url"].endswith("/rest/v1/video_jobs")