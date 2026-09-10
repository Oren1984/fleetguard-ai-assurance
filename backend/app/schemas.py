"""Pydantic (de)serialization schemas."""
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


class TruckOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    driver_name: str
    cargo_type: str
    temp_setpoint_c: float
    route_name: str
    origin: str
    destination: str
    region: str
    is_demo_scenario: bool


class TelemetryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    truck_id: str
    timestamp: datetime
    cargo_temp_c: Optional[float]
    external_temp_c: Optional[float]
    humidity_pct: Optional[float]
    latitude: Optional[float]
    longitude: Optional[float]
    speed_kmh: Optional[float]
    route_delay_minutes: Optional[float]
    weather_condition: Optional[str]
    weather_data_available: bool


class TelemetryIn(BaseModel):
    cargo_temp_c: Optional[float] = None
    external_temp_c: Optional[float] = None
    humidity_pct: Optional[float] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    speed_kmh: Optional[float] = None
    route_delay_minutes: Optional[float] = None
    weather_condition: Optional[str] = None
    weather_data_available: bool = True


class RiskAssessmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    truck_id: str
    timestamp: datetime
    risk_score: float
    risk_level: str
    reasons: list[dict[str, Any]]
    recommended_action: str
    requires_approval: bool
    sop_sources: Optional[list[dict[str, Any]]]
    explanation: str
    grounded: bool
    evidence_snapshot: dict[str, Any]
    approval_status: Optional[str] = None
    approval_id: Optional[int] = None


class ApprovalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    risk_assessment_id: int
    status: str
    requested_at: datetime
    decided_at: Optional[datetime]
    decided_by: Optional[str]
    comments: Optional[str]


class ApprovalDecisionIn(BaseModel):
    decision: str  # "approve" | "reject"
    actor: str
    comments: Optional[str] = None


class ActionExecutionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    approval_id: int
    executed_at: datetime
    executed_by: Optional[str]
    outcome: str
    notes: Optional[str]


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    timestamp: datetime
    event_type: str
    actor: str
    truck_id: Optional[str]
    details: dict[str, Any]


class KillSwitchIn(BaseModel):
    engaged: bool
    actor: str
    reason: Optional[str] = None


class KillSwitchOut(BaseModel):
    kill_switch_engaged: bool
    updated_at: Optional[datetime]
    updated_by: Optional[str]


class HealthOut(BaseModel):
    status: str
    database: str
    kill_switch_engaged: bool
    llm_provider: str
    truck_count: int
