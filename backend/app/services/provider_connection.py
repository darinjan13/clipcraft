import httpx

from .ai.provider_registry import NVIDIA_TEXT_MODEL


TEST_TIMEOUT_SECONDS = 5.0


class ProviderTestResult:
    def __init__(self, status: str, message: str):
        self.status = status
        self.message = message


def _classify_response(response: httpx.Response) -> ProviderTestResult:
    if 200 <= response.status_code < 300:
        return ProviderTestResult("connected", "provider credential accepted")
    if response.status_code in (401, 403):
        return ProviderTestResult("invalid_credentials", "provider rejected credentials")
    if response.status_code == 402:
        return ProviderTestResult("quota_exceeded", "provider quota is unavailable")
    if response.status_code == 429:
        return ProviderTestResult("rate_limited", "provider rate limit reached")
    if response.status_code == 408:
        return ProviderTestResult("timeout", "provider request timed out")
    if response.status_code >= 500:
        return ProviderTestResult("provider_error", "provider returned an upstream error")
    return ProviderTestResult("provider_error", "provider rejected the connection test")


def _request(method: str, url: str, **kwargs) -> ProviderTestResult:
    try:
        response = httpx.request(method, url, timeout=TEST_TIMEOUT_SECONDS, **kwargs)
    except httpx.TimeoutException:
        return ProviderTestResult("timeout", "provider request timed out")
    except httpx.RequestError:
        return ProviderTestResult("unavailable", "provider is unavailable")
    return _classify_response(response)


def test_gemini(secret: str) -> ProviderTestResult:
    return _request(
        "GET",
        "https://generativelanguage.googleapis.com/v1beta/models",
        headers={"x-goog-api-key": secret},
    )


def test_cloudflare(secret: str, metadata: dict[str, object] | None) -> ProviderTestResult:
    account_id = (metadata or {}).get("account_id")
    if not isinstance(account_id, str) or not account_id.strip():
        return ProviderTestResult("configuration_error", "Cloudflare account ID is required")
    return _request(
        "GET",
        f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/models/search?search=llama",
        headers={"Authorization": f"Bearer {secret}"},
    )


def test_pexels(secret: str) -> ProviderTestResult:
    return _request(
        "GET",
        "https://api.pexels.com/v1/curated?per_page=1",
        headers={"Authorization": secret},
    )


def test_nvidia(secret: str) -> ProviderTestResult:
    return _request(
        "POST",
        "https://integrate.api.nvidia.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {secret}", "Content-Type": "application/json"},
        json={
            "model": NVIDIA_TEXT_MODEL,
            "messages": [{"role": "user", "content": "Reply OK."}],
            "temperature": 0,
            "max_tokens": 4,
            "stream": False,
        },
    )


def run_provider_test(provider_id: str, secret: str, metadata: dict[str, object] | None) -> ProviderTestResult:
    if provider_id == "gemini":
        return test_gemini(secret)
    if provider_id == "cloudflare":
        return test_cloudflare(secret, metadata)
    if provider_id == "pexels":
        return test_pexels(secret)
    if provider_id == "nvidia":
        return test_nvidia(secret)
    return ProviderTestResult("not_implemented", "provider connection testing is not implemented")
