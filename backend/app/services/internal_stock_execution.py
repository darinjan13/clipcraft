import time
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .ai.credential_resolution import CredentialResolutionError, CredentialResolver, ExecutionContext
from .ai.pexels_stock import (
    CLIP_MAX_BYTES,
    PHOTO_MAX_BYTES,
    HttpxPexelsTransport,
    PexelsTransport,
    ProviderExecutionError,
    search_params as pexels_search_params,
    select_clip as select_pexels_clip,
    select_photo as select_pexels_photo,
)
from .ai.pixabay_stock import (
    HttpxPixabayTransport,
    search_params as pixabay_search_params,
    select_clip as select_pixabay_clip,
    select_photo as select_pixabay_photo,
)
from .ai.provider_registry import (
    PROVIDER_CONFIGURATION_VERSION,
    RegistryValidationError,
    validate_pexels_media_type,
    validate_pexels_orientation,
    validate_pixabay_media_type,
    validate_pixabay_orientation,
    validate_visual_source,
)
from .ai.routing import RoutingDecision
from .internal_text_execution import InternalExecutionFailure, _credential_failure, _execution_failure, _routing_failure
from ..config import Settings

# Dummy text pair for credential-context validation (mirrors the internal
# image service); stock-only requests carry no text provider of their own.
_ROUTING_TEXT_PROVIDER = "cloudflare"
_ROUTING_TEXT_MODEL = "@cf/meta/llama-3.1-8b-instruct"

_JPEG_SIGNATURE = b"\xff\xd8\xff"
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class InternalStockInput(BaseModel):
    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    query: str | None = None
    image_prompt: str | None = None
    media_type: str = "photo"
    orientation: str = "portrait"
    scene_id: str | None = None
    scene_index: int = Field(ge=0)
    duration_seconds: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _require_query(self):
        query = self.query if isinstance(self.query, str) and self.query.strip() else ""
        fallback = self.image_prompt if isinstance(self.image_prompt, str) and self.image_prompt.strip() else ""
        if not query and not fallback:
            raise ValueError("a query is required")
        return self

    def resolved_query(self) -> str:
        if isinstance(self.query, str) and self.query.strip():
            return self.query.strip()
        return str(self.image_prompt).strip()


class InternalStockExecutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    job_id: UUID
    provider_id: Literal["pexels", "pixabay"]
    credential_source: Literal["stored"]
    operation: Literal["stock_media"]
    input: InternalStockInput
    routing_version: str
    request_id: UUID


class InternalStockExecutionResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    request_id: UUID
    job_id: UUID
    provider_id: str
    scene_id: str | None = None
    scene_index: int | None = None
    media_type: str
    capability: Literal["stock_media"]
    status: Literal["completed"]
    local_path: str
    mime_type: str
    file_size: int
    width: int | None = None
    height: int | None = None
    duration: float | None = None
    elapsed_ms: float | None = None
    routing_version: str


class InternalStockExecutionService:
    def __init__(
        self,
        settings: Settings,
        database: object,
        encryption: object | None,
        data_dir: str | Path | None = None,
        transport: PexelsTransport | None = None,
    ):
        self._settings = settings
        self._database = database
        self._encryption = encryption
        self._data_dir = Path(data_dir) if data_dir is not None else Path(settings.data_dir)
        self._transport = transport or HttpxPexelsTransport()
        self._pixabay_transport = HttpxPixabayTransport()

    async def execute(self, request: InternalStockExecutionRequest) -> InternalStockExecutionResponse:
        started = time.perf_counter()
        if request.routing_version != PROVIDER_CONFIGURATION_VERSION:
            raise InternalExecutionFailure("AI_MODEL_NOT_ALLOWED", "request is not allowed", 422, False)
        provider = request.provider_id
        try:
            validate_visual_source(provider)
            if provider == "pixabay":
                validate_pixabay_media_type(request.input.media_type)
                validate_pixabay_orientation(request.input.orientation)
            else:
                validate_pexels_media_type(request.input.media_type)
                validate_pexels_orientation(request.input.orientation)
        except RegistryValidationError as exc:
            raise _routing_failure(exc.code) from None
        if request.input.media_type not in ("photo", "video"):
            # Scene-level tags (e.g. a 'both' mix request) must be resolved to a
            # concrete asset kind by the caller; never guess here.
            raise _execution_failure("invalid_request")
        credential = self._resolve_credential(request)
        query = request.input.resolved_query()
        if provider == "pixabay":
            params = pixabay_search_params(query, request.input.orientation, kind=request.input.media_type)
            transport = self._pixabay_transport
            pick_photo = select_pixabay_photo
            pick_clip = select_pixabay_clip
        else:
            params = pexels_search_params(query)
            params["orientation"] = request.input.orientation
            transport = self._transport
            pick_photo = select_pexels_photo
            pick_clip = select_pexels_clip
        kind = "photo" if request.input.media_type == "photo" else "video"
        try:
            payload = await transport.search(kind=kind, api_key=credential.secret.get_secret_value(), params=params)
        except ProviderExecutionError as exc:
            raise _execution_failure(exc.code) from None
        if kind == "photo":
            try:
                selected = pick_photo(payload)
            except ProviderExecutionError as exc:
                raise _execution_failure(exc.code) from None
            asset = await self._download(transport, credential.secret.get_secret_value(), selected.url, PHOTO_MAX_BYTES)
            extension, mime_type = _sniff_image(asset)
            width = height = None
            duration = None
        else:
            try:
                selected = pick_clip(payload, request.input.duration_seconds or 0.0)
            except ProviderExecutionError as exc:
                raise _execution_failure(exc.code) from None
            asset = await self._download(transport, credential.secret.get_secret_value(), selected.url, CLIP_MAX_BYTES)
            extension, mime_type = "mp4", "video/mp4"
            width = height = None
            duration = selected.duration
        filename = f"scene-{request.input.scene_index:02d}.{extension}"
        local_path = self._data_dir / str(request.job_id) / filename
        try:
            local_path.parent.mkdir(parents=True, exist_ok=True)
            local_path.write_bytes(asset)
        except OSError as exc:
            raise _execution_failure("execution_error") from None
        return InternalStockExecutionResponse(
            request_id=request.request_id,
            job_id=request.job_id,
            provider_id=provider,
            scene_id=request.input.scene_id,
            scene_index=request.input.scene_index,
            media_type=request.input.media_type,
            capability="stock_media",
            status="completed",
            local_path=str(local_path),
            mime_type=mime_type,
            file_size=len(asset),
            width=width,
            height=height,
            duration=duration,
            elapsed_ms=round((time.perf_counter() - started) * 1000, 2),
            routing_version=request.routing_version,
        )

    async def _download(self, transport, api_key: str, url: str, max_bytes: int) -> bytes:
        try:
            return await transport.download(api_key=api_key, url=url, max_bytes=max_bytes)
        except ProviderExecutionError as exc:
            raise _execution_failure(exc.code) from None

    def _resolve_credential(self, request: InternalStockExecutionRequest):
        decision = RoutingDecision(
            text_provider=_ROUTING_TEXT_PROVIDER,
            text_model=_ROUTING_TEXT_MODEL,
            visual_source=request.provider_id,
            image_provider=None,
            image_model=None,
            credential_strategy="stored",
            routing_version=int(PROVIDER_CONFIGURATION_VERSION),
        )
        resolver = CredentialResolver(self._settings, self._database, self._encryption)
        try:
            return resolver.resolve(decision, request.credential_source, request.provider_id)
        except CredentialResolutionError as exc:
            raise _credential_failure(exc.code) from None
        except Exception:
            raise _credential_failure("credential_configuration_error") from None


def _sniff_image(asset: bytes) -> tuple[str, str]:
    if asset.startswith(_PNG_SIGNATURE):
        return "png", "image/png"
    if asset.startswith(_JPEG_SIGNATURE):
        return "jpg", "image/jpeg"
    return "jpg", "image/jpeg"
