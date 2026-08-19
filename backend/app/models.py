from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


SupportedDuration = Literal[30, 45, 60, 90]
AspectRatio = Literal["9:16", "16:9", "1:1"]
VideoStatus = Literal["queued", "rendering", "completed", "failed", "cancelled", "awaiting_audio"]


class VideoDraft(BaseModel):
    title: str = ""
    prompt: str
    duration: int
    style: str
    voice: str
    captions: str
    aspectRatio: AspectRatio = "9:16"
    text_provider: str | None = None
    text_model: str | None = None
    image_provider: str | None = None
    image_model: str | None = None
    visual_source: str | None = None
    pexels_media_type: str | None = None
    pexels_orientation: str | None = None
    credential_source: str | None = None
    provider_configuration_version: str | None = None
    audio_mode: Literal["automatic", "custom_audio"] = "automatic"

    @field_validator("duration", mode="before")
    @classmethod
    def parse_duration(cls, value: object) -> int:
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("duration must be 30, 45, 60, or 90 seconds") from exc

    @field_validator("duration")
    @classmethod
    def validate_duration(cls, value: int) -> int:
        if value not in (30, 45, 60, 90):
            raise ValueError("duration must be 30, 45, 60, or 90 seconds")
        return value


class ProviderCredentialWrite(BaseModel):
    secret: str = Field(min_length=1)
    metadata: dict[str, Any] | None = None
    enabled: bool = True


class ProviderCredentialResponse(BaseModel):
    provider_id: str
    configured: bool
    enabled: bool
    status: str
    secret_last_four: str | None = None
    last_tested_at: datetime | None = None
    last_test_status: str | None = None
    last_test_error_safe: str | None = None


class ProviderConnectionTestResponse(BaseModel):
    provider_id: str
    status: str
    message: str
    persisted: bool


class ApplicationPreferencesWrite(BaseModel):
    default_text_provider: str | None = None
    default_text_model: str | None = None
    default_visual_source: str | None = None
    default_image_provider: str | None = None
    default_image_model: str | None = None
    default_pexels_media_type: str | None = None
    default_pexels_orientation: str | None = None


class ApplicationPreferencesResponse(BaseModel):
    default_text_provider: str
    default_text_model: str
    default_visual_source: str
    default_image_provider: str
    default_image_model: str
    default_pexels_media_type: str | None = None
    default_pexels_orientation: str | None = None
    updated_at: datetime | None = None


class Video(BaseModel):
    id: UUID
    title: str
    prompt: str
    status: VideoStatus
    progress: int = Field(ge=0, le=100)
    duration: int
    aspectRatio: AspectRatio
    style: str
    createdAt: datetime
    thumbnail: str
    videoUrl: str | None = None
    audio_mode: Literal["automatic", "custom_audio"] = "automatic"
    uploaded_audio_duration: float | None = None
    effective_duration: float | None = None
    script_json: dict[str, Any] | None = None


class ImageProgress(BaseModel):
    completed: int = 0
    total: int = 0
    failed: int = 0


class AssetCompletion(BaseModel):
    narration: bool = False
    captions: bool = False
    manifest: bool = False
    video: bool = False
    thumbnail: bool = False


class SafeVideoError(BaseModel):
    code: str
    message: str
    metadata: dict[str, Any] | None = None


class VideoJobEvent(BaseModel):
    id: UUID
    type: str
    stage: str | None = None
    status: str | None = None
    progress: int | None = None
    message: str
    created_at: datetime


class VideoStatusResponse(BaseModel):
    id: UUID
    status: str
    display_status: str = ""
    progress: int = Field(ge=0, le=100)
    current_step: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    elapsed_seconds: float = 0
    stale: bool = False
    image_progress: ImageProgress | None = None
    assets: AssetCompletion | None = None
    error: SafeVideoError | None = None
    recent_events: list[VideoJobEvent] = []
