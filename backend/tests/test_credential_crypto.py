import base64
import os

import pytest

from app.services.credential_crypto import (
    CredentialCryptoError,
    CredentialEncryption,
    MissingEncryptionKeyError,
)


def encoded_key(length=32):
    return base64.b64encode(os.urandom(length)).decode("ascii")


def test_encrypt_decrypt_round_trip_and_provider_bound_associated_data():
    crypto = CredentialEncryption.from_base64(encoded_key())
    envelope = crypto.encrypt("secret-value", "gemini")

    assert crypto.decrypt(envelope, "gemini") == "secret-value"
    with pytest.raises(CredentialCryptoError):
        crypto.decrypt(envelope, "cloudflare")


def test_identical_plaintext_produces_different_ciphertext():
    crypto = CredentialEncryption.from_base64(encoded_key())

    first = crypto.encrypt("same-secret", "gemini")
    second = crypto.encrypt("same-secret", "gemini")

    assert first != second


def test_tampering_wrong_key_and_malformed_envelope_fail_closed():
    crypto = CredentialEncryption.from_base64(encoded_key())
    envelope = crypto.encrypt("secret-value", "gemini")
    parts = envelope.split(":")
    ciphertext = bytearray(base64.urlsafe_b64decode(parts[-1] + "=" * (-len(parts[-1]) % 4)))
    ciphertext[0] ^= 1
    parts[-1] = base64.urlsafe_b64encode(ciphertext).rstrip(b"=").decode("ascii")

    with pytest.raises(CredentialCryptoError):
        crypto.decrypt(":".join(parts), "gemini")
    with pytest.raises(CredentialCryptoError):
        CredentialEncryption.from_base64(encoded_key()).decrypt(envelope, "gemini")
    with pytest.raises(CredentialCryptoError):
        crypto.decrypt("cc-aes-gcm:v1:not-enough-parts", "gemini")


def test_key_version_support_uses_the_matching_key():
    old_key = encoded_key()
    new_key = encoded_key()
    old_crypto = CredentialEncryption.from_base64(old_key, key_version="v1")
    rotated_crypto = CredentialEncryption.from_base64(
        new_key,
        key_version="v2",
        previous_keys={"v1": base64.b64decode(old_key)},
    )
    envelope = old_crypto.encrypt("rotatable-secret", "gemini")

    assert rotated_crypto.decrypt(envelope, "gemini") == "rotatable-secret"


def test_missing_and_invalid_environment_keys_fail_without_generation(monkeypatch):
    monkeypatch.delenv("AI_CREDENTIAL_ENCRYPTION_KEY", raising=False)
    with pytest.raises(MissingEncryptionKeyError):
        CredentialEncryption.from_environment()

    monkeypatch.setenv("AI_CREDENTIAL_ENCRYPTION_KEY", encoded_key(31))
    with pytest.raises(CredentialCryptoError):
        CredentialEncryption.from_environment()

    monkeypatch.setenv("AI_CREDENTIAL_ENCRYPTION_KEY", "not-base64!!!")
    with pytest.raises(CredentialCryptoError):
        CredentialEncryption.from_environment()


def test_secret_never_appears_in_envelope_or_crypto_errors():
    secret = "unique-secret-value-123"
    crypto = CredentialEncryption.from_base64(encoded_key())
    envelope = crypto.encrypt(secret, "gemini")

    assert secret not in envelope
    try:
        crypto.decrypt("malformed", "gemini")
    except CredentialCryptoError as error:
        assert secret not in str(error)
