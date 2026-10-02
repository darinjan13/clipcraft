"""Pixabay stock search + download. Transport-injected; never logs secrets.

Pixabay accepts the API key only as a `key` query parameter (no header
alternative), so the key must never appear in log lines or error messages.
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Mapping, Protocol

import httpx

from .provider_executor import ProviderExecutionError

PIXABAY_API_BASE = "https://pixabay.com"
PHOTO_MAX_BYTES = 16 * 1024 * 1024
CLIP_MAX_BYTES = 64 * 1024 * 1024
SEARCH_TIMEOUT_SECONDS = 30.0
DOWNLOAD_TIMEOUT_SECONDS = 120.0
RATE_LIMIT_BACKOFF_CAP_SECONDS = 30.0
SEARCH_CACHE_TTL_SECONDS = 24 * 60 * 60
SEARCH_CACHE_MAX_ENTRIES = 500
# Transient upstream failures worth one more attempt before surfacing.
SEARCH_MAX_ATTEMPTS = 3
SEARCH_RETRYABLE_STATUSES = frozenset({429, 502, 503, 504})
SEARCH_RETRY_BASE_DELAY_SECONDS = 1.0

# Pixabay terms require search responses to be cached for 24 hours. Keys are
# derived from request params only; the API key is added after the lookup so
# secrets never enter the cache.
_search_cache: dict[tuple[tuple[str, object], ...], tuple[float, Any]] = {}


def clear_search_cache() -> None:
    _search_cache.clear()


def _cache_key(kind: str, params: Mapping[str, object]) -> tuple[tuple[str, object], ...]:
    return tuple([(kind, kind)] + sorted((k, _freeze(v)) for k, v in params.items()))


def _freeze(value: object) -> object:
    if isinstance(value, Mapping):
        return tuple(sorted((k, _freeze(v)) for k, v in value.items()))
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(v) for v in value)
    return value


def _cache_get(key: tuple[tuple[str, object], ...]) -> Any | None:
    entry = _search_cache.get(key)
    if entry is None:
        return None
    expires, payload = entry
    if time.monotonic() >= expires:
        _search_cache.pop(key, None)
        return None
    return payload


def _cache_put(key: tuple[tuple[str, object], ...], payload: Any) -> None:
    while len(_search_cache) >= SEARCH_CACHE_MAX_ENTRIES:
        _search_cache.pop(next(iter(_search_cache)))
    _search_cache[key] = (time.monotonic() + SEARCH_CACHE_TTL_SECONDS, payload)


@dataclass(frozen=True)
class PixabayPhoto:
    url: str


@dataclass(frozen=True)
class PixabayClip:
    url: str
    duration: float


class PixabayTransport(Protocol):
    async def search(self, *, kind: str, api_key: str, params: Mapping[str, object]) -> Any:
        """GET /api/ or /api/videos/; kind is 'photo' or 'video'."""

    async def download(self, *, api_key: str, url: str, max_bytes: int) -> bytes:
        """Download raw bytes with a size cap."""


def _backoff_seconds(response: httpx.Response) -> float:
    try:
        retry_after = float(response.headers.get("Retry-After", ""))
        if retry_after >= 0:
            return min(retry_after, RATE_LIMIT_BACKOFF_CAP_SECONDS)
    except (TypeError, ValueError):
        pass
    try:
        reset = float(response.headers.get("X-RateLimit-Reset", ""))
        now = time.time()
        if reset > now:
            return min(reset - now, RATE_LIMIT_BACKOFF_CAP_SECONDS)
    except (TypeError, ValueError):
        pass
    return 0.0


class HttpxPixabayTransport:
    async def search(self, *, kind: str, api_key: str, params: Mapping[str, object]) -> Any:
        path = "/api/" if kind == "photo" else "/api/videos/"
        key = _cache_key(kind, params)
        cached = _cache_get(key)
        if cached is not None:
            return cached
        query = dict(params)
        query["key"] = api_key
        response = await self._get(PIXABAY_API_BASE + path, query, SEARCH_TIMEOUT_SECONDS)
        attempt = 1
        while (response.status_code in SEARCH_RETRYABLE_STATUSES
               and attempt < SEARCH_MAX_ATTEMPTS):
            delay = _backoff_seconds(response)
            if delay <= 0:
                delay = min(
                    SEARCH_RETRY_BASE_DELAY_SECONDS * (2 ** (attempt - 1)),
                    RATE_LIMIT_BACKOFF_CAP_SECONDS,
                )
            await asyncio.sleep(delay)
            attempt += 1
            response = await self._get(PIXABAY_API_BASE + path, query, SEARCH_TIMEOUT_SECONDS)
        payload = self._decode(response, "search")
        _cache_put(key, payload)
        return payload

    async def download(self, *, api_key: str, url: str, max_bytes: int) -> bytes:
        try:
            async with httpx.AsyncClient(timeout=DOWNLOAD_TIMEOUT_SECONDS, follow_redirects=True) as client:
                async with client.stream("GET", url) as response:
                    if response.status_code == 429:
                        raise ProviderExecutionError("rate_limited", "Pixabay rate limit reached")
                    if not 200 <= response.status_code < 300:
                        raise ProviderExecutionError("provider_error", "Pixabay download failed")
                    chunks = bytearray()
                    async for chunk in response.aiter_bytes():
                        chunks.extend(chunk)
                        if len(chunks) > max_bytes:
                            raise ProviderExecutionError("provider_error", "Pixabay asset exceeds size cap")
                    if not chunks:
                        raise ProviderExecutionError("empty_response", "Pixabay returned no bytes")
                    return bytes(chunks)
        except ProviderExecutionError:
            raise
        except httpx.TimeoutException as exc:
            raise ProviderExecutionError("timeout", "Pixabay download timed out") from exc
        except httpx.RequestError as exc:
            raise ProviderExecutionError("unavailable", "Pixabay provider is unavailable") from exc

    async def _get(self, url: str, params: Mapping[str, object], timeout: float) -> httpx.Response:
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                return await client.get(url, params=dict(params))
        except httpx.TimeoutException as exc:
            raise ProviderExecutionError("timeout", "Pixabay request timed out") from exc
        except httpx.RequestError as exc:
            raise ProviderExecutionError("unavailable", "Pixabay provider is unavailable") from exc

    def _decode(self, response: httpx.Response, operation: str) -> Any:
        if response.status_code == 400:
            raise ProviderExecutionError("invalid_request", "Pixabay rejected the request")
        if response.status_code == 429:
            raise ProviderExecutionError("rate_limited", "Pixabay rate limit reached")
        if not 200 <= response.status_code < 300:
            raise ProviderExecutionError("provider_error", f"Pixabay provider {operation} failed")
        try:
            return response.json()
        except ValueError as exc:
            raise ProviderExecutionError("malformed_response", "Pixabay returned malformed JSON") from exc


def select_photo(payload: Mapping[str, Any]) -> PixabayPhoto:
    hits = payload.get("hits") if isinstance(payload, dict) else None
    if not isinstance(hits, list) or not hits:
        raise ProviderExecutionError("empty_response", "Pixabay returned no photos")
    for item in hits:
        if not isinstance(item, dict):
            continue
        large = item.get("largeImageURL")
        if isinstance(large, str) and large.strip():
            return PixabayPhoto(url=large.strip())
    for item in hits:
        if not isinstance(item, dict):
            continue
        fallback = item.get("webformatURL")
        if isinstance(fallback, str) and fallback.strip():
            return PixabayPhoto(url=fallback.strip())
    raise ProviderExecutionError("empty_response", "Pixabay returned no usable photo")


def select_clip(payload: Mapping[str, Any], min_duration: float) -> PixabayClip:
    hits = payload.get("hits") if isinstance(payload, dict) else None
    if not isinstance(hits, list) or not hits:
        raise ProviderExecutionError("empty_response", "Pixabay returned no videos")
    candidates: list[PixabayClip] = []
    for item in hits:
        if not isinstance(item, dict):
            continue
        duration = item.get("duration")
        renditions = item.get("videos")
        if not isinstance(renditions, dict):
            continue
        url = None
        for size in ("medium", "small", "large", "tiny"):
            entry = renditions.get(size)
            candidate = entry.get("url") if isinstance(entry, dict) else None
            if isinstance(candidate, str) and candidate.strip():
                url = candidate.strip()
                break
        if url is None:
            continue
        candidates.append(
            PixabayClip(
                url=url,
                duration=float(duration) if isinstance(duration, (int, float)) else 0.0,
            )
        )
    if not candidates:
        raise ProviderExecutionError("empty_response", "Pixabay returned no usable video")
    fitting = [clip for clip in candidates if clip.duration >= min_duration]
    return fitting[0] if fitting else candidates[0]


def search_params(query: str, orientation: str, kind: str = "photo") -> dict[str, object]:
    if not isinstance(query, str) or not query.strip():
        raise ProviderExecutionError("invalid_request", "Pixabay search query is required")
    params: dict[str, object] = {
        "q": query.strip()[:100],
        "safesearch": "true",
        "per_page": 3,
    }
    if kind == "video":
        # The videos endpoint accepts no orientation/image_type parameters.
        params["video_type"] = "film"
        return params
    params["image_type"] = "photo"
    if orientation == "portrait":
        params["orientation"] = "vertical"
    return params
