"""Weather provider abstraction.

The POC does not call a real weather API (out of scope per project
constraints) - it uses a deterministic mock provider that is wired the same
way a real integration would be, so ingestion code and tests exercise the
real failure-handling path. Swapping in a real provider later only requires
implementing WeatherProvider.get_conditions().
"""
import random
from dataclasses import dataclass
from typing import Optional, Protocol

from app.exceptions import WeatherServiceError


@dataclass
class WeatherConditions:
    external_temp_c: float
    humidity_pct: float
    condition: str


class WeatherProvider(Protocol):
    def get_conditions(self, latitude: float, longitude: float) -> WeatherConditions:
        ...


class MockWeatherProvider:
    """Deterministic synthetic weather. Can be forced to fail via
    `force_failure` to exercise the "weather API failure" QA scenario."""

    def __init__(self, force_failure: bool = False, rng: Optional[random.Random] = None):
        self.force_failure = force_failure
        self.rng = rng or random.Random()

    def get_conditions(self, latitude: float, longitude: float) -> WeatherConditions:
        if self.force_failure:
            raise WeatherServiceError("Weather provider request failed (simulated outage)")

        base_temp = 22 + 10 * abs(latitude) / 90 * self.rng.choice([-1, 1])
        return WeatherConditions(
            external_temp_c=round(base_temp, 1),
            humidity_pct=round(self.rng.uniform(30, 80), 1),
            condition=self.rng.choice(["clear", "cloudy", "rain", "heatwave"]),
        )


def fetch_weather_safely(provider: WeatherProvider, latitude: float, longitude: float) -> tuple[Optional[WeatherConditions], bool]:
    """Returns (conditions_or_None, data_available). Never raises - a
    failure degrades gracefully to 'no weather data available' rather than
    crashing ingestion or fabricating a reading."""
    try:
        return provider.get_conditions(latitude, longitude), True
    except WeatherServiceError:
        return None, False
