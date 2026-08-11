import time
from dataclasses import dataclass
from typing import Any, Mapping, Protocol

import httpx

from .provider_executor import ExecutionOutput, ExecutionRequest, ProviderExecutionError, ProviderExecutionRegistry

CLOUDFLARE_API_BASE = "https://api.cloudflare.com/client/v4/accounts"
CLOUDFLARE_TIMEOUT_SECONDS = 60.0
MAX_RESPONSE_BYTES = 4 * 1024 * 1024


def _raise_for_status(status_code: int) -> None:
    if 200 <= status_code < 300:
        return
    codes = {
        400: ("invalid_request", "Cloudflare rejected the request"),
        401: ("invalid_credentials", "Cloudflare credentials were rejected"),
        403: ("permission_denied", "Cloudflare denied permission"),
        408: ("timeout", "Cloudflare request timed out"),
        402: ("quota_exceeded", "Cloudflare quota was exceeded"),
        429: ("rate_limited", "Cloudflare rate limit reached"),
    }
    code, message = codes.get(status_code, ("unavailable" if status_code >= 500 else "provider_error", "Cloudflare provider request failed"))
    raise ProviderExecutionError(code, message)


@dataclass(frozen=True)
class CloudflareResponse:
    status_code: int
    body: object
    headers: Mapping[str, str] = None


class CloudflareTransport(Protocol):
    async def run(self, *, model: str, account_id: str, api_key: str, body: Mapping[str, object], timeout_seconds: float) -> CloudflareResponse:
        """Perform one Cloudflare Workers AI request."""


class HttpxCloudflareTransport:
    async def run(self, *, model: str, account_id: str, api_key: str, body: Mapping[str, object], timeout_seconds: float) -> CloudflareResponse:
        url = f"{CLOUDFLARE_API_BASE}/{account_id}/ai/run/{model}"
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=False) as client:
                response = await client.post(
                    url,
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json=body,
                )
        except httpx.TimeoutException as exc:
            raise ProviderExecutionError("timeout", "Cloudflare request timed out") from None
        except httpx.RequestError as exc:
            raise ProviderExecutionError("unavailable", "Cloudflare provider is unavailable") from None
        if len(response.content) > MAX_RESPONSE_BYTES:
            raise ProviderExecutionError("malformed_response", "Cloudflare response exceeded the permitted size")
        try:
            response_body = response.json()
        except ValueError:
            response_body = None
        return CloudflareResponse(response.status_code, response_body, dict(response.headers))


def _extract_choices_content(resource: object) -> str:
    """Fallback for Cloudflare responses that place the text under OpenAI-style
    choices[].message.content (with the legacy `response` field null or non-string)."""
    choices = resource.get("choices") if isinstance(resource, dict) else None
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, dict):
        return ""
    message = first.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            return content
    text = first.get("text")
    if isinstance(text, str) and text.strip():
        return text
    return ""


class CloudflareTextExecution:
    def __init__(self, transport: CloudflareTransport | None = None, timeout_seconds: float = CLOUDFLARE_TIMEOUT_SECONDS):
        self._transport = transport or HttpxCloudflareTransport()
        self._timeout_seconds = timeout_seconds

    async def __call__(self, request: ExecutionRequest) -> ExecutionOutput:
        credential = next((item for item in request.runtime_context.credentials if item.provider_id == "cloudflare"), None)
        if credential is None:
            raise ProviderExecutionError("credential_resolution_error", "Cloudflare credential is unavailable")
        account_id = credential.account_id
        if not account_id:
            raise ProviderExecutionError("credential_resolution_error", "Cloudflare credential metadata is incomplete")
        payload = request.payload
        messages: list[dict[str, str]] = []
        if payload.get("system_prompt"):
            messages.append({"role": "system", "content": payload["system_prompt"]})
        messages.append({"role": "user", "content": payload["prompt"]})
        body = {
            "messages": messages,
            "max_tokens": payload.get("max_tokens", 8192),
            "temperature": payload.get("temperature", 0.6),
        }
        started = time.perf_counter()
        try:
            response = await self._transport.run(
                model=request.model_id or "",
                account_id=account_id,
                api_key=credential.secret.get_secret_value(),
                body=body,
                timeout_seconds=self._timeout_seconds,
            )
        except ProviderExecutionError:
            raise
        except TimeoutError:
            raise ProviderExecutionError("timeout", "Cloudflare request timed out") from None
        except Exception:
            raise ProviderExecutionError("unavailable", "Cloudflare provider is unavailable") from None
        _raise_for_status(response.status_code)
        text = self._extract_text(response.body)
        return ExecutionOutput(
            provider_id="cloudflare",
            model_id=request.model_id,
            capability="text_generation",
            text=text,
            elapsed_ms=round((time.perf_counter() - started) * 1000, 2),
        )

    @staticmethod
    def _extract_text(body: object) -> str:
        if not isinstance(body, dict):
            raise ProviderExecutionError("malformed_response", "Cloudflare returned malformed JSON")
        if not body.get("success"):
            raise ProviderExecutionError("provider_error", "Cloudflare returned an error")
        result = body.get("result")
        if not isinstance(result, dict):
            raise ProviderExecutionError("malformed_response", "Cloudflare returned malformed result")
        text = result.get("response")
        if not isinstance(text, str) or not text.strip():
            text = _extract_choices_content(result)
        if not isinstance(text, str) or not text.strip():
            raise ProviderExecutionError("empty_response", "Cloudflare returned no text")
        return text.strip()


class CloudflareImageExecution:
    def __init__(self, transport: CloudflareTransport | None = None, timeout_seconds: float = CLOUDFLARE_TIMEOUT_SECONDS):
        self._transport = transport or HttpxCloudflareTransport()
        self._timeout_seconds = timeout_seconds

    async def __call__(self, request: ExecutionRequest) -> ExecutionOutput:
        credential = next((item for item in request.runtime_context.credentials if item.provider_id == "cloudflare"), None)
        if credential is None:
            raise ProviderExecutionError("credential_resolution_error", "Cloudflare credential is unavailable")
        account_id = credential.account_id
        if not account_id:
            raise ProviderExecutionError("credential_resolution_error", "Cloudflare credential metadata is incomplete")
        payload = request.payload
        body = {"prompt": payload["prompt"]}
        started = time.perf_counter()
        try:
            response = await self._transport.run(
                model=request.model_id or "",
                account_id=account_id,
                api_key=credential.secret.get_secret_value(),
                body=body,
                timeout_seconds=self._timeout_seconds,
            )
        except ProviderExecutionError:
            raise
        except TimeoutError:
            raise ProviderExecutionError("timeout", "Cloudflare request timed out") from None
        except Exception:
            raise ProviderExecutionError("unavailable", "Cloudflare provider is unavailable") from None
        _raise_for_status(response.status_code)
        image = self._extract_image(response.body)
        return ExecutionOutput(
            provider_id="cloudflare",
            model_id=request.model_id,
            capability="image_generation",
            text=image,
            elapsed_ms=round((time.perf_counter() - started) * 1000, 2),
        )

    @staticmethod
    def _extract_image(body: object) -> str:
        if not isinstance(body, dict):
            raise ProviderExecutionError("malformed_response", "Cloudflare returned malformed JSON")
        if not body.get("success"):
            raise ProviderExecutionError("provider_error", "Cloudflare returned an error")
        result = body.get("result")
        if not isinstance(result, dict):
            raise ProviderExecutionError("malformed_response", "Cloudflare returned malformed result")
        image = result.get("image")
        if not isinstance(image, str) or not image.strip():
            raise ProviderExecutionError("empty_response", "Cloudflare returned no image")
        return image.strip()


def register_cloudflare_executions(registry: ProviderExecutionRegistry, transport: CloudflareTransport | None = None) -> None:
    registry.register("cloudflare", "text_generation", CloudflareTextExecution(transport))
    registry.register("cloudflare", "image_generation", CloudflareImageExecution(transport))
