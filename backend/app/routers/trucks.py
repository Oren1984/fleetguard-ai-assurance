from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import RiskAssessment, TelemetryReading, Truck
from app.schemas import TelemetryOut, TruckOut

router = APIRouter(prefix="/trucks", tags=["trucks"])


@router.get("", response_model=list[TruckOut])
def list_trucks(db: Session = Depends(get_db)):
    return db.execute(select(Truck).order_by(Truck.id)).scalars().all()


@router.get("/{truck_id}", response_model=TruckOut)
def get_truck(truck_id: str, db: Session = Depends(get_db)):
    truck = db.get(Truck, truck_id)
    if truck is None:
        raise HTTPException(status_code=404, detail=f"Truck {truck_id} not found")
    return truck


@router.get("/{truck_id}/telemetry", response_model=list[TelemetryOut])
def get_truck_telemetry(truck_id: str, limit: int = 50, db: Session = Depends(get_db)):
    truck = db.get(Truck, truck_id)
    if truck is None:
        raise HTTPException(status_code=404, detail=f"Truck {truck_id} not found")
    readings = (
        db.execute(
            select(TelemetryReading)
            .where(TelemetryReading.truck_id == truck_id)
            .order_by(TelemetryReading.timestamp.asc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return readings


@router.get("/{truck_id}/latest-assessment")
def get_latest_assessment(truck_id: str, db: Session = Depends(get_db)):
    truck = db.get(Truck, truck_id)
    if truck is None:
        raise HTTPException(status_code=404, detail=f"Truck {truck_id} not found")
    assessment = (
        db.execute(
            select(RiskAssessment)
            .where(RiskAssessment.truck_id == truck_id)
            .order_by(RiskAssessment.timestamp.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )
    if assessment is None:
        raise HTTPException(status_code=404, detail=f"No risk assessment yet for truck {truck_id}")
    from app.routers.risk import _to_out

    return _to_out(assessment)
