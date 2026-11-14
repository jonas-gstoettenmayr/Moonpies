"""Meteomatics API client for the Moonpies NASA Space Apps project."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import os
from typing import Any, Dict, List, Optional, Tuple, Union

try:
    import polars as pl
    POLARS_AVAILABLE = True
except ImportError:
    POLARS_AVAILABLE = False

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

# Available parameters that work with the current API credentials
DEFAULT_PARAMS = [
    't_2m:C',                    # Temperature at 2m in Celsius
    'rh_2m:p',                   # Relative humidity at 2m in percent
    'wind_speed_10m:ms',         # Wind speed at 10m in m/s
    'wind_dir_10m:d',           # Wind direction at 10m in degrees
    'precip_1h:mm',              # Precipitation in last hour in mm
    'precip_24h:mm',             # Precipitation in last 24 hours in mm
    'evapotranspiration_24h:mm', # Evapotranspiration in last 24 hours in mm
]

# Legacy default parameters (for backward compatibility)
LEGACY_PARAMS = ['t_2m:C', 'precip_1h:mm', 'wind_speed_10m:ms']


def get_weather(
    latitude: float,
    longitude: float,
    valid_time: datetime,
    params: Optional[List[str]] = None
) -> dict[str, Any]:
    """
    Fetch weather data from the Meteomatics API for a single location and time.

    Args:
        latitude: Latitude in decimal degrees
        longitude: Longitude in decimal degrees
        valid_time: Datetime for which to get weather data
        params: List of parameter names to fetch. If None, uses LEGACY_PARAMS
               for backward compatibility.

    Returns:
        Dictionary containing weather data from the Meteomatics API.
        The structure depends on the API response format.

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

    if params is None:
        params = LEGACY_PARAMS

    timestamp = valid_time.astimezone().isoformat(timespec="seconds")
    param_str = ','.join(params)
    url = f"{METEOMATICS_URL}/{timestamp}/{param_str}/{latitude},{longitude}/json"

    response = requests.get(
        url,
        auth=(username, password),
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def fetch_weather_batch(
    coordinates: List[Tuple[float, float]],
    timestamp: datetime,
    params: Optional[List[str]] = None,
    rate_limit: float = 1.0,
    progress_callback: Optional[callable] = None
) -> List[Dict[str, Any]]:
    """
    Fetch weather data for multiple coordinates at a single timestamp.
    
    This is useful for fetching weather data for all fire detection points
    from FIRMS data at a specific date/time.

    Args:
        coordinates: List of (latitude, longitude) tuples
        timestamp: Datetime for which to get weather data (UTC)
        params: List of parameter names to fetch. If None, uses DEFAULT_PARAMS.
        rate_limit: Minimum seconds between API requests (to avoid rate limiting)
        progress_callback: Optional function to call with progress updates.
                         Called with (current_index, total, result) for each successful request.
    
    Returns:
        List of dictionaries, one for each coordinate, containing:
        - lat: Latitude
        - lon: Longitude
        - timestamp: The request timestamp
        - date: Date in ISO format
        - year, month, day: Date components
        - Parameter values (with cleaned names, e.g., 't_2m_C' for 't_2m:C')
        
        Returns None for coordinates that failed.
    """
    username = os.environ.get("METEOMATICS_USERNAME")
    password = os.environ.get("METEOMATICS_PASSWORD")

    if not username or not password:
        raise ValueError(
            "METEOMATICS_USERNAME and METEOMATICS_PASSWORD must be set in the environment"
        )

    if params is None:
        params = DEFAULT_PARAMS

    results = []
    timestamp_str = timestamp.strftime('%Y-%m-%dT%H:%M:%SZ')
    param_str = ','.join(params)
    
    for i, (lat, lon) in enumerate(coordinates):
        url = f"{METEOMATICS_URL}/{timestamp_str}/{param_str}/{lat},{lon}/json"
        
        try:
            response = requests.get(
                url,
                auth=(username, password),
                timeout=30,
            )
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get('status') == 'OK' and 'data' in data:
                    # Parse the data into a flat dictionary
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
                    
                    results.append(weather_point)
                    
                    if progress_callback:
                        progress_callback(i, len(coordinates), weather_point)
                else:
                    # Status not OK
                    print(f"  Warning: Bad status for ({lat}, {lon}): {data.get('status')}")
                    results.append(None)
            else:
                print(f"  Warning: HTTP {response.status_code} for ({lat}, {lon})")
                results.append(None)
            
        except Exception as e:
            print(f"  Error for ({lat}, {lon}): {e}")
            results.append(None)
        
        # Rate limiting
        if i < len(coordinates) - 1:
            time.sleep(rate_limit)
    
    return results


def get_weather_for_firms(
    firms_data: Union[str, Path, pl.DataFrame, 'pd.DataFrame'],
    timestamp: datetime,
    lat_col: str = 'latitude',
    lon_col: str = 'longitude',
    params: Optional[List[str]] = None,
    rate_limit: float = 1.0
) -> List[Dict[str, Any]]:
    """
    Fetch weather data for all coordinates in a FIRMS dataset.
    
    This function takes FIRMS fire detection data (from MODIS, VIIRS, etc.)
    and fetches weather data for each unique latitude/longitude coordinate.
    
    Args:
        firms_data: Can be:
                   - Path to a CSV file (str or Path)
                   - Polars DataFrame
                   - Pandas DataFrame
        timestamp: Datetime for which to get weather data (UTC).
                   This should match the acquisition time of the FIRMS data.
        lat_col: Name of the latitude column in the FIRMS data [default: 'latitude']
        lon_col: Name of the longitude column in the FIRMS data [default: 'longitude']
        params: List of parameter names to fetch. If None, uses DEFAULT_PARAMS.
        rate_limit: Minimum seconds between API requests [default: 1.0]
    
    Returns:
        List of dictionaries with weather data for each coordinate.
        Each dictionary includes lat, lon, timestamp, and parameter values.
    
    Example:
        >>> from datetime import datetime, timezone
        >>> import polars as pl
        >>> firms_df = pl.read_csv('data/modis/modis_2020_Austria.csv')
        >>> timestamp = datetime(2020, 1, 1, 12, 0, tzinfo=timezone.utc)
        >>> weather_data = get_weather_for_firms(firms_df, timestamp)
    """
    # Load data if it's a file path
    if isinstance(firms_data, (str, Path)):
        if not POLARS_AVAILABLE:
            try:
                import pandas as pd
                firms_df = pd.read_csv(firms_data)
            except ImportError:
                raise ImportError("Neither polars nor pandas is available")
        else:
            firms_df = pl.read_csv(firms_data)
    else:
        firms_df = firms_data
    
    # Extract unique coordinates
    if POLARS_AVAILABLE and isinstance(firms_df, pl.DataFrame):
        # Get unique coordinates using polars
        coords = (
            firms_df
            .select([lat_col, lon_col])
            .unique()
            .iter_rows(named=True)
        )
        coordinates = [(row[lat_col], row[lon_col]) for row in coords]
    else:
        # Use pandas
        coords = firms_df[[lat_col, lon_col]].drop_duplicates().to_dict('records')
        coordinates = [(c[lat_col], c[lon_col]) for c in coords]
    
    print(f"Found {len(coordinates)} unique coordinates in FIRMS data")
    print(f"Fetching weather data for {timestamp.isoformat()}")
    
    return fetch_weather_batch(
        coordinates=coordinates,
        timestamp=timestamp,
        params=params,
        rate_limit=rate_limit
    )


def merge_weather_with_firms(
    firms_data: Union[str, Path, pl.DataFrame, 'pd.DataFrame'],
    weather_data: List[Dict[str, Any]],
    lat_col: str = 'latitude',
    lon_col: str = 'longitude',
    timestamp_col: Optional[str] = None,
    output_path: Optional[Union[str, Path]] = None
) -> Union[pl.DataFrame, 'pd.DataFrame']:
    """
    Merge weather data with FIRMS data.
    
    This function takes FIRMS fire detection data and weather data
    (from get_weather_for_firms) and merges them based on latitude/longitude.
    
    Args:
        firms_data: FIRMS data (path, polars DataFrame, or pandas DataFrame)
        weather_data: List of weather data dictionaries from get_weather_for_firms
        lat_col: Name of the latitude column [default: 'latitude']
        lon_col: Name of the longitude column [default: 'longitude']
        timestamp_col: Name of the timestamp column in FIRMS data. If provided,
                      will be used for merging. If None, only lat/lon are used.
        output_path: If provided, save the merged data to this path.
    
    Returns:
        Merged DataFrame (polars if available, otherwise pandas)
    
    Example:
        >>> weather_data = get_weather_for_firms(firms_df, timestamp)
        >>> merged = merge_weather_with_firms(firms_df, weather_data)
        >>> merged.write_csv('firms_with_weather.csv')
    """
    # Load data if it's a file path
    if isinstance(firms_data, (str, Path)):
        if not POLARS_AVAILABLE:
            try:
                import pandas as pd
                firms_df = pd.read_csv(firms_data)
                is_polars = False
            except ImportError:
                raise ImportError("Neither polars nor pandas is available")
        else:
            firms_df = pl.read_csv(firms_data)
            is_polars = True
    else:
        firms_df = firms_data
        is_polars = isinstance(firms_df, pl.DataFrame)
    
    # Create weather DataFrame
    if weather_data and weather_data[0] is not None:
        if is_polars:
            weather_df = pl.DataFrame(weather_data)
        else:
            import pandas as pd
            weather_df = pd.DataFrame(weather_data)
        
        # Remove None entries
        weather_df = weather_df.filter(pl.col('lat').is_not_null()) if is_polars else \
                    weather_df.dropna(subset=['lat'])
    else:
        # No weather data
        if is_polars:
            weather_df = pl.DataFrame()
        else:
            import pandas as pd
            weather_df = pd.DataFrame()
    
    # Merge based on latitude and longitude
    # Round coordinates to match (Meteomatics API uses 4 decimal places)
    if is_polars:
        firms_df = firms_df.with_columns(
            pl.col(lat_col).round(4).alias('lat_rounded'),
            pl.col(lon_col).round(4).alias('lon_rounded')
        )
        weather_df = weather_df.with_columns(
            pl.col('lat').round(4).alias('lat_rounded'),
            pl.col('lon').round(4).alias('lon_rounded')
        )
        
        merged = firms_df.join(
            weather_df,
            on=['lat_rounded', 'lon_rounded'],
            how='left'
        ).drop(['lat_rounded', 'lon_rounded'])
    else:
        firms_df['lat_rounded'] = firms_df[lat_col].round(4)
        firms_df['lon_rounded'] = firms_df[lon_col].round(4)
        weather_df['lat_rounded'] = weather_df['lat'].round(4)
        weather_df['lon_rounded'] = weather_df['lon'].round(4)
        
        merged = firms_df.merge(
            weather_df,
            on=['lat_rounded', 'lon_rounded'],
            how='left'
        ).drop(columns=['lat_rounded', 'lon_rounded'])
    
    # Save if output path provided
    if output_path:
        if is_polars:
            merged.write_csv(output_path)
        else:
            merged.to_csv(output_path, index=False)
        print(f"Merged data saved to {output_path}")
    
    return merged


# Import time for the rate limiting in fetch_weather_batch
import time
