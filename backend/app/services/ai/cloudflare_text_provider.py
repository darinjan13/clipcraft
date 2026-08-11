import json
import logging
from typing import Any

import httpx

from .text_provider import TextGenerationProvider
from .provider_registry import validate_model_selection

logger = logging.getLogger(__name__)

class CloudflareTextProvider(TextGenerationProvider):
    PROVIDER_ID = "cloudflare"

    def __init__(self, account_id: str, api_token: str):
        self._base_url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run"
        self._headers = {"Authorization": f"Bearer {api_token}"}

    async def generate_structured_content(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        generation_config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        validate_model_selection(self.PROVIDER_ID, model, "text")

        config = generation_config or {}
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})

        body = {
            "messages": messages,
            "max_tokens": config.get("max_tokens", 8192),
            "temperature": config.get("temperature", 0.6),
        }

        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(f"{self._base_url}/{model}", json=body, headers=self._headers)
        response.raise_for_status()

        data = response.json()
        if not data.get("success") or "result" not in data:
            raise RuntimeError(f"Cloudflare AI error: {data}")

        text = data["result"]["response"]
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
            raise RuntimeError("Cloudflare response is not valid JSON")
