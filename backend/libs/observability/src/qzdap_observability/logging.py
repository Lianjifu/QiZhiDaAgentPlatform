"""structlog setup.

JSON logs in non-dev, pretty console in dev. Every log line includes
trace_id, tenant_id, principal_id automatically.
"""

from __future__ import annotations

import logging
import sys

import structlog
from qzdap_kernel.contextvars import current_trace_id
from qzdap_persistence.tenant_guard import current_tenant_id


def _add_trace_id(_: object, __: str, event_dict: dict) -> dict:
    if (tid := current_trace_id()) and "trace_id" not in event_dict:
        event_dict["trace_id"] = tid
    return event_dict


def _add_tenant_id(_: object, __: str, event_dict: dict) -> dict:
    if (tid := current_tenant_id()) and "tenant_id" not in event_dict:
        event_dict["tenant_id"] = str(tid)
    return event_dict


def configure_logging(*, level: str = "INFO", json: bool = True) -> None:
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _add_trace_id,
        _add_tenant_id,
    ]
    if json:
        processors.append(structlog.processors.format_exc_info)
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty()))

    structlog.configure(
        processors=processors,  # type: ignore[arg-type]
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, level)),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Bridge stdlib `logging` → structlog so any `logging.getLogger(__name__).info(...)`
    # call (e.g. background tasks) renders through the same JSON / console pipeline.
    class _StructlogHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            try:
                structlog.get_logger(record.name).log(
                    record.levelno, record.getMessage()
                )
            except (ValueError, TypeError, RuntimeError):
                # Never raise from a logging handler
                pass

    root = logging.getLogger()
    # Replace previous install (test re-runs / hot reload).
    for h in list(root.handlers):
        if isinstance(h, _StructlogHandler):
            root.removeHandler(h)
    root.addHandler(_StructlogHandler(level=getattr(logging, level)))
    root.setLevel(getattr(logging, level))

    # Quiet noisy third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
