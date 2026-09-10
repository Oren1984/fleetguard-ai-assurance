"""Audit trail helper. Every consequential system action must be recorded
through this module so the audit log is the single, reliable source of truth."""
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.logging_config import get_logger
from app.models import AuditLog

logger = get_logger("fleetguard.audit")


def record(
    db: Session,
    *,
    event_type: str,
    actor: str,
    truck_id: Optional[str] = None,
    details: Optional[dict[str, Any]] = None,
    commit: bool = True,
) -> AuditLog:
    entry = AuditLog(
        event_type=event_type,
        actor=actor,
        truck_id=truck_id,
        details=details or {},
    )
    db.add(entry)
    if commit:
        db.commit()
        db.refresh(entry)
    else:
        db.flush()

    logger.info(
        "audit_event",
        extra={"extra_fields": {"event_type": event_type, "actor": actor, "truck_id": truck_id, **(details or {})}},
    )
    return entry
