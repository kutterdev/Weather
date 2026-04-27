"""City to airport station mapping.

Each Polymarket weather temperature contract resolves on a specific airport
ASOS station, not on the city center. The high temperature for a given date
is the daily max recorded by NOAA at that station.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class City:
    name: str
    station: str  # ICAO airport code, e.g. KLGA
    lat: float
    lon: float
    tz: str  # IANA timezone for daily aggregation


# Source: airport coordinates (approximate, sufficient for forecast lookup).
# These are the stations Polymarket resolves on, per the contract rules.
#
# Station codes must match the exact resolution source on each market.
# Several US cities have more than one ASOS-reporting airport (Dallas:
# KDAL Love Field vs KDFW Dallas/Fort Worth; New York: KLGA vs KJFK vs
# KEWR; Chicago: KORD vs KMDW; Houston: KIAH vs KHOU). Polymarket picks
# one airport per market, so changing this code silently routes us to a
# different station and miscalibrates every forecast and settlement for
# that city. Verify against the resolution source on the market itself
# before editing.
CITIES: list[City] = [
    City("New York",   "KLGA", 40.7772, -73.8726, "America/New_York"),
    City("Chicago",    "KORD", 41.9786, -87.9048, "America/Chicago"),
    City("Miami",      "KMIA", 25.7959, -80.2870, "America/New_York"),
    City("Dallas",     "KDAL", 32.8471, -96.8518, "America/Chicago"),
    City("Seattle",    "KSEA", 47.4502, -122.3088, "America/Los_Angeles"),
    City("Atlanta",    "KATL", 33.6407, -84.4277, "America/New_York"),
    City("Los Angeles", "KLAX", 33.9416, -118.4085, "America/Los_Angeles"),
    City("Phoenix",    "KPHX", 33.4342, -112.0116, "America/Phoenix"),
]

CITIES_BY_STATION: dict[str, City] = {c.station: c for c in CITIES}


def get_city(station: str) -> City:
    return CITIES_BY_STATION[station]
