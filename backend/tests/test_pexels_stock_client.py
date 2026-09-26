from app.services.ai import pexels_stock


def test_selects_first_portrait_photo():
    payload = {"photos": [{"id": 1, "src": {"original": "https://example.com/a.jpg"}, "alt": "rain"}]}
    photo = pexels_stock.select_photo(payload)
    assert photo.url == "https://example.com/a.jpg"


def test_empty_search_raises_empty_response():
    import pytest
    from app.services.ai.provider_executor import ProviderExecutionError
    with pytest.raises(ProviderExecutionError) as error:
        pexels_stock.select_photo({"photos": []})
    assert error.value.code == "empty_response"


def _clip_video(files, duration=10):
    return {"id": 1, "width": 720, "height": 1280, "duration": duration, "video_files": files}


def _mp4(quality, width, link):
    return {"id": 1, "quality": quality, "file_type": "video/mp4", "width": width, "height": width * 16 // 9, "link": link}


def test_select_clip_prefers_hd_over_first_sd_file():
    payload = {"videos": [_clip_video([
        _mp4("sd", 240, "https://example.com/sd.mp4"),
        _mp4("hd", 720, "https://example.com/hd.mp4"),
    ])]}
    clip = pexels_stock.select_clip(payload, 5.0)
    assert clip.url == "https://example.com/hd.mp4"


def test_select_clip_falls_back_to_first_usable_when_none_meets_duration():
    payload = {"videos": [_clip_video(
        [_mp4("sd", 240, "https://example.com/only.mp4")],
        duration=2,
    )]}
    clip = pexels_stock.select_clip(payload, 30.0)
    assert clip.url == "https://example.com/only.mp4"
