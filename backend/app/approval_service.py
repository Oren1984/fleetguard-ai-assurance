"""Human-in-the-loop approval workflow and gated action execution."""
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app import audit
from app.exceptions import ApprovalRequiredError
from app.kill_switch import assert_not_engaged
from app.metrics import action_execution_blocked_total, action_executions_total, pending_approvals
from app.models import ActionExecution, Approval, ApprovalStatus


def decide(db: Session, approval: Approval, decision: str, actor: str, comments: str | None = None) -> Approval:
    decision = decision.lower().strip()
    if decision not in {"approve", "reject"}:
        raise ValueError("decision must be 'approve' or 'reject'")

    approval.status = ApprovalStatus.APPROVED.value if decision == "approve" else ApprovalStatus.REJECTED.value
    approval.decided_at = datetime.now(timezone.utc)
    approval.decided_by = actor
    approval.comments = comments
    db.commit()
    db.refresh(approval)

    pending = db.query(Approval).filter(Approval.status == ApprovalStatus.PENDING.value).count()
    pending_approvals.set(pending)

    audit.record(
        db,
        event_type=f"approval_{approval.status.lower()}",
        actor=actor,
        truck_id=approval.risk_assessment.truck_id,
        details={"approval_id": approval.id, "risk_assessment_id": approval.risk_assessment_id, "comments": comments},
    )
    return approval


def execute_action(db: Session, approval: Approval, actor: str) -> ActionExecution:
    """Executes the recommended action, but ONLY if it has been approved and
    the kill switch is not engaged. This is the enforcement point for the
    "no execution without human approval" guardrail."""
    try:
        assert_not_engaged(db)
    except Exception:
        action_execution_blocked_total.inc()
        audit.record(
            db,
            event_type="execution_blocked_kill_switch",
            actor=actor,
            truck_id=approval.risk_assessment.truck_id,
            details={"approval_id": approval.id},
        )
        raise

    if approval.status != ApprovalStatus.APPROVED.value:
        action_execution_blocked_total.inc()
        audit.record(
            db,
            event_type="execution_blocked_no_approval",
            actor=actor,
            truck_id=approval.risk_assessment.truck_id,
            details={"approval_id": approval.id, "approval_status": approval.status},
        )
        raise ApprovalRequiredError(
            f"Approval {approval.id} is '{approval.status}', not APPROVED. Action cannot be executed."
        )

    execution = ActionExecution(
        approval_id=approval.id,
        executed_by=actor,
        outcome="SUCCESS",
        notes=f"Executed recommended action: {approval.risk_assessment.recommended_action}",
    )
    db.add(execution)
    db.commit()
    db.refresh(execution)

    action_executions_total.labels(outcome="SUCCESS").inc()

    audit.record(
        db,
        event_type="action_executed",
        actor=actor,
        truck_id=approval.risk_assessment.truck_id,
        details={
            "approval_id": approval.id,
            "action": approval.risk_assessment.recommended_action,
            "execution_id": execution.id,
        },
    )
    return execution
