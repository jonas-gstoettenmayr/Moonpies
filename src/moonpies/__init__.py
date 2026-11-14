"""Moonpies - NASA Space Apps Challenge 2026 package.

from moonpies.merge import harmonize
from moonpies.meteomatics import get_weather

__all__ = ["get_weather", "harmonize"]
This package provides tools for fetching and analyzing weather data
from the Meteomatics API, particularly for integrating with NASA FIRMS
fire detection data.
"""

from moonpies.merge import harmonize
from moonpies.meteomatics import (
    DEFAULT_PARAMS,
    LEGACY_PARAMS,
    fetch_weather_batch,
    get_weather,
    get_weather_for_firms,
    merge_weather_with_firms,
)

__all__ = [
    "DEFAULT_PARAMS",
    "LEGACY_PARAMS",
    "fetch_weather_batch",
    "get_weather",
    "get_weather_for_firms",
    "harmonize",
    "merge_weather_with_firms"
]

def main() -> None:
    print("Hello from moonpies!")
