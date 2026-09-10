from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AuditLog
from app.schemas import AuditLogOut

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=list[AuditLogOut])
def list_audit_log(
    truck_id: Optional[str] = None,
    event_type: Optional[str] = None,
    limit: int = 200,
    db: Session = Depends(get_db),
):
    query = select(AuditLog).order_by(AuditLog.timestamp.desc()).limit(limit)
    entries = db.execute(query).scalars().all()
    if truck_id:
        entries = [e for e in entries if e.truck_id == truck_id]
    if event_type:
        entries = [e for e in entries if e.event_type == event_type]
    return entries
