from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import approval_service
from app.database import get_db
from app.exceptions import ApprovalRequiredError, KillSwitchEngagedError
from app.models import Approval
from app.schemas import ActionExecutionOut, ApprovalDecisionIn, ApprovalOut

router = APIRouter(prefix="/approvals", tags=["approvals"])


@router.get("", response_model=list[ApprovalOut])
def list_approvals(status: Optional[str] = None, db: Session = Depends(get_db)):
    query = select(Approval).order_by(Approval.requested_at.desc())
    approvals = db.execute(query).scalars().all()
    if status:
        approvals = [a for a in approvals if a.status == status.upper()]
    return approvals


@router.get("/{approval_id}", response_model=ApprovalOut)
def get_approval(approval_id: int, db: Session = Depends(get_db)):
    approval = db.get(Approval, approval_id)
    if approval is None:
        raise HTTPException(status_code=404, detail="Approval not found")
    return approval


@router.post("/{approval_id}/decision", response_model=ApprovalOut)
def decide_approval(approval_id: int, decision: ApprovalDecisionIn, db: Session = Depends(get_db)):
    approval = db.get(Approval, approval_id)
    if approval is None:
        raise HTTPException(status_code=404, detail="Approval not found")
    if approval.status != "PENDING":
        raise HTTPException(status_code=409, detail=f"Approval {approval_id} already {approval.status}")
    try:
        return approval_service.decide(db, approval, decision.decision, decision.actor, decision.comments)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/{approval_id}/execute", response_model=ActionExecutionOut)
def execute_approval(approval_id: int, actor: str = "operator", db: Session = Depends(get_db)):
    approval = db.get(Approval, approval_id)
    if approval is None:
        raise HTTPException(status_code=404, detail="Approval not found")
    try:
        return approval_service.execute_action(db, approval, actor)
    except KillSwitchEngagedError as exc:
        raise HTTPException(status_code=423, detail=str(exc)) from exc
    except ApprovalRequiredError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
