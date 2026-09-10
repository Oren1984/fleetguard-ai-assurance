"""Global kill switch: a single-row table that, when engaged, halts every
agent action (risk assessment generation and action execution)."""
from sqlalchemy.orm import Session

from app.exceptions import KillSwitchEngagedError
from app.models import SystemState


def get_state(db: Session) -> SystemState:
    state = db.get(SystemState, 1)
    if state is None:
        state = SystemState(id=1, kill_switch_engaged=False)
        db.add(state)
        db.commit()
        db.refresh(state)
    return state


def is_engaged(db: Session) -> bool:
    return get_state(db).kill_switch_engaged


def assert_not_engaged(db: Session) -> None:
    if is_engaged(db):
        raise KillSwitchEngagedError(
            "The FleetGuard kill switch is engaged. All agent operations are halted."
        )


def set_engaged(db: Session, engaged: bool, actor: str) -> SystemState:
    from datetime import datetime, timezone

    state = get_state(db)
    state.kill_switch_engaged = engaged
    state.updated_by = actor
    state.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(state)
    return state
