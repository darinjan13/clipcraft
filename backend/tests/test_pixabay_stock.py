import pytest

from app.services.ai.pixabay_stock import (
    search_params,
    select_clip,
    select_photo,
)
from app.services.ai.provider_executor import ProviderExecutionError


def test_search_params_truncates_long_prompts():
    params = search_params("x" * 150, "portrait")
    assert len(params["q"]) <= 100
    assert params["safesearch"] == "true"
    assert params["per_page"] == 3


def test_search_params_empty_query_rejected():
    with pytest.raises(ProviderExecutionError):
        search_params("   ", "portrait")


def test_search_params_video_has_no_orientation_or_image_type():
    params = search_params("forest", "portrait", "video")
    assert params["video_type"] == "film"
    assert "orientation" not in params
    assert "image_type" not in params


def test_select_photo_prefers_large():
    payload = {"hits": [{"webformatURL": "https://x/small.jpg", "largeImageURL": "https://x/large.jpg"}]}
    assert select_photo(payload).url == "https://x/large.jpg"


def test_select_photo_falls_back_to_webformat():
    payload = {"hits": [{"webformatURL": "https://x/small.jpg"}]}
    assert select_photo(payload).url == "https://x/small.jpg"


def test_select_photo_empty_raises():
    with pytest.raises(ProviderExecutionError):
        select_photo({"hits": []})


def test_select_clip_prefers_medium_and_filters_duration():
    payload = {"hits": [
        {"duration": 2, "videos": {"medium": {"url": "https://x/short.mp4"}}},
        {"duration": 9, "videos": {"medium": {"url": "https://x/long.mp4"}}},
    ]}
    assert select_clip(payload, 5.0).url == "https://x/long.mp4"


def test_select_clip_empty_raises():
    with pytest.raises(ProviderExecutionError):
        select_clip({"hits": []}, 0.0)


def test_search_responses_are_cached_24h(monkeypatch):
    import httpx
    from app.services.ai import pixabay_stock as mod

    calls = {"n": 0}

    class FakeResponse:
        status_code = 200
        headers = {}

        def json(self):
            return {"hits": []}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, *args, **kwargs):
            calls["n"] += 1
            return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    mod.clear_search_cache()

    async def run():
        transport = mod.HttpxPixabayTransport()
        first = await transport.search(kind="photo", api_key="secret", params={"q": "forest"})
        second = await transport.search(kind="photo", api_key="secret", params={"q": "forest"})
        return first, second

    import asyncio
    first, second = asyncio.run(run())
    assert first == {"hits": []}
    assert second == {"hits": []}
    assert calls["n"] == 1
