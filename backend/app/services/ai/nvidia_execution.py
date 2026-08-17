import time
from dataclasses import dataclass
from typing import Mapping, Protocol

import httpx

from .provider_executor import ExecutionOutput, ExecutionRequest, ProviderExecutionError, ProviderExecutionRegistry


NVIDIA_CHAT_COMPLETIONS_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
NVIDIA_TIMEOUT_SECONDS = 300.0
MAX_RESPONSE_BYTES = 4 * 1024 * 1024


@dataclass(frozen=True)
class NVIDIAResponse:
    status_code: int
    body: object
    headers: Mapping[str, str] | None = None


class NVIDIATransport(Protocol):
    async def complete(self, *, model: str, api_key: str, body: Mapping[str, object], timeout_seconds: float) -> NVIDIAResponse:
        """Perform one NVIDIA chat-completions request."""


class HttpxNVIDIATransport:
    async def complete(self, *, model: str, api_key: str, body: Mapping[str, object], timeout_seconds: float) -> NVIDIAResponse:
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=False) as client:
                response = await client.post(
                    NVIDIA_CHAT_COMPLETIONS_URL,
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json=body,
                )
        except httpx.TimeoutException:
            raise ProviderExecutionError("timeout", "NVIDIA request timed out") from None
        except httpx.RequestError:
            raise ProviderExecutionError("unavailable", "NVIDIA provider is unavailable") from None
        if len(response.content) > MAX_RESPONSE_BYTES:
            raise ProviderExecutionError("malformed_response", "NVIDIA response exceeded the permitted size")
        try:
            response_body = response.json()
        except ValueError:
            response_body = None
        return NVIDIAResponse(response.status_code, response_body, dict(response.headers))


class NVIDIATextExecution:
    def __init__(self, transport: NVIDIATransport | None = None, timeout_seconds: float = NVIDIA_TIMEOUT_SECONDS):
        self._transport = transport or HttpxNVIDIATransport()
        self._timeout_seconds = timeout_seconds

    async def __call__(self, request: ExecutionRequest) -> ExecutionOutput:
        credential = next((item for item in request.runtime_context.credentials if item.provider_id == "nvidia"), None)
        if credential is None:
            raise ProviderExecutionError("credential_resolution_error", "NVIDIA credential is unavailable")
        messages: list[dict[str, str]] = []
        if request.payload.get("system_prompt"):
            messages.append({"role": "system", "content": str(request.payload["system_prompt"])})
        messages.append({"role": "user", "content": str(request.payload["prompt"])})
        body = {
            "model": request.model_id or "",
            "messages": messages,
            "temperature": request.payload.get("temperature", 0.6),
            "max_tokens": request.payload.get("max_tokens", 8192),
            "stream": False,
        }
        started = time.perf_counter()
        try:
            response = await self._transport.complete(
                model=request.model_id or "",
                api_key=credential.secret.get_secret_value(),
                body=body,
                timeout_seconds=self._timeout_seconds,
            )
        except ProviderExecutionError:
            raise
        except TimeoutError:
            raise ProviderExecutionError("timeout", "NVIDIA request timed out") from None
        except Exception:
            raise ProviderExecutionError("unavailable", "NVIDIA provider is unavailable") from None
        self._raise_for_status(response.status_code)
        text, finish_reason = self._extract_text(response.body)
        if finish_reason == "length":
            raise ProviderExecutionError("truncated_response", "NVIDIA response reached the output limit")
        body_mapping = response.body if isinstance(response.body, dict) else {}
        return ExecutionOutput(
            provider_id="nvidia",
            model_id=request.model_id,
            capability="text_generation",
            text=text,
            finish_reason=finish_reason,
            usage=self._safe_usage(body_mapping.get("usage")),
            provider_request_id=body_mapping.get("id") if isinstance(body_mapping.get("id"), str) else None,
            elapsed_ms=round((time.perf_counter() - started) * 1000, 2),
        )

    @staticmethod
    def _raise_for_status(status_code: int) -> None:
        if 200 <= status_code < 300:
            return
        codes = {
            400: ("invalid_request", "NVIDIA rejected the request"),
            401: ("invalid_credentials", "NVIDIA credentials were rejected"),
            403: ("permission_denied", "NVIDIA denied permission"),
            402: ("quota_exceeded", "NVIDIA quota was exceeded"),
            408: ("timeout", "NVIDIA request timed out"),
            429: ("rate_limited", "NVIDIA rate limit reached"),
        }
        code, message = codes.get(status_code, ("unavailable" if status_code >= 500 else "provider_error", "NVIDIA provider request failed"))
        raise ProviderExecutionError(code, message)

    @staticmethod
    def _extract_text(body: object) -> tuple[str, str | None]:
        if not isinstance(body, dict):
            raise ProviderExecutionError("malformed_response", "NVIDIA returned malformed JSON")
        choices = body.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise ProviderExecutionError("malformed_response", "NVIDIA returned no choices")
        message = choices[0].get("message")
        if not isinstance(message, dict):
            raise ProviderExecutionError("malformed_response", "NVIDIA returned malformed content")
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ProviderExecutionError("empty_response", "NVIDIA returned no text")
        finish_reason = choices[0].get("finish_reason")
        return content.strip(), finish_reason if isinstance(finish_reason, str) else None

    @staticmethod
    def _safe_usage(usage: object) -> Mapping[str, int]:
        if not isinstance(usage, dict):
            return {}
        return {key: value for key, value in usage.items() if isinstance(key, str) and isinstance(value, int)}


def register_nvidia_execution(registry: ProviderExecutionRegistry, transport: NVIDIATransport | None = None) -> None:
    registry.register("nvidia", "text_generation", NVIDIATextExecution(transport))
