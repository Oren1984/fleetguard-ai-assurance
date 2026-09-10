from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import assessment_service
from app.database import get_db
from app.exceptions import InvalidTelemetryError, KillSwitchEngagedError
from app.models import RiskAssessment, Truck
from app.schemas import RiskAssessmentOut

router = APIRouter(prefix="/risk", tags=["risk"])


def _to_out(a: RiskAssessment) -> RiskAssessmentOut:
    approval = a.approval
    return RiskAssessmentOut(
        id=a.id,
        truck_id=a.truck_id,
        timestamp=a.timestamp,
        risk_score=a.risk_score,
        risk_level=a.risk_level,
        reasons=a.reasons,
        recommended_action=a.recommended_action,
        requires_approval=a.requires_approval,
        sop_sources=a.sop_sources,
        explanation=a.explanation,
        grounded=a.grounded,
        evidence_snapshot=a.evidence_snapshot,
        approval_status=approval.status if approval else None,
        approval_id=approval.id if approval else None,
    )


@router.get("/assessments", response_model=list[RiskAssessmentOut])
def list_assessments(risk_level: Optional[str] = None, latest_only: bool = True, db: Session = Depends(get_db)):
    query = select(RiskAssessment).order_by(RiskAssessment.timestamp.desc())
    assessments = db.execute(query).scalars().all()

    if latest_only:
        seen: set[str] = set()
        deduped = []
        for a in assessments:
            if a.truck_id in seen:
                continue
            seen.add(a.truck_id)
            deduped.append(a)
        assessments = deduped

    if risk_level:
        assessments = [a for a in assessments if a.risk_level == risk_level.upper()]

    return [_to_out(a) for a in assessments]


@router.get("/assessments/{assessment_id}", response_model=RiskAssessmentOut)
def get_assessment(assessment_id: int, db: Session = Depends(get_db)):
    a = db.get(RiskAssessment, assessment_id)
    if a is None:
        raise HTTPException(status_code=404, detail="Risk assessment not found")
    return _to_out(a)


@router.post("/assessments/run/{truck_id}", response_model=RiskAssessmentOut)
def run_assessment(truck_id: str, db: Session = Depends(get_db)):
    truck = db.get(Truck, truck_id)
    if truck is None:
        raise HTTPException(status_code=404, detail=f"Truck {truck_id} not found")
    try:
        assessment = assessment_service.run_assessment(db, truck, actor="api")
    except KillSwitchEngagedError as exc:
        raise HTTPException(status_code=423, detail=str(exc)) from exc
    except InvalidTelemetryError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _to_out(assessment)


@router.post("/assessments/run-all", response_model=list[RiskAssessmentOut])
def run_all(db: Session = Depends(get_db)):
    try:
        results = assessment_service.run_assessment_for_all_trucks(db, actor="api")
    except KillSwitchEngagedError as exc:
        raise HTTPException(status_code=423, detail=str(exc)) from exc
    return [_to_out(a) for a in results]
