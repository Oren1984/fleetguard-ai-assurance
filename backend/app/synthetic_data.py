"""Synthetic fleet + telemetry generator.

Produces a deterministic (seeded) fleet of trucks spanning all three risk
levels, plus one dedicated "primary demo scenario" truck whose cargo
temperature gradually climbs from 4C to 10C while it experiences extreme
external heat and a route delay - exactly the scenario described in the
project brief.
"""
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.config import settings
from app.models import TelemetryReading, Truck

READING_COUNT = 6
READING_INTERVAL_MINUTES = 20

CARGO_TYPES = ["Fresh Produce", "Pharmaceuticals", "Dairy", "Frozen Seafood", "Meat Products"]

REGIONS = {
    "North": ("Portland", "Seattle"),
    "Central": ("Chicago", "St. Louis"),
    "South": ("Houston", "New Orleans"),
    "East": ("Boston", "New York"),
    "West": ("Los Angeles", "San Diego"),
}

FIRST_NAMES = ["Alex", "Jordan", "Sam", "Taylor", "Morgan", "Casey", "Riley", "Jamie", "Drew", "Avery"]
LAST_NAMES = ["Nguyen", "Garcia", "Smith", "Patel", "Kim", "Johnson", "Rossi", "Cohen", "Mueller", "Silva"]

DEMO_TRUCK_ID = "TRK-014"


@dataclass
class Profile:
    name: str
    weight: float


PROFILES = [Profile("normal", 0.62), Profile("moderate", 0.28), Profile("severe", 0.10)]


def _weighted_profile(rng: random.Random) -> str:
    names = [p.name for p in PROFILES]
    weights = [p.weight for p in PROFILES]
    return rng.choices(names, weights=weights, k=1)[0]


def _ramp(start: float, end: float, steps: int) -> list[float]:
    if steps == 1:
        return [end]
    return [round(start + (end - start) * i / (steps - 1), 2) for i in range(steps)]


def _build_readings(
    truck_id: str,
    setpoint: float,
    profile: str,
    rng: random.Random,
    now: datetime,
) -> list[TelemetryReading]:
    if profile == "severe":
        temps = _ramp(setpoint, setpoint + 6.0, READING_COUNT)
        external_temps = _ramp(34.0, 41.5, READING_COUNT)
        delays = _ramp(15, 50, READING_COUNT)
    elif profile == "moderate":
        temps = _ramp(setpoint + 0.3, setpoint + 3.2, READING_COUNT)
        external_temps = [round(rng.uniform(27, 33), 1) for _ in range(READING_COUNT)]
        delays = _ramp(10, 35, READING_COUNT)
    else:  # normal
        base = setpoint + rng.uniform(-0.3, 0.6)
        temps = [round(base + rng.uniform(-0.4, 0.4), 2) for _ in range(READING_COUNT)]
        external_temps = [round(rng.uniform(14, 27), 1) for _ in range(READING_COUNT)]
        delays = [round(rng.uniform(0, 15), 1) for _ in range(READING_COUNT)]

    readings = []
    for i in range(READING_COUNT):
        ts = now - timedelta(minutes=READING_INTERVAL_MINUTES * (READING_COUNT - 1 - i))
        readings.append(
            TelemetryReading(
                truck_id=truck_id,
                timestamp=ts,
                cargo_temp_c=temps[i],
                external_temp_c=external_temps[i],
                humidity_pct=round(rng.uniform(35, 75), 1),
                latitude=round(rng.uniform(25, 49), 4),
                longitude=round(rng.uniform(-124, -71), 4),
                speed_kmh=round(rng.uniform(0, 110), 1),
                route_delay_minutes=delays[i],
                weather_condition="heatwave" if profile == "severe" else rng.choice(["clear", "cloudy", "rain"]),
                weather_data_available=True,
            )
        )
    return readings


def generate_fleet(truck_count: int | None = None, seed: int | None = None, now: datetime | None = None):
    """Returns (trucks, telemetry_readings) ready to be added to the DB."""
    truck_count = truck_count or settings.SYNTHETIC_TRUCK_COUNT
    rng = random.Random(seed if seed is not None else settings.RANDOM_SEED)
    now = now or datetime.now(timezone.utc)

    trucks: list[Truck] = []
    readings: list[TelemetryReading] = []
    region_names = list(REGIONS.keys())

    for i in range(1, truck_count + 1):
        truck_id = f"TRK-{i:03d}"
        region = region_names[(i - 1) % len(region_names)]
        origin, destination = REGIONS[region]
        driver = f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"
        cargo_type = rng.choice(CARGO_TYPES)
        setpoint = 4.0 if cargo_type != "Frozen Seafood" else -18.0

        if truck_id == DEMO_TRUCK_ID:
            profile = "severe"
            cargo_type = "Fresh Produce"
            setpoint = 4.0
            region = "South"
            origin, destination = REGIONS[region]
        else:
            profile = _weighted_profile(rng)

        truck = Truck(
            id=truck_id,
            driver_name=driver,
            cargo_type=cargo_type,
            temp_setpoint_c=setpoint,
            route_name=f"{origin} -> {destination}",
            origin=origin,
            destination=destination,
            region=region,
            is_demo_scenario=(truck_id == DEMO_TRUCK_ID),
        )
        trucks.append(truck)
        readings.extend(_build_readings(truck_id, setpoint, profile, rng, now))

    return trucks, readings
