import json
import logging
from typing import Any

import httpx

from .text_provider import TextGenerationProvider
from .provider_registry import validate_model_selection

logger = logging.getLogger(__name__)

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"


class GeminiRateLimitError(Exception):
    pass


class GeminiInvalidResponse(Exception):
    pass


class GeminiQuotaExceeded(Exception):
    pass


class GeminiAuthError(Exception):
    pass


class GeminiTextProvider(TextGenerationProvider):
    PROVIDER_ID = "gemini"
    def __init__(self, api_key: str):
        self._api_key = api_key

    async def generate_structured_content(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        generation_config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        validate_model_selection(self.PROVIDER_ID, model, "text")

        url = f"{GEMINI_API_BASE}/models/{model}:generateContent?key={self._api_key}"
        config = generation_config or {}

        contents = []
        if system_prompt:
            contents.append({"role": "user", "parts": [{"text": system_prompt}]})
            contents.append({"role": "model", "parts": [{"text": "Understood."}]})
        contents.append({"role": "user", "parts": [{"text": user_prompt}]})

        body: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": config.get("temperature", 0.6),
                "maxOutputTokens": config.get("max_tokens", 8192),
            },
        }

        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(url, json=body)

        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            raise GeminiRateLimitError(f"rate limited; retry after {retry_after}s")
        if response.status_code == 403:
            raise GeminiQuotaExceeded("quota exceeded or API key lacks permission")
        if response.status_code in (401, 400):
            raise GeminiAuthError("invalid or missing API credentials")
        response.raise_for_status()

        data = response.json()
        try:
            text = data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError):
            raise GeminiInvalidResponse("Gemini returned no content")

        text = text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            raise GeminiInvalidResponse("Gemini response is not valid JSON")
