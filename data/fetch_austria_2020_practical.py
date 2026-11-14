"""
Practical script to fetch historical weather data for Austria (year 2020).

This script fetches the following parameters from Meteomatics API:
- Temperature (t_2m:C)
- Relative Humidity (rh_2m:p)
- Wind Speed (wind_speed_10m:ms)
- Wind Direction (wind_dir_10m:d)
- Precipitation 1h (precip_1h:mm)
- Precipitation 24h (precip_24h:mm)
- Evapotranspiration 24h (evapotranspiration_24h:mm)

NOTE: Forest fire risk indices (FWI, DMC, DC, ISI, BUI) are NOT available
in the Meteomatics API with the current credentials. However, you can:
1. Compute FWI from the available weather data using the Canadian FWI System
2. Look for alternative fire risk data sources (e.g., Copernicus, MODIS)

This script:
- Uses a configurable grid resolution
- Can fetch hourly or daily data
- Saves to CSV with lat/lon columns for merging with NASA FIRMS data
- Includes rate limiting to avoid hitting API limits
- Can be run incrementally for specific date ranges

Usage:
    # Fetch a single month at 0.5 degree resolution
    python fetch_austria_2020_practical.py --start 2020-01-01 --end 2020-01-31 --resolution 0.5
    
    # Fetch full year at 1.0 degree resolution (faster)
    python fetch_austria_2020_practical.py --start 2020-01-01 --end 2020-12-31 --resolution 1.0
"""

import argparse
import csv
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
import time
from typing import List, Dict, Any, Optional, Tuple

import requests
from dotenv import load_dotenv

# Load environment variables
env_path = Path(__file__).resolve().parents[1] / "meteo-api.env"
if env_path.exists():
    load_dotenv(env_path)

METEOMATICS_URL = "https://api.meteomatics.com"

# Austria bounding box
AUSTRIA_BBOX = {
    'min_lat': 46.4,
    'max_lat': 49.0,
    'min_lon': 9.5,
    'max_lon': 17.2
}

# Available parameters (tested and working)
AVAILABLE_PARAMS = [
    't_2m:C',                    # Temperature at 2m in Celsius
    'rh_2m:p',                   # Relative humidity at 2m in percent
    'wind_speed_10m:ms',         # Wind speed at 10m in m/s
    'wind_dir_10m:d',           # Wind direction at 10m in degrees
    'precip_1h:mm',              # Precipitation in last hour in mm
    'precip_24h:mm',             # Precipitation in last 24 hours in mm
    'evapotranspiration_24h:mm', # Evapotranspiration in mm (24h)
]

# Default output
DEFAULT_OUTPUT = Path(__file__).parent / "austria_weather_2020.csv"


def generate_grid(bbox: Dict[str, float], resolution: float) -> List[Tuple[float, float]]:
    """
    Generate a grid of (lat, lon) points covering the bounding box.
    
    Args:
        bbox: Dictionary with min_lat, max_lat, min_lon, max_lon
        resolution: Grid spacing in degrees
    
    Returns:
        List of (lat, lon) tuples
    """
    points = []
    
    lat = bbox['min_lat']
    while lat <= bbox['max_lat']:
        lon = bbox['min_lon']
        while lon <= bbox['max_lon']:
            points.append((round(lat, 4), round(lon, 4)))
            lon += resolution
        lat += resolution
    
    return points


def get_csv_fieldnames(params: List[str]) -> List[str]:
    """Generate CSV field names from parameter list."""
    base_fields = ['lat', 'lon', 'timestamp', 'date', 'year', 'month', 'day']
    param_fields = [p.replace(':', '_').replace('/', '_') for p in params]
    return base_fields + param_fields


def fetch_single_point(
    lat: float,
    lon: float,
    timestamp: datetime,
    params: List[str],
    username: str,
    password: str
) -> Optional[Dict[str, Any]]:
    """
    Fetch weather data for a single point at a single timestamp.
    
    Args:
        lat: Latitude
        lon: Longitude
        timestamp: Datetime in UTC
        params: List of parameter names
        username: Meteomatics username
        password: Meteomatics password
    
    Returns:
        Dictionary with weather data or None if error
    """
    timestamp_str = timestamp.strftime('%Y-%m-%dT%H:%M:%SZ')
    param_str = ','.join(params)
    url = f"{METEOMATICS_URL}/{timestamp_str}/{param_str}/{lat},{lon}/json"
    
    try:
        response = requests.get(
            url,
            auth=(username, password),
            timeout=60,
        )
        
        if response.status_code != 200:
            print(f"  HTTP {response.status_code} for ({lat}, {lon}) at {timestamp_str}")
            return None
        
        data = response.json()
        
        if data.get('status') != 'OK' or 'data' not in data:
            print(f"  Bad status for ({lat}, {lon}) at {timestamp_str}: {data.get('status')}")
            return None
        
        # Parse the data
        weather_point = {
            'lat': lat,
            'lon': lon,
            'timestamp': timestamp_str,
            'date': timestamp.date().isoformat(),
            'year': timestamp.year,
            'month': timestamp.month,
            'day': timestamp.day,
        }
        
        # Extract parameter values
        for data_point in data['data']:
            param_name = data_point.get('parameter', '')
            param_clean = param_name.replace(':', '_').replace('/', '_')
            
            if data_point.get('coordinates'):
                for coord in data_point['coordinates']:
                    for date_info in coord.get('dates', []):
                        weather_point[param_clean] = date_info.get('value')
        
        return weather_point
        
    except Exception as e:
        print(f"  Error for ({lat}, {lon}) at {timestamp_str}: {e}")
        return None


def fetch_date_range(
    start_date: datetime,
    end_date: datetime,
    bbox: Dict[str, float],
    resolution: float,
    params: List[str],
    output_csv: Path,
    time_resolution: str = 'daily',
    rate_limit: float = 1.0,
    append: bool = False
) -> None:
    """
    Fetch weather data for a date range and save to CSV.
    
    Args:
        start_date: Start datetime (UTC)
        end_date: End datetime (UTC)
        bbox: Bounding box dictionary
        resolution: Grid resolution in degrees
        params: List of parameter names
        output_csv: Output CSV file path
        time_resolution: 'hourly' or 'daily'
        rate_limit: Seconds between requests
        append: Whether to append to existing file
    """
    username = os.environ.get("METEOMATICS_USERNAME")
    password = os.environ.get("METEOMATICS_PASSWORD")
    
    if not username or not password:
        raise ValueError("METEOMATICS_USERNAME and METEOMATICS_PASSWORD must be set")
    
    # Generate grid
    print(f"Generating grid with resolution {resolution}°...")
    grid_points = generate_grid(bbox, resolution)
    print(f"  Grid has {len(grid_points)} points")
    
    # Calculate total requests
    if time_resolution == 'hourly':
        delta = timedelta(hours=1)
        num_time_points = int((end_date - start_date) / delta) + 1
    else:
        delta = timedelta(days=1)
        num_time_points = int((end_date - start_date) / delta) + 1
    
    total_requests = len(grid_points) * num_time_points
    estimated_time = total_requests * rate_limit / 3600
    
    print(f"Date range: {start_date.date()} to {end_date.date()}")
    print(f"Time resolution: {time_resolution}")
    print(f"Total requests: {total_requests:,}")
    print(f"Estimated time at {rate_limit}s/request: {estimated_time:.1f} hours")
    
    # Confirm
    if total_requests > 100 and not append:
        proceed = input(f"\nProceed with {total_requests:,} requests? (y/n): ")
        if proceed.lower() != 'y':
            print("Aborted.")
            return
    
    # Prepare CSV
    fieldnames = get_csv_fieldnames(params)
    mode = 'a' if append and output_csv.exists() else 'w'
    
    with output_csv.open(mode, newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        
        if mode == 'w':
            writer.writeheader()
        
        # Process each date
        current_date = start_date
        request_count = 0
        success_count = 0
        
        while current_date <= end_date:
            print(f"\nProcessing date: {current_date.date()}")
            
            for lat, lon in grid_points:
                request_count += 1
                
                if request_count % 10 == 0:
                    print(f"  Request {request_count}/{total_requests} - Success: {success_count}")
                
                result = fetch_single_point(
                    lat, lon, current_date, params, username, password
                )
                
                if result:
                    writer.writerow(result)
                    csvfile.flush()  # Flush after each write
                    success_count += 1
                
                time.sleep(rate_limit)
            
            # Move to next time point
            current_date += delta
    
    print(f"\n✓ Completed!")
    print(f"  Requests made: {request_count}")
    print(f"  Successful: {success_count}")
    print(f"  Data saved to: {output_csv}")
    
    # Count rows in CSV
    with output_csv.open() as f:
        num_rows = sum(1 for _ in f) - 1  # -1 for header
    print(f"  Total records: {num_rows}")


def main():
    parser = argparse.ArgumentParser(
        description='Fetch weather data for Austria from Meteomatics API'
    )
    parser.add_argument(
        '--start',
        type=str,
        default='2020-01-01',
        help='Start date (YYYY-MM-DD)'
    )
    parser.add_argument(
        '--end',
        type=str,
        default='2020-01-31',
        help='End date (YYYY-MM-DD)'
    )
    parser.add_argument(
        '--resolution',
        type=float,
        default=0.5,
        help='Grid resolution in degrees (default: 0.5 ≈ 55km)'
    )
    parser.add_argument(
        '--time-res',
        type=str,
        default='daily',
        choices=['daily', 'hourly'],
        help='Time resolution (default: daily)'
    )
    parser.add_argument(
        '--output',
        type=str,
        default=str(DEFAULT_OUTPUT),
        help='Output CSV file path'
    )
    parser.add_argument(
        '--rate',
        type=float,
        default=1.0,
        help='Rate limit in seconds between requests (default: 1.0)'
    )
    parser.add_argument(
        '--append',
        action='store_true',
        help='Append to existing CSV file'
    )
    
    args = parser.parse_args()
    
    # Parse dates
    start_date = datetime.strptime(args.start, '%Y-%m-%d').replace(
        hour=12, minute=0, second=0, tzinfo=timezone.utc
    )
    end_date = datetime.strptime(args.end, '%Y-%m-%d').replace(
        hour=12, minute=0, second=0, tzinfo=timezone.utc
    )
    
    # Use all available parameters
    params = AVAILABLE_PARAMS
    
    print("="*70)
    print("Meteomatics API - Austria Weather Data Fetcher")
    print("="*70)
    print(f"\nParameters to fetch:")
    for p in params:
        print(f"  - {p}")
    print()
    
    # Run fetch
    fetch_date_range(
        start_date=start_date,
        end_date=end_date,
        bbox=AUSTRIA_BBOX,
        resolution=args.resolution,
        params=params,
        output_csv=Path(args.output),
        time_resolution=args.time_res,
        rate_limit=args.rate,
        append=args.append
    )


if __name__ == "__main__":
    main()
