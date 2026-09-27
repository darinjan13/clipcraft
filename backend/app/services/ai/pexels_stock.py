"""Pexels stock search + download. Transport-injected; never logs secrets."""

import time
from dataclasses import dataclass
from typing import Any, Mapping, Protocol

import httpx

from .provider_executor import ProviderExecutionError

PEXELS_API_BASE = "https://api.pexels.com"
PHOTO_MAX_BYTES = 16 * 1024 * 1024
CLIP_MAX_BYTES = 64 * 1024 * 1024
SEARCH_TIMEOUT_SECONDS = 30.0
DOWNLOAD_TIMEOUT_SECONDS = 120.0


@dataclass(frozen=True)
class PexelsPhoto:
    url: str


@dataclass(frozen=True)
class PexelsClip:
    url: str
    duration: float


class PexelsTransport(Protocol):
    async def search(self, *, kind: str, api_key: str, params: Mapping[str, object]) -> Any:
        """GET /v1/search or /videos/search; kind is 'photo' or 'video'."""

    async def download(self, *, api_key: str, url: str, max_bytes: int) -> bytes:
        """Download raw bytes with a size cap."""


class HttpxPexelsTransport:
    async def search(self, *, kind: str, api_key: str, params: Mapping[str, object]) -> Any:
        path = "/v1/search" if kind == "photo" else "/videos/search"
        try:
            async with httpx.AsyncClient(timeout=SEARCH_TIMEOUT_SECONDS, follow_redirects=True) as client:
                response = await client.get(
                    PEXELS_API_BASE + path,
                    headers={"Authorization": api_key},
                    params=dict(params),
                )
        except httpx.TimeoutException as exc:
            raise ProviderExecutionError("timeout", "Pexels request timed out") from exc
        except httpx.RequestError as exc:
            raise ProviderExecutionError("unavailable", "Pexels provider is unavailable") from exc
        if response.status_code == 401:
            raise ProviderExecutionError("invalid_credentials", "Pexels credentials were rejected")
        if response.status_code == 429:
            raise ProviderExecutionError("rate_limited", "Pexels rate limit reached")
        if not 200 <= response.status_code < 300:
            raise ProviderExecutionError("provider_error", "Pexels provider request failed")
        try:
            return response.json()
        except ValueError as exc:
            raise ProviderExecutionError("malformed_response", "Pexels returned malformed JSON") from exc

    async def download(self, *, api_key: str, url: str, max_bytes: int) -> bytes:
        try:
            async with httpx.AsyncClient(timeout=DOWNLOAD_TIMEOUT_SECONDS, follow_redirects=True) as client:
                async with client.stream("GET", url, headers={"Authorization": api_key}) as response:
                    if response.status_code == 401:
                        raise ProviderExecutionError("invalid_credentials", "Pexels credentials were rejected")
                    if response.status_code == 429:
                        raise ProviderExecutionError("rate_limited", "Pexels rate limit reached")
                    if not 200 <= response.status_code < 300:
                        raise ProviderExecutionError("provider_error", "Pexels download failed")
                    chunks = bytearray()
                    async for chunk in response.aiter_bytes():
                        chunks.extend(chunk)
                        if len(chunks) > max_bytes:
                            raise ProviderExecutionError("provider_error", "Pexels asset exceeds size cap")
                    if not chunks:
                        raise ProviderExecutionError("empty_response", "Pexels returned no bytes")
                    return bytes(chunks)
        except ProviderExecutionError:
            raise
        except httpx.TimeoutException as exc:
            raise ProviderExecutionError("timeout", "Pexels download timed out") from exc
        except httpx.RequestError as exc:
            raise ProviderExecutionError("unavailable", "Pexels provider is unavailable") from exc


def select_photo(payload: Mapping[str, Any]) -> PexelsPhoto:
    photos = payload.get("photos") if isinstance(payload, dict) else None
    if not isinstance(photos, list) or not photos:
        raise ProviderExecutionError("empty_response", "Pexels returned no photos")
    for item in photos:
        if not isinstance(item, dict):
            continue
        src = item.get("src")
        url = src.get("original") if isinstance(src, dict) else None
        if isinstance(url, str) and url.strip():
            return PexelsPhoto(url=url.strip())
    raise ProviderExecutionError("empty_response", "Pexels returned no usable photo")


_QUALITY_RANK = {"uhd": 0, "hd": 1, "sd": 2}


def _file_rank(file: Mapping[str, Any]) -> tuple[int, int]:
    quality = file.get("quality") if isinstance(file, dict) else None
    width = file.get("width") if isinstance(file, dict) else 0
    return (
        _QUALITY_RANK.get(quality, 3) if isinstance(quality, str) else 3,
        -(width if isinstance(width, int) else 0),
    )


def select_clip(payload: Mapping[str, Any], min_duration: float) -> PexelsClip:
    videos = payload.get("videos") if isinstance(payload, dict) else None
    if not isinstance(videos, list) or not videos:
        raise ProviderExecutionError("empty_response", "Pexels returned no videos")
    candidates: list[tuple[PexelsClip, tuple[int, int]]] = []
    for item in videos:
        if not isinstance(item, dict):
            continue
        duration = item.get("duration")
        files = item.get("video_files")
        if not isinstance(files, list):
            continue
        mp4s = [
            f for f in files
            if isinstance(f, dict) and f.get("file_type") == "video/mp4"
            and isinstance(f.get("link"), str) and f["link"].strip()
        ]
        if not mp4s:
            continue
        best = sorted(mp4s, key=_file_rank)[0]
        clip = PexelsClip(
            url=str(best["link"]).strip(),
            duration=float(duration) if isinstance(duration, (int, float)) else 0.0,
        )
        candidates.append((clip, _file_rank(best)))
    if not candidates:
        raise ProviderExecutionError("empty_response", "Pexels returned no usable video")
    fitting = [(clip, rank) for clip, rank in candidates if clip.duration >= min_duration]
    pool = fitting or candidates
    pool.sort(key=lambda entry: entry[1])
    return pool[0][0]


def search_params(query: str) -> dict[str, object]:
    if not isinstance(query, str) or not query.strip():
        raise ProviderExecutionError("invalid_request", "Pexels search query is required")
    return {"query": query.strip(), "orientation": "portrait", "per_page": 3}
