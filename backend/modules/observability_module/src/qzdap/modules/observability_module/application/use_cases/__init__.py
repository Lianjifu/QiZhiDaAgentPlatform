"""Observability use cases.

Each module exposes ``build(service: ObservabilityService) -> Callable``
that returns the executable closure.  ``services.ObservabilityService``
caches the closures on init.

Use cases are pure orchestration: validate the command, call repo(s),
return the entity / list.  They never touch HTTP concerns.
"""
