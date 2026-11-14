"""Moonpies - NASA Space Apps Challenge 2026 package.

This package provides tools for fetching and analyzing weather data
from the Meteomatics API, particularly for integrating with NASA FIRMS
fire detection data.
"""

from moonpies.meteomatics import (
    get_weather,
    fetch_weather_batch,
    get_weather_for_firms,
    merge_weather_with_firms,
    DEFAULT_PARAMS,
    LEGACY_PARAMS,
)

__all__ = [
    "get_weather",
    "fetch_weather_batch",
    "get_weather_for_firms",
    "merge_weather_with_firms",
    "DEFAULT_PARAMS",
    "LEGACY_PARAMS",
]

def main() -> None:
    print("Hello from moonpies!")
