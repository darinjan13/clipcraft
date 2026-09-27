# Pixabay Stock Media Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Pixabay as a per-video visual source with photo/video/mix parity to Pexels, following the exact Pexels implementation pattern.

**Architecture:** New `pixabay` provider in the registry, new `pixabay_stock.py` transport beside `pexels_stock.py`, provider dispatch inside the existing stock execution service and custom node, WF05 passes the provider through, frontend mirrors the Pexels picker. No new endpoints, no WF04/06/07/08 changes.

**Tech Stack:** Python (FastAPI/pydantic/httpx), n8n custom nodes (JS), React+TS frontend, Supabase RPC unchanged.

**Base:** Branch `feature/pixabay-stock-media`. Task 0 merges `feature/pexels-mix-subtitles` first (scene tags, subtitle timing, stock media gate) so Pixabay inherits them.

---

### Task 0: Merge the mix branch and verify baseline

**Files:** none (git only).

- [ ] **Step 1: Merge**
```bash
git merge feature/pexels-mix-subtitles -m 'merge feature/pexels-mix-subtitles into feature/pixabay-stock-media'
```
Resolve conflicts by keeping both providers' additions. The mix branch touches `clipcraft/workflows/04,05,07`, `backend/app/services/internal_stock_execution.py`, `backend/tests/test_internal_stock_execution.py`, `frontend` video types/service/form, and DB migrations (already applied live).

- [ ] **Step 2: Run baseline tests**
```bash
py -3 -m pytest backend/tests -q -p no:warnings
```
Expected: PASS (the 2 pre-existing `AI_CREDENTIAL_INVALID` vs `AI_CREDENTIAL_MISSING` failures are known; anything else is a merge break — fix before continuing).

- [ ] **Step 3: Frontend build**
```bash
cd frontend && pnpm build
```
Expected: PASS.

- [ ] **Step 4: Commit the merge** (git creates it automatically; if conflicts were resolved, amend nothing — keep the merge commit).

---

### Task 1: Registry — Pixabay provider, sets, validators

**Files:**
- Modify: `backend/app/services/ai/provider_registry.py`
- Test: `backend/tests/test_provider_registry_pixabay.py` (create)

- [ ] **Step 1: Write the failing test**
```python
from app.services.ai.provider_registry import (
    SUPPORTED_PIXABAY_MEDIA_TYPES,
    SUPPORTED_PIXABAY_ORIENTATIONS,
    SUPPORTED_VISUAL_SOURCES,
    get_provider,
    validate_pixabay_media_type,
    validate_pixabay_orientation,
    validate_visual_source,
)


def test_pixabay_is_a_supported_visual_source():
    assert "pixabay" in SUPPORTED_VISUAL_SOURCES
    provider = get_provider("pixabay")
    assert provider.provider_type == "stock_media"
    assert "stock_media" in provider.capabilities
    assert provider.requires_credential is True
    assert provider.implemented is True
    validate_visual_source("pixabay")


def test_pixabay_media_types():
    assert SUPPORTED_PIXABAY_MEDIA_TYPES == {"photo", "video", "both"}
    validate_pixabay_media_type("photo")
    validate_pixabay_media_type("video")
    validate_pixabay_media_type("both")


def test_pixabay_orientations():
    assert SUPPORTED_PIXABAY_ORIENTATIONS == {"landscape", "portrait", "square"}
    validate_pixabay_orientation("portrait")
```

- [ ] **Step 2: Run it (fails: names do not exist)**
```bash
py -3 -m pytest backend/tests/test_provider_registry_pixabay.py -q -p no:warnings
```

- [ ] **Step 3: Implement.** In `provider_registry.py`:
  - `SUPPORTED_VISUAL_SOURCES = {"ai", "pexels", "pixabay"}`
  - Add after the pexels `ProviderDefinition`:
```python
ProviderDefinition(
    provider_id="pixabay",
    display_name="Pixabay",
    provider_type="stock_media",
    capabilities=("stock_media",),
    requires_credential=True,
    credential_type="api_key",
    enabled=True,
    implemented=True,
    credential_configuration_supported=True,
    connection_test_supported=True,
    default_model=None,
    models=(),
),
```
  - Add sets (next to `SUPPORTED_PEXELS_MEDIA_TYPES`):
```python
SUPPORTED_PIXABAY_MEDIA_TYPES = {"photo", "video", "both"}
SUPPORTED_PIXABAY_ORIENTATIONS = {"landscape", "portrait", "square"}
```
  - Extend `validate_visual_source` with a pixabay branch mirroring pexels, and add:
```python
def validate_pixabay_media_type(value: str) -> None:
    if value not in SUPPORTED_PIXABAY_MEDIA_TYPES:
        raise RegistryValidationError("unsupported_pixabay_media_type", f"unsupported Pixabay media type: {value}")


def validate_pixabay_orientation(value: str) -> None:
    if value not in SUPPORTED_PIXABAY_ORIENTATIONS:
        raise RegistryValidationError("unsupported_pixabay_orientation", f"unsupported Pixabay orientation: {value}")
```

- [ ] **Step 4: Run test (passes) + full registry tests.**
- [ ] **Step 5: Commit** `git add backend/app/services/ai/provider_registry.py backend/tests/test_provider_registry_pixabay.py && git commit -m 'feat(pixabay): register provider, sets, validators'`

---

### Task 2: Resolution, executor, adapters

**Files:**
- Modify: `backend/app/services/ai/credential_resolution.py`
- Modify: `backend/app/services/ai/provider_executor.py` (line ~213)
- Modify: `backend/app/services/ai/adapters.py` (lines ~80-81, ~167)

- [ ] **Step 1: credential_resolution.py** — mirror each pexels branch:
  - allowed providers: `if routing_decision.visual_source == "pixabay": allowed_providers.add("pixabay")`
  - `_resolve_environment`: `if provider_id == "pixabay": raise CredentialResolutionError("credential_configuration_error", "environment credential configuration is unavailable")` (stored-only, like pexels)
  - `build_execution_context`: `if routing_decision.visual_source == "pixabay": provider_ids.append("pixabay")`
- [ ] **Step 2: provider_executor.py** — extend the stock condition to `provider_id in ("pexels", "pixabay")` with matching visual_source.
- [ ] **Step 3: adapters.py** — mirror the pexels visual_source branch and add `PixabayAdapter("pixabay", {"stock_media", "connection_test"})` following the `PexelsAdapter` class exactly.
- [ ] **Step 4: Run backend tests** (`pytest backend/tests -q -p no:warnings`), expect only the 2 known pre-existing failures.
- [ ] **Step 5: Commit** `git commit -m 'feat(pixabay): resolution, executor, adapter branches'`

---

### Task 3: Connection test

**Files:**
- Modify: `backend/app/services/provider_connection.py`

- [ ] **Step 1: Add after `test_pexels`:**
```python
def test_pixabay(secret: str) -> ProviderTestResult:
    return _request(
        "GET",
        "https://pixabay.com/api/?key=" + secret + "&q=test&per_page=3",
        headers={},
    )
```
Wait — `_request` signature is `_request(method, url, headers, json?)`; the key goes in the query string (Pixabay has no header auth). Pass the secret only in the URL, never in logs (follow how `_request` sanitizes; check it does not log URLs with keys — read `_request` first, and if it logs URLs, add redaction for `key=`).

- [ ] **Step 2: Register in `run_provider_test`:** `if provider_id == "pixabay": return test_pixabay(secret)`.
- [ ] **Step 3: Backend tests pass.**
- [ ] **Step 4: Commit** `git commit -m 'feat(pixabay): connection test'`

---

### Task 4: Pixabay transport, selection, params (TDD)

**Files:**
- Create: `backend/app/services/ai/pixabay_stock.py`
- Create: `backend/tests/test_pixabay_stock.py`

Pixabay response shapes: images → `{"hits": [{"largeImageURL", "webformatURL", ...}]}`; videos → `{"hits": [{"duration", "videos": {"medium": {"url", "width", "height"}, "small": {...}}}]}`. `medium` is always present.

- [ ] **Step 1: Write failing unit tests** (pure functions + fake transport; no network):
```python
from app.services.ai.pixabay_stock import (
    search_params,
    select_clip,
    select_photo,
)
from app.services.ai.provider_executor import ProviderExecutionError
import pytest


def test_search_params_truncates_long_prompts():
    params = search_params("x" * 150, "portrait")
    assert len(params["q"]) <= 100
    assert params["safesearch"] == "true"
    assert params["per_page"] == 3


def test_search_params_empty_query_rejected():
    with pytest.raises(ProviderExecutionError):
        search_params("   ", "portrait")


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
```

- [ ] **Step 2: Run (fails: module missing).**
- [ ] **Step 3: Implement `pixabay_stock.py`** mirroring `pexels_stock.py` structure:
  - `PIXABAY_API_BASE = "https://pixabay.com"`, same byte caps/timeouts.
  - `HttpxPixabayTransport.search(kind, api_key, params)`: images → `GET /api/` with `params | {"key": api_key}`; videos → `GET /api/videos/` likewise. Key in query string only, never in log/error strings. 429 → single backoff: read `Retry-After` else `X-RateLimit-Reset` (seconds, cap 30), `await asyncio.sleep(...)`, retry once, then raise `rate_limited`. Other non-2xx → `provider_error`; 400 → `invalid_request`. Malformed JSON → `malformed_response`.
  - `download(api_key, url, max_bytes)`: plain GET (Pixabay file URLs need no key), same caps/errors as Pexels download.
  - `select_photo(payload)`: first hit with `largeImageURL`, else `webformatURL`, else raise `empty_response`.
  - `select_clip(payload, min_duration)`: hits with `videos.medium.url`, prefer duration >= min_duration, else first; missing → `empty_response`.
  - `search_params(query, orientation)`: images get `image_type=photo` + `orientation=vertical` when orientation == "portrait" (omit otherwise); videos get `video_type=film` and NO orientation key. `q` truncated to 100 chars. Empty → `invalid_request`.
- [ ] **Step 4: Tests pass.**
- [ ] **Step 5: Commit** `git commit -m 'feat(pixabay): transport, selection, search params'`

---

### Task 5: 24-hour search-response cache (terms requirement)

**Files:**
- Modify: `backend/app/services/ai/pixabay_stock.py`
- Modify: `backend/tests/test_pixabay_stock.py`

- [ ] **Step 1: Add failing test:**
```python
def test_search_responses_are_cached_24h(monkeypatch):
    import time
    from app.services.ai import pixabay_stock as mod
    calls = {"n": 0}
    async def fake_get(*a, **k):
        calls["n"] += 1
        class R:
            status_code = 200
            def json(self): return {"hits": []}
            headers = {}
        return R()
    # (wire fake_get into the transport's client however Task 4 structured it;
    # assert two identical searches issue ONE network call)
```
Write it against the actual Task 4 structure (monkeypatch `httpx.AsyncClient`).

- [ ] **Step 2: Implement** a module-level cache in `pixabay_stock.py`: key `(kind, q, orientation, per_page)`, value `(expires_monotonic, payload)`, TTL 86400s, max 500 entries with oldest-eviction. Only successful (2xx) payloads cached. No key material in cache keys.
- [ ] **Step 3: Tests pass.**
- [ ] **Step 4: Commit** `git commit -m 'feat(pixabay): 24h search response cache'`

---

### Task 6: Service dispatch by provider

**Files:**
- Modify: `backend/app/services/internal_stock_execution.py`
- Test: `backend/tests/test_internal_pixabay_execution.py` (create)

After Task 0 this file validates per-provider media types and rejects `both` at the boundary — read the merged version first, then:

- [ ] **Step 1: Write failing route tests** mirroring `test_internal_stock_execution.py` helpers (copy `signed_stock_request` + `_FakeDatabase` pattern; `provider_id="pixabay"`):
  - valid photo request with mocked `HttpxPixabayTransport` saves `scene-00.jpg`, `media_type == "photo"`, secret never in response;
  - `media_type="both"` → 422 `AI_EXECUTION_FAILED` (no transport mock needed);
  - unknown provider (e.g. `"acme"`) → 422.
- [ ] **Step 2: Run (fails: pixabay unknown).**
- [ ] **Step 3: Implement:**
  - `provider_id: Literal["pexels", "pixabay"]` on the request model.
  - Transport map: pixabay → `HttpxPixabayTransport()` (keep constructor default pexels; select inside `execute` by `request.provider_id`).
  - Validation branch: pixabay → `validate_visual_source("pixabay")`, `validate_pixabay_media_type`, `validate_pixabay_orientation`; keep the `both` rejection for both providers.
  - Selection branch: pixabay → `pixabay_stock.select_photo/select_clip`, same save/extension/mime logic.
  - Credential decision: `visual_source=request.provider_id`.
  - Response: add `provider_id: str` echoing `request.provider_id` (the custom node needs it; pexels responses return `"pexels"`).
- [ ] **Step 4: Tests pass + full suite green (minus 2 known).**
- [ ] **Step 5: Commit** `git commit -m 'feat(pixabay): service dispatch and response provider'`

---

### Task 7: Backend brief + draft models

**Files:**
- Modify: `backend/app/models.py` (add `pixabay_media_type`, `pixabay_orientation` beside pexels fields, all create/update variants)
- Modify: `backend/app/main.py` (mirror the three pexels blocks: field allow-list ~line 214, validation ~239-243, brief persistence ~898-902)

- [ ] **Step 1: models.py** — add `pixabay_media_type: str | None = None` and `pixabay_orientation: str | None = None` next to every pexels pair.
- [ ] **Step 2: main.py** — three mirrors:
  - allow-list: add `"pixabay_media_type", "pixabay_orientation"`;
  - `if visual_source == "pixabay":` validate both via the Task 1 validators;
  - brief: `brief["pixabayMediaType"]` / `brief["pixabayOrientation"]`.
- [ ] **Step 3: Backend tests pass.**
- [ ] **Step 4: Commit** `git commit -m 'feat(pixabay): draft models and brief fields'`

---

### Task 8: Custom node provider param + tests

**Files:**
- Modify: `clipcraft/n8n-custom-nodes/n8n-nodes-clipcraft/src/nodes/ClipCraftStockExecute/ClipCraftStockExecute.node.js`
- Modify: `clipcraft/n8n-custom-nodes/n8n-nodes-clipcraft/test/clipcraft-stock-execute.test.js` (read it first)

- [ ] **Step 1: Add failing node test:** `buildNormalizedRequest` with `provider: 'pixabay'` yields `provider_id: 'pixabay'`; without provider yields `'pexels'` (backward compat); `normalizeStockResponse` surfaces `provider` from response.
- [ ] **Step 2: Run node tests (fails).** (`cd clipcraft/n8n-custom-nodes/n8n-nodes-clipcraft && npm test`; confirm command in package.json first.)
- [ ] **Step 3: Implement:** add `optionsField('Provider', 'provider', ['pexels', 'pixabay'], 'pexels')`, include `'provider'` in the `getNodeParameter` list, `provider_id: String(input.provider || 'pexels')`, normalize `provider: response.provider_id || input.provider || 'pexels'`, update description text (Pexels → stock media).
- [ ] **Step 4: Node tests pass (34+ new).**
- [ ] **Step 5: Commit** `git commit -m 'feat(pixabay): stock node provider param'`

---

### Task 9: WF05 provider passthrough

**Files:**
- Modify: `clipcraft/workflows/05-generate-scene-images.json` (node `Call Stock Media`)

- [ ] **Step 1: Set params** `provider: "={{ $json.visualSource }}"` and keep `mediaType` as the merged per-scene value. No other node changes (tags, routing, manifest flow untouched).
- [ ] **Step 2: Syntax check** the edited node with `node --check` and assert node set + connections unchanged (same guard style as prior deploys: only `Call Stock Media` differs).
- [ ] **Step 3: Commit** `git commit -m 'feat(pixabay): WF05 passes provider to stock node'`

---

### Task 10: Frontend — types, form, service

**Files:**
- Modify: `frontend/src/features/videos/types.ts`
- Modify: `frontend/src/features/generate/components/GenerateForm.tsx` (lines ~77-78, ~96)
- Modify: `frontend/src/features/videos/api/videoService.ts` (lines ~37-52)

- [ ] **Step 1: types.ts** — `visual_source?: 'ai' | 'pexels' | 'pixabay'`; add `pixabay_media_type?: 'photo' | 'video' | 'both'` and `pixabay_orientation?: ...` mirroring the pexels fields (match the post-merge pexels shape exactly).
- [ ] **Step 2: GenerateForm.tsx** — add `<option value="pixabay">Pixabay stock media</option>`; mirror the pexels media-type/orientation block for `draft.visual_source === 'pixabay'` (help text: saved Pixabay key); extend the submit-disabled condition from `!== 'pexels'` to exclude both stock sources.
- [ ] **Step 3: videoService.ts** — mirror the pexels destructure/spread for `pixabay_media_type`/`pixabay_orientation`; extend `credential_source` to `'stored'` when `visual_source === 'pixabay'`.
- [ ] **Step 4: `pnpm build` passes.** (Settings credential UI is registry-driven — no change needed; verify the Pixabay card appears once the backend registry from Task 1 is live.)
- [ ] **Step 5: Commit** `git commit -m 'feat(pixabay): frontend source picker and request mapping'`

---

### Task 11: Rebuild, deploy, verify (gated)

- [ ] **Step 1: Backend tests + node tests + frontend build green.**
- [ ] **Step 2: Rebuild images** `docker compose build clipcraft-backend` (context is repo root — verify) and the n8n image (custom node ships in it), recreate, wait healthy. **Do NOT `n8n import:workflow`.**
- [ ] **Step 3: Versioned WF05 deploy** (stop n8n → fresh `docker cp` DB out → new `workflow_history` row + repoint, assert only `Call Stock Media` differs → `wal_checkpoint` + integrity → rm `-wal`/`-shm` in volume BEFORE copy-back → copy back → start → clean boot, all workflows active).
- [ ] **Step 4: Save the Pixabay key** (user provides) via Settings → stored credential, confirm `status: connected`.
- [ ] **Step 5: E2E photo video** (30s, pixabay/photo/portrait) → completed; frame shows photo + subtitle; manifest `provider: pixabay`.
- [ ] **Step 6: E2E mix video** (30s, pixabay/both) → manifest shows photo + clip mix; ASS events tiled; mid-narration frame check.
- [ ] **Step 7: Commit** any deploy-sync diffs; report.

**E2E discipline:** one video at a time, sequential scenes only, stop all stock traffic while any provider ban is active. Do not run E2E until the user confirms the Pixabay key AND the Pexels cooldown is over (shared IP reputation).

---

## Self-review

- Spec coverage: provider+creds (§1) → Tasks 1–3, 7; backend (§2) → Tasks 4–6; workflow (§3) → Tasks 8–9; frontend (§3) → Task 10; compliance (§4: 24h cache → Task 5, local storage → Task 6 save path, attribution → recorded in asset `provider` + response `provider_id` surfaced to UI via manifest); verification (§5) → Tasks 4, 6, 8, 10, 11.
- No placeholders: every step names exact files, code, and commands. Task 6 says "read the merged version first" — legitimate (Task 0 changes it), scoped to one file.
- Type consistency: `provider_id` string across registry/route/node/response; `media_type` photo|video at the boundary, `both` only in registry + frontend picker (rejected server-side like Pexels).
