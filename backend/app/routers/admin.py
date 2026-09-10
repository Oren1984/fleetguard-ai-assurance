from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import audit, kill_switch
from app.database import get_db
from app.schemas import KillSwitchIn, KillSwitchOut

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/kill-switch", response_model=KillSwitchOut)
def get_kill_switch(db: Session = Depends(get_db)):
    state = kill_switch.get_state(db)
    return KillSwitchOut(
        kill_switch_engaged=state.kill_switch_engaged, updated_at=state.updated_at, updated_by=state.updated_by
    )


@router.post("/kill-switch", response_model=KillSwitchOut)
def set_kill_switch(payload: KillSwitchIn, db: Session = Depends(get_db)):
    state = kill_switch.set_engaged(db, payload.engaged, payload.actor)

    from app.metrics import kill_switch_status

    kill_switch_status.set(1 if state.kill_switch_engaged else 0)

    audit.record(
        db,
        event_type="kill_switch_engaged" if payload.engaged else "kill_switch_disengaged",
        actor=payload.actor,
        details={"reason": payload.reason},
    )
    return KillSwitchOut(
        kill_switch_engaged=state.kill_switch_engaged, updated_at=state.updated_at, updated_by=state.updated_by
    )
