"""
Purpose of this file.
Encrypts and decrypts OAuth tokens.
Responsibility of this file.
Ensuring access_token/refresh_token values are never stored or logged in plaintext.
"""

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings


class TokenEncryptionError(Exception):
    """Raised when a token cannot be encrypted or decrypted."""


def _get_fernet() -> Fernet:
    settings = get_settings()
    return Fernet(settings.token_encryption_key.encode())


def encrypt_token(plaintext_token: str) -> str:
    if not plaintext_token:
        raise TokenEncryptionError("Cannot encrypt an empty token")
    fernet = _get_fernet()
    return fernet.encrypt(plaintext_token.encode()).decode()


def decrypt_token(encrypted_token: str) -> str:
    if not encrypted_token:
        raise TokenEncryptionError("Cannot decrypt an empty token")
    fernet = _get_fernet()
    try:
        return fernet.decrypt(encrypted_token.encode()).decode()
    except InvalidToken as exc:
        raise TokenEncryptionError(
            "Token could not be decrypted - it may be corrupted or encrypted with a different key"
        ) from exc
