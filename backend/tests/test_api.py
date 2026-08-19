import io
import struct
import wave
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.clients import BackendDependencyError
from app.main import create_app
from app.models import VideoDraft
from app.services.ai import provider_registry


class FakeWorkflowClient:
    def __init__(self):
        self.create_payload = None

    def create_job(self, payload):
        self.create_payload = payload
        return {"success": True, "jobId": str(uuid4()), "status": "queued"}

    def get_status(self, job_id):
        return {
            "found": True,
            "jobId": job_id,
            "status": "queued",
            "progress": 0,
            "currentStep": "queued",
            "error": None,
        }

    def get_result(self, job_id):
        return None


class EmptyStatusWorkflowClient(FakeWorkflowClient):
    def get_status(self, job_id):
        raise BackendDependencyError("empty workflow response")


class MissingJobWorkflowClient(FakeWorkflowClient):
    def create_job(self, payload):
        return {"success": True, "status": "queued"}


class FakeDatabaseClient:
    def __init__(self, rows=None, scenes=None, assets=None, events=None):
        self.rows = rows or []
        self._scenes = scenes or []
        self._assets = assets or []
        self._events = events or []
        self.url = "http://test"
        self.hard_delete_calls = []
        self.credential = None
        self.fail_custom_audio_persist = False

    def get_credential_for_test(self, provider_id):
        return self.credential if provider_id == "nvidia" else None

    def get_job(self, job_id):
        return next((row for row in self.rows if row["id"] == str(job_id)), None)

    def list_jobs(self):
        return self.rows

    def get_scene_counts(self, job_id):
        scenes = [s for s in self._scenes if s.get("job_id") == str(job_id)]
        completed = sum(1 for s in scenes if s.get("generation_status") == "completed")
        failed = sum(1 for s in scenes if s.get("generation_status") == "failed")
        total = len(scenes)
        return {"completed": completed, "total": total, "failed": failed}

    def get_asset_types(self, job_id):
        return [a.get("asset_type", "") for a in self._assets if a.get("job_id") == str(job_id)]

    def get_job_events(self, job_id):
        return [e for e in self._events if e.get("job_id") == str(job_id)]

    def update_job(self, job_id, data):
        for row in self.rows:
            if row["id"] == str(job_id):
                row.update(data)
                return row
        return {}

    def _write_request(self, method, path, json_data=None, prefer="return=representation"):
        if method == "POST" and path == "/rest/v1/assets":
            asset = {"id": str(uuid4()), **(json_data or {})}
            self._assets.append(asset)
            return [asset]
        raise AssertionError(f"unexpected database write: {method} {path}")

    def _request(self, path, params=None):
        if path == "/rest/v1/assets":
            return [
                asset for asset in self._assets
                if asset.get("job_id") == params.get("job_id", "").removeprefix("eq.")
                and asset.get("asset_type") == params.get("asset_type", "").removeprefix("eq.")
            ]
        raise AssertionError(f"unexpected database read: {path}")

    def persist_custom_audio_upload(self, job_id, data):
        if self.fail_custom_audio_persist:
            raise BackendDependencyError("database service unavailable")
        job = self.get_job(job_id)
        if not job or job.get("audio_mode") != "custom_audio" or job.get("status") != "awaiting_audio":
            return None
        job.update({
            "uploaded_audio_duration": data["duration"],
            "effective_duration": data["duration"],
            "updated_at": data["updated_at"],
        })
        self._assets = [
            asset for asset in self._assets
            if not (asset.get("job_id") == str(job_id) and asset.get("asset_type") == "narration_custom")
        ]
        asset = {
            "id": str(uuid4()),
            "job_id": str(job_id),
            "asset_type": "narration_custom",
            "local_path": data["local_path"],
            "mime_type": data["mime_type"],
            "file_size": data["file_size"],
        }
        self._assets.append(asset)
        return asset

    def resume_custom_audio_job(self, job_id):
        job = self.get_job(job_id)
        if not job:
            return None
        if job.get("status") == "awaiting_audio":
            if not any(
                asset.get("job_id") == str(job_id) and asset.get("asset_type") == "narration_custom"
                for asset in self._assets
            ):
                raise BackendDependencyError("uploaded narration is required")
            job.update({"status": "resuming", "current_step": "resuming", "next_stage": "generate_images"})
        return {"status": job.get("status"), "next_stage": job.get("next_stage")}

    def insert_job(self, data):
        new_row = {"id": str(uuid4()), **data}
        self.rows.append(new_row)
        return new_row

    def hard_delete_job(self, job_id):
        self.hard_delete_calls.append(job_id)
        self.rows = [row for row in self.rows if row["id"] != str(job_id)]
        return True


def make_client(tmp_path, workflow=None, database=None):
    return TestClient(
        create_app(
            workflow_client=workflow or FakeWorkflowClient(),
            database_client=database or FakeDatabaseClient(),
            data_dir=tmp_path,
        )
    )


def wav_bytes(duration_seconds, sample_value):
    stream = io.BytesIO()
    with wave.open(stream, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(24000)
        output.writeframes(struct.pack("<h", sample_value) * int(24000 * duration_seconds))
    return stream.getvalue()


def test_custom_audio_replacement_is_atomic_and_upserts_one_asset(tmp_path):
    video_id = uuid4()
    database = FakeDatabaseClient(rows=[{
        "id": str(video_id),
        "audio_mode": "custom_audio",
        "status": "awaiting_audio",
        "brief_json": {"duration": 30},
    }])
    client = make_client(tmp_path, database=database)

    first = client.post(
        f"/api/videos/{video_id}/audio",
        files={"audio": ("first.wav", wav_bytes(1.0, 1000), "audio/wav")},
    )
    replacement = client.post(
        f"/api/videos/{video_id}/audio",
        files={"audio": ("replacement.wav", wav_bytes(1.5, 2000), "audio/wav")},
    )
    canonical = tmp_path / str(video_id) / "narration_custom.wav"
    replacement_bytes = canonical.read_bytes()
    invalid = client.post(
        f"/api/videos/{video_id}/audio",
        files={"audio": ("invalid.wav", b"not audio", "audio/wav")},
    )

    assert first.status_code == 200
    assert replacement.status_code == 200
    assert invalid.status_code == 400
    assert canonical.read_bytes() == replacement_bytes
    custom_assets = [
        asset for asset in database._assets
        if asset["job_id"] == str(video_id) and asset["asset_type"] == "narration_custom"
    ]
    assert len(custom_assets) == 1
    assert database.rows[0]["effective_duration"] == pytest.approx(1.5, abs=0.01)


def test_custom_audio_database_failure_preserves_canonical_file(tmp_path):
    video_id = uuid4()
    database = FakeDatabaseClient(rows=[{
        "id": str(video_id),
        "audio_mode": "custom_audio",
        "status": "awaiting_audio",
        "brief_json": {"duration": 30},
    }])
    client = make_client(tmp_path, database=database)
    first = client.post(
        f"/api/videos/{video_id}/audio",
        files={"audio": ("first.wav", wav_bytes(1.0, 1000), "audio/wav")},
    )
    canonical = tmp_path / str(video_id) / "narration_custom.wav"
    original_bytes = canonical.read_bytes()
    database.fail_custom_audio_persist = True

    replacement = client.post(
        f"/api/videos/{video_id}/audio",
        files={"audio": ("replacement.wav", wav_bytes(1.5, 2000), "audio/wav")},
    )

    assert first.status_code == 200
    assert replacement.status_code == 502
    assert canonical.read_bytes() == original_bytes
    assert database.rows[0]["effective_duration"] == pytest.approx(1.0, abs=0.01)


def test_custom_audio_resume_starts_first_incomplete_image_stage_idempotently(tmp_path):
    video_id = uuid4()
    database = FakeDatabaseClient(
        rows=[{
            "id": str(video_id),
            "audio_mode": "custom_audio",
            "status": "awaiting_audio",
            "current_step": "awaiting_audio",
            "next_stage": "generate_images",
        }],
        assets=[{"job_id": str(video_id), "asset_type": "narration_custom"}],
    )
    client = make_client(tmp_path, workflow=EmptyStatusWorkflowClient(), database=database)

    first = client.post(f"/api/videos/{video_id}/resume")
    second = client.post(f"/api/videos/{video_id}/resume")
    status = client.get(f"/api/videos/{video_id}")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == {"ok": True, "status": "resuming", "next_stage": "generate_images"}
    assert second.json() == first.json()
    assert database.rows[0]["next_stage"] == "generate_images"
    assert status.status_code == 200
    assert status.json()["status"] == "rendering"


def test_create_video_maps_frontend_draft_to_db_brief(tmp_path):
    workflow = FakeWorkflowClient()
    database = FakeDatabaseClient()
    client = make_client(tmp_path, workflow=workflow, database=database)

    response = client.post(
        "/api/videos",
        json={
            "title": "Why the Sky Is Blue",
            "prompt": "Create a concise educational video explaining why the sky appears blue.",
            "duration": "30",
            "style": "Educational",
            "voice": "Studio neutral",
            "captions": "Clean",
            "aspectRatio": "9:16",
        },
    )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    assert body["prompt"] == "Create a concise educational video explaining why the sky appears blue."
    assert len(database.rows) == 1
    row = database.rows[0]
    assert row["brief_json"] == {
        "topic": "Create a concise educational video explaining why the sky appears blue.",
        "duration": 30,
        "contentStyle": "Educational",
        "visualStyle": "Educational",
        "voiceTone": "Studio neutral",
        "captionStyle": "Clean",
        "language": "English",
        "aspectRatio": "9:16",
        "textProvider": "gemini",
        "textModel": "gemini-2.5-flash",
        "imageProvider": "cloudflare",
        "imageModel": "@cf/black-forest-labs/flux-1-schnell",
    }


def test_legacy_create_video_does_not_invent_provider_snapshot(tmp_path):
    database = FakeDatabaseClient()
    client = make_client(tmp_path, database=database)

    response = client.post(
        "/api/videos",
        json={
            "prompt": "Snapshot defaults",
            "duration": 30,
            "style": "Educational",
            "voice": "Neutral",
            "captions": "Clean",
        },
    )

    assert response.status_code == 202
    assert all(database.rows[0].get(field) is None for field in (
        "text_provider", "text_model", "visual_source", "image_provider",
        "image_model", "credential_source", "provider_configuration_version",
    ))
    assert not {"text_provider", "text_model", "visual_source", "credential_source"} & response.json().keys()


def test_create_video_snapshots_explicit_provider_and_model_selection(tmp_path):
    database = FakeDatabaseClient()
    client = make_client(tmp_path, database=database)

    response = client.post(
        "/api/videos",
        json={
            "prompt": "Snapshot explicit choices",
            "duration": 30,
            "style": "Educational",
            "voice": "Neutral",
            "captions": "Clean",
            "text_provider": "cloudflare",
            "text_model": "@cf/meta/llama-3.1-8b-instruct",
            "image_provider": "cloudflare",
            "image_model": "@cf/black-forest-labs/flux-1-schnell",
            "visual_source": "ai",
            "credential_source": "environment",
            "provider_configuration_version": "1",
        },
    )

    assert response.status_code == 202
    assert database.rows[0]["text_provider"] == "cloudflare"
    assert database.rows[0]["text_model"] == "@cf/meta/llama-3.1-8b-instruct"
    assert database.rows[0]["visual_source"] == "ai"
    assert database.rows[0]["credential_source"] == "environment"
    assert database.rows[0]["provider_configuration_version"] == "1"
    assert "visualSource" not in database.rows[0]["brief_json"]


def test_create_video_snapshots_nvidia_stored_credential_selection(tmp_path):
    database = FakeDatabaseClient()
    database.credential = {"encrypted_secret": "ciphertext", "enabled": True, "status": "configured"}
    client = make_client(tmp_path, database=database)

    response = client.post(
        "/api/videos",
        json={
            "prompt": "NVIDIA snapshot",
            "duration": 30,
            "style": "Educational",
            "voice": "Neutral",
            "captions": "Clean",
            "text_provider": "nvidia",
            "text_model": "nvidia/llama-3.3-nemotron-super-49b-v1",
            "image_provider": "cloudflare",
            "image_model": "@cf/black-forest-labs/flux-1-schnell",
            "visual_source": "ai",
            "credential_source": "stored",
            "provider_configuration_version": "1",
        },
    )

    assert response.status_code == 202
    assert database.rows[0]["text_provider"] == "nvidia"
    assert database.rows[0]["text_model"] == "nvidia/llama-3.3-nemotron-super-49b-v1"
    assert database.rows[0]["credential_source"] == "stored"
    assert database.rows[0]["brief_json"]["textProvider"] == "nvidia"
    assert database.rows[0]["brief_json"]["textModel"] == "nvidia/llama-3.3-nemotron-super-49b-v1"


def test_create_video_rejects_nvidia_environment_credentials(tmp_path):
    response = make_client(tmp_path).post(
        "/api/videos",
        json={
            "prompt": "NVIDIA must use stored credentials",
            "duration": 30,
            "style": "Educational",
            "voice": "Neutral",
            "captions": "Clean",
            "text_provider": "nvidia",
            "text_model": "nvidia/llama-3.3-nemotron-super-49b-v1",
            "credential_source": "environment",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "unsupported_credential_source"


def test_nvidia_metadata_and_generation_require_configured_stored_credential(tmp_path):
    database = FakeDatabaseClient()
    client = make_client(tmp_path, database=database)

    unavailable = client.get("/api/ai/providers/nvidia")
    rejected = client.post(
        "/api/videos",
        json={
            "prompt": "NVIDIA needs a configured credential",
            "duration": 30,
            "style": "Educational",
            "voice": "Neutral",
            "captions": "Clean",
            "text_provider": "nvidia",
            "text_model": "nvidia/llama-3.3-nemotron-super-49b-v1",
            "credential_source": "stored",
        },
    )

    assert unavailable.json()["available"] is False
    assert unavailable.json()["models"][0]["available"] is False
    assert rejected.status_code == 422
    assert rejected.json()["detail"]["code"] == "unavailable_provider"


def test_legacy_explicit_text_selection_remains_backward_compatible(tmp_path):
    database = FakeDatabaseClient()
    client = make_client(tmp_path, database=database)

    response = client.post(
        "/api/videos",
        json={
            "prompt": "Legacy explicit text selection",
            "duration": 30,
            "style": "Educational",
            "voice": "Neutral",
            "captions": "Clean",
            "text_provider": "cloudflare",
            "text_model": "@cf/meta/llama-3.1-8b-instruct",
        },
    )

    assert response.status_code == 202
    assert database.rows[0]["text_provider"] == "cloudflare"
    assert database.rows[0]["image_provider"] == "cloudflare"


def test_create_video_persists_colon_containing_model_id_exactly(tmp_path, monkeypatch):
    cloudflare = next(item for item in provider_registry.PROVIDER_REGISTRY if item.provider_id == "cloudflare")
    colon_model = provider_registry.ModelDefinition(
        model_id="model:variant:version",
        display_name="Colon model",
        capability="text",
        implemented=True,
        enabled=True,
        deprecated=False,
    )
    patched_cloudflare = provider_registry.ProviderDefinition(
        provider_id=cloudflare.provider_id,
        display_name=cloudflare.display_name,
        provider_type=cloudflare.provider_type,
        capabilities=cloudflare.capabilities,
        requires_credential=cloudflare.requires_credential,
        credential_type=cloudflare.credential_type,
        enabled=cloudflare.enabled,
        implemented=cloudflare.implemented,
        models=cloudflare.models + (colon_model,),
        default_model=cloudflare.default_model,
    )
    monkeypatch.setattr(
        provider_registry,
        "PROVIDER_REGISTRY",
        tuple(patched_cloudflare if item.provider_id == "cloudflare" else item for item in provider_registry.PROVIDER_REGISTRY),
    )
    database = FakeDatabaseClient()
    client = make_client(tmp_path, database=database)

    response = client.post(
        "/api/videos",
        json={
            "prompt": "Opaque model ID",
            "duration": 30,
            "style": "Educational",
            "voice": "Neutral",
            "captions": "Clean",
            "text_provider": "cloudflare",
            "text_model": "model:variant:version",
            "image_provider": "cloudflare",
            "image_model": "@cf/black-forest-labs/flux-1-schnell",
            "visual_source": "ai",
        },
    )

    assert response.status_code == 202
    assert database.rows[0]["text_model"] == "model:variant:version"


def test_create_video_snapshots_pexels_without_ai_image_selection(tmp_path):
    database = FakeDatabaseClient()
    workflow = FakeWorkflowClient()
    client = make_client(tmp_path, workflow=workflow, database=database)

    response = client.post(
        "/api/videos",
        json={
            "prompt": "Stock footage",
            "duration": 30,
            "style": "Editorial",
            "voice": "Neutral",
            "captions": "Clean",
            "text_provider": "cloudflare",
            "text_model": "@cf/meta/llama-3.1-8b-instruct",
            "visual_source": "pexels",
            "pexels_media_type": "video",
            "pexels_orientation": "portrait",
            "credential_source": "environment",
            "provider_configuration_version": "1",
        },
    )

    assert response.status_code == 202
    row = database.rows[0]
    assert row["visual_source"] == "pexels"
    assert row.get("image_provider") is None
    assert row.get("image_model") is None
    assert "visual_source" not in row["brief_json"]
    assert workflow.create_payload is None


@pytest.mark.parametrize(
    ("fields", "code"),
    [
        ({"text_provider": "cloudflare"}, "incomplete_provider_model"),
        ({"text_provider": "cloudflare", "text_model": "gemini-2.5-flash"}, "provider_model_mismatch"),
        ({"text_provider": "missing", "text_model": "missing"}, "unknown_provider"),
        ({"text_provider": "nvidia", "text_model": "not-a-nvidia-model", "credential_source": "stored"}, "unknown_model"),
        ({"text_provider": "cloudflare", "text_model": "@cf/meta/llama-3.1-8b-instruct", "visual_source": "cdn"}, "unsupported_visual_source"),
        ({"text_provider": "cloudflare", "text_model": "@cf/meta/llama-3.1-8b-instruct", "credential_source": "vault"}, "unsupported_credential_source"),
    ],
)
def test_create_video_rejects_invalid_generation_configuration(tmp_path, fields, code):
    client = make_client(tmp_path)
    payload = {
        "prompt": "Invalid configuration",
        "duration": 30,
        "style": "Educational",
        "voice": "Neutral",
        "captions": "Clean",
        **fields,
    }

    response = client.post("/api/videos", json=payload)

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == code


def test_create_video_rejects_unavailable_provider(tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    client = make_client(tmp_path)

    response = client.post(
        "/api/videos",
        json={
            "prompt": "Unavailable provider",
            "duration": 30,
            "style": "Educational",
            "voice": "Neutral",
            "captions": "Clean",
            "text_provider": "gemini",
            "text_model": "gemini-2.5-flash",
            "image_provider": "cloudflare",
            "image_model": "@cf/black-forest-labs/flux-1-schnell",
            "visual_source": "ai",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "unavailable_provider"


def test_rename_does_not_change_job_configuration_snapshot(tmp_path):
    video_id = uuid4()
    snapshot = {
        "text_provider": "gemini",
        "text_model": "gemini-2.5-flash",
        "visual_source": "ai",
        "image_provider": "cloudflare",
        "image_model": "@cf/black-forest-labs/flux-1-schnell",
        "credential_source": "environment",
        "provider_configuration_version": "registry-v1",
    }
    database = FakeDatabaseClient([{
        "id": str(video_id),
        "topic": "Old title",
        "status": "completed",
        "progress": 100,
        "brief_json": {"topic": "Old title", "duration": 30, "visualStyle": "Cinematic"},
        **snapshot,
    }])
    client = make_client(tmp_path, database=database)

    response = client.patch(f"/api/videos/{video_id}", json={"title": "New title"})

    assert response.status_code == 200
    row = database.get_job(video_id)
    assert row is not None
    assert {key: row[key] for key in snapshot} == snapshot


def test_legacy_job_without_snapshot_remains_readable(tmp_path):
    video_id = uuid4()
    database = FakeDatabaseClient([{
        "id": str(video_id),
        "topic": "Legacy job",
        "status": "completed",
        "progress": 100,
        "brief_json": {"topic": "Legacy job", "duration": 30, "visualStyle": "Cinematic"},
    }])
    client = make_client(tmp_path, database=database)

    assert client.get("/api/videos").status_code == 200
    assert client.get(f"/api/videos/{video_id}").status_code == 200
    assert client.get(f"/api/videos/{video_id}/status").status_code == 200


def test_regeneration_and_duplicate_copy_existing_snapshot(tmp_path):
    video_id = uuid4()
    snapshot = {
        "text_provider": "cloudflare",
        "text_model": "@cf/meta/llama-3.1-8b-instruct",
        "visual_source": "ai",
        "image_provider": "cloudflare",
        "image_model": "@cf/black-forest-labs/flux-1-schnell",
        "credential_source": "environment",
        "provider_configuration_version": "registry-v1",
    }
    database = FakeDatabaseClient([{
        "id": str(video_id),
        "topic": "Existing configuration",
        "status": "completed",
        "progress": 100,
        "brief_json": {
            "topic": "Existing configuration",
            "duration": 30,
            "visualStyle": "Cinematic",
            "textProvider": "gemini",
            "textModel": "gemini-2.5-flash",
        },
        **snapshot,
    }])
    client = make_client(tmp_path, database=database)

    regenerated = client.post(f"/api/videos/{video_id}/regenerate")
    duplicated = client.post(f"/api/videos/{video_id}/duplicate")

    assert regenerated.status_code == 202
    assert duplicated.status_code == 200
    created_rows = [row for row in database.rows if row["id"] != str(video_id)]
    assert len(created_rows) == 2
    for row in created_rows:
        assert {key: row[key] for key in snapshot} == snapshot


def test_legacy_regeneration_does_not_invent_snapshot(tmp_path):
    video_id = uuid4()
    database = FakeDatabaseClient([{
        "id": str(video_id),
        "topic": "Legacy job",
        "status": "completed",
        "progress": 100,
        "brief_json": {"topic": "Legacy job", "duration": 30},
    }])
    client = make_client(tmp_path, database=database)

    response = client.post(f"/api/videos/{video_id}/regenerate")

    assert response.status_code == 202
    derived = database.rows[-1]
    assert not any(field in derived for field in (
        "text_provider", "text_model", "visual_source", "image_provider",
        "image_model", "credential_source", "provider_configuration_version",
    ))


def test_regeneration_and_duplication_preserve_pexels_snapshot_without_ai_image_fields(tmp_path):
    video_id = uuid4()
    snapshot = {
        "text_provider": "cloudflare",
        "text_model": "@cf/meta/llama-3.1-8b-instruct",
        "visual_source": "pexels",
        "image_provider": None,
        "image_model": None,
        "credential_source": "environment",
        "provider_configuration_version": "1",
    }
    database = FakeDatabaseClient([{
        "id": str(video_id),
        "topic": "Pexels source",
        "status": "completed",
        "progress": 100,
        "brief_json": {"topic": "Pexels source", "duration": 30},
        **snapshot,
    }])
    client = make_client(tmp_path, database=database)

    assert client.post(f"/api/videos/{video_id}/regenerate").status_code == 202
    assert client.post(f"/api/videos/{video_id}/duplicate").status_code == 200
    for row in database.rows[1:]:
        assert {key: row.get(key) for key in snapshot} == snapshot


def test_snapshot_migration_is_additive_and_contains_only_non_secret_fields():
    import pytest
    migration = Path(__file__).parents[2] / "clipcraft/supabase/migrations/009_video_job_configuration_snapshots.sql"
    if not migration.is_file():
        pytest.skip(f"Migration file not found: {migration}")
    sql = migration.read_text(encoding="utf-8").lower()

    for column in (
        "text_provider",
        "text_model",
        "visual_source",
        "image_provider",
        "image_model",
        "credential_source",
        "provider_configuration_version",
    ):
        assert f"add column if not exists {column} text" in sql
    assert "alter table public.video_jobs" in sql
    assert "update public.video_jobs" not in sql
    assert "delete from public.video_jobs" not in sql
    assert "encrypted_secret" not in sql


def test_create_video_creates_shared_job_directory(tmp_path):
    workflow = FakeWorkflowClient()
    client = make_client(tmp_path, workflow=workflow)

    response = client.post(
        "/api/videos",
        json={
            "title": "Directory test",
            "prompt": "Create a short video",
            "duration": "30",
            "style": "Cinematic",
            "voice": "Warm narrator",
            "captions": "Clean",
            "aspectRatio": "9:16",
        },
    )

    assert response.status_code == 202
    assert (tmp_path / response.json()["id"]).is_dir()


def test_create_video_rejects_duration_not_supported_by_wf02(tmp_path):
    client = make_client(tmp_path)

    response = client.post(
        "/api/videos",
        json={
            "title": "Unsupported",
            "prompt": "A short video",
            "duration": "15",
            "style": "Educational",
            "voice": "Neutral",
            "captions": "Clean",
            "aspectRatio": "9:16",
        },
    )

    assert response.status_code == 422
    assert "30, 45, 60, or 90" in response.json()["detail"][0]["msg"]


def test_create_video_returns_dependency_error_when_database_insert_fails(tmp_path):
    class BrokenDatabaseClient(FakeDatabaseClient):
        def insert_job(self, data):
            raise BackendDependencyError("database service is not configured")

    client = make_client(tmp_path, database=BrokenDatabaseClient())

    response = client.post(
        "/api/videos",
        json={
            "title": "DB fail",
            "prompt": "A video",
            "duration": "30",
            "style": "Educational",
            "voice": "Neutral",
            "captions": "Clean",
            "aspectRatio": "9:16",
        },
    )

    assert response.status_code == 502
    assert response.json()["detail"] == "database service is not configured"


def test_media_endpoint_serves_fixed_video_path_without_leaking_filesystem(tmp_path):
    video_id = uuid4()
    job_dir = tmp_path / str(video_id)
    job_dir.mkdir()
    video_path = job_dir / "final.mp4"
    video_path.write_bytes(b"mp4-test")
    database = FakeDatabaseClient([{"id": str(video_id), "topic": "A test", "status": "completed"}])
    client = make_client(tmp_path, database=database)

    response = client.get(f"/api/videos/{video_id}/file")

    assert response.status_code == 200
    assert response.headers["content-type"] == "video/mp4"
    assert response.content == b"mp4-test"
    assert str(tmp_path) not in response.text


def test_media_endpoint_rejects_invalid_uuid_and_missing_job(tmp_path):
    client = make_client(tmp_path)

    invalid = client.get("/api/videos/not-a-uuid/file")
    missing = client.get(f"/api/videos/{uuid4()}/file")

    assert invalid.status_code == 422
    assert missing.status_code == 404
    assert str(tmp_path) not in missing.text


def test_thumbnail_uses_fixed_filename_and_jpeg_type(tmp_path):
    video_id = uuid4()
    job_dir = tmp_path / str(video_id)
    job_dir.mkdir()
    (job_dir / "thumbnail.jpg").write_bytes(b"jpeg-test")
    database = FakeDatabaseClient([{"id": str(video_id), "topic": "A test", "status": "completed"}])
    client = make_client(tmp_path, database=database)

    response = client.get(f"/api/videos/{video_id}/thumbnail")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert response.content == b"jpeg-test"


def test_media_endpoint_supports_ranges_and_reports_unsatisfiable_ranges(tmp_path):
    video_id = uuid4()
    job_dir = tmp_path / str(video_id)
    job_dir.mkdir()
    (job_dir / "final.mp4").write_bytes(b"0123456789")
    database = FakeDatabaseClient([{"id": str(video_id), "topic": "A test", "status": "completed"}])
    client = make_client(tmp_path, database=database)

    partial = client.get(f"/api/videos/{video_id}/file", headers={"Range": "bytes=2-5"})
    invalid = client.get(f"/api/videos/{video_id}/file", headers={"Range": "bytes=20-30"})

    assert partial.status_code == 206
    assert partial.content == b"2345"
    assert partial.headers["content-range"] == "bytes 2-5/10"
    assert invalid.status_code == 416
    assert invalid.headers["content-range"] == "bytes */10"


def test_status_falls_back_to_existing_database_row_when_wf10_is_empty(tmp_path):
    video_id = uuid4()
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    database = FakeDatabaseClient([{
        "id": str(video_id),
        "topic": "A test",
        "status": "rendering",
        "progress": 64,
        "current_step": "rendering",
        "created_at": now,
        "updated_at": now,
    }])
    client = make_client(tmp_path, workflow=EmptyStatusWorkflowClient(), database=database)

    response = client.get(f"/api/videos/{video_id}/status")

    assert response.status_code == 200
    assert response.json()["status"] == "rendering"
    assert response.json()["progress"] == 64


def test_status_returns_scene_counts_and_asset_facts(tmp_path):
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    video_id = uuid4()
    database = FakeDatabaseClient(
        rows=[{
            "id": str(video_id),
            "topic": "Test",
            "status": "generating_images",
            "progress": 35,
            "current_step": "Generating image 3 of 6",
            "created_at": now,
            "updated_at": now,
        }],
        scenes=[
            {"job_id": str(video_id), "generation_status": "completed"},
            {"job_id": str(video_id), "generation_status": "completed"},
            {"job_id": str(video_id), "generation_status": "completed"},
            {"job_id": str(video_id), "generation_status": "failed"},
            {"job_id": str(video_id), "generation_status": "pending"},
            {"job_id": str(video_id), "generation_status": "pending"},
        ],
        assets=[
            {"job_id": str(video_id), "asset_type": "narration"},
            {"job_id": str(video_id), "asset_type": "captions"},
        ],
    )
    client = make_client(tmp_path, workflow=EmptyStatusWorkflowClient(), database=database)

    response = client.get(f"/api/videos/{video_id}/status")
    assert response.status_code == 200
    body = response.json()
    assert body["image_progress"] == {"completed": 3, "total": 6, "failed": 1}
    assert body["assets"] == {"narration": True, "captions": True, "manifest": False, "video": False, "thumbnail": False}


def test_status_returns_completed_state_with_events(tmp_path):
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    video_id = uuid4()
    database = FakeDatabaseClient(
        rows=[{
            "id": str(video_id),
            "topic": "Done job",
            "status": "completed",
            "progress": 100,
            "current_step": "completed",
            "created_at": now,
            "updated_at": now,
            "completed_at": now,
        }],
        events=[
            {"id": str(uuid4()), "job_id": str(video_id), "event_type": "job_created", "stage": None, "status": None, "progress": 0, "message": "Job created", "created_at": now},
            {"id": str(uuid4()), "job_id": str(video_id), "event_type": "job_completed", "stage": None, "status": None, "progress": 100, "message": "Completed", "created_at": now},
        ],
    )
    client = make_client(tmp_path, workflow=EmptyStatusWorkflowClient(), database=database)

    response = client.get(f"/api/videos/{video_id}/status")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["display_status"] == "Completed"
    assert body["stale"] is False
    assert len(body["recent_events"]) == 2
    assert body["recent_events"][0]["type"] == "job_completed" or body["recent_events"][1]["type"] == "job_completed"


def test_status_returns_failed_with_sanitized_error(tmp_path):
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    video_id = uuid4()
    database = FakeDatabaseClient(
        rows=[{
            "id": str(video_id),
            "topic": "Failed job",
            "status": "failed",
            "progress": 5,
            "current_step": "generating_script",
            "error_message": "Word count out of range",
            "failure_class": "runtime",
            "created_at": now,
            "updated_at": now,
        }],
        events=[
            {"id": str(uuid4()), "job_id": str(video_id), "event_type": "job_failed", "stage": "generating_script", "status": None, "progress": 5, "message": "Word count out of range", "created_at": now},
        ],
    )
    client = make_client(tmp_path, workflow=EmptyStatusWorkflowClient(), database=database)

    response = client.get(f"/api/videos/{video_id}/status")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["error"]["message"] == "Word count out of range"


def test_status_surfaces_timeout_for_stale_active_job_without_error(tmp_path):
    from datetime import datetime, timedelta, timezone

    video_id = uuid4()
    old = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    database = FakeDatabaseClient(rows=[{
        "id": str(video_id),
        "topic": "Stalled job",
        "status": "generating_voice",
        "progress": 50,
        "current_step": "generating_voice",
        "created_at": old,
        "updated_at": old,
    }])
    client = make_client(tmp_path, workflow=EmptyStatusWorkflowClient(), database=database)

    response = client.get(f"/api/videos/{video_id}/status")

    assert response.status_code == 200
    body = response.json()
    assert body["stale"] is True
    assert body["error"]["code"] == "STAGE_TIMEOUT"
    assert body["error"]["message"] == "Video generation stalled during generating_voice"


def test_status_does_not_expose_internal_paths(tmp_path):
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    video_id = uuid4()
    database = FakeDatabaseClient(
        rows=[{
            "id": str(video_id),
            "topic": "Clean",
            "status": "completed",
            "progress": 100,
            "current_step": None,
            "created_at": now,
            "updated_at": now,
        }],
    )
    client = make_client(tmp_path, workflow=EmptyStatusWorkflowClient(), database=database)

    response = client.get(f"/api/videos/{video_id}/status")
    body = response.json()
    body_str = str(body)
    assert str(tmp_path) not in body_str and "/data" not in body_str
    assert "service_role" not in body_str.lower() and "apikey" not in body_str.lower()
    assert "token" not in body_str.lower() and "prompt" not in body_str


def test_status_handles_legacy_record_without_event_or_scene_rows(tmp_path):
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    video_id = uuid4()
    database = FakeDatabaseClient(
        rows=[{
            "id": str(video_id),
            "topic": "Old record",
            "status": "completed",
            "progress": 100,
            "current_step": None,
            "created_at": now,
            "updated_at": now,
        }],
    )
    client = make_client(tmp_path, workflow=EmptyStatusWorkflowClient(), database=database)

    response = client.get(f"/api/videos/{video_id}/status")
    assert response.status_code == 200
    body = response.json()
    assert body["image_progress"] == {"completed": 0, "total": 0, "failed": 0}
    assert body["recent_events"] == []


def test_rename_video_updates_title(tmp_path):
    video_id = uuid4()
    database = FakeDatabaseClient(
        rows=[{
            "id": str(video_id),
            "topic": "Old title",
            "status": "completed",
            "progress": 100,
            "brief_json": {"topic": "Old title", "duration": 30, "visualStyle": "Cinematic"},
        }],
    )
    client = make_client(tmp_path, database=database)

    response = client.patch(f"/api/videos/{video_id}", json={"title": "New title"})

    assert response.status_code == 200
    assert response.json()["title"] == "New title"


def test_rename_video_requires_title(tmp_path):
    video_id = uuid4()
    client = make_client(tmp_path)

    response = client.patch(f"/api/videos/{video_id}", json={"not_title": "nope"})

    assert response.status_code == 422


def test_rename_video_404_when_missing(tmp_path):
    client = make_client(tmp_path)

    response = client.patch(f"/api/videos/{uuid4()}", json={"title": "Nope"})

    assert response.status_code == 404


def test_regenerate_video_returns_new_job_id(tmp_path):
    video_id = uuid4()
    database = FakeDatabaseClient(
        rows=[{
            "id": str(video_id),
            "topic": "Regenerate me",
            "status": "completed",
            "progress": 100,
            "brief_json": {"topic": "Regenerate me", "duration": 30, "visualStyle": "Cinematic"},
        }],
    )
    client = make_client(tmp_path, database=database)

    response = client.post(f"/api/videos/{video_id}/regenerate")

    assert response.status_code == 202
    body = response.json()
    assert "id" in body
    assert UUID(body["id"])


def test_regenerate_video_404_when_missing(tmp_path):
    client = make_client(tmp_path)

    response = client.post(f"/api/videos/{uuid4()}/regenerate")

    assert response.status_code == 404


def test_duplicate_video_creates_new_copy(tmp_path):
    video_id = uuid4()
    database = FakeDatabaseClient(
        rows=[{
            "id": str(video_id),
            "topic": "Original",
            "status": "completed",
            "progress": 100,
            "channel_id": "default",
            "brief_json": {"topic": "Original", "duration": 30, "visualStyle": "Cinematic", "voiceTone": "Neutral", "captionStyle": "Clean", "aspectRatio": "9:16"},
        }],
    )
    client = make_client(tmp_path, database=database)

    response = client.post(f"/api/videos/{video_id}/duplicate")

    assert response.status_code == 200
    body = response.json()
    assert "id" in body
    duplicate_id = body["id"]
    assert duplicate_id != str(video_id)

    dup = database.get_job(UUID(duplicate_id))
    assert dup is not None
    assert dup.get("topic") == "Original"


def test_duplicate_video_404_when_missing(tmp_path):
    client = make_client(tmp_path)

    response = client.post(f"/api/videos/{uuid4()}/duplicate")

    assert response.status_code == 404


def test_delete_video_hard_deletes_and_removes_only_target_files(tmp_path):
    video_id = uuid4()
    database = FakeDatabaseClient(
        rows=[{
            "id": str(video_id),
            "topic": "Delete me",
            "status": "completed",
            "progress": 100,
        }],
    )
    job_dir = tmp_path / str(video_id)
    job_dir.mkdir()
    (job_dir / "final.mp4").write_text("fake_video")
    sibling_dir = tmp_path / str(uuid4())
    sibling_dir.mkdir()
    (sibling_dir / "keep.mp4").write_text("keep")
    shared_file = tmp_path / "shared.txt"
    shared_file.write_text("keep")
    client = make_client(tmp_path, database=database)

    response = client.delete(f"/api/videos/{video_id}")

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert database.get_job(video_id) is None
    assert database.hard_delete_calls == [video_id]
    assert not job_dir.exists()
    assert (sibling_dir / "keep.mp4").read_text() == "keep"
    assert shared_file.read_text() == "keep"


def test_delete_video_database_failure_leaves_local_files(tmp_path):
    video_id = uuid4()

    class FailingDatabase(FakeDatabaseClient):
        def hard_delete_job(self, job_id):
            raise BackendDependencyError("database service returned an error")

    database = FailingDatabase(rows=[{"id": str(video_id), "status": "completed"}])
    job_dir = tmp_path / str(video_id)
    job_dir.mkdir()
    (job_dir / "final.mp4").write_text("keep")
    client = make_client(tmp_path, database=database)

    response = client.delete(f"/api/videos/{video_id}")

    assert response.status_code == 502
    assert (job_dir / "final.mp4").read_text() == "keep"


def test_delete_video_validates_path_before_and_after_database_delete(tmp_path, monkeypatch):
    from app import main as main_module

    video_id = uuid4()
    sequence = []

    class RecordingDatabase(FakeDatabaseClient):
        def hard_delete_job(self, job_id):
            sequence.append("database")
            return super().hard_delete_job(job_id)

    database = RecordingDatabase(rows=[{"id": str(video_id), "status": "completed"}])
    job_dir = tmp_path / str(video_id)
    job_dir.mkdir()
    validations = []

    def validate(root, requested_id):
        sequence.append("validate")
        validations.append((root, requested_id))
        return job_dir

    monkeypatch.setattr(main_module, "_safe_job_directory", validate, raising=False)
    client = make_client(tmp_path, database=database)

    response = client.delete(f"/api/videos/{video_id}")

    assert response.status_code == 200
    assert validations == [(tmp_path.resolve(), video_id), (tmp_path.resolve(), video_id)]
    assert sequence == ["validate", "database", "validate"]


def test_safe_job_directory_rejects_symlink_to_another_directory(tmp_path):
    from app import main as main_module

    video_id = uuid4()
    outside = tmp_path.parent / f"outside-{uuid4()}"
    outside.mkdir()
    candidate = tmp_path / str(video_id)
    try:
        candidate.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks are unavailable")

    try:
        with pytest.raises(ValueError, match="unsafe video job directory"):
            main_module._safe_job_directory(tmp_path, video_id)
        assert outside.exists()
    finally:
        candidate.unlink(missing_ok=True)
        outside.rmdir()


def test_delete_video_404_when_missing(tmp_path):
    client = make_client(tmp_path)

    response = client.delete(f"/api/videos/{uuid4()}")

    assert response.status_code == 404


def test_cancel_video_sets_status_to_cancelled(tmp_path):
    video_id = uuid4()
    database = FakeDatabaseClient(
        rows=[{
            "id": str(video_id),
            "topic": "Cancel me",
            "status": "rendering",
            "progress": 50,
            "current_step": "rendering",
        }],
    )
    client = make_client(tmp_path, database=database)

    response = client.post(f"/api/videos/{video_id}/cancel")

    assert response.status_code == 200
    assert response.json() == {"ok": True, "id": str(video_id), "status": "cancelled"}
    row = database.get_job(video_id)
    assert row is not None
    assert row["status"] == "cancelled"


def test_cancel_video_idempotent_for_already_cancelled(tmp_path):
    video_id = uuid4()
    database = FakeDatabaseClient(
        rows=[{
            "id": str(video_id),
            "topic": "Already cancelled",
            "status": "cancelled",
            "progress": 0,
        }],
    )
    client = make_client(tmp_path, database=database)

    response = client.post(f"/api/videos/{video_id}/cancel")

    assert response.status_code == 200
    assert response.json() == {"ok": True, "id": str(video_id), "status": "cancelled"}


def test_cancel_video_rejects_completed_job(tmp_path):
    video_id = uuid4()
    database = FakeDatabaseClient(
        rows=[{
            "id": str(video_id),
            "topic": "Already done",
            "status": "completed",
            "progress": 100,
        }],
    )
    client = make_client(tmp_path, database=database)

    response = client.post(f"/api/videos/{video_id}/cancel")

    assert response.status_code == 409
    assert "completed" in response.json()["detail"]


def test_cancel_video_rejects_failed_job(tmp_path):
    video_id = uuid4()
    database = FakeDatabaseClient(
        rows=[{
            "id": str(video_id),
            "topic": "Already failed",
            "status": "failed",
            "progress": 5,
        }],
    )
    client = make_client(tmp_path, database=database)

    response = client.post(f"/api/videos/{video_id}/cancel")

    assert response.status_code == 409
    assert "failed" in response.json()["detail"]


def test_cancel_video_404_when_missing(tmp_path):
    client = make_client(tmp_path)

    response = client.post(f"/api/videos/{uuid4()}/cancel")

    assert response.status_code == 404
