"""API-key hashing with argon2id.

Storage format: `argon2id$v=19$m=...,t=...,p=...$<salt>$<hash>` — a single
self-describing string. Verification uses constant-time comparison.
"""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

DEFAULT_HASH_ROUNDS = 12


class ApiKeyHasher:
    def __init__(
        self, time_cost: int = 3, memory_cost: int = 64 * 1024, parallelism: int = 4
    ) -> None:
        self._ph = PasswordHasher(
            time_cost=time_cost,
            memory_cost=memory_cost,
            parallelism=parallelism,
        )

    def hash(self, raw: str) -> str:
        return self._ph.hash(raw)

    def verify(self, raw: str, hashed: str) -> bool:
        try:
            return self._ph.verify(hashed, raw)
        except VerifyMismatchError:
            return False
        except Exception:  # noqa: BLE001 — bad hashes fail closed
            return False


_default = ApiKeyHasher()


def hash_api_key(raw: str) -> str:
    return _default.hash(raw)


def verify_api_key(raw: str, hashed: str) -> bool:
    return _default.verify(raw, hashed)
