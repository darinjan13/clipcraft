import time
from dataclasses import dataclass
from typing import Any, Mapping, Protocol
from urllib.parse import quote

import httpx

from .provider_executor import ExecutionOutput, ExecutionRequest, ProviderExecutionError, ProviderExecutionRegistry

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"
GEMINI_TIMEOUT_SECONDS = 60.0
MAX_RESPONSE_BYTES = 4 * 1024 * 1024


@dataclass(frozen=True)
class GeminiResponse:
    status_code: int
    body: object
    headers: Mapping[str, str] = None


class GeminiTransport(Protocol):
    async def generate(self, *, model: str, api_key: str, body: Mapping[str, object], timeout_seconds: float) -> GeminiResponse:
        """Perform one Gemini request without exposing the response outside execution."""


class HttpxGeminiTransport:
    async def generate(self, *, model: str, api_key: str, body: Mapping[str, object], timeout_seconds: float) -> GeminiResponse:
        encoded_model = quote(model, safe="")
        url = f"{GEMINI_API_BASE}/models/{encoded_model}:generateContent"
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=False) as client:
                response = await client.post(
                    url,
                    headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
                    json=body,
                )
        except httpx.TimeoutException as exc:
            raise ProviderExecutionError("timeout", "Gemini request timed out") from None
        except httpx.RequestError as exc:
            raise ProviderExecutionError("unavailable", "Gemini provider is unavailable") from None
        if len(response.content) > MAX_RESPONSE_BYTES:
            raise ProviderExecutionError("malformed_response", "Gemini response exceeded the permitted size")
        try:
            response_body = response.json()
        except ValueError:
            response_body = None
        return GeminiResponse(response.status_code, response_body, dict(response.headers))


class GeminiTextExecution:
    def __init__(self, transport: GeminiTransport | None = None, timeout_seconds: float = GEMINI_TIMEOUT_SECONDS):
        self._transport = transport or HttpxGeminiTransport()
        self._timeout_seconds = timeout_seconds

    async def __call__(self, request: ExecutionRequest) -> ExecutionOutput:
        credential = next((item for item in request.runtime_context.credentials if item.provider_id == "gemini"), None)
        if credential is None:
            raise ProviderExecutionError("credential_resolution_error", "Gemini credential is unavailable")
        payload = request.payload
        body: dict[str, object] = {
            "contents": [{"role": "user", "parts": [{"text": payload["prompt"]}]}],
            "generationConfig": {
                "temperature": payload.get("temperature", 0.6),
                "maxOutputTokens": payload.get("max_tokens", 8192),
            },
        }
        if payload.get("system_prompt"):
            body["systemInstruction"] = {"parts": [{"text": payload["system_prompt"]}]}
        started = time.perf_counter()
        try:
            response = await self._transport.generate(
                model=request.model_id or "",
                api_key=credential.secret.get_secret_value(),
                body=body,
                timeout_seconds=self._timeout_seconds,
            )
        except ProviderExecutionError:
            raise
        except TimeoutError:
            raise ProviderExecutionError("timeout", "Gemini request timed out") from None
        except Exception:
            raise ProviderExecutionError("unavailable", "Gemini provider is unavailable") from None
        self._raise_for_status(response.status_code)
        text, finish_reason = self._extract_text(response.body)
        usage = self._safe_usage(response.body)
        request_id = self._header(response.headers or {}, "x-request-id")
        return ExecutionOutput(
            provider_id="gemini",
            model_id=request.model_id,
            capability="text_generation",
            text=text,
            finish_reason=finish_reason,
            usage=usage,
            provider_request_id=request_id,
            elapsed_ms=round((time.perf_counter() - started) * 1000, 2),
        )

    @staticmethod
    def _raise_for_status(status_code: int) -> None:
        if 200 <= status_code < 300:
            return
        codes = {
            400: ("invalid_request", "Gemini rejected the request"),
            401: ("invalid_credentials", "Gemini credentials were rejected"),
            403: ("permission_denied", "Gemini denied permission"),
            408: ("timeout", "Gemini request timed out"),
            402: ("quota_exceeded", "Gemini quota was exceeded"),
            429: ("rate_limited", "Gemini rate limit reached"),
        }
        code, message = codes.get(status_code, ("unavailable" if status_code >= 500 else "provider_error", "Gemini provider request failed"))
        raise ProviderExecutionError(code, message)

    @staticmethod
    def _extract_text(body: object) -> tuple[str, str | None]:
        if not isinstance(body, dict):
            raise ProviderExecutionError("malformed_response", "Gemini returned malformed JSON")
        feedback = body.get("promptFeedback")
        if isinstance(feedback, dict) and feedback.get("blockReason"):
            raise ProviderExecutionError("blocked_response", "Gemini blocked the response")
        candidates = body.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            raise ProviderExecutionError("malformed_response", "Gemini returned no candidates")
        candidate = candidates[0]
        content = candidate.get("content") if isinstance(candidate, dict) else None
        if not isinstance(content, dict):
            raise ProviderExecutionError("malformed_response", "Gemini returned malformed content")
        parts = content.get("parts", [])
        if not isinstance(parts, list):
            raise ProviderExecutionError("malformed_response", "Gemini returned malformed parts")
        text = "".join(part.get("text", "") for part in parts if isinstance(part, dict) and isinstance(part.get("text"), str)).strip()
        if not text:
            raise ProviderExecutionError("empty_response", "Gemini returned no text")
        finish_reason = candidate.get("finishReason") if isinstance(candidate, dict) and isinstance(candidate.get("finishReason"), str) else None
        return text, finish_reason

    @staticmethod
    def _safe_usage(body: object) -> Mapping[str, int]:
        if not isinstance(body, dict) or not isinstance(body.get("usageMetadata"), dict):
            return {}
        return {key: value for key, value in body["usageMetadata"].items() if isinstance(key, str) and isinstance(value, int) and key.endswith("TokenCount")}

    @staticmethod
    def _header(headers: Mapping[str, str], name: str) -> str | None:
        return next((value for key, value in headers.items() if key.lower() == name), None)


def register_gemini_execution(registry: ProviderExecutionRegistry, transport: GeminiTransport | None = None) -> None:
    registry.register("gemini", "text_generation", GeminiTextExecution(transport))
