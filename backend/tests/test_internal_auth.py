import hashlib
import hmac
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.services.internal_auth import NonceStore, verify_internal_signature


SECRET = "internal-signing-secret"


def signed_headers(body: bytes, *, timestamp=None, nonce="nonce-1", secret=SECRET):
    timestamp = str(int(time.time()) if timestamp is None else timestamp)
    message = f"{timestamp}\n{nonce}\n".encode() + body
    signature = hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()
    return timestamp, nonce, signature


def test_valid_signature_uses_exact_raw_body():
    body = b'{"b":2,"a":1}'
    timestamp, nonce, signature = signed_headers(body)
    store = NonceStore()

    verify_internal_signature(SECRET, timestamp, nonce, signature, body, store=store)


@pytest.mark.parametrize(
    "timestamp",
    ["not-a-timestamp", str(int(time.time()) - 301), str(int(time.time()) + 10_000)],
)
def test_invalid_timestamp_is_rejected(timestamp):
    body = b"{}"
    timestamp, nonce, signature = signed_headers(body, timestamp=timestamp)

    with pytest.raises(ValueError):
        verify_internal_signature(SECRET, timestamp, nonce, signature, body, store=NonceStore())


def test_bad_signature_and_missing_secret_are_rejected():
    body = b"{}"
    timestamp, nonce, signature = signed_headers(body)

    with pytest.raises(ValueError):
        verify_internal_signature(SECRET, timestamp, nonce, "0" * 64, body, store=NonceStore())
    with pytest.raises(ValueError):
        verify_internal_signature("", timestamp, nonce, signature, body, store=NonceStore())


def test_duplicate_nonce_is_rejected():
    body = b"{}"
    timestamp, nonce, signature = signed_headers(body)
    store = NonceStore()

    verify_internal_signature(SECRET, timestamp, nonce, signature, body, store=store)
    with pytest.raises(ValueError, match="replayed"):
        verify_internal_signature(SECRET, timestamp, nonce, signature, body, store=store)


def test_expired_nonce_is_cleaned_and_capacity_is_bounded():
    store = NonceStore(max_entries=2, ttl_seconds=1)
    assert store.consume_once("a", now=100.0) is True
    assert store.consume_once("b", now=100.0) is True
    assert store.consume_once("a", now=100.5) is False
    assert store.consume_once("c", now=101.1) is True
    assert store.size == 1


def test_concurrent_duplicate_nonce_is_consumed_once():
    body = b"{}"
    timestamp, nonce, signature = signed_headers(body, nonce="concurrent")
    store = NonceStore()

    def attempt():
        try:
            verify_internal_signature(SECRET, timestamp, nonce, signature, body, store=store)
            return True
        except ValueError:
            return False

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(lambda _: attempt(), range(8)))

    assert sum(results) == 1
