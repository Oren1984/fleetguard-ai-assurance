"""Domain-specific exceptions used across the risk/assurance pipeline."""


class FleetGuardError(Exception):
    """Base class for all domain errors."""


class InvalidTelemetryError(FleetGuardError):
    """Raised when telemetry data is missing or invalid for risk scoring."""


class WeatherServiceError(FleetGuardError):
    """Raised when the (mock) weather provider fails to return data."""


class SopNotFoundError(FleetGuardError):
    """Raised when no SOP documents could be loaded for retrieval."""


class KillSwitchEngagedError(FleetGuardError):
    """Raised when an operation is blocked because the kill switch is engaged."""


class ApprovalRequiredError(FleetGuardError):
    """Raised when an action is executed without prior human approval."""
