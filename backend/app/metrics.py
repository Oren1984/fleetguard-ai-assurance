"""Prometheus metrics for FleetGuard AI."""
from prometheus_client import Counter, Gauge, Histogram

risk_assessments_total = Counter(
    "fleetguard_risk_assessments_total", "Total risk assessments generated", ["risk_level"]
)

active_high_risk_trucks = Gauge(
    "fleetguard_active_high_risk_trucks", "Number of trucks currently classified HIGH risk"
)

pending_approvals = Gauge(
    "fleetguard_pending_approvals", "Number of approvals currently pending human decision"
)

kill_switch_status = Gauge(
    "fleetguard_kill_switch_engaged", "1 if the kill switch is engaged, else 0"
)

ungrounded_responses_blocked_total = Counter(
    "fleetguard_ungrounded_responses_blocked_total", "Number of AI explanations rejected for lacking grounding"
)

action_executions_total = Counter(
    "fleetguard_action_executions_total", "Total actions executed after approval", ["outcome"]
)

action_execution_blocked_total = Counter(
    "fleetguard_action_execution_blocked_total", "Total action executions blocked (no approval / kill switch)"
)

risk_scoring_duration_seconds = Histogram(
    "fleetguard_risk_scoring_duration_seconds", "Time spent computing a risk assessment"
)
