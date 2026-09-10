from fastapi import APIRouter, Depends
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.kill_switch import get_state
from app.models import Truck
from app.schemas import HealthOut

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthOut)
def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception:
        db_status = "unavailable"

    truck_count = len(db.execute(select(Truck.id)).all())
    state = get_state(db)

    return HealthOut(
        status="ok" if db_status == "ok" else "degraded",
        database=db_status,
        kill_switch_engaged=state.kill_switch_engaged,
        llm_provider=settings.LLM_PROVIDER,
        truck_count=truck_count,
    )
