"""
Fetch historical weather data for Austria (year 2020) from Meteomatics API.

This script fetches:
- Temperature (t_2m:C)
- Relative Humidity (relhum_2m:p)
- Wind Speed (wind_speed_10m:ms)
- Wind Direction (wind_dir_10m:d)
- Precipitation (precip_1h:mm)
- Evaporation (evapotranspiration:mm or evaporation:mm)
- Forest Fire Risk Index (if available)

The data will be saved to CSV with latitude and longitude columns for merging
with NASA FIRMS fire data.

Note: This is a large data fetch. The script includes:
- Rate limiting (1 request per second by default)
- Grid-based sampling of Austria
- Hourly or daily resolution options
- Progress tracking
"""

import csv
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import time
from typing import List, Dict, Any, Optional

import requests
from dotenv import load_dotenv

# Load environment variables
env_path = Path(__file__).resolve().parents[1] / "meteo-api.env"
if env_path.exists():
    load_dotenv(env_path)

METEOMATICS_URL = "https://api.meteomatics.com"

# Austria bounding box
# Approximate coordinates for Austria
AUSTRIA_BBOX = {
    'min_lat': 46.4,
    'max_lat': 49.0,
    'min_lon': 9.5,
    'max_lon': 17.2
}

# Grid resolution in degrees (0.1 = ~11km, 0.2 = ~22km, 0.5 = ~55km)
GRID_RESOLUTION = 0.2

# Time resolution: 'hourly' or 'daily'
TIME_RESOLUTION = 'daily'  # For year 2020, daily is more manageable

# Output file
OUTPUT_CSV = Path(__file__).parent / "austria_weather_2020.csv"


def get_available_parameters() -> List[str]:
    """
    Test which parameters are available in the Meteomatics API.
    
    Returns a list of confirmed working parameter names.
    """
    username = os.environ.get("METEOMATICS_USERNAME")
    password = os.environ.get("METEOMATICS_PASSWORD")
    
    if not username or not password:
        raise ValueError("METEOMATICS_USERNAME and METEOMATICS_PASSWORD must be set")
    
    # Test parameters we want to fetch
    test_params = {
        'temperature': 't_2m:C',
        'humidity': 'relhum_2m:p',
        'wind_speed': 'wind_speed_10m:ms',
        'wind_direction': 'wind_dir_10m:d',
        'precipitation': 'precip_1h:mm',
        'precipitation_24h': 'precip_24h:mm',
        'evaporation': 'evapotranspiration:mm',
        'evaporation_alt': 'evaporation:mm',
        'solar_radiation': 'radshort_1h:W',
        # Fire risk indices (may vary by API)
        'fire_risk_fwi': 'fwi:idx',  # Fire Weather Index
        'fire_risk_dmc': 'dmc:idx',  # Duff Moisture Code
        'fire_risk_dc': 'dc:idx',    # Drought Code
        'fire_risk_isi': 'isi:idx',  # Initial Spread Index
        'fire_risk_bui': 'bui:idx',  # Buildup Index
    }
    
    # Test with a sample location and time
    test_lat, test_lon = 47.07, 15.44  # Graz
    test_time = datetime(2020, 1, 1, 12, 0, tzinfo=timezone.utc)
    
    working_params = {}
    for name, param in test_params.items():
        try:
            timestamp = test_time.isoformat(timespec="seconds")
            url = f"{METEOMATICS_URL}/{timestamp}/{param}/{test_lat},{test_lon}/json"
            
            response = requests.get(
                url,
                auth=(username, password),
                timeout=30,
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('status') == 'OK':
                    working_params[name] = param
                    print(f"✓ {name} ({param}) - available")
                else:
                    print(f"✗ {name} ({param}) - status: {data.get('status')}")
            else:
                print(f"✗ {name} ({param}) - HTTP {response.status_code}")
        except Exception as e:
            print(f"✗ {name} ({param}) - error: {e}")
        
        time.sleep(0.5)  # Rate limit
    
    return working_params


def generate_grid(bbox: Dict[str, float], resolution: float) -> List[Dict[str, float]]:
    """
    Generate a grid of points covering the bounding box.
    
    Args:
        bbox: Dictionary with min_lat, max_lat, min_lon, max_lon
        resolution: Grid spacing in degrees
    
    Returns:
        List of dictionaries with 'lat' and 'lon' keys
    """
    points = []
    
    lat = bbox['min_lat']
    while lat <= bbox['max_lat']:
        lon = bbox['min_lon']
        while lon <= bbox['max_lon']:
            points.append({'lat': lat, 'lon': lon})
            lon += resolution
        lat += resolution
    
    return points


def fetch_weather_data(
    lat: float,
    lon: float,
    start_time: datetime,
    end_time: datetime,
    resolution: str = 'daily',
    params: List[str] = None
) -> List[Dict[str, Any]]:
    """
    Fetch weather data for a single location across a time range.
    
    Args:
        lat: Latitude
        lon: Longitude
        start_time: Start datetime (UTC)
        end_time: End datetime (UTC)
        resolution: 'hourly' or 'daily'
        params: List of parameter names to fetch
    
    Returns:
        List of dictionaries with weather data for each time point
    """
    username = os.environ.get("METEOMATICS_USERNAME")
    password = os.environ.get("METEOMATICS_PASSWORD")
    
    if not username or not password:
        raise ValueError("METEOMATICS_USERNAME and METEOMATICS_PASSWORD must be set")
    
    if params is None:
        # Default parameters that we know work with this API
        params = [
            't_2m:C',              # Temperature at 2m in Celsius
            'rh_2m:p',             # Relative humidity at 2m in percent
            'wind_speed_10m:ms',   # Wind speed at 10m in m/s
            'wind_dir_10m:d',      # Wind direction at 10m in degrees
            'precip_1h:mm',        # Precipitation in last hour in mm
            'precip_24h:mm',       # Precipitation in last 24 hours in mm
            'evapotranspiration_24h:mm',  # Evapotranspiration in mm
        ]
    
    results = []
    current_time = start_time
    
    while current_time <= end_time:
        # Use UTC timestamp without timezone offset in the URL
        timestamp = current_time.strftime('%Y-%m-%dT%H:%M:%SZ')
        param_str = ','.join(params)
        url = f"{METEOMATICS_URL}/{timestamp}/{param_str}/{lat},{lon}/json"
        
        try:
            response = requests.get(
                url,
                auth=(username, password),
                timeout=60,
            )
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get('status') == 'OK' and 'data' in data:
                    # Parse the data
                    weather_point = {
                        'lat': lat,
                        'lon': lon,
                        'timestamp': timestamp,
                        'date': current_time.date().isoformat()
                    }
                    
                    # Extract parameter values
                    # The data structure: data -> list of parameter objects
                    # Each parameter has: parameter, coordinates -> dates -> value
                    for data_point in data['data']:
                        param_name = data_point.get('parameter', '')
                        # Clean parameter name for CSV column
                        param_clean = param_name.replace(':', '_').replace('/', '_')
                        
                        if data_point.get('coordinates'):
                            for coord in data_point['coordinates']:
                                for date_info in coord.get('dates', []):
                                    weather_point[param_clean] = date_info.get('value')
                    
                    results.append(weather_point)
                else:
                    print(f"  Warning: Unexpected status for {timestamp}: {data.get('status')}")
            elif response.status_code == 404:
                print(f"  Warning: 404 for {timestamp} - parameter may not be available for this date")
            else:
                print(f"  Error: HTTP {response.status_code} for {timestamp}")
            
        except requests.exceptions.RequestException as e:
            print(f"  Error fetching data for {timestamp}: {e}")
        
        # Move to next time point
        if resolution == 'hourly':
            current_time += timedelta(hours=1)
        else:  # daily
            current_time += timedelta(days=1)
        
        time.sleep(1)  # Rate limiting - be gentle with the API
    
    return results


def fetch_austria_year(
    year: int = 2020,
    bbox: Dict[str, float] = None,
    grid_resolution: float = 0.2,
    time_resolution: str = 'daily',
    params: List[str] = None,
    output_csv: Path = None
) -> None:
    """
    Main function to fetch weather data for Austria for a full year.
    
    Args:
        year: Year to fetch data for
        bbox: Bounding box for Austria
        grid_resolution: Grid spacing in degrees
        time_resolution: 'hourly' or 'daily'
        params: List of parameter names
        output_csv: Output CSV file path
    """
    if bbox is None:
        bbox = AUSTRIA_BBOX
    
    if params is None:
        # Default parameters based on what we know works
        params = [
            't_2m:C',           # Temperature at 2m in Celsius
            'relhum_2m:p',      # Relative humidity at 2m in percent
            'wind_speed_10m:ms', # Wind speed at 10m in m/s
            'wind_dir_10m:d',   # Wind direction at 10m in degrees
            'precip_1h:mm',     # Precipitation in last hour in mm
            'precip_24h:mm',    # Precipitation in last 24 hours in mm
        ]
    
    if output_csv is None:
        output_csv = Path(f"austria_weather_{year}_{time_resolution}.csv")
    
    # Generate grid
    print(f"Generating grid for Austria with resolution {grid_resolution}°...")
    grid_points = generate_grid(bbox, grid_resolution)
    print(f"  Created {len(grid_points)} grid points")
    
    # Calculate date range
    start_time = datetime(year, 1, 1, 12, 0, tzinfo=timezone.utc)
    if time_resolution == 'hourly':
        end_time = datetime(year, 12, 31, 23, 0, tzinfo=timezone.utc)
    else:
        end_time = datetime(year, 12, 31, 12, 0, tzinfo=timezone.utc)
    
    total_points = len(grid_points)
    
    # Estimate total requests
    if time_resolution == 'hourly':
        time_points = 365 * 24  # Approximate
    else:
        time_points = 366  # 2020 is a leap year
    
    estimated_requests = total_points * time_points
    print(f"  Time range: {start_time.date()} to {end_time.date()}")
    print(f"  Estimated API requests: {estimated_requests:,}")
    print(f"  At 1 request/second, this will take ~{estimated_requests/3600:.1f} hours")
    
    # Ask for confirmation
    proceed = input(f"\nThis will make ~{estimated_requests:,} API requests. Continue? (y/n): ")
    if proceed.lower() != 'y':
        print("  Aborted.")
        return
    
    # Open CSV file for writing
    with output_csv.open('w', newline='') as csvfile:
        fieldnames = ['lat', 'lon', 'timestamp', 'date'] + \
                     [p.replace(':', '_').replace('/', '_') for p in params]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        
        # Process each grid point
        all_data = []
        for i, point in enumerate(grid_points):
            lat = point['lat']
            lon = point['lon']
            print(f"\nProcessing point {i+1}/{total_points}: ({lat:.2f}, {lon:.2f})")
            
            try:
                data = fetch_weather_data(
                    lat, lon,
                    start_time, end_time,
                    time_resolution,
                    params
                )
                all_data.extend(data)
                
                # Write batch to CSV periodically
                if len(all_data) >= 100:
                    writer.writerows(all_data)
                    csvfile.flush()
                    all_data = []
                
            except Exception as e:
                print(f"  Error processing point ({lat}, {lon}): {e}")
        
        # Write remaining data
        if all_data:
            writer.writerows(all_data)
    
    print(f"\n✓ Data saved to {output_csv}")
    print(f"  Total records written: {sum(1 for _ in output_csv.open()) - 1}")  # -1 for header


def test_single_point():
    """Test fetching data for a single point."""
    print("\n" + "="*60)
    print("Testing single point fetch...")
    print("="*60)
    
    # Test with Graz
    lat, lon = 47.07, 15.44
    start = datetime(2020, 1, 1, 12, 0, tzinfo=timezone.utc)
    end = datetime(2020, 1, 5, 12, 0, tzinfo=timezone.utc)
    
    params = ['t_2m:C', 'relhum_2m:p', 'precip_1h:mm']
    
    print(f"Fetching data for Graz ({lat}, {lon}) from {start.date()} to {end.date()}...")
    data = fetch_weather_data(lat, lon, start, end, 'daily', params)
    
    print(f"  Retrieved {len(data)} data points")
    if data:
        print(f"  Sample: {data[0]}")
    
    return data


def main():
    """Main entry point."""
    print("Meteomatics API - Austria 2020 Weather Data Fetcher")
    print("="*60)
    
    # First, check which parameters are available
    print("\n1. Checking available parameters...")
    print("-"*60)
    available = get_available_parameters()
    
    print("\n2. Available parameters:")
    for name, param in available.items():
        print(f"   - {name}: {param}")
    
    # Run a test fetch
    print("\n3. Testing data fetch for a single point...")
    test_data = test_single_point()
    
    if test_data:
        print("\n4. Ready to fetch full dataset!")
        print("   Run: fetch_austria_year() to fetch all data")
        print("   WARNING: This will make many API requests!")
        
        # Uncomment to run the full fetch
        # fetch_austria_year(
        #     year=2020,
        #     bbox=AUSTRIA_BBOX,
        #     grid_resolution=0.5,  # Start with coarse resolution
        #     time_resolution='daily',
        #     output_csv=OUTPUT_CSV
        # )
    else:
        print("\n⚠ Test failed. Check your API credentials and parameters.")


if __name__ == "__main__":
    main()
