"""Meteomatics API client for the Moonpies NASA Space Apps project."""

from datetime import datetime
from pathlib import Path
import os
from typing import Any

import requests
from dotenv import load_dotenv

# Load environment variables from the .env file
# Look for meteo-api.env in the project root or parent directories
env_path = Path(__file__).resolve().parents[2] / "meteo-api.env"
if env_path.exists():
    load_dotenv(env_path)
else:
    # Try loading from default .env
    load_dotenv()

METEOMATICS_URL = "https://api.meteomatics.com"


def get_weather(
    latitude: float,
    longitude: float,
    valid_time: datetime,
) -> dict[str, Any]:
    """
    Fetch weather data from the Meteomatics API.

    Args:
        latitude: Latitude in decimal degrees
        longitude: Longitude in decimal degrees
        valid_time: Datetime for which to get weather data

    Returns:
        Dictionary containing weather data with keys:
        - t_2m:C: Temperature at 2m in Celsius
        - precip_1h:mm: Precipitation in the last hour in mm
        - wind_speed_10m:ms: Wind speed at 10m in m/s

    Raises:
        ValueError: If METEOMATICS_USERNAME or METEOMATICS_PASSWORD are not set
        requests.exceptions.RequestException: If the API request fails
    """
    username = os.environ.get("METEOMATICS_USERNAME")
    password = os.environ.get("METEOMATICS_PASSWORD")

    if not username or not password:
        raise ValueError(
            "METEOMATICS_USERNAME and METEOMATICS_PASSWORD must be set in the environment"
        )

    timestamp = valid_time.astimezone().isoformat(timespec="seconds")
    url = (
        f"{METEOMATICS_URL}/{timestamp}/"
        "t_2m:C,precip_1h:mm,wind_speed_10m:ms/"
        f"{latitude},{longitude}/json"
    )

    response = requests.get(
        url,
        auth=(username, password),
        timeout=30,
    )
    response.raise_for_status()
    return response.json()
