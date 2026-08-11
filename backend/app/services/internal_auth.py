import hashlib
import hmac
import threading
import time


class NonceStore:
    def __init__(self, *, max_entries: int = 100_000, ttl_seconds: int = 300):
        self.max_entries = max_entries
        self.ttl_seconds = ttl_seconds
        self._entries: dict[str, float] = {}
        self._lock = threading.Lock()

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._entries)

    def consume_once(self, nonce: str, *, now: float | None = None) -> bool:
        current = time.time() if now is None else now
        with self._lock:
            self._remove_expired(current)
            if nonce in self._entries:
                return False
            if len(self._entries) >= self.max_entries:
                return False
            self._entries[nonce] = current + self.ttl_seconds
            return True

    def _remove_expired(self, now: float) -> None:
        expired = [nonce for nonce, expiry in self._entries.items() if expiry <= now]
        for nonce in expired:
            self._entries.pop(nonce, None)


def verify_internal_signature(
    secret: str,
    timestamp: str,
    nonce: str,
    signature: str,
    raw_body: bytes,
    *,
    store: NonceStore,
    now: float | None = None,
    max_age_seconds: int = 300,
) -> None:
    if not isinstance(secret, str) or not secret.strip():
        raise ValueError("signing secret is unavailable")
    if not isinstance(timestamp, str) or len(timestamp) > 20:
        raise ValueError("timestamp is invalid")
    if not isinstance(nonce, str) or not nonce or len(nonce) > 256:
        raise ValueError("nonce is invalid")
    if not isinstance(signature, str) or len(signature) != 64:
        raise ValueError("signature is invalid")
    try:
        timestamp_value = int(timestamp)
    except (TypeError, ValueError):
        raise ValueError("timestamp is invalid") from None

    current = time.time() if now is None else now
    if abs(current - timestamp_value) > max_age_seconds:
        raise ValueError("timestamp is outside the validity window")

    message = f"{timestamp}\n{nonce}\n".encode("utf-8") + raw_body
    expected = hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise ValueError("signature is invalid")
    if not store.consume_once(nonce, now=current):
        raise ValueError("request replayed")
