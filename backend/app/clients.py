import json as json_lib
import logging
import time
from typing import Any
from uuid import UUID

import httpx

from .config import Settings

logger = logging.getLogger(__name__)


class BackendDependencyError(RuntimeError):
    pass


class TransientError(BackendDependencyError):
    pass


class WorkflowClient:
    def __init__(self, settings: Settings):
        self.base_url = settings.n8n_base_url
        self.api_key = settings.n8n_api_key

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        url = f"{self.base_url}{path}"
        try:
            response = httpx.request(method, url, timeout=30, **kwargs)
        except httpx.HTTPError as exc:
            logger.error("n8n request failed: %s %s — %s", method, url, exc)
            raise BackendDependencyError("workflow service unavailable") from exc
        if response.status_code >= 400:
            logger.warning("n8n returned %s: %s %s — %s", response.status_code, method, url, response.text[:500])
            raise BackendDependencyError("workflow service returned an error")
        try:
            return response.json()
        except ValueError as exc:
            logger.error("n8n returned empty/non-JSON body: %s %s — status=%s body=%r", method, url, response.status_code, response.content[:500])
            raise BackendDependencyError("workflow service returned an empty response") from exc

    def create_job(self, payload: dict[str, Any]) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                return self._request("POST", "/webhook/videos/create", json=payload)
            except BackendDependencyError as exc:
                last_error = exc
                if "empty response" in str(exc) and attempt < 2:
                    time.sleep(0.5 * (attempt + 1))
                    continue
                raise
        raise last_error  # type: ignore[misc]

    def get_status(self, job_id: UUID) -> dict[str, Any]:
        return self._request("GET", f"/webhook/video/status?jobId={job_id}")

    def get_result(self, job_id: UUID) -> dict[str, Any] | None:
        try:
            return self._request("GET", f"/webhook/video/result?jobId={job_id}")
        except BackendDependencyError:
            return None

    def stop_execution(self, execution_id: str) -> None:
        if not self.api_key:
            raise BackendDependencyError("n8n api key is not configured")
        headers = {"X-N8N-API-KEY": self.api_key}
        self._request("POST", f"/rest/executions/{execution_id}/stop", headers=headers)


class DatabaseClient:
    columns = "id,topic,status,progress,current_step,error_message,brief_json,script_json,created_at,updated_at,output_url,thumbnail_url,completed_at,text_provider,text_model,visual_source,image_provider,image_model,credential_source,provider_configuration_version,audio_mode,effective_duration,next_stage,last_completed_stage"

    def __init__(self, settings: Settings):
        self.url = settings.supabase_url
        self.key = settings.supabase_service_role_key
        self._headers = {"apikey": self.key, "Authorization": f"Bearer {self.key}"}

    def _request(self, path: str, params: dict[str, str] | None = None) -> Any:
        if not self.url or not self.key:
            raise BackendDependencyError("database service is not configured")
        try:
            response = httpx.get(
                f"{self.url}{path}",
                params=params,
                headers={**self._headers},
                timeout=30,
            )
        except httpx.HTTPError as exc:
            raise BackendDependencyError("database service unavailable") from exc
        if response.status_code >= 400:
            raise BackendDependencyError("database service returned an error")
        return response.json()

    def _write_request(
        self,
        method: str,
        path: str,
        json_data: dict[str, Any] | None = None,
        prefer: str = "return=representation",
    ) -> Any:
        if not self.url or not self.key:
            raise BackendDependencyError("database service is not configured")
        try:
            response = httpx.request(
                method,
                f"{self.url}{path}",
                json=json_data,
                headers={
                    **self._headers,
                    "Content-Type": "application/json",
                    "Prefer": prefer,
                },
                timeout=30,
            )
        except httpx.HTTPError as exc:
            raise BackendDependencyError("database service unavailable") from exc
        if response.status_code >= 400:
            raise BackendDependencyError("database service returned an error")
        if response.content:
            return response.json()
        return None

    def get_job(self, job_id: UUID) -> dict[str, Any] | None:
        rows = self._request(
            "/rest/v1/video_jobs",
            {"id": f"eq.{job_id}", "select": self.columns, "limit": "1"},
        )
        return rows[0] if rows else None

    def list_jobs(self) -> list[dict[str, Any]]:
        return self._request(
            "/rest/v1/video_jobs",
            {"select": self.columns, "order": "created_at.desc", "status": "neq.cancelled"},
        )

    def update_job(self, job_id: UUID, data: dict[str, Any]) -> dict[str, Any]:
        result = self._write_request(
            "PATCH",
            f"/rest/v1/video_jobs?id=eq.{job_id}",
            json_data=data,
        )
        if isinstance(result, list):
            return result[0] if result else {}
        return result or {}

    def persist_custom_audio_upload(self, job_id: UUID, data: dict[str, Any]) -> dict[str, Any]:
        result = self._write_request(
            "POST",
            "/rest/v1/rpc/persist_custom_audio_upload",
            json_data={
                "p_job_id": str(job_id),
                "p_local_path": data["local_path"],
                "p_mime_type": data["mime_type"],
                "p_file_size": data["file_size"],
                "p_duration": data["duration"],
            },
        )
        return result or {}

    def resume_custom_audio_job(self, job_id: UUID) -> dict[str, Any]:
        result = self._write_request(
            "POST",
            "/rest/v1/rpc/resume_custom_audio_job",
            json_data={"p_job_id": str(job_id)},
        )
        return result or {}

    def insert_job(self, data: dict[str, Any]) -> dict[str, Any]:
        result = self._write_request(
            "POST",
            "/rest/v1/video_jobs",
            json_data=data,
        )
        if isinstance(result, list):
            return result[0] if result else {}
        return result or {}

    def hard_delete_job(self, job_id: UUID) -> bool:
        result = self._write_request(
            "POST",
            "/rest/v1/rpc/hard_delete_video_job",
            json_data={"p_job_id": str(job_id)},
        )
        return result is True

    def list_credentials(self) -> list[dict[str, Any]]:
        return self._request(
            "/rest/v1/ai_provider_credentials",
            {
                "select": "id,provider_id,secret_last_four,enabled,status,created_at,updated_at,last_tested_at,last_test_status,last_test_error_safe",
                "order": "provider_id.asc",
            },
        )

    def get_credential(self, provider_id: str) -> dict[str, Any] | None:
        rows = self._request(
            "/rest/v1/ai_provider_credentials",
            {
                "provider_id": f"eq.{provider_id}",
                "select": "id,provider_id,secret_last_four,enabled,status,created_at,updated_at,last_tested_at,last_test_status,last_test_error_safe",
                "limit": "1",
            },
        )
        return rows[0] if rows else None

    def get_credential_for_test(self, provider_id: str) -> dict[str, Any] | None:
        rows = self._request(
            "/rest/v1/ai_provider_credentials",
            {
                "provider_id": f"eq.{provider_id}",
                "select": "provider_id,encrypted_secret,encrypted_metadata,secret_last_four,enabled,status,updated_at",
                "limit": "1",
            },
        )
        return rows[0] if rows else None

    def upsert_credential(self, data: dict[str, Any]) -> dict[str, Any]:
        result = self._write_request(
            "POST",
            "/rest/v1/ai_provider_credentials?on_conflict=provider_id",
            json_data=data,
            prefer="return=representation,resolution=merge-duplicates",
        )
        if isinstance(result, list):
            return result[0] if result else {}
        return result or {}

    def delete_credential(self, provider_id: str) -> None:
        self._write_request(
            "DELETE",
            f"/rest/v1/ai_provider_credentials?provider_id=eq.{provider_id}",
        )

    def update_credential_test(
        self,
        provider_id: str,
        expected_updated_at: str,
        expected_ciphertext: str,
        data: dict[str, Any],
    ) -> bool:
        from urllib.parse import quote

        path = (
            "/rest/v1/ai_provider_credentials?"
            f"provider_id=eq.{quote(provider_id, safe='')}"
            f"&updated_at=eq.{quote(expected_updated_at, safe='')}"
            f"&encrypted_secret=eq.{quote(expected_ciphertext, safe='')}"
        )
        result = self._write_request("PATCH", path, json_data=data)
        return bool(result)

    def get_preferences(self) -> dict[str, Any] | None:
        rows = self._request(
            "/rest/v1/ai_application_preferences",
            {
                "id": "eq.true",
                "select": "id,default_text_provider,default_text_model,default_visual_source,default_image_provider,default_image_model,default_pexels_media_type,default_pexels_orientation,updated_at",
                "limit": "1",
            },
        )
        return rows[0] if rows else None

    def upsert_preferences(self, data: dict[str, Any]) -> dict[str, Any]:
        result = self._write_request(
            "POST",
            "/rest/v1/ai_application_preferences?on_conflict=id",
            json_data={"id": True, **data},
            prefer="return=representation,resolution=merge-duplicates",
        )
        if isinstance(result, list):
            return result[0] if result else {}
        return result or {}

    def get_scene_counts(self, job_id: UUID) -> dict[str, int]:
        scenes = self._request(
            "/rest/v1/scenes",
            {"job_id": f"eq.{job_id}", "select": "generation_status", "limit": "200"},
        )
        completed = sum(1 for s in scenes if s.get("generation_status") == "completed")
        failed = sum(1 for s in scenes if s.get("generation_status") == "failed")
        total = len(scenes)
        return {"completed": completed, "total": total, "failed": failed}

    def get_asset_types(self, job_id: UUID) -> list[str]:
        assets = self._request(
            "/rest/v1/assets",
            {"job_id": f"eq.{job_id}", "select": "asset_type", "limit": "50"},
        )
        return [a.get("asset_type", "") for a in assets]

    def get_job_events(self, job_id: UUID) -> list[dict[str, Any]]:
        return self._request(
            "/rest/v1/video_job_events",
            {
                "job_id": f"eq.{job_id}",
                "select": "id,event_type,stage,level,progress,message,created_at",
                "order": "created_at.desc,id.desc",
                "limit": "50",
            },
        )
