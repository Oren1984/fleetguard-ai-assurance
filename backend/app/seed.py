"""Idempotent startup seeding: synthetic fleet + initial risk assessments."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit, synthetic_data
from app.assessment_service import run_assessment_for_all_trucks
from app.logging_config import get_logger
from app.models import Truck

logger = get_logger("fleetguard.seed")


def seed_if_empty(db: Session) -> bool:
    existing = db.execute(select(Truck).limit(1)).scalar_one_or_none()
    if existing is not None:
        logger.info("seed_skipped_existing_data")
        return False

    trucks, readings = synthetic_data.generate_fleet()
    db.add_all(trucks)
    db.flush()
    db.add_all(readings)
    db.commit()

    audit.record(
        db,
        event_type="synthetic_data_loaded",
        actor="system",
        details={"truck_count": len(trucks), "reading_count": len(readings)},
    )

    run_assessment_for_all_trucks(db, actor="system")
    logger.info("seed_completed", extra={"extra_fields": {"truck_count": len(trucks)}})
    return True
