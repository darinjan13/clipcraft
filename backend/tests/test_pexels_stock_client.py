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
