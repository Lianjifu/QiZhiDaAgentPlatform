"""Per-package conftest for messaging integration tests.

Bridges ``tests/shared/fixtures.py`` (session-scoped Redis
testcontainers) into the libs/messaging test namespace so integration
tests can opt in via plain ``redis_client`` fixture parameters.
"""

from __future__ import annotations

from shared.fixtures import (  # noqa: F401
    redis_client,
    redis_url,
)
