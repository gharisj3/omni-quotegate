from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditEvent


def write_audit_event(
    db: Session,
    *,
    entity_type: str,
    entity_id: int,
    event_type: str,
    actor: str,
    message: str,
    payload: dict[str, Any],
) -> AuditEvent:
    event = AuditEvent(
        entity_type=entity_type,
        entity_id=entity_id,
        event_type=event_type,
        actor=actor,
        message=message,
        payload_json=json.dumps(payload, default=str),
    )
    db.add(event)
    db.flush()
    return event
