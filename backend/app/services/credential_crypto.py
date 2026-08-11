import base64
import binascii
import os
import re
from collections.abc import Mapping

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


_ENVELOPE_PREFIX = "cc-aes-gcm"
_FORMAT_VERSION = "v1"
_NONCE_BYTES = 12
_KEY_BYTES = 32
_KEY_VERSION_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")


class CredentialCryptoError(ValueError):
    """Safe error for credential encryption configuration or ciphertext."""


class MissingEncryptionKeyError(CredentialCryptoError):
    pass


def _validate_key_version(key_version: str) -> str:
    if not key_version or not _KEY_VERSION_PATTERN.fullmatch(key_version):
        raise CredentialCryptoError("invalid encryption key version")
    return key_version


def _decode_base64(value: str) -> bytes:
    try:
        padding = "=" * (-len(value) % 4)
        return base64.b64decode(value + padding, altchars=b"-_", validate=True)
    except (binascii.Error, ValueError, TypeError) as exc:
        raise CredentialCryptoError("invalid encrypted credential encoding") from exc


def _encode_base64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _associated_data(provider_id: str) -> bytes:
    if not provider_id or ":" in provider_id or "\n" in provider_id:
        raise CredentialCryptoError("invalid provider identifier")
    return f"clipcraft-credential-v1\n{provider_id}".encode("utf-8")


class CredentialEncryption:
    def __init__(self, active_key: bytes, active_key_version: str = "v1", previous_keys: Mapping[str, bytes] | None = None):
        if len(active_key) != _KEY_BYTES:
            raise CredentialCryptoError("encryption key must be exactly 32 bytes")
        active_key_version = _validate_key_version(active_key_version)
        keys = {active_key_version: active_key}
        for version, key in (previous_keys or {}).items():
            if len(key) != _KEY_BYTES:
                raise CredentialCryptoError("encryption key must be exactly 32 bytes")
            keys[_validate_key_version(version)] = key
        self._active_key = active_key
        self._active_key_version = active_key_version
        self._keys = keys

    @classmethod
    def from_base64(
        cls,
        encoded_key: str,
        *,
        key_version: str = "v1",
        previous_keys: Mapping[str, bytes] | None = None,
    ) -> "CredentialEncryption":
        if not encoded_key:
            raise MissingEncryptionKeyError("credential encryption key is not configured")
        decoded = _decode_base64(encoded_key)
        return cls(decoded, active_key_version=key_version, previous_keys=previous_keys)

    @classmethod
    def from_environment(cls, env: Mapping[str, str] | None = None) -> "CredentialEncryption":
        values = env or os.environ
        encoded_key = values.get("AI_CREDENTIAL_ENCRYPTION_KEY")
        key_version = values.get("AI_CREDENTIAL_ENCRYPTION_KEY_VERSION", "v1")
        if not encoded_key:
            raise MissingEncryptionKeyError("credential encryption key is not configured")
        return cls.from_base64(encoded_key, key_version=key_version)

    def encrypt(self, plaintext: str, provider_id: str) -> str:
        if not isinstance(plaintext, str):
            raise CredentialCryptoError("credential plaintext must be text")
        nonce = os.urandom(_NONCE_BYTES)
        ciphertext = AESGCM(self._active_key).encrypt(nonce, plaintext.encode("utf-8"), _associated_data(provider_id))
        return ":".join(
            (_ENVELOPE_PREFIX, _FORMAT_VERSION, self._active_key_version, _encode_base64(nonce), _encode_base64(ciphertext))
        )

    def decrypt(self, envelope: str, provider_id: str) -> str:
        try:
            parts = envelope.split(":")
            if len(parts) != 5 or parts[0] != _ENVELOPE_PREFIX or parts[1] != _FORMAT_VERSION:
                raise CredentialCryptoError("invalid encrypted credential envelope")
            key = self._keys.get(parts[2])
            if key is None:
                raise CredentialCryptoError("unknown encryption key version")
            nonce = _decode_base64(parts[3])
            ciphertext = _decode_base64(parts[4])
            if len(nonce) != _NONCE_BYTES or len(ciphertext) < 16:
                raise CredentialCryptoError("invalid encrypted credential envelope")
            plaintext = AESGCM(key).decrypt(nonce, ciphertext, _associated_data(provider_id))
            return plaintext.decode("utf-8")
        except CredentialCryptoError:
            raise
        except (InvalidTag, UnicodeDecodeError, TypeError, ValueError) as exc:
            raise CredentialCryptoError("credential could not be decrypted") from exc
