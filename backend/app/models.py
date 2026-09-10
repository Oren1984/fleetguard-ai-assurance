"""ORM models for FleetGuard AI."""
import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.database import Base


def utcnow():
    return datetime.now(timezone.utc)


class RiskLevel(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class RecommendedAction(str, enum.Enum):
    CONTINUE_JOURNEY = "CONTINUE_JOURNEY"
    CHANGE_ROUTE = "CHANGE_ROUTE"
    DIVERT_TO_FACILITY = "DIVERT_TO_FACILITY"
    MANUAL_REVIEW = "MANUAL_REVIEW"


class ApprovalStatus(str, enum.Enum):
    NOT_REQUIRED = "NOT_REQUIRED"
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class Truck(Base):
    __tablename__ = "trucks"

    id = Column(String, primary_key=True)  # e.g. "TRK-014"
    driver_name = Column(String, nullable=False)
    cargo_type = Column(String, nullable=False)
    temp_setpoint_c = Column(Float, nullable=False, default=4.0)
    route_name = Column(String, nullable=False)
    origin = Column(String, nullable=False)
    destination = Column(String, nullable=False)
    region = Column(String, nullable=False, default="Central")
    is_demo_scenario = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    telemetry = relationship("TelemetryReading", back_populates="truck", cascade="all, delete-orphan")
    assessments = relationship("RiskAssessment", back_populates="truck", cascade="all, delete-orphan")


class TelemetryReading(Base):
    __tablename__ = "telemetry_readings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    truck_id = Column(String, ForeignKey("trucks.id"), nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    cargo_temp_c = Column(Float, nullable=True)
    external_temp_c = Column(Float, nullable=True)
    humidity_pct = Column(Float, nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    speed_kmh = Column(Float, nullable=True)
    route_delay_minutes = Column(Float, nullable=True)
    weather_condition = Column(String, nullable=True)
    weather_data_available = Column(Boolean, default=True)

    truck = relationship("Truck", back_populates="telemetry")


class RiskAssessment(Base):
    __tablename__ = "risk_assessments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    truck_id = Column(String, ForeignKey("trucks.id"), nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    risk_score = Column(Float, nullable=False)
    risk_level = Column(String, nullable=False)
    reasons = Column(JSON, nullable=False, default=list)
    recommended_action = Column(String, nullable=False)
    requires_approval = Column(Boolean, default=False)
    sop_sources = Column(JSON, nullable=True)  # list of {doc, section, similarity, excerpt}
    explanation = Column(Text, nullable=False)
    grounded = Column(Boolean, default=True)
    evidence_snapshot = Column(JSON, nullable=False, default=dict)

    truck = relationship("Truck", back_populates="assessments")
    approval = relationship(
        "Approval", back_populates="risk_assessment", uselist=False, cascade="all, delete-orphan"
    )


class Approval(Base):
    __tablename__ = "approvals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    risk_assessment_id = Column(Integer, ForeignKey("risk_assessments.id"), nullable=False, unique=True)
    status = Column(String, nullable=False, default=ApprovalStatus.PENDING.value)
    requested_at = Column(DateTime(timezone=True), default=utcnow)
    decided_at = Column(DateTime(timezone=True), nullable=True)
    decided_by = Column(String, nullable=True)
    comments = Column(String, nullable=True)

    risk_assessment = relationship("RiskAssessment", back_populates="approval")
    execution = relationship(
        "ActionExecution", back_populates="approval", uselist=False, cascade="all, delete-orphan"
    )


class ActionExecution(Base):
    __tablename__ = "action_executions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    approval_id = Column(Integer, ForeignKey("approvals.id"), nullable=False, unique=True)
    executed_at = Column(DateTime(timezone=True), default=utcnow)
    executed_by = Column(String, nullable=True)
    outcome = Column(String, nullable=False)
    notes = Column(String, nullable=True)

    approval = relationship("Approval", back_populates="execution")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime(timezone=True), default=utcnow, index=True)
    event_type = Column(String, nullable=False, index=True)
    actor = Column(String, nullable=False)
    truck_id = Column(String, nullable=True, index=True)
    details = Column(JSON, nullable=False, default=dict)


class SystemState(Base):
    __tablename__ = "system_state"

    id = Column(Integer, primary_key=True, default=1)
    kill_switch_engaged = Column(Boolean, default=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow)
    updated_by = Column(String, nullable=True)
