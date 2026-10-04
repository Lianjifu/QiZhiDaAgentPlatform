"""DomainEvent base class.

The kernel package owns this primitive because every aggregate, in every
module, raises events that descend from it. Keeping it here means the
domain layer never has to import `qzdap_messaging` (an infrastructure
adapter) just to declare an event.
"""

from __future__ import annotations


class DomainEvent:
    """Marker class for domain events. Concrete events subclass this.

    Conventions:
      - name = past tense (``OrderPlaced``, ``MemoryRevoked``)
      - include ``tenant_id``; the envelope adds it on dispatch, so
        duplicating it on the event itself is optional
    """

    @property
    def event_name(self) -> str:
        return type(self).__name__
