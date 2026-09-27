from fastapi.testclient import TestClient

from app.main import create_app
from app.services.ai.provider_registry import (
    SUPPORTED_PIXABAY_MEDIA_TYPES,
    SUPPORTED_PIXABAY_ORIENTATIONS,
    SUPPORTED_VISUAL_SOURCES,
    validate_pixabay_media_type,
    validate_pixabay_orientation,
    validate_visual_source,
)


def test_pixabay_is_a_supported_visual_source(tmp_path):
    assert "pixabay" in SUPPORTED_VISUAL_SOURCES
    response = TestClient(create_app(data_dir=tmp_path)).get("/api/ai/providers/pixabay")

    assert response.status_code == 200
    provider = response.json()
    assert provider["provider_type"] == "stock_media"
    assert "stock_media" in provider["capabilities"]
    assert provider["requires_credential"] is True
    assert provider["implemented"] is True
    validate_visual_source("pixabay")


def test_pixabay_media_types():
    assert SUPPORTED_PIXABAY_MEDIA_TYPES == {"photo", "video", "both"}
    validate_pixabay_media_type("photo")
    validate_pixabay_media_type("video")
    validate_pixabay_media_type("both")


def test_pixabay_orientations():
    assert SUPPORTED_PIXABAY_ORIENTATIONS == {"landscape", "portrait", "square"}
    validate_pixabay_orientation("portrait")
