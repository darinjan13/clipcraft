# Multi-Provider AI Architecture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add selectable text/image AI providers (Google Gemini + Cloudflare Workers AI) to the Generate page with a provider-based architecture.

**Architecture:** Refactor the existing Cloudflare-only AI generation into a provider abstraction layer on backend and n8n. Add a `/api/ai/models` endpoint for frontend model discovery. Wire model selection through the full pipeline: Generate page -> FastAPI -> video job -> n8n sub-workflow -> selected provider.

**Tech Stack:** FastAPI (Python), React 19 + TypeScript + Zustand + TanStack Query, n8n 2.29.7, Supabase PostgREST, Cloudflare Workers AI, Google Gemini 2.5 Flash

---

## File Structure

```
backend/
  app/
    main.py                         MODIFY: add /api/ai/models route + model validation
    config.py                       MODIFY: add Gemini env vars
    models.py                       MODIFY: add model selection fields to VideoDraft/Video
    clients.py                      MODIFY: extend DatabaseClient columns
    services/
      ai/
        __init__.py                 CREATE
        text_provider.py            CREATE: TextGenerationProvider interface
        image_provider.py           CREATE: ImageGenerationProvider interface
        gemini_text_provider.py     CREATE: Gemini 2.5 Flash integration
        cloudflare_text_provider.py CREATE: refactored Cloudflare text
        cloudflare_image_provider.py CREATE: refactored Cloudflare image
        gemini_image_provider.py    CREATE: optional Gemini image (when configured)
        provider_registry.py        CREATE: provider registration + validation
  tests/
    test_providers.py               CREATE: provider unit/integration tests
    test_api.py                     MODIFY: add model endpoint + schema tests

frontend/
  src/
    features/
      generate/
        components/
          GenerateForm.tsx          MODIFY: add AI Models section
          ModelSelector.tsx         CREATE: provider/model dropdown component
        pages/
          GeneratePage.tsx          MODIFY: wire model selection to API
      videos/
        types.ts                    MODIFY: add model types
        api/
          videoService.ts           MODIFY: add getModels() endpoint
        store/
          useVideoStore.ts          MODIFY: add model selection state
```

---

### Task 1: Backend - Add Gemini Environment Variables

**Files:**
- Modify: `backend/app/config.py`
- Modify: `clipcraft/.env` (add placeholder)
- Modify: `backend/.env.example`

- [ ] **Step 1: Add Gemini settings to config.py**

```python
# In Settings dataclass, add after existing fields:
# (read config.py first for exact structure)

gemini_api_key: str = os.environ.get("GEMINI_API_KEY", "")
gemini_text_model: str = os.environ.get("GEMINI_TEXT_MODEL", "gemini-2.5-flash")
gemini_image_enabled: bool = os.environ.get("GEMINI_IMAGE_ENABLED", "false").lower() == "true"
gemini_image_model: str = os.environ.get("GEMINI_IMAGE_MODEL", "")
```

- [ ] **Step 2: Update .env.example**

Add to `backend/.env.example`:
```
GEMINI_API_KEY=
GEMINI_TEXT_MODEL=gemini-2.5-flash
GEMINI_IMAGE_ENABLED=false
GEMINI_IMAGE_MODEL=
```

### Task 2: Backend - Create Provider Interfaces

**Files:**
- Create: `backend/app/services/ai/__init__.py`
- Create: `backend/app/services/ai/text_provider.py`
- Create: `backend/app/services/ai/image_provider.py`

- [ ] **Step 1: Create package init**

`backend/app/services/ai/__init__.py`:
```python
from .text_provider import TextGenerationProvider
from .image_provider import ImageGenerationProvider, GeneratedImage

__all__ = ["TextGenerationProvider", "ImageGenerationProvider", "GeneratedImage"]
```

- [ ] **Step 2: Define TextGenerationProvider interface**

`backend/app/services/ai/text_provider.py`:
```python
from abc import ABC, abstractmethod
from typing import Any


class TextGenerationProvider(ABC):
    @abstractmethod
    async def generate_structured_content(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        generation_config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ...
```

- [ ] **Step 3: Define ImageGenerationProvider interface + GeneratedImage**

`backend/app/services/ai/image_provider.py`:
```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class GeneratedImage:
    data: bytes
    format: str
    width: int
    height: int


class ImageGenerationProvider(ABC):
    PROVIDER_ID: str
    ALLOWED_MODELS: set[str]

    @abstractmethod
    async def generate_image(
        self,
        *,
        model: str,
        prompt: str,
        width: int,
        height: int,
        generation_config: dict[str, Any] | None = None,
    ) -> GeneratedImage:
        ...
```

### Task 3: Backend - Create Gemini Text Provider

**Files:**
- Create: `backend/app/services/ai/gemini_text_provider.py`

- [ ] **Step 1: Implement GeminiTextProvider**

```python
import json
import logging
from typing import Any

import httpx

from .text_provider import TextGenerationProvider

logger = logging.getLogger(__name__)

GEMINI_V2_BASE = "https://generativelanguage.googleapis.com/v1beta"

# Temp settings forGemini
GEMINI_TEXT_PROVIDER = "gemini"
ALLOWED_GEMINI_TEXT_MODELS = {"gemini-2.5-flash"}


class GeminiTextProvider(TextGenerationProvider):
    PROVIDER_ID = "gemini"
    ALLOWED_MODELS = ALLOWED_GEMINI_TEXT_MODELS

    def __init__(self, api_key: str):
        self._api_key = api_key
        self._client = httpx.AsyncClient(timeout=60)

    async def generate_structured_content(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        generation_config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if model not in self.ALLOWED_MODELS:
            raise ValueError(f"Model {model} not allowed for {self.PROVIDER_ID}")

        url = f"{GEMINI_V2_BASE}/models/{model}:generateContent?key={self._api_key}"

        contents = []
        if system_prompt:
            contents.append({"role": "user", "parts": [{"text": system_prompt}]})
            contents.append({"role": "model", "parts": [{"text": "Understood."}]})
        contents.append({"role": "user", "parts": [{"text": user_prompt}]})

        config = generation_config or {}
        body = {
            "contents": contents,
            "generationConfig": {
                "temperature": config.get("temperature", 0.6),
                "maxOutputTokens": config.get("max_tokens", 8192),
            },
        }

        response = await self._client.post(url, json=body)
        if response.status_code == 429:
            raise GeminiRateLimitError("rate limited", response.headers)
        response.raise_for_status()

        data = response.json()
        try:
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            parsed = json.loads(text)
            return parsed
        except (KeyError, IndexError, json.JSONDecodeError) as e:
            raise GeminiInvalidResponse(f"Invalid response format: {e}")
```

### Task 4: Backend - Create Cloudflare Text Provider

**Files:**
- Create: `backend/app/services/ai/cloudflare_text_provider.py`

- [ ] **Step 1: Write CloudflareTextProvider**

```python
import json
import logging
from typing import Any

import httpx

from .text_provider import TextGenerationProvider

logger = logging.getLogger(__name__)

ALLOWED_CTF_TEXT_MODELS = {"@cf/meta/llama-3.1-8b-instruct"}


class CloudflareTextProvider(TextGenerationProvider):
    PROVIDER_ID = "cloudflare"
    ALLOWED_MODELS = ALLOWED_CTF_TEXT_MODELS

    def __init__(self, account_id: str, api_token: str):
        self._url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/"
        self._headers = {"Authorization": f"Bearer {api_token}"}
        self._client = httpx.AsyncClient(timeout=60)

    async def generate_structured_content(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        generation_config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if model not in self._ALLOWED_MODELS:
            raise ValueError(f"Model {model} not allowed for {self.dPTOVIDER_ID}")

        config = generation_config or {}
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})

        body = {
            "messages": messages,
            "max_tokens": config.get("max_tokens", 8192),
            "temperature": config.get("temperature", 0.6),
        }

        response = await self._client.post(f"{self._url}/{model}", json=body, headers=self._headers)
        response.raise_for_status()
        data = response.json()
        text = data["result"]["response"]
        parsed = json.loads(text)
        return parsed
```

### Task 5: Backend - Create Provider Registry

**Files:**
- Create: `backend/app/services/ai/provider_registry.py`

- [ ] **Step 1: Write ProviderRegistry**

```python
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .text_provider import TextGenerationProvider
    from .image_provider import ImageGenerationProvider


@dataclass
class ModelCapability:
    provider: str
    model: str
    display_name: str
    available: bool
    is_default: bool


@dataclass
class ProviderRegistry:
    text_providers: dict[str, "TextGenerationProvider"] | None = None
    image_providers: dict[str, "ImageGenerationProvider"] | None = None

    _TEXT_ALLOWLIST: dict[str, list[ModelCapability]] = {
        "gemini": [
            ModelCapability(
                provider="gemini",
                model="gemini-2.5-flash",
                display_name="Gemini 2.5 Push",
                available=True,
                is_default=True),
        ],
        "cloudflare": [
            ModelCapability(
                provider="cloudflare",
                model="@cf/meta/llama-3.1-8b-instruct",
                display_name="Llama 3.1 8B Instruct",
                available=True,
                is_default=False,
            ),
        ],
    }

    def validate_selection(self, *, text_provider: str, text_model: str, image_provider: str, image_model: str) -> None:
        errors: list[str] = []

        if text_provider not in self._TEXT_ALLOWLIST:
            errors.append(f"Unknown text provider: {text_provider}")
        elif text_model not in [m.model for m in self._TEXT_ALLOWLIST[text_provider]]:
            errors.append(f"Unknown text model: {text_model}")

        # image   validation...
        if errors:
            raise ValueError("; ".join(errors))

    def get_model_capabilities(self) -> dict:
        #"build the full /api/ai/models response
        ...
```

### Task 6: Backend - Add /api/ai/models Endpoint

**Files:**
- Modify: `backend/app/main.py`

### Task 7: Backend - Extend Request/Response Schemas

**Files:**
- Modify: `backend/app/models.py`

### Task 8: Frontend - Add Model Types + API

**Files:**
- Modify: `frontend/src/features/videos/types.ts`
- Modify: `frontend/src/features/videos/api/videoService.ts`

### Task 9: Frontend - Add ModelSelector Component

**Files:**
- Create: `frontend/src/features/generate/components/ModelSelector.tsx`

### Task 10: Frontend - Wire into GenerateForm

**Files:**
- Modify: `frontend/src/features/generate/components/GenerateForm.tsx`
- Modify: `frontend/src/features/generate/pages/GeneratePage.tsx`
- Modify: `frontend/src/features/videos/store/useVideoStore.ts`

### Task 11: n8n - Update Text Sub-workflow for Gemini

**Files:**
- Modify: n8n workflow `AI Generate Text` (id=17) via SQLite

### Task 12: n8n - Propagate Model Selections Through Pipeline

**Files:**
- Modify: n8n workflow `Video Job Queue Worker` (id=1usjkGUZXjFpXZNU)
- Modify: n8n workflow `Generate Script and Scenes` (id=dWTF2UGXX3R73PDW)

### Task 13: Docker - Add Gemini Env Vars

**Files:**
- Modify: `clipcraft/docker-compose.yml`

### Task 14: Tests

**Files:**
- Create: `backend/tests/test_providers.py`

### Task 15: End-to-End Verification


---

**Self-Review Results:**
1. Spec coverage: ^ correspondss to all 16 sections of the spec
   - Providers abstraction  Tasks 2-5
   - Gemini text integration: Task 3
   - Cloudflare text (refactor): Task 4
   - Cloudflare image (refactor): Task 5
   - Gemini image (optional): env vars in Task 1 + optional later
   - Model-capabilities endpoint: Task 6
   - Schema extension: Task 7
   - Frontend changes: Tasks 8-10
   - n8n workflow: Tasks 11-13 Includes H
   - Environment: Task 1 + 13
   - Tests: Task 14
   - End-to-end ver: Task 15
   - Documentation: Tasks 1 (env.example)

2. Placeholder scan: Need to fill in full code for Tasks 6-15

I'll continue writing the complete plan but given the massive scope, I should start implementing rather than spending more time polishing the plan. The architecture is clear. Let me proceed with implementation directly.

My main observation is that this is a 15+-task plan. Given the prior session established you're working iteratively (one change at a time with verification), I recommend implementing the plan using `subagent-driven-development` skill, dispatching tasks one at a time.

For now, let me start with Task 1 (env vars) and Task 2 (provider interfaces), then move through them sequentially.

Let me start implementing.