"""Parent PIN hashing and verification."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Protocol

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

_hasher = PasswordHasher()


def hash_pin(pin: str) -> str:
    """Hash a numeric parent PIN with Argon2."""
    if not pin.isdigit() or not 4 <= len(pin) <= 12:
        raise ValueError("PIN must contain 4 to 12 digits.")
    return _hasher.hash(pin)


def verify_pin(pin: str, encoded_hash: str) -> bool:
    """Verify a PIN without exposing the stored secret."""
    try:
        return _hasher.verify(encoded_hash, pin)
    except (VerificationError, InvalidHashError):
        # VerificationError covers a wrong PIN *and* other verification failures.
        return False


class AttemptStore(Protocol):
    """Where failed-attempt state is kept so a restart cannot reset the lockout."""

    def get(self, key: str, default: str = "") -> str: ...

    def put(self, key: str, value: str) -> None: ...


class ParentPinVerifier:
    """Apply a lockout after repeated incorrect PIN attempts.

    Pass ``store`` to persist the lockout; otherwise it only lives in memory.
    """

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.time,
        max_attempts: int = 5,
        lockout_seconds: int = 300,
        store: AttemptStore | None = None,
    ) -> None:
        self._clock = clock
        self._max_attempts = max_attempts
        self._lockout_seconds = lockout_seconds
        self._store = store
        self._failures = 0
        self._locked_until = 0.0
        if store is not None:
            try:
                self._failures = int(store.get("pin_failures", "0") or 0)
                self._locked_until = float(store.get("pin_locked_until", "0") or 0)
            except ValueError:
                self._failures, self._locked_until = 0, 0.0

    @property
    def locked_seconds(self) -> int:
        """Return the remaining lockout time, rounded up to whole seconds."""
        return max(0, int(self._locked_until - self._clock() + 0.999))

    def _save(self) -> None:
        if self._store is not None:
            self._store.put("pin_failures", str(self._failures))
            self._store.put("pin_locked_until", repr(self._locked_until))

    def verify(self, pin: str, encoded_hash: str) -> bool:
        """Verify a PIN and lock out after the configured number of failures."""
        if self.locked_seconds:
            return False
        if verify_pin(pin, encoded_hash):
            self._failures = 0
            self._save()
            return True
        self._failures += 1
        if self._failures >= self._max_attempts:
            self._failures = 0
            self._locked_until = self._clock() + self._lockout_seconds
        self._save()
        return False
