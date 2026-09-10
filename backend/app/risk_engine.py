"""Rule-based, fully explainable risk scoring engine.

Deliberately NOT machine-learned: every point on the 0-100 scale traces back
to a documented threshold, so every score can be explained in plain language
and audited. See docs/ASSURANCE.md for the scoring rationale.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from app.config import settings
from app.exceptions import InvalidTelemetryError
from app.models import RecommendedAction, RiskLevel, TelemetryReading

EXTREME_HEAT_BASELINE_C = 30.0
EXTREME_HEAT_SCALE = 2.5
MAX_WEATHER_SCORE = 25.0

DELAY_SCALE_MINUTES = 2.0
MAX_DELAY_SCORE = 25.0

TEMP_DEVIATION_SCALE = 5.0
MAX_DEVIATION_SCORE = 35.0
TREND_SCALE = 2.0
MAX_TREND_SCORE = 15.0
MAX_TEMP_SCORE = 50.0


@dataclass
class RiskReason:
    factor: str
    value: Any
    detail: str
    score_contribution: float


@dataclass
class RiskResult:
    risk_score: float
    risk_level: str
    reasons: list[dict[str, Any]]
    recommended_action: str
    requires_approval: bool
    evidence_snapshot: dict[str, Any]


def _validate_reading(reading: TelemetryReading) -> None:
    if reading is None:
        raise InvalidTelemetryError("No telemetry reading available for this truck")
    if reading.cargo_temp_c is None:
        raise InvalidTelemetryError("Missing cargo temperature reading")
    if not (-50.0 <= reading.cargo_temp_c <= 60.0):
        raise InvalidTelemetryError(f"Cargo temperature out of physically valid range: {reading.cargo_temp_c}")


def _temperature_component(setpoint_c: float, latest: TelemetryReading, history: list[TelemetryReading]) -> tuple[float, list[RiskReason]]:
    reasons: list[RiskReason] = []
    deviation = max(0.0, latest.cargo_temp_c - setpoint_c)
    deviation_score = min(MAX_DEVIATION_SCORE, deviation * TEMP_DEVIATION_SCALE)
    if deviation > 0:
        reasons.append(
            RiskReason(
                factor="temperature_deviation",
                value=round(deviation, 2),
                detail=(
                    f"Cargo temperature {latest.cargo_temp_c:.1f}°C exceeds the "
                    f"{setpoint_c:.1f}°C setpoint by {deviation:.1f}°C"
                ),
                score_contribution=round(deviation_score, 2),
            )
        )

    trend_score = 0.0
    usable_history = [r for r in history if r.cargo_temp_c is not None]
    if len(usable_history) >= 2:
        ordered = sorted(usable_history, key=lambda r: r.timestamp)
        temp_delta = ordered[-1].cargo_temp_c - ordered[0].cargo_temp_c
        if temp_delta > 0:
            per_step = temp_delta / max(1, len(ordered) - 1)
            trend_score = min(MAX_TREND_SCORE, temp_delta * TREND_SCALE)
            reasons.append(
                RiskReason(
                    factor="temperature_trend",
                    value=round(per_step, 2),
                    detail=(
                        f"Cargo temperature rose {temp_delta:.1f}°C over the last "
                        f"{len(ordered)} readings (~{per_step:.2f}°C per reading), indicating "
                        "active refrigeration failure rather than a single bad sensor sample"
                    ),
                    score_contribution=round(trend_score, 2),
                )
            )

    total = min(MAX_TEMP_SCORE, deviation_score + trend_score)
    return total, reasons


def _weather_component(latest: TelemetryReading) -> tuple[float, list[RiskReason]]:
    if not latest.weather_data_available or latest.external_temp_c is None:
        return 0.0, [
            RiskReason(
                factor="weather_data_unavailable",
                value=None,
                detail="External weather data could not be retrieved; weather contribution excluded from the score",
                score_contribution=0.0,
            )
        ]

    if latest.external_temp_c <= EXTREME_HEAT_BASELINE_C:
        return 0.0, []

    score = min(MAX_WEATHER_SCORE, (latest.external_temp_c - EXTREME_HEAT_BASELINE_C) * EXTREME_HEAT_SCALE)
    reason = RiskReason(
        factor="extreme_weather",
        value=latest.external_temp_c,
        detail=(
            f"External temperature {latest.external_temp_c:.1f}°C is classified as extreme heat "
            f"(baseline {EXTREME_HEAT_BASELINE_C:.0f}°C), accelerating any cooling-unit strain"
        ),
        score_contribution=round(score, 2),
    )
    return score, [reason]


def _delay_component(latest: TelemetryReading) -> tuple[float, list[RiskReason]]:
    delay = latest.route_delay_minutes or 0.0
    if delay <= 0:
        return 0.0, []
    score = min(MAX_DELAY_SCORE, delay / DELAY_SCALE_MINUTES)
    reason = RiskReason(
        factor="route_delay",
        value=delay,
        detail=(
            f"Route delay of {delay:.0f} minutes extends cargo exposure time beyond the planned schedule"
        ),
        score_contribution=round(score, 2),
    )
    return score, [reason]


def classify(score: float) -> str:
    if score >= settings.RISK_LEVEL_HIGH_THRESHOLD:
        return RiskLevel.HIGH.value
    if score >= settings.RISK_LEVEL_MEDIUM_THRESHOLD:
        return RiskLevel.MEDIUM.value
    return RiskLevel.LOW.value


def recommend_action(risk_level: str) -> tuple[str, bool]:
    if risk_level == RiskLevel.HIGH.value:
        return RecommendedAction.DIVERT_TO_FACILITY.value, True
    if risk_level == RiskLevel.MEDIUM.value:
        return RecommendedAction.CHANGE_ROUTE.value, True
    return RecommendedAction.CONTINUE_JOURNEY.value, False


def assess(
    setpoint_c: float,
    latest: TelemetryReading,
    history: Optional[list[TelemetryReading]] = None,
) -> RiskResult:
    """Compute an explainable risk score for the latest telemetry reading of
    a truck, given recent history for trend detection.

    Raises InvalidTelemetryError for missing/out-of-range data - callers must
    handle this rather than silently scoring bad data.
    """
    _validate_reading(latest)
    history = history or []

    temp_score, temp_reasons = _temperature_component(setpoint_c, latest, history)
    weather_score, weather_reasons = _weather_component(latest)
    delay_score, delay_reasons = _delay_component(latest)

    total_score = round(min(100.0, temp_score + weather_score + delay_score), 2)
    risk_level = classify(total_score)
    action, requires_approval = recommend_action(risk_level)

    all_reasons = temp_reasons + weather_reasons + delay_reasons
    if not all_reasons:
        all_reasons = [
            RiskReason(
                factor="nominal",
                value=None,
                detail="Cargo temperature is within setpoint and no external risk factors were detected",
                score_contribution=0.0,
            )
        ]

    evidence_snapshot = {
        "setpoint_c": setpoint_c,
        "cargo_temp_c": latest.cargo_temp_c,
        "external_temp_c": latest.external_temp_c,
        "route_delay_minutes": latest.route_delay_minutes,
        "weather_data_available": latest.weather_data_available,
        "timestamp": latest.timestamp.isoformat() if isinstance(latest.timestamp, datetime) else latest.timestamp,
        "component_scores": {
            "temperature": round(temp_score, 2),
            "weather": round(weather_score, 2),
            "route_delay": round(delay_score, 2),
        },
    }

    return RiskResult(
        risk_score=total_score,
        risk_level=risk_level,
        reasons=[r.__dict__ for r in all_reasons],
        recommended_action=action,
        requires_approval=requires_approval,
        evidence_snapshot=evidence_snapshot,
    )
