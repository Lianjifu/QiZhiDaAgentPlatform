"""CORS configuration + FastAPI wrapper.

We don't ship a full middleware here — `build_default_middleware_chain`
delegates to FastAPI's built-in `CORSMiddleware` with our config object.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class CORSMiddlewareConfig:
    allow_origins: tuple[str, ...] = ("*",)
    allow_credentials: bool = True
    allow_methods: tuple[str, ...] = (
        "GET",
        "POST",
        "PUT",
        "PATCH",
        "DELETE",
        "OPTIONS",
    )
    allow_headers: tuple[str, ...] = ("*",)


# Alias for symmetry with other middleware
CORSMiddleware = CORSMiddlewareConfig


def build_cors_config(env: dict[str, str]) -> CORSMiddlewareConfig:
    origins_raw = env.get("QZDAP_CORS_ALLOW_ORIGINS", "*").strip()
    origins = tuple(o.strip() for o in origins_raw.split(",") if o.strip())
    return CORSMiddlewareConfig(
        allow_origins=origins or ("*",),
        allow_credentials=env.get("QZDAP_CORS_ALLOW_CREDENTIALS", "true").lower()
        == "true",
        allow_methods=tuple(
            m.strip()
            for m in env.get(
                "QZDAP_CORS_ALLOW_METHODS",
                "GET,POST,PUT,PATCH,DELETE,OPTIONS",
            ).split(",")
            if m.strip()
        ),
        allow_headers=tuple(
            h.strip()
            for h in env.get("QZDAP_CORS_ALLOW_HEADERS", "*").split(",")
            if h.strip()
        ),
    )
