"""Approved refrigerated diversion facilities (mirrors SOP-04)."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Facility:
    id: str
    name: str
    region: str


APPROVED_FACILITIES: list[Facility] = [
    Facility("FAC-01", "Northgate Cold Storage", "North"),
    Facility("FAC-02", "Riverside Refrigerated Depot", "Central"),
    Facility("FAC-03", "Southbay Cold Chain Hub", "South"),
    Facility("FAC-04", "Eastline Distribution Facility", "East"),
    Facility("FAC-05", "Westpoint Frozen Logistics", "West"),
]

_BY_REGION = {f.region: f for f in APPROVED_FACILITIES}


def facility_for_region(region: str) -> Facility | None:
    return _BY_REGION.get(region)
