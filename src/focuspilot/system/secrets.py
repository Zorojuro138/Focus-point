"""Windows user-bound encryption for API credentials stored in app settings."""

from __future__ import annotations

import base64
import sys


def protect_secret(value: str) -> str:
    """Encrypt a credential so only the signed-in Windows account can decrypt it."""
    if sys.platform != "win32":
        raise RuntimeError("Credential protection is available only on Windows.")
    import win32crypt

    encrypted: bytes = win32crypt.CryptProtectData(
        value.encode("utf-8"), "FocusPilot Gemini API key", None, None, None, 0
    )
    return base64.b64encode(encrypted).decode("ascii")


def unprotect_secret(value: str) -> str:
    """Decrypt a credential previously protected for this Windows account."""
    if sys.platform != "win32":
        raise RuntimeError("Credential protection is available only on Windows.")
    import win32crypt

    encrypted = base64.b64decode(value, validate=True)
    _, decrypted = win32crypt.CryptUnprotectData(encrypted, None, None, None, 0)
    plaintext: bytes = decrypted
    return plaintext.decode("utf-8")
