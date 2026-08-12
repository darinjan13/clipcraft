import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from .clients import BackendDependencyError, DatabaseClient, WorkflowClient
from .config import Settings
from .media import media_response, safe_media_path
from .models import (
    AssetCompletion,
    ImageProgress,
    SafeVideoError,
    ProviderCredentialResponse,
    ProviderCredentialWrite,
    ProviderConnectionTestResponse,
    ApplicationPreferencesResponse,
    ApplicationPreferencesWrite,
    Video,
    VideoDraft,
    VideoJobEvent,
    VideoStatusResponse,
)
from .services.ai.provider_registry import (
    RegistryValidationError,
    get_provider,
    get_model_capabilities,
    list_providers,
    resolve_provider_selection,
    DEFAULT_CREDENTIAL_SOURCE,
    DEFAULT_VISUAL_SOURCE,
    PROVIDER_CONFIGURATION_VERSION,
    DEFAULT_TEXT_MODEL,
    DEFAULT_TEXT_PROVIDER,
    DEFAULT_IMAGE_MODEL,
    DEFAULT_IMAGE_PROVIDER,
    default_model_for_provider,
    validate_model_selection,
    validate_pexels_media_type,
    validate_pexels_orientation,
    validate_visual_source,
    SUPPORTED_VISUAL_SOURCES,
)
from .services.credential_crypto import CredentialCryptoError, CredentialEncryption
from .services.provider_connection import ProviderTestResult, run_provider_test
from .services.ai.shadow_execution import ShadowExecutionRunner
from .services.ai.runtime_comparison import RuntimeMetadata
from .services.internal_auth import NonceStore, verify_internal_signature
from .services.internal_image_execution import InternalImageExecutionRequest, InternalImageExecutionService
from .services.internal_text_execution import (
    InternalExecutionFailure,
    InternalTextExecutionRequest,
    InternalTextExecutionService,
)

MAX_INTERNAL_TEXT_BODY_BYTES = 1 * 1024 * 1024
MAX_INTERNAL_IMAGE_BODY_BYTES = 1 * 1024 * 1024


def _safe_job_directory(root: Path, video_id: UUID) -> Path:
    resolved_root = root.resolve()
    candidate = resolved_root / str(video_id)
    if candidate.is_symlink():
        raise ValueError("unsafe video job directory")

    resolved_candidate = candidate.resolve()
    if (
        resolved_candidate in {resolved_root, resolved_root.parent}
        or resolved_candidate.parent != resolved_root
        or resolved_candidate.name != str(video_id)
        or (resolved_candidate.exists() and not resolved_candidate.is_dir())
    ):
        raise ValueError("unsafe video job directory")
    return resolved_candidate


def _status_value(value: str) -> str:
    return "rendering" if value in {"generating_script", "script_ready", "generating_images", "generating_voice", "building_captions", "building_manifest", "rendering", "processing"} else value


def _brief(row: dict[str, Any]) -> dict[str, Any]:
    return row.get("brief_json") or {}


def _video_from_row(row: dict[str, Any], status: dict[str, Any] | None = None, result: dict[str, Any] | None = None) -> Video:
    brief = _brief(row)
    script = row.get("script_json") or {}
    current_status = _status_value((status or {}).get("status", row.get("status", "queued")))
    result = result or {}
    return Video(
        id=row["id"],
        title=script.get("title") or result.get("title") or row.get("topic", "Untitled creation"),
        prompt=brief.get("topic") or row.get("topic", ""),
        status=current_status,
        progress=(status or {}).get("progress", row.get("progress", 0)),
        duration=int(brief.get("duration", 0) or 0),
        aspectRatio=brief.get("aspectRatio", "9:16"),
        style=brief.get("visualStyle") or brief.get("contentStyle") or "Cinematic",
        createdAt=row.get("created_at") or datetime.now(timezone.utc),
        thumbnail=f"/api/videos/{row['id']}/thumbnail" if current_status == "completed" else "",
        videoUrl=f"/api/videos/{row['id']}/file" if current_status == "completed" else None,
    )


def _dependency_error(exc: BackendDependencyError) -> HTTPException:
    return HTTPException(status_code=502, detail=str(exc))


def _shadow(app: FastAPI, draft: VideoDraft, selection: dict[str, str], snapshot: dict[str, str | None], database: object, encryption: object | None, job_id: str) -> None:
    try:
        runner = getattr(app.state, "shadow_runner", None)
        if runner is None:
            return
        runner.run_with_comparison(
            legacy_metadata=_legacy_runtime_metadata(draft, selection, snapshot),
            text_provider=selection.get("text_provider"),
            text_model=selection.get("text_model"),
            image_provider=selection.get("image_provider"),
            image_model=selection.get("image_model"),
            visual_source=draft.visual_source or DEFAULT_VISUAL_SOURCE,
            credential_source=draft.credential_source,
            database=database,
            encryption=encryption,
            job_id=job_id,
        )
    except Exception:
        pass


def _legacy_runtime_metadata(draft: VideoDraft, selection: dict[str, str], snapshot: dict[str, str | None]) -> tuple[RuntimeMetadata, ...]:
    visual_source = snapshot.get("visual_source") or draft.visual_source or DEFAULT_VISUAL_SOURCE
    routing_version = int(snapshot.get("provider_configuration_version") or PROVIDER_CONFIGURATION_VERSION)
    metadata = [RuntimeMetadata(selection["text_provider"], selection["text_model"], "text_generation", routing_version, None)]
    if visual_source == "ai":
        metadata.append(RuntimeMetadata(selection["image_provider"], selection["image_model"], "image_generation", routing_version, None))
    return tuple(metadata)


def _credential_response(row: dict[str, Any]) -> ProviderCredentialResponse:
    return ProviderCredentialResponse(
        provider_id=row["provider_id"],
        configured=bool(row.get("encrypted_secret") or row.get("secret_last_four")),
        enabled=bool(row.get("enabled", True)),
        status=row.get("status", "configured"),
        secret_last_four=row.get("secret_last_four"),
        last_tested_at=row.get("last_tested_at"),
        last_test_status=row.get("last_test_status"),
        last_test_error_safe=row.get("last_test_error_safe"),
    )


def _configuration_snapshot(selection: dict[str, str], *, visual_source: str = DEFAULT_VISUAL_SOURCE, include_image: bool = True, credential_source: str = DEFAULT_CREDENTIAL_SOURCE, provider_configuration_version: str = PROVIDER_CONFIGURATION_VERSION) -> dict[str, str | None]:
    return {
        "text_provider": selection["text_provider"],
        "text_model": selection["text_model"],
        "visual_source": visual_source,
        "image_provider": selection["image_provider"] if include_image else None,
        "image_model": selection["image_model"] if include_image else None,
        "credential_source": credential_source,
        "provider_configuration_version": provider_configuration_version,
    }


def _snapshot_from_row(row: dict[str, Any]) -> dict[str, str | None] | None:
    snapshot_fields = (
        "text_provider",
        "text_model",
        "visual_source",
        "image_provider",
        "image_model",
        "credential_source",
        "provider_configuration_version",
    )
    common_fields = ("text_provider", "text_model", "visual_source", "credential_source", "provider_configuration_version")
    if all(row.get(field) is not None for field in common_fields):
        visual_source = row["visual_source"]
        ai_image_fields_present = row.get("image_provider") is not None and row.get("image_model") is not None
        pexels_image_fields_absent = visual_source == "pexels" and row.get("image_provider") is None and row.get("image_model") is None
        if (visual_source == "ai" and ai_image_fields_present) or pexels_image_fields_absent:
            return {field: row.get(field) for field in snapshot_fields}
    return None


def _validate_available_selection(settings: Settings, provider_id: str, model_id: str, capability: str) -> None:
    validate_model_selection(provider_id, model_id, capability)
    provider = get_provider(provider_id, settings)
    if not provider["available"]:
        raise RegistryValidationError("unavailable_provider", f"provider is unavailable: {provider_id}")
    model = next(item for item in provider["models"] if item["model_id"] == model_id)
    if not model["available"]:
        raise RegistryValidationError("unavailable_model", f"model is unavailable: {model_id}")


def _generation_snapshot(draft: VideoDraft, settings: Settings, selection: dict[str, str]) -> dict[str, str | None]:
    has_configuration = any(
        getattr(draft, field) is not None
        for field in (
            "text_provider", "text_model", "visual_source", "image_provider", "image_model",
            "credential_source", "provider_configuration_version", "pexels_media_type", "pexels_orientation",
        )
    )
    if not has_configuration:
        return {}
    if (draft.text_provider is None) != (draft.text_model is None):
        raise RegistryValidationError("incomplete_provider_model", "text provider and model must be provided together")
    if draft.text_provider is None or draft.text_model is None:
        raise RegistryValidationError("incomplete_provider_model", "text provider and model are required")
    _validate_available_selection(settings, draft.text_provider, draft.text_model, "text")

    visual_source = draft.visual_source or DEFAULT_VISUAL_SOURCE
    if visual_source not in SUPPORTED_VISUAL_SOURCES:
        raise RegistryValidationError("unsupported_visual_source", f"unsupported visual source: {visual_source}")
    if visual_source == "ai":
        include_image = True
        legacy_image_defaults = draft.visual_source is None and draft.image_provider is None and draft.image_model is None
        if legacy_image_defaults:
            pass
        else:
            if (draft.image_provider is None) != (draft.image_model is None) or draft.image_provider is None or draft.image_model is None:
                raise RegistryValidationError("incomplete_provider_model", "image provider and model are required for AI visuals")
            _validate_available_selection(settings, draft.image_provider, draft.image_model, "image")
    else:
        include_image = False
    if visual_source == "pexels":
        if draft.pexels_media_type is not None:
            validate_pexels_media_type(draft.pexels_media_type)
        if draft.pexels_orientation is not None:
            validate_pexels_orientation(draft.pexels_orientation)

    credential_source = draft.credential_source or DEFAULT_CREDENTIAL_SOURCE
    if credential_source not in {"environment", "stored"}:
        raise RegistryValidationError("unsupported_credential_source", "unsupported credential source")
    if draft.text_provider == "nvidia" and credential_source != "stored":
        raise RegistryValidationError("unsupported_credential_source", "NVIDIA requires a stored credential")
    provider_configuration_version = draft.provider_configuration_version or PROVIDER_CONFIGURATION_VERSION
    if provider_configuration_version != PROVIDER_CONFIGURATION_VERSION:
        raise RegistryValidationError("unsupported_provider_configuration_version", "unsupported provider configuration version")
    return _configuration_snapshot(
        selection,
        visual_source=visual_source,
        include_image=include_image,
        credential_source=credential_source,
        provider_configuration_version=provider_configuration_version,
    )


def _validate_generation_request_shape(draft: VideoDraft) -> None:
    if (draft.text_provider is None) != (draft.text_model is None):
        raise RegistryValidationError("incomplete_provider_model", "text provider and model must be provided together")
    if draft.credential_source is not None and draft.credential_source not in {"environment", "stored"}:
        raise RegistryValidationError("unsupported_credential_source", "unsupported credential source")
    if draft.text_provider == "nvidia" and draft.credential_source != "stored":
        raise RegistryValidationError("unsupported_credential_source", "NVIDIA requires a stored credential")
    if draft.provider_configuration_version is not None and draft.provider_configuration_version != PROVIDER_CONFIGURATION_VERSION:
        raise RegistryValidationError("unsupported_provider_configuration_version", "unsupported provider configuration version")


def _preference_defaults() -> dict[str, str | None]:
    return {
        "default_text_provider": DEFAULT_TEXT_PROVIDER,
        "default_text_model": DEFAULT_TEXT_MODEL,
        "default_visual_source": DEFAULT_VISUAL_SOURCE,
        "default_image_provider": DEFAULT_IMAGE_PROVIDER,
        "default_image_model": DEFAULT_IMAGE_MODEL,
        "default_pexels_media_type": None,
        "default_pexels_orientation": None,
    }


def _preference_response(row: dict[str, Any] | None) -> ApplicationPreferencesResponse:
    values = _preference_defaults()
    if row:
        for field in values:
            if row.get(field) is not None:
                values[field] = row[field]
    _validate_preference_values(values)
    return ApplicationPreferencesResponse(**values, updated_at=(row or {}).get("updated_at"))


def _validate_preference_values(values: dict[str, str | None]) -> None:
    validate_model_selection(values["default_text_provider"], values["default_text_model"], "text")
    validate_model_selection(values["default_image_provider"], values["default_image_model"], "image")
    validate_visual_source(values["default_visual_source"])
    if values["default_pexels_media_type"] is not None:
        validate_pexels_media_type(values["default_pexels_media_type"])
    if values["default_pexels_orientation"] is not None:
        validate_pexels_orientation(values["default_pexels_orientation"])


def _resolve_preference_write(body: ApplicationPreferencesWrite) -> dict[str, str | None]:
    text_provider = body.default_text_provider or DEFAULT_TEXT_PROVIDER if body.default_text_provider is None else body.default_text_provider
    image_provider = body.default_image_provider or DEFAULT_IMAGE_PROVIDER if body.default_image_provider is None else body.default_image_provider
    text_model = (
        default_model_for_provider(text_provider, "text")
        if body.default_text_model is None and body.default_text_provider is not None
        else DEFAULT_TEXT_MODEL if body.default_text_model is None else body.default_text_model
    )
    image_model = (
        default_model_for_provider(image_provider, "image")
        if body.default_image_model is None and body.default_image_provider is not None
        else DEFAULT_IMAGE_MODEL if body.default_image_model is None else body.default_image_model
    )
    visual_source = body.default_visual_source if body.default_visual_source is not None else DEFAULT_VISUAL_SOURCE
    values = {
        "default_text_provider": text_provider,
        "default_text_model": text_model,
        "default_visual_source": visual_source,
        "default_image_provider": image_provider,
        "default_image_model": image_model,
        "default_pexels_media_type": body.default_pexels_media_type,
        "default_pexels_orientation": body.default_pexels_orientation,
    }
    _validate_preference_values(values)
    return values


_DISPLAY_STATUS: dict[str, str] = {
    "queued": "Queued",
    "generating_script": "Generating script",
    "script_ready": "Script ready",
    "generating_images": "Generating images",
    "generating_voice": "Generating voice",
    "building_captions": "Building captions",
    "building_manifest": "Building manifest",
    "rendering": "Rendering",
    "processing": "Processing",
    "completed": "Completed",
    "failed": "Failed",
    "cancelled": "Cancelled",
}

_STALE_SECONDS = 60

_ACTIVE_STATUSES = {
    "queued", "generating_script", "script_ready", "generating_images",
    "generating_voice", "building_captions", "building_manifest", "rendering", "processing",
}


def _sanitize_error(row: dict[str, Any]) -> SafeVideoError | None:
    error_message = row.get("error_message")
    if not error_message:
        return None
    code = row.get("failure_class") or row.get("last_error") or "VIDEO_GENERATION_FAILED"
    if code == "VIDEO_GENERATION_FAILED":
        return SafeVideoError(code=code, message=error_message)
    return SafeVideoError(code=code, message=error_message)


def _assemble_assets(asset_types: list[str]) -> AssetCompletion:
    return AssetCompletion(
        narration=any(t in ("narration", "voice", "audio", "tts") for t in asset_types),
        captions=any(t in ("captions", "subtitles", "subtitle") for t in asset_types),
        manifest=any(t in ("manifest", "render_manifest") for t in asset_types),
        video=any(t in ("video", "final", "render", "mp4") for t in asset_types),
        thumbnail=any(t in ("thumbnail", "thumb") for t in asset_types),
    )


def _assemble_status(
    db: DatabaseClient,
    video_id: UUID,
    row: dict[str, Any],
    status: dict[str, Any] | None = None,
) -> VideoStatusResponse:
    raw = (status or {}).get("status", row.get("status", "queued"))
    now = datetime.now(timezone.utc)
    created = row.get("created_at")
    updated = row.get("updated_at")

    if isinstance(created, str):
        created = datetime.fromisoformat(created.replace("Z", "+00:00"))
    if isinstance(updated, str):
        updated = datetime.fromisoformat(updated.replace("Z", "+00:00"))

    elapsed = 0.0
    if created is not None:
        elapsed = (now - created).total_seconds()

    stale = False
    if raw not in ("completed", "failed", "cancelled") and updated is not None:
        stale = (now - updated).total_seconds() > _STALE_SECONDS

    image_progress = ImageProgress()
    assets = AssetCompletion()
    events: list[dict[str, Any]] = []

    if db and db.url:
        try:
            scene_counts = db.get_scene_counts(video_id)
            image_progress = ImageProgress(
                completed=scene_counts["completed"],
                total=scene_counts["total"],
                failed=scene_counts["failed"],
            )
            asset_types = db.get_asset_types(video_id)
            assets = _assemble_assets(asset_types)
            raw_events = db.get_job_events(video_id)
            events = raw_events
        except BackendDependencyError:
            pass

    recent = [
        VideoJobEvent(
            id=e.get("id", uuid4()),
            type=e.get("event_type", ""),
            stage=e.get("stage"),
            status=e.get("status"),
            progress=e.get("progress"),
            message=e.get("message", ""),
            created_at=e.get("created_at", now),
        )
        for e in events[:20]
    ]

    return VideoStatusResponse(
        id=video_id,
        status=raw,
        display_status=_DISPLAY_STATUS.get(raw, raw.replace("_", " ").capitalize()),
        progress=(status or {}).get("progress", row.get("progress", 0)),
        current_step=row.get("current_step"),
        created_at=created,
        updated_at=updated,
        elapsed_seconds=round(elapsed, 1),
        stale=stale,
        image_progress=image_progress,
        assets=assets,
        error=_sanitize_error(row),
        recent_events=recent,
    )


def create_app(
    workflow_client: WorkflowClient | None = None,
    database_client: DatabaseClient | None = None,
    data_dir: str | Path | None = None,
) -> FastAPI:
    settings = Settings.from_env()
    workflow = workflow_client or WorkflowClient(settings)
    database = database_client or DatabaseClient(settings)
    root = Path(data_dir or settings.data_dir).resolve()
    app = FastAPI(title="ClipCraft API")
    try:
        app.state.credential_encryption = CredentialEncryption.from_environment()
    except CredentialCryptoError:
        app.state.credential_encryption = None
    app.state.shadow_runner = ShadowExecutionRunner(settings)
    app.state.internal_nonce_store = NonceStore()
    app.state.internal_text_execution = InternalTextExecutionService(
        settings,
        database,
        app.state.credential_encryption,
    )
    app.state.internal_image_execution = InternalImageExecutionService(
        settings,
        database,
        app.state.credential_encryption,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def provider_metadata(provider_id: str) -> dict[str, Any]:
        provider = get_provider(provider_id, settings)
        if provider_id != "nvidia":
            return provider
        try:
            row = database.get_credential_for_test("nvidia")
        except BackendDependencyError:
            row = None
        configured = bool(row and row.get("encrypted_secret") and row.get("enabled") and row.get("status") == "configured")
        return {
            **provider,
            "available": configured,
            "models": [{**model, "available": configured and model["available"]} for model in provider["models"]],
        }

    def model_capabilities_metadata(capability: str | None = None, provider_id: str | None = None) -> dict[str, Any]:
        payload = get_model_capabilities(settings, capability=capability, provider_id=provider_id)
        nvidia = provider_metadata("nvidia")
        payload["providers"] = [nvidia if provider["provider_id"] == "nvidia" else provider for provider in payload["providers"]]
        available = {model["model_id"]: model["available"] for model in nvidia["models"]}
        for key in ("models", "text_models"):
            payload[key] = [
                {**model, "available": available.get(model.get("model_id") or model.get("model"), model["available"])}
                for model in payload[key]
            ]
        return payload

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/internal/ai/text/execute", include_in_schema=False)
    async def internal_ai_text_execute(request: Request) -> Response:
        content_length = request.headers.get("content-length")
        try:
            if content_length is not None and int(content_length) > MAX_INTERNAL_TEXT_BODY_BYTES:
                return JSONResponse(status_code=413, content={"error": {"code": "AI_EXECUTION_FAILED", "message": "request is too large", "retryable": False}})
        except ValueError:
            return JSONResponse(status_code=413, content={"error": {"code": "AI_EXECUTION_FAILED", "message": "request is invalid", "retryable": False}})
        raw_body = await request.body()
        if len(raw_body) > MAX_INTERNAL_TEXT_BODY_BYTES:
            return JSONResponse(status_code=413, content={"error": {"code": "AI_EXECUTION_FAILED", "message": "request is too large", "retryable": False}})
        timestamp = request.headers.get("X-ClipCraft-Timestamp")
        nonce = request.headers.get("X-ClipCraft-Nonce")
        signature = request.headers.get("X-ClipCraft-Signature")
        if not settings.n8n_internal_signing_secret or not timestamp or not nonce or not signature:
            return JSONResponse(status_code=401, content={"error": {"code": "INTERNAL_AUTH_REQUIRED", "message": "internal authentication required", "retryable": False}})
        try:
            verify_internal_signature(
                settings.n8n_internal_signing_secret,
                timestamp,
                nonce,
                signature,
                raw_body,
                store=app.state.internal_nonce_store,
            )
        except ValueError as exc:
            code = "INTERNAL_REQUEST_REPLAYED" if "replayed" in str(exc) else "INTERNAL_SIGNATURE_INVALID"
            return JSONResponse(status_code=401 if code.endswith("REPLAYED") else 403, content={"error": {"code": code, "message": "internal request rejected", "retryable": False}})
        try:
            body = InternalTextExecutionRequest.model_validate_json(raw_body)
        except Exception as exc:
            print(f"[TEXT-EXEC-VALIDATION] {str(exc)[:300]} body={raw_body[:400]}", flush=True)
            return JSONResponse(status_code=422, content={"error": {"code": "AI_EXECUTION_FAILED", "message": "request is invalid", "retryable": False}})
        try:
            result = await app.state.internal_text_execution.execute(body)
            return JSONResponse(status_code=200, content=result.model_dump(mode="json"))
        except InternalExecutionFailure as exc:
            print(f"[TEXT-EXEC-FAIL] provider={body.provider_id} model={body.model_id} credential_source={body.credential_source} routing_version={body.routing_version} code={exc.code}", flush=True)
            return JSONResponse(status_code=exc.status_code, content={"error": {"code": exc.code, "message": exc.message, "retryable": exc.retryable}})
        except Exception:
            return JSONResponse(status_code=502, content={"error": {"code": "AI_EXECUTION_FAILED", "message": "provider execution failed", "retryable": False}})

    @app.post("/internal/ai/image/execute", include_in_schema=False)
    async def internal_ai_image_execute(request: Request) -> Response:
        content_length = request.headers.get("content-length")
        try:
            if content_length is not None and int(content_length) > MAX_INTERNAL_IMAGE_BODY_BYTES:
                return JSONResponse(status_code=413, content={"error": {"code": "AI_EXECUTION_FAILED", "message": "request is too large", "retryable": False}})
        except ValueError:
            return JSONResponse(status_code=413, content={"error": {"code": "AI_EXECUTION_FAILED", "message": "request is invalid", "retryable": False}})
        raw_body = await request.body()
        if len(raw_body) > MAX_INTERNAL_IMAGE_BODY_BYTES:
            return JSONResponse(status_code=413, content={"error": {"code": "AI_EXECUTION_FAILED", "message": "request is too large", "retryable": False}})
        timestamp = request.headers.get("X-ClipCraft-Timestamp")
        nonce = request.headers.get("X-ClipCraft-Nonce")
        signature = request.headers.get("X-ClipCraft-Signature")
        if not settings.n8n_internal_signing_secret or not timestamp or not nonce or not signature:
            return JSONResponse(status_code=401, content={"error": {"code": "INTERNAL_AUTH_REQUIRED", "message": "internal authentication required", "retryable": False}})
        try:
            verify_internal_signature(
                settings.n8n_internal_signing_secret,
                timestamp,
                nonce,
                signature,
                raw_body,
                store=app.state.internal_nonce_store,
            )
        except ValueError as exc:
            code = "INTERNAL_REQUEST_REPLAYED" if "replayed" in str(exc) else "INTERNAL_SIGNATURE_INVALID"
            return JSONResponse(status_code=401 if code.endswith("REPLAYED") else 403, content={"error": {"code": code, "message": "internal request rejected", "retryable": False}})
        try:
            body = InternalImageExecutionRequest.model_validate_json(raw_body)
        except Exception:
            return JSONResponse(status_code=422, content={"error": {"code": "AI_EXECUTION_FAILED", "message": "request is invalid", "retryable": False}})
        try:
            job_dir = root / str(body.job_id)
            job_dir.mkdir(parents=True, exist_ok=True)
            job_dir.chmod(0o777)
        except OSError:
            return JSONResponse(status_code=500, content={"error": {"code": "AI_EXECUTION_FAILED", "message": "failed to prepare job storage", "retryable": False}})
        try:
            result = await app.state.internal_image_execution.execute(body)
            return JSONResponse(status_code=200, content=result.model_dump(mode="json"))
        except InternalExecutionFailure as exc:
            return JSONResponse(status_code=exc.status_code, content={"error": {"code": exc.code, "message": exc.message, "retryable": exc.retryable}})
        except Exception:
            return JSONResponse(status_code=502, content={"error": {"code": "AI_EXECUTION_FAILED", "message": "provider execution failed", "retryable": False}})

    @app.get("/api/ai/providers")
    def ai_providers() -> dict[str, Any]:
        return {"providers": [provider_metadata(provider["provider_id"]) for provider in list_providers(settings)]}

    @app.get("/api/ai/providers/{provider_id}")
    def ai_provider(provider_id: str) -> dict[str, Any]:
        try:
            return provider_metadata(provider_id)
        except RegistryValidationError as exc:
            raise HTTPException(status_code=404, detail={"code": exc.code, "message": exc.message}) from exc

    @app.get("/api/ai/models")
    def ai_models(capability: str | None = None, provider_id: str | None = None) -> dict[str, Any]:
        try:
            return model_capabilities_metadata(capability=capability, provider_id=provider_id)
        except RegistryValidationError as exc:
            raise HTTPException(status_code=422, detail={"code": exc.code, "message": exc.message}) from exc

    @app.get("/api/settings/preferences", response_model=ApplicationPreferencesResponse)
    def get_preferences() -> ApplicationPreferencesResponse:
        try:
            return _preference_response(database.get_preferences())
        except RegistryValidationError as exc:
            raise HTTPException(status_code=500, detail="stored application preferences are invalid") from exc
        except BackendDependencyError as exc:
            raise _dependency_error(exc) from exc

    @app.put("/api/settings/preferences", response_model=ApplicationPreferencesResponse)
    def put_preferences(body: ApplicationPreferencesWrite) -> ApplicationPreferencesResponse:
        try:
            values = _resolve_preference_write(body)
            return _preference_response(database.upsert_preferences(values))
        except RegistryValidationError as exc:
            raise HTTPException(status_code=422, detail={"code": exc.code, "message": exc.message}) from exc
        except BackendDependencyError as exc:
            raise _dependency_error(exc) from exc

    @app.get("/api/ai/credentials", response_model=dict[str, list[ProviderCredentialResponse]])
    def list_ai_credentials() -> dict[str, list[ProviderCredentialResponse]]:
        try:
            return {"credentials": [_credential_response(row) for row in database.list_credentials()]}
        except BackendDependencyError as exc:
            raise _dependency_error(exc) from exc

    @app.get("/api/ai/credentials/{provider_id}", response_model=ProviderCredentialResponse)
    def get_ai_credential(provider_id: str) -> ProviderCredentialResponse:
        try:
            get_provider(provider_id, settings)
        except RegistryValidationError as exc:
            raise HTTPException(status_code=404, detail={"code": exc.code, "message": exc.message}) from exc
        try:
            row = database.get_credential(provider_id)
            if not row:
                raise HTTPException(status_code=404, detail="credential not found")
            return _credential_response(row)
        except BackendDependencyError as exc:
            raise _dependency_error(exc) from exc

    @app.put("/api/ai/credentials/{provider_id}", response_model=ProviderCredentialResponse)
    def put_ai_credential(provider_id: str, body: ProviderCredentialWrite) -> ProviderCredentialResponse:
        try:
            get_provider(provider_id, settings)
        except RegistryValidationError as exc:
            raise HTTPException(status_code=422, detail={"code": exc.code, "message": exc.message}) from exc
        encryption = app.state.credential_encryption
        if encryption is None:
            raise HTTPException(status_code=503, detail="credential encryption is not configured")
        try:
            encrypted_metadata = None
            if body.metadata is not None:
                encrypted_metadata = encryption.encrypt(
                    json.dumps(body.metadata, sort_keys=True, separators=(",", ":")),
                    provider_id,
                )
            row = database.upsert_credential({
                "provider_id": provider_id,
                "encrypted_secret": encryption.encrypt(body.secret, provider_id),
                "encrypted_metadata": encrypted_metadata,
                "secret_last_four": body.secret[-4:],
                "enabled": body.enabled,
                "status": "configured" if body.enabled else "disabled",
                "last_tested_at": None,
                "last_test_status": None,
                "last_test_error_safe": None,
            })
            return _credential_response(row)
        except BackendDependencyError as exc:
            raise _dependency_error(exc) from exc
        except (CredentialCryptoError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail="credential could not be stored") from exc

    @app.delete("/api/ai/credentials/{provider_id}", status_code=204)
    def delete_ai_credential(provider_id: str) -> Response:
        try:
            get_provider(provider_id, settings)
            database.delete_credential(provider_id)
            return Response(status_code=204)
        except RegistryValidationError as exc:
            raise HTTPException(status_code=404, detail={"code": exc.code, "message": exc.message}) from exc
        except BackendDependencyError as exc:
            raise _dependency_error(exc) from exc

    @app.post("/api/ai/credentials/{provider_id}/test", response_model=ProviderConnectionTestResponse)
    def test_ai_credential(provider_id: str) -> ProviderConnectionTestResponse:
        try:
            provider = get_provider(provider_id, settings)
        except RegistryValidationError as exc:
            raise HTTPException(status_code=404, detail={"code": exc.code, "message": exc.message}) from exc
        if not provider["enabled"]:
            raise HTTPException(status_code=422, detail={"code": "disabled_provider", "message": "provider is disabled"})
        if not provider["connection_test_supported"]:
            return ProviderConnectionTestResponse(
                provider_id=provider_id,
                status="not_implemented",
                message="provider connection testing is not implemented",
                persisted=False,
            )

        try:
            row = database.get_credential_for_test(provider_id)
        except BackendDependencyError as exc:
            raise _dependency_error(exc) from exc
        if not row:
            return ProviderConnectionTestResponse(
                provider_id=provider_id,
                status="configuration_error",
                message="no stored credential is configured",
                persisted=False,
            )

        encryption = app.state.credential_encryption
        if encryption is None:
            result_status = "configuration_error"
            result_message = "credential encryption is not configured"
            persisted = False
            return ProviderConnectionTestResponse(
                provider_id=provider_id,
                status=result_status,
                message=result_message,
                persisted=persisted,
            )

        metadata: dict[str, object] | None = None
        try:
            secret = encryption.decrypt(row["encrypted_secret"], provider_id)
            if row.get("encrypted_metadata"):
                metadata = json.loads(encryption.decrypt(row["encrypted_metadata"], provider_id))
            result = run_provider_test(provider_id, secret, metadata)
        except (CredentialCryptoError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            result = ProviderTestResult("configuration_error", "stored credential could not be used")

        try:
            current_provider = get_provider(provider_id, settings)
        except RegistryValidationError:
            current_provider = {"enabled": False}
        if not current_provider["enabled"]:
            raise HTTPException(status_code=422, detail={"code": "disabled_provider", "message": "provider is disabled"})

        try:
            persisted = database.update_credential_test(
                provider_id,
                row.get("updated_at", ""),
                row["encrypted_secret"],
                {
                    "last_tested_at": datetime.now(timezone.utc).isoformat(),
                    "last_test_status": result.status,
                    "last_test_error_safe": None if result.status == "connected" else result.message,
                },
            )
        except BackendDependencyError as exc:
            raise _dependency_error(exc) from exc
        return ProviderConnectionTestResponse(
            provider_id=provider_id,
            status=result.status,
            message=result.message,
            persisted=persisted,
        )

    @app.post("/api/videos", response_model=Video, status_code=202)
    def create_video(draft: VideoDraft, background_tasks: BackgroundTasks) -> Video:
        try:
            _validate_generation_request_shape(draft)
            selection = resolve_provider_selection(
                text_provider=draft.text_provider,
                text_model=draft.text_model,
                image_provider=draft.image_provider,
                image_model=draft.image_model,
            )
            snapshot = _generation_snapshot(draft, settings, selection)
            if draft.text_provider == "nvidia" and not provider_metadata("nvidia")["available"]:
                raise RegistryValidationError("unavailable_provider", "provider is unavailable: nvidia")
        except RegistryValidationError as exc:
            raise HTTPException(status_code=422, detail={"code": exc.code, "message": exc.message}) from exc
        payload = {
            "brief": {
                "topic": draft.prompt.strip(),
                "duration": draft.duration,
                "contentStyle": draft.style,
                "visualStyle": draft.style,
                "voiceTone": draft.voice,
                "captionStyle": draft.captions,
                "language": "English",
                "aspectRatio": draft.aspectRatio,
                "textProvider": selection["text_provider"],
                "textModel": selection["text_model"],
                "imageProvider": selection["image_provider"],
                "imageModel": selection["image_model"],
            },
            "channelId": "default",
            "sessionId": None,
        }
        try:
            job_id = uuid4()
            now = datetime.now(timezone.utc).isoformat()
            row = database.insert_job({
                "id": str(job_id),
                "topic": payload["brief"]["topic"],
                "status": "queued",
                "progress": 0,
                "current_step": "queued",
                "brief_json": payload["brief"],
                "created_at": now,
                "updated_at": now,
                **snapshot,
            })
            row["id"] = job_id
            (root / str(job_id)).mkdir(parents=True, exist_ok=True)
            background_tasks.add_task(
                _shadow,
                app,
                draft,
                selection,
                snapshot,
                database,
                app.state.credential_encryption,
                str(job_id),
            )
            return _video_from_row(row, {"status": "queued", "progress": 0})
        except BackendDependencyError as exc:
            raise _dependency_error(exc) from exc

    @app.get("/api/videos", response_model=list[Video])
    def list_videos() -> list[Video]:
        try:
            return [_video_from_row(row) for row in database.list_jobs()]
        except BackendDependencyError as exc:
            raise _dependency_error(exc) from exc

    @app.get("/api/videos/{video_id}", response_model=Video)
    def get_video(video_id: UUID) -> Video:
        try:
            row = database.get_job(video_id)
            if not row:
                raise HTTPException(status_code=404, detail="video not found")
            try:
                status = workflow.get_status(video_id)
                if status.get("found") is False:
                    status = {"status": row.get("status", "queued"), "progress": row.get("progress", 0)}
            except BackendDependencyError:
                status = {"status": row.get("status", "queued"), "progress": row.get("progress", 0)}
            result = workflow.get_result(video_id) if _status_value(status.get("status", "queued")) == "completed" else None
            return _video_from_row(row, status, result)
        except BackendDependencyError as exc:
            raise _dependency_error(exc) from exc

    @app.get("/api/videos/{video_id}/status", response_model=VideoStatusResponse)
    def get_video_status(video_id: UUID) -> VideoStatusResponse:
        try:
            row = database.get_job(video_id)
            if not row:
                raise HTTPException(status_code=404, detail="video not found")
            try:
                status = workflow.get_status(video_id)
                if status.get("found") is False:
                    status = None
            except BackendDependencyError:
                status = None
            return _assemble_status(database, video_id, row, status)
        except BackendDependencyError as exc:
            raise _dependency_error(exc) from exc

    def serve_media(video_id: UUID, filename: str, media_type: str, request: Request):
        try:
            if not database.get_job(video_id):
                raise HTTPException(status_code=404, detail="video not found")
            path = safe_media_path(root, video_id, filename)
            return media_response(request, path, media_type)
        except BackendDependencyError as exc:
            raise _dependency_error(exc) from exc

    @app.get("/api/videos/{video_id}/file")
    def get_video_file(video_id: UUID, request: Request):
        return serve_media(video_id, "final.mp4", "video/mp4", request)

    @app.patch("/api/videos/{video_id}", response_model=Video)
    def update_video(video_id: UUID, body: dict[str, str]) -> Video:
        if "title" not in body:
            raise HTTPException(status_code=422, detail="title is required")
        try:
            row = database.get_job(video_id)
            if not row:
                raise HTTPException(status_code=404, detail="video not found")
            title = body["title"]
            brief = _brief(row)
            brief["topic"] = title
            database.update_job(video_id, {"brief_json": brief, "topic": title})
            row.update({"brief_json": brief, "topic": title})
            return _video_from_row(row)
        except BackendDependencyError as exc:
            raise _dependency_error(exc) from exc

    @app.post("/api/videos/{video_id}/regenerate", status_code=202)
    def regenerate_video(video_id: UUID) -> dict[str, str]:
        try:
            row = database.get_job(video_id)
            if not row:
                raise HTTPException(status_code=404, detail="video not found")
            brief = _brief(row)
            new_id = uuid4()
            now = datetime.now(timezone.utc).isoformat()
            database.insert_job({
                "id": str(new_id),
                "channel_id": "default",
                "topic": brief.get("topic", row.get("topic", "")),
                "status": "queued",
                "progress": 0,
                "current_step": "queued",
                "brief_json": brief,
                **(_snapshot_from_row(row) or {}),
                "created_at": now,
                "updated_at": now,
            })
            (root / str(new_id)).mkdir(parents=True, exist_ok=True)
            return {"id": str(new_id)}
        except BackendDependencyError as exc:
            raise _dependency_error(exc) from exc

    @app.post("/api/videos/{video_id}/duplicate")
    def duplicate_video(video_id: UUID) -> dict[str, str]:
        try:
            row = database.get_job(video_id)
            if not row:
                raise HTTPException(status_code=404, detail="video not found")
            brief = _brief(row)
            new_row = database.insert_job({
                "user_id": row.get("user_id"),
                "channel_id": row.get("channel_id", "default"),
                "topic": brief.get("topic", row.get("topic", "")),
                "status": "queued",
                "progress": 0,
                "current_step": "queued",
                "brief_json": brief,
                **(_snapshot_from_row(row) or {}),
            })
            return {"id": str(new_row.get("id", ""))}
        except BackendDependencyError as exc:
            raise _dependency_error(exc) from exc

    @app.delete("/api/videos/{video_id}")
    def delete_video(video_id: UUID) -> dict[str, Any]:
        try:
            row = database.get_job(video_id)
            if not row:
                raise HTTPException(status_code=404, detail="video not found")
            try:
                _safe_job_directory(root, video_id)
            except ValueError as exc:
                raise HTTPException(status_code=500, detail="unsafe video job directory") from exc
            if not database.hard_delete_job(video_id):
                raise HTTPException(status_code=404, detail="video not found")
            try:
                job_dir = _safe_job_directory(root, video_id)
            except ValueError as exc:
                raise HTTPException(status_code=500, detail="video deleted but local cleanup was unsafe") from exc
            if job_dir.exists():
                shutil.rmtree(job_dir)
            return {"ok": True, "id": str(video_id)}
        except BackendDependencyError as exc:
            raise _dependency_error(exc) from exc

    @app.post("/api/videos/{video_id}/cancel")
    def cancel_video(video_id: UUID) -> dict[str, Any]:
        try:
            row = database.get_job(video_id)
            if not row:
                raise HTTPException(status_code=404, detail="video not found")
            current = row.get("status", "queued")
            if current == "cancelled":
                return {"ok": True, "id": str(video_id), "status": "cancelled"}
            if current in ("completed", "failed"):
                raise HTTPException(status_code=409, detail=f"cannot cancel a {current} job")
            if current not in _ACTIVE_STATUSES:
                raise HTTPException(status_code=409, detail=f"cannot cancel a job with status '{current}'")
            now = datetime.now(timezone.utc).isoformat()
            database.update_job(video_id, {
                "status": "cancelled",
                "current_step": "cancelled",
                "progress": 0,
                "updated_at": now,
            })
            return {"ok": True, "id": str(video_id), "status": "cancelled"}
        except BackendDependencyError as exc:
            raise _dependency_error(exc) from exc

    @app.get("/api/videos/{video_id}/thumbnail")
    def get_video_thumbnail(video_id: UUID, request: Request):
        return serve_media(video_id, "thumbnail.jpg", "image/jpeg", request)

    return app


app = create_app()
