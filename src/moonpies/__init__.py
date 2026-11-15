"""Moonpies - NASA Space Apps Challenge 2026 package.

This package provides tools for fetching and analyzing weather data
from the Meteomatics API, particularly for integrating with NASA FIRMS
fire detection data.
"""

# Core meteomatics functionality (always available)
from moonpies.meteomatics import (
    DEFAULT_PARAMS,
    LEGACY_PARAMS,
    fetch_weather_batch,
    get_weather,
    get_weather_for_firms,
    merge_weather_with_firms,
)

# Optional imports (may require additional dependencies)
try:
    from moonpies.merge import harmonize
    _HAS_MERGE = True
except ImportError:
    _HAS_MERGE = False
    harmonize = None

try:
    from moonpies.data_ingestion import fetch_data
    _HAS_DATA_INGESTION = True
except ImportError:
    _HAS_DATA_INGESTION = False
    fetch_data = None

__all__ = [
    "DEFAULT_PARAMS",
    "LEGACY_PARAMS",
    "fetch_weather_batch",
    "get_weather",
    "get_weather_for_firms",
    "merge_weather_with_firms",
    "harmonize",
    "fetch_data",
]

def main() -> None:
    print("Hello from moonpies!")
