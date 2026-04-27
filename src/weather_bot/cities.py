"""City to airport station mapping.

Each Polymarket weather temperature contract resolves on a specific airport
station, not on the city center. The high temperature for a given date is
the daily max recorded by the resolving authority at that station: NOAA
ASOS for US airports, the local met office (or whichever source Polymarket
references) for international ones.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class City:
    name: str
    station: str   # ICAO airport code, e.g. KLGA, EGLL, RJTT
    lat: float
    lon: float
    tz: str        # IANA timezone for daily aggregation
    country: str   # ISO 3166-1 alpha-2, e.g. "US", "GB", "JP"


# Source: airport coordinates (approximate, sufficient for forecast lookup).
# These are the stations we believe Polymarket resolves on.
#
# Station codes must match the exact resolution source on each market.
# Many cities have more than one airport on the wire:
#   Dallas      : KDAL Love Field vs KDFW Dallas/Fort Worth
#   New York    : KLGA vs KJFK vs KEWR
#   Chicago     : KORD O'Hare vs KMDW Midway
#   Houston     : KIAH Bush vs KHOU Hobby
#   Tokyo       : RJTT Haneda vs RJAA Narita
#   Sao Paulo   : SBGR Guarulhos vs SBSP Congonhas
#   Buenos Aires: SAEZ Ezeiza vs SABE Aeroparque
#   London      : EGLL Heathrow vs EGLC City vs EGSS Stansted
# Polymarket picks one airport per market, so a silent edit routes us to
# a different station and miscalibrates every forecast and settlement for
# that city. Verify against the resolution source on the market itself
# before editing. International picks here are educated guesses based on
# the major hub (see CLAUDE.md Gotchas).
CITIES: list[City] = [
    # United States
    City("New York",      "KLGA", 40.7772,  -73.8726, "America/New_York",       "US"),
    City("Chicago",       "KORD", 41.9786,  -87.9048, "America/Chicago",        "US"),
    City("Miami",         "KMIA", 25.7959,  -80.2870, "America/New_York",       "US"),
    City("Dallas",        "KDAL", 32.8471,  -96.8518, "America/Chicago",        "US"),
    City("Seattle",       "KSEA", 47.4502, -122.3088, "America/Los_Angeles",    "US"),
    City("Atlanta",       "KATL", 33.6407,  -84.4277, "America/New_York",       "US"),
    City("Los Angeles",   "KLAX", 33.9416, -118.4085, "America/Los_Angeles",    "US"),
    City("Phoenix",       "KPHX", 33.4342, -112.0116, "America/Phoenix",        "US"),
    City("Austin",        "KAUS", 30.1945,  -97.6699, "America/Chicago",        "US"),
    City("Denver",        "KDEN", 39.8561, -104.6737, "America/Denver",         "US"),
    City("Houston",       "KIAH", 29.9844,  -95.3414, "America/Chicago",        "US"),
    City("San Francisco", "KSFO", 37.6213, -122.3790, "America/Los_Angeles",    "US"),

    # International
    City("Toronto",       "CYYZ", 43.6777,  -79.6248, "America/Toronto",        "CA"),
    City("London",        "EGLL", 51.4700,   -0.4543, "Europe/London",          "GB"),
    City("Paris",         "LFPG", 49.0097,    2.5479, "Europe/Paris",           "FR"),
    City("Berlin",        "EDDB", 52.3667,   13.5033, "Europe/Berlin",          "DE"),
    City("Madrid",        "LEMD", 40.4719,   -3.5626, "Europe/Madrid",          "ES"),
    City("Tokyo",         "RJTT", 35.5494,  139.7798, "Asia/Tokyo",             "JP"),
    City("Seoul",         "RKSI", 37.4602,  126.4407, "Asia/Seoul",             "KR"),
    City("Hong Kong",     "VHHH", 22.3080,  113.9185, "Asia/Hong_Kong",         "HK"),
    City("Shanghai",      "ZSPD", 31.1443,  121.8083, "Asia/Shanghai",          "CN"),
    City("Singapore",     "WSSS",  1.3644,  103.9915, "Asia/Singapore",         "SG"),
    City("Mexico City",   "MMMX", 19.4361,  -99.0719, "America/Mexico_City",    "MX"),
    City("Sao Paulo",     "SBGR", -23.4356, -46.4731, "America/Sao_Paulo",      "BR"),
    City("Buenos Aires",  "SAEZ", -34.8222, -58.5358,
         "America/Argentina/Buenos_Aires",                                      "AR"),
]

CITIES_BY_STATION: dict[str, City] = {c.station: c for c in CITIES}


def get_city(station: str) -> City:
    return CITIES_BY_STATION[station]
