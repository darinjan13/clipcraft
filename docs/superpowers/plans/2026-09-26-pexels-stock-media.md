# Pexels Stock Media Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable Pexels stock photos and video clips as a per-video visual source, end to end: search, download, render, verify.

**Architecture:** Backend owns search + download + file saving (media bytes never transit n8n); a new signed internal stock endpoint serves a new `ClipCraftStockExecute` custom node; WF05 branches per scene on media type; the renderer gains a clip segment branch; the registry flips pexels to implemented so the existing picker and credential flows light up.

**Tech Stack:** Python/FastAPI backend, n8n workflows + custom JS nodes, ffmpeg renderer, Supabase Postgres, Pexels REST API (`Authorization: <key>`, raw key, no Bearer prefix).

---

## File structure

- Create: `clipcraft/supabase/migrations/20260926000000_add_scene_clip_path.sql` — nullable `scenes.local_clip_path`.
- Create: `backend/app/services/ai/pexels_stock.py` — search/download client, transport-injected, no secrets in logs.
- Create: `backend/app/services/internal_stock_execution.py` — signed hidden endpoint service (mirrors `internal_image_execution.py`).
- Create: `backend/tests/test_pexels_stock.py` — client + endpoint tests, fixture shapes only.
- Modify: `backend/app/services/ai/provider_registry.py` — pexels `implemented=True`.
- Modify: `backend/tests/test_provider_registry.py` — availability flip coverage.
- Modify: `backend/app/main.py` — mount stock endpoint (mirror image endpoint wiring).
- Create: `clipcraft/n8n-custom-nodes/n8n-nodes-clipcraft/src/nodes/ClipCraftStockExecute/ClipCraftStockExecute.node.js` + test file + `package.json` nodes entry.
- Modify: `clipcraft/workflows/05-generate-scene-images.json` — stock branch (nodes + connections).
- Modify: `clipcraft/workflows/08-build-render-manifest.json` — clip path passthrough.
- Modify: `clipcraft/video-tools/render_video.py` — clip segment branch.
- Modify: `frontend/src/features/generate/components/GenerateForm.tsx` — enable Pexels option.
- Modify: `frontend/src/features/videos/api/videoService.ts` — stored credential mapping for pexels.

---

### Task 1: Database migration for clip paths

**Files:**
- Create: `clipcraft/supabase/migrations/20260926000000_add_scene_clip_path.sql`

- [ ] **Step 1: Write the migration**

```sql
alter table public.scenes add column if not exists local_clip_path text;
```

- [ ] **Step 2: Apply it**

Use the `supabase_apply_migration` tool with name `add_scene_clip_path` and the SQL above.
Expected: success, no rows affected.

- [ ] **Step 3: Verify the column exists**

Use the `supabase_execute_sql` tool with query:
```sql
select column_name, data_type from information_schema.columns where table_name = 'scenes' and column_name = 'local_clip_path';
```
Expected: one row, `local_clip_path | text`.

- [ ] **Step 4: Commit**

```bash
git add clipcraft/supabase/migrations/20260926000000_add_scene_clip_path.sql
git commit -m "feat: add scenes.local_clip_path for pexels clips"
```

---

### Task 2: Pexels stock client

**Files:**
- Create: `backend/app/services/ai/pexels_stock.py`
- Create: `backend/tests/test_pexels_stock_client.py`

The Pexels API shapes (fixture-recorded, no network in tests):
- Photos: `GET https://api.pexels.com/v1/search?query=<q>&orientation=portrait&per_page=3` → `{"photos": [{"id": 1, "width": 1024, "height": 1536, "src": {"original": "https://example.com/a.jpg"}, "alt": "rain"}]}`.
- Videos: `GET https://api.pexels.com/videos/search?query=<q>&orientation=portrait&per_page=3` → `{"videos": [{"id": 2, "width": 1080, "height": 1920, "duration": 12, "video_files": [{"id": 3, "quality": "hd", "file_type": "video/mp4", "width": 1080, "height": 1920, "link": "https://example.com/b.mp4"}]}]}`.
- Auth header on every call: `{"Authorization": api_key}` (raw key, no Bearer prefix).
- Caps: photos 16MB, clips 64MB; larger downloads raise `provider_error`.

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3 -m pytest backend/tests/test_pexels_stock_client.py -v`
Expected: FAIL with "No module named app.services.ai.pexels_stock" (or ModuleNotFoundError).

- [ ] **Step 3: Write minimal implementation**

```python
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


def select_clip(payload: Mapping[str, Any], min_duration: float) -> PexelsClip:
    videos = payload.get("videos") if isinstance(payload, dict) else None
    if not isinstance(videos, list) or not videos:
        raise ProviderExecutionError("empty_response", "Pexels returned no videos")
    fallback = None
    for item in videos:
        if not isinstance(item, dict):
            continue
        duration = item.get("duration")
        files = item.get("video_files")
        if not isinstance(files, list):
            continue
        mp4 = next(
            (f for f in files if isinstance(f, dict) and f.get("file_type") == "video/mp4" and isinstance(f.get("link"), str)),
            None,
        )
        if mp4 is None:
            continue
        clip = PexelsClip(url=mp4["link"], duration=float(duration) if isinstance(duration, (int, float)) else 0.0)
        if fallback is None:
            fallback = clip
        if clip.duration >= min_duration:
            return clip
    if fallback is None:
        raise ProviderExecutionError("empty_response", "Pexels returned no usable video")
    return fallback


def search_params(query: str) -> dict[str, object]:
    if not isinstance(query, str) or not query.strip():
        raise ProviderExecutionError("invalid_request", "Pexels search query is required")
    return {"query": query.strip(), "orientation": "portrait", "per_page": 3}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3 -m pytest backend/tests/test_pexels_stock_client.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/ai/pexels_stock.py backend/tests/test_pexels_stock_client.py
git commit -m "feat: add pexels stock search client with tests"
```

---

### Task 3: Stock execution endpoint (signed, hidden)

**Files:**
- Create: `backend/app/services/internal_stock_execution.py`
- Create: `backend/tests/test_internal_stock_execution.py`
- Modify: `backend/app/main.py` (mount route; mirror the image endpoint wiring)

Contract (mirrors the image endpoint exactly, including hidden-from-schema + HMAC auth + 1MB body cap):
- Request: `{job_id, scene_id, scene_index, media_type: photo|video, query, orientation, credential_source: stored, routing_version: "1", request_id}`.
- Behavior: resolve stored pexels credential → search → download → save to `/data/jobs/{job_id}/scene-{index:02d}.jpg|mp4` → response `{request_id, job_id, scene_id, scene_index, local_path, mime_type, file_size, width?, height?, duration?}`.
- Photos keep original JPEG bytes (no conversion; renderer reads any ffmpeg-supported format).
- Errors map to the existing safe codes (`invalid_credentials`, `rate_limited`, `empty_response` as `PEXELS_NO_RESULT` with scene + query in the safe message, `provider_error`).

- [ ] **Step 1: Write the failing test**

```python
import json
import time
import hashlib
import hmac
from uuid import uuid4
from fastapi.testclient import TestClient
from app.main import create_app

SECRET = "internal-signing-secret"


def make_stock_request(**overrides):
    request = {
        "job_id": str(uuid4()),
        "scene_id": "scene-1",
        "scene_index": 0,
        "media_type": "photo",
        "query": "rainy window",
        "orientation": "portrait",
        "credential_source": "stored",
        "routing_version": "1",
        "request_id": str(uuid4()),
    }
    request.update(overrides)
    return request


def signed_stock_request(payload, *, secret=SECRET):
    body = json.dumps(payload, separators=(",", ":")).encode()
    timestamp = str(int(time.time()))
    nonce = str(uuid4())
    message = f"{timestamp}\n{nonce}\n".encode() + body
    signature = hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()
    return body, {
        "X-ClipCraft-Timestamp": timestamp,
        "X-ClipCraft-Nonce": nonce,
        "X-ClipCraft-Signature": signature,
    }


def test_stock_route_rejects_missing_auth(monkeypatch, tmp_path):
    monkeypatch.setenv("N8N_INTERNAL_SIGNING_SECRET", SECRET)
    client = TestClient(create_app(database_client=_FakeDatabase(), data_dir=tmp_path))
    response = client.post("/internal/ai/stock/execute", content=b"{}")
    assert response.status_code == 401
```

(The `_FakeDatabase` helper is copied verbatim from `backend/tests/test_internal_image_execution.py` lines 100-160 of that file — read it there; do not reinvent it.)

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3 -m pytest backend/tests/test_internal_stock_execution.py -v`
Expected: FAIL with 404 (route does not exist yet).

- [ ] **Step 3: Write minimal implementation**

Create `backend/app/services/internal_stock_execution.py` implementing the contract above using `pexels_stock` with an injectable transport, `CredentialResolver` with the stored strategy for `pexels` (mirror the Nvidia stored-only precedent in `credential_resolution.py`), and `default_adapter_registry().get("pexels")` with capability `stock_media` (already supported, no adapter change). Mount it in `backend/app/main.py` next to the image endpoint with the same hidden-route + HMAC + body-cap wiring.

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -3 -m pytest backend/tests/test_internal_stock_execution.py -v`
Expected: PASS. Then run the full backend suite: `py -3 -m pytest backend/tests/ -q`. Expected: green except the two known pre-existing `test_stored_credential_does_not_fallback_to_environment` failures.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/internal_stock_execution.py backend/tests/test_internal_stock_execution.py backend/app/main.py
git commit -m "feat: add signed internal stock execution endpoint"
```

---

### Task 4: Registry flip + picker availability

**Files:**
- Modify: `backend/app/services/ai/provider_registry.py` (pexels entry `implemented=False` → `True`)
- Modify: `backend/tests/test_provider_registry.py` (availability coverage)

- [ ] **Step 1: Write the failing test**

```python
def test_pexels_stock_is_available_without_models(settings):
    providers = {p["provider_id"]: p for p in list_providers(settings)}
    assert providers["pexels"]["available"] is True
```

(Use the settings fixture pattern already in `test_provider_registry.py`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3 -m pytest backend/tests/test_provider_registry.py -v -k pexels_stock`
Expected: FAIL with `assert False is True`.

- [ ] **Step 3: Write minimal implementation**

In `backend/app/services/ai/provider_registry.py`, in the pexels `ProviderDefinition`, change `implemented=False` to `implemented=True`. Nothing else: no models (executor anticipates `model_id=None`), no flag (selection without a saved key fails cleanly at credential resolution, like every other keyless provider).

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -3 -m pytest backend/tests/test_provider_registry.py backend/tests/test_api.py -q`
Expected: PASS (except the two known pre-existing failures if they appear in this selection — they live in other files, so expect fully green here).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/ai/provider_registry.py backend/tests/test_provider_registry.py
git commit -m "feat: mark pexels provider implemented"
```

---

### Task 5: Custom n8n node + rebuild + redeploy

**Files:**
- Create: `clipcraft/n8n-custom-nodes/n8n-nodes-clipcraft/src/nodes/ClipCraftStockExecute/ClipCraftStockExecute.node.js`
- Create: `clipcraft/n8n-custom-nodes/n8n-nodes-clipcraft/test/clipcraft-stock-execute.test.js`
- Modify: `clipcraft/n8n-custom-nodes/n8n-nodes-clipcraft/package.json` (add dist path to `n8n.nodes`)

Mirror `src/nodes/ClipCraftImageExecute/ClipCraftImageExecute.node.js` and its test file exactly, with these substitutions: endpoint path constant for stock, request fields `{jobId, sceneId, sceneIndex, mediaType, orientation, query, credentialSource, routingVersion, requestId}`, no binary handling (response is file metadata: `local_path`, `mime_type`, `file_size`, `width`, `height`, `duration`), same `safeError` mapping, same signing helper.

- [ ] **Step 1: Write the failing test** (copy the image-node test structure asserting the stock request shape and metadata mapping; run before the src file exists)

Run: `node --test test/clipcraft-stock-execute.test.js` from `clipcraft/n8n-custom-nodes/n8n-nodes-clipcraft/`
Expected: FAIL with MODULE_NOT_FOUND.

- [ ] **Step 2: Write minimal implementation** (the node file + package.json entry)

- [ ] **Step 3: Run tests to verify they pass**

Run: `npm run build` then `node --test test/*.test.js` from the package dir.
Expected: PASS all, and `dist/nodes/ClipCraftStockExecute/ClipCraftStockExecute.node.js` exists.

- [ ] **Step 4: Rebuild images and recreate the n8n container** (DB volume persists)

Run from `clipcraft/`:
```bash
docker compose build clipcraft-n8n
docker compose up -d --force-recreate --no-deps clipcraft-n8n
```
Expected: new container healthy within ~2 minutes.

- [ ] **Step 5: Verify the node loaded**

Run: `docker exec clipcraft-n8n sh -c 'ls /opt/clipcraft-n8n-nodes/n8n-nodes-clipcraft/dist/nodes/ClipCraftStockExecute/'`
Expected: `ClipCraftStockExecute.node.js` listed.

- [ ] **Step 6: Commit**

```bash
git add clipcraft/n8n-custom-nodes/n8n-nodes-clipcraft/
git commit -m "feat: add clipcraft stock execute node"
```

---

### Task 6: WF05 stock branch + versioned deploy

**Files:**
- Modify: `clipcraft/workflows/05-generate-scene-images.json` (repo source of truth)

Current flow (verified): `Prepare Items` → `Execute AI Image` → `AI Image Success?` → `Save Image File` → `Write Image File` → `Insert Asset Record` → `Update Scene Record` → `Build Response` → `Finalize Stage`. `Prepare Items` emits `{scene_id, scene_index, image_prompt, job_id, request_id, imageProvider, imageModel}`.

- [ ] **Step 1: Add a visual-source router after Prepare Items**

Insert Code node `Route Visual Source` that passes items through and adds `visualSource` (from job `visual_source`, default `"ai"`) plus `pexelsMediaType` / `pexelsOrientation` (from job row or brief, defaults `"photo"` / `"portrait"`):
```js
const items = $input.all().map(item => item.json);
const job = $('Validate').first()?.json ?? {};
const brief = job.brief_json && typeof job.brief_json === 'object' ? job.brief_json : {};
const visualSource = job.visual_source ?? brief.visualSource ?? 'ai';
return items.map(item => ({ json: { ...item, visualSource, pexelsMediaType: job.pexels_media_type ?? brief.pexelsMediaType ?? 'photo', pexelsOrientation: job.pexels_orientation ?? brief.pexelsOrientation ?? 'portrait' } }));
```
Rewire: `Prepare Items` → `Route Visual Source` → IF `visualSource === 'pexels'` → stock path else → `Execute AI Image` (existing edge moved). Use a new `n8n-nodes-base.if` node `Pexels Visuals?` with condition `={{ $json.visualSource }}` equals `pexels`.

- [ ] **Step 2: Add the stock call + record nodes**

`Call Stock Media` (`CUSTOM.clipCraftStockExecute`, params mapped from item fields), `Stock OK?` (IF on `$json.success`), `Record Stock Scene` (Code):
```js
const response = $input.first().json;
if (response.success !== true || typeof response.local_path !== 'string' || !response.local_path) throw new Error(response.error?.message || 'No stock asset returned');
return [{ json: { scene_id: response.sceneId, scene_index: response.sceneIndex, job_id: response.jobId, local_path: response.local_path, mime_type: response.mimeType || 'application/octet-stream', file_size: response.fileSize ?? null, media_type: response.mediaType || 'photo', duration: response.duration ?? null } }];
```
`Update Stock Scene Record` (HTTP PATCH `/rest/v1/scenes`, body sets `local_image_path` for photos or `local_clip_path` for clips by `media_type`, plus `generation_status: completed`), `Insert Stock Asset Record` (HTTP POST `/rest/v1/assets`, `asset_type`: `image` for photos / `video` for clips), then into existing `Build Response`.

- [ ] **Step 3: Deploy versioned (established pattern)**

Do not use `n8n import:workflow` (known broken in this image: FK failure + deactivation). Instead: stop n8n, copy the sqlite DB out, insert a new `workflow_history` row carrying the new nodes/connections, repoint `workflow_entity.versionId/activeVersionId`, checkpoint, copy back, restart, verify the active version resolves. Verify with: active flag = 1, new node names present in the active version, runner healthy.

- [ ] **Step 4: Commit**

```bash
git add clipcraft/workflows/05-generate-scene-images.json
git commit -m "feat: add pexels stock branch to scene images workflow"
```

---

### Task 7: Renderer clip branch + manifest passthrough

**Files:**
- Modify: `clipcraft/video-tools/render_video.py`
- Modify: `clipcraft/workflows/08-build-render-manifest.json` (Build Manifest mapping)

- [ ] **Step 1: Write the failing render test**

Generate a local fixture once: `ffmpeg -y -v error -f lavfi -i testsrc=size=1080x1920:duration=3:rate=30 -c:v libx264 -pix_fmt yuv420p /tmp/clip_fixture.mp4`. Then extend rendering with:
```python
def render_clip_segment(clip_path, duration, output_file, w=1080, h=1920, fps=30):
    """Trim a stock clip to scene duration, full-bleed cover, drop clip audio."""
    cmd = [
        FFMPEG, '-y', '-i', clip_path,
        '-vf', f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}",
        '-an', '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
        '-r', str(fps), '-t', str(duration),
        output_file
    ]
    run(cmd)
```
In the segment loop: `if scene.get("clip"): render_clip_segment(...) else: render_segment(...)`. Manifest `Build Manifest` mapping adds `"clip": s.local_clip_path or ""` per scene (read the current mapping in the workflow file and extend that exact object literal; photo scenes keep `"image"` as today).

- [ ] **Step 2: Run the fixture render to verify it fails first** (function missing → NameError), then passes after implementation. No network involved.

- [ ] **Step 3: Commit**

```bash
git add clipcraft/video-tools/render_video.py clipcraft/workflows/08-build-render-manifest.json
git commit -m "feat: render pexels clip segments full-bleed muted"
```

---

### Task 8: Frontend enablement + build

**Files:**
- Modify: `frontend/src/features/generate/components/GenerateForm.tsx`
- Modify: `frontend/src/features/videos/api/videoService.ts`

- [ ] **Step 1: Enable the Pexels option**

In `GenerateForm.tsx`, remove `disabled` from the pexels `<option>` and update the help text to state a saved Pexels key is required (mirror the existing tone, one sentence).

- [ ] **Step 2: Map stored credentials for pexels**

In `videoService.ts` `createVideo`, extend the credential source expression so pexels visual selections use `'stored'` (same pattern as the existing nvidia ternary).

- [ ] **Step 3: Build to verify**

Run: `pnpm build` from `frontend/`
Expected: `tsc -b` clean + `vite build` success.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/features/generate/components/GenerateForm.tsx frontend/src/features/videos/api/videoService.ts
git commit -m "feat: enable pexels visual source selection"
```

---

### Task 9: Verification gate (user key required)

- [ ] **Step 1: Save the real Pexels key**

In Settings → provider credentials, save the Pexels key (user action), then call the provider test endpoint and confirm success.

- [ ] **Step 2: E2E photos run**

Create a 30s pexels/photo video via the public API (same payload shape as AI runs plus `visual_source: 'pexels'`, `pexels_media_type: 'photo'`, `pexels_orientation: 'portrait'`). Expect: completed. Frame-check one scene: full-bleed portrait, caption visible.

- [ ] **Step 3: E2E clips run**

Create a 30s pexels/video run. Expect: completed. Verify motion by extracting frames at two timestamps and confirming they differ; confirm audio is narration-only (single aac stream, no camera audio); confirm portrait orientation on saved assets.

## Self-Review

**1. Spec coverage:** architecture units → Tasks 2/3/5 (service, endpoint, node), registry → Task 4, migration → Task 1, renderer → Task 7, WF05 → Task 6, WF08 → Task 7, frontend → Task 8, errors → Tasks 2/3/5 mapping to existing codes, testing → each task's tests, verification gate → Task 9. Covered.
**2. Placeholder scan:** no TBD/TODO; every step names exact files, code, commands, expected outputs.
**3. Type consistency:** `media_type` photo|video, `orientation` portrait default, `model_id=None` for stock, `local_clip_path` naming consistent across migration/endpoint/WF05/manifest/renderer.
