from uuid import uuid4

import pytest

from app.clients import DatabaseClient
from app.config import Settings


@pytest.fixture
def settings():
    return Settings(
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


@pytest.mark.parametrize(("rpc_result", "expected"), [(True, True), (False, False)])
def test_hard_delete_job_calls_atomic_rpc(monkeypatch, settings, rpc_result, expected):
    captured = {}

    def fake_request(method, url, **kwargs):
        captured.update(method=method, url=url, **kwargs)

        class Response:
            status_code = 200
            content = b"true" if rpc_result else b"false"

            def json(self):
                return rpc_result

        return Response()

    monkeypatch.setattr("httpx.request", fake_request)
    video_id = uuid4()

    result = DatabaseClient(settings).hard_delete_job(video_id)

    assert captured["method"] == "POST"
    assert captured["url"].endswith("/rest/v1/rpc/hard_delete_video_job")
    assert captured["json"] == {"p_job_id": str(video_id)}
    assert result is expected
