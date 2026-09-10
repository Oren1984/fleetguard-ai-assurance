"""Orchestrates a full risk assessment: score -> retrieve SOP -> explain ->
persist -> (maybe) open an approval -> audit. This is the one place that
ties the individual assurance-critical steps together."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit, risk_engine
from app.exceptions import InvalidTelemetryError
from app.facilities import facility_for_region
from app.kill_switch import assert_not_engaged
from app.llm_provider import generate_explanation
from app.metrics import active_high_risk_trucks, pending_approvals, risk_assessments_total, risk_scoring_duration_seconds
from app.models import Approval, ApprovalStatus, RecommendedAction, RiskAssessment, RiskLevel, TelemetryReading, Truck
from app.rag import build_query, get_index

MAX_HISTORY = 8


def run_assessment(db: Session, truck: Truck, actor: str = "system") -> RiskAssessment:
    """Runs one full assessment for a truck's latest telemetry reading.
    Raises KillSwitchEngagedError if the kill switch is engaged, and
    InvalidTelemetryError if the latest reading cannot be scored."""
    assert_not_engaged(db)

    readings = (
        db.execute(
            select(TelemetryReading)
            .where(TelemetryReading.truck_id == truck.id)
            .order_by(TelemetryReading.timestamp.desc())
            .limit(MAX_HISTORY)
        )
        .scalars()
        .all()
    )
    if not readings:
        raise InvalidTelemetryError(f"No telemetry available for truck {truck.id}")

    latest = readings[0]
    history = list(reversed(readings))  # oldest -> newest

    with risk_scoring_duration_seconds.time():
        result = risk_engine.assess(truck.temp_setpoint_c, latest, history)

    sop_matches = []
    try:
        query = build_query(result.evidence_snapshot, result.reasons, result.risk_level)
        sop_matches = get_index().search(query, top_k=3)
    except Exception:
        sop_matches = []

    if result.recommended_action == RecommendedAction.DIVERT_TO_FACILITY.value:
        facility = facility_for_region(truck.region)
        if facility:
            result.evidence_snapshot["recommended_facility"] = {
                "id": facility.id,
                "name": facility.name,
                "region": facility.region,
            }

    explanation = generate_explanation(
        truck.id, result.risk_level, result.recommended_action, result.evidence_snapshot, result.reasons, sop_matches
    )

    assessment = RiskAssessment(
        truck_id=truck.id,
        risk_score=result.risk_score,
        risk_level=result.risk_level,
        reasons=result.reasons,
        recommended_action=result.recommended_action,
        requires_approval=result.requires_approval,
        sop_sources=[{"doc": m.doc, "section": m.section, "similarity": m.similarity, "excerpt": m.excerpt} for m in sop_matches],
        explanation=explanation.text,
        grounded=explanation.grounded,
        evidence_snapshot=result.evidence_snapshot,
    )
    db.add(assessment)
    db.flush()

    if result.requires_approval:
        db.add(Approval(risk_assessment_id=assessment.id, status=ApprovalStatus.PENDING.value))

    db.commit()
    db.refresh(assessment)

    risk_assessments_total.labels(risk_level=assessment.risk_level).inc()
    _refresh_gauges(db)

    audit.record(
        db,
        event_type="risk_assessment_generated",
        actor=actor,
        truck_id=truck.id,
        details={
            "risk_assessment_id": assessment.id,
            "risk_score": assessment.risk_score,
            "risk_level": assessment.risk_level,
            "recommended_action": assessment.recommended_action,
            "requires_approval": assessment.requires_approval,
            "grounded": assessment.grounded,
        },
    )

    return assessment


def _refresh_gauges(db: Session) -> None:
    high_risk = db.execute(
        select(RiskAssessment).where(RiskAssessment.risk_level == RiskLevel.HIGH.value)
    ).scalars().all()
    active_high_risk_trucks.set(len({a.truck_id for a in high_risk}))

    pending = db.execute(select(Approval).where(Approval.status == ApprovalStatus.PENDING.value)).scalars().all()
    pending_approvals.set(len(pending))


def run_assessment_for_all_trucks(db: Session, actor: str = "system") -> list[RiskAssessment]:
    trucks = db.execute(select(Truck)).scalars().all()
    results = []
    for truck in trucks:
        try:
            results.append(run_assessment(db, truck, actor=actor))
        except InvalidTelemetryError:
            continue
    return results
