#!/usr/bin/env python3
"""
Fetch weather data for a single high FRP fire event.

This script:
1. Finds the highest FRP fire in Austria 2020
2. Fetches weather data for ~2 months before, during, and after the fire
3. Saves result as parquet file

This is optimized for a single fire location to minimize API calls.

Usage:
    python fetch_weather_for_single_fire.py --months 2 --days-after 7 --rate 0.5
    
Options:
    --lat FLOAT         Latitude of fire (default: auto-detect highest FRP)
    --lon FLOAT         Longitude of fire (default: auto-detect highest FRP)
    --date YYYY-MM-DD   Date of fire (default: auto-detect highest FRP)
    --months INT        Months before fire to fetch (default: 2)
    --days-after INT    Days after fire to fetch (default: 7)
    --rate FLOAT        Rate limit in seconds (default: 0.5)
    --output FILE       Output parquet file (default: data/single_fire_with_weather.parquet)
"""

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
import time

import polars as pl

from moonpies.meteomatics import fetch_weather_batch, DEFAULT_PARAMS


DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def find_highest_frp_fire(
    df: pl.DataFrame,
    austria_bbox: dict = None
) -> dict:
    """Find the single highest FRP fire in Austria 2020."""
    # Filter to Austria if bbox provided
    if austria_bbox:
        df = df.filter(
            (pl.col('latitude') >= austria_bbox['min_lat']) &
            (pl.col('latitude') <= austria_bbox['max_lat']) &
            (pl.col('longitude') >= austria_bbox['min_lon']) &
            (pl.col('longitude') <= austria_bbox['max_lon'])
        )
    
    # Filter to 2020
    df_2020 = df.filter(
        (pl.col('acq_date') >= datetime(2020, 1, 1).date()) &
        (pl.col('acq_date') <= datetime(2020, 12, 31).date())
    )
    
    # Find highest FRP
    highest_df = (
        df_2020
        .filter(pl.col('frp').is_not_null())
        .sort('frp', descending=True)
        .limit(1)
    )
    
    if len(highest_df) == 0:
        raise ValueError("No fire data found")
    
    return highest_df.to_dicts()[0]


def get_all_fires_at_location(
    df: pl.DataFrame,
    lat: float,
    lon: float,
    tolerance: float = 0.01
) -> pl.DataFrame:
    """Get all fire detections at or near a specific location."""
    # Use a simple distance-based filter
    lat_min = lat - tolerance
    lat_max = lat + tolerance
    lon_min = lon - tolerance
    lon_max = lon + tolerance
    
    return df.filter(
        (pl.col('latitude') >= lat_min) &
        (pl.col('latitude') <= lat_max) &
        (pl.col('longitude') >= lon_min) &
        (pl.col('longitude') <= lon_max)
    ).sort('acq_date')


def fetch_weather_time_series(
    lat: float,
    lon: float,
    start_date: datetime,
    end_date: datetime,
    params: list = None,
    rate_limit: float = 0.5
) -> list:
    """
    Fetch weather data for a location across a date range.
    
    Returns list of weather records with additional metadata.
    """
    if params is None:
        params = DEFAULT_PARAMS
    
    # Convert to datetime.date if needed
    if isinstance(start_date, datetime):
        start_dt = start_date.date()
    else:
        start_dt = start_date
        
    if isinstance(end_date, datetime):
        end_dt = end_date.date()
    else:
        end_dt = end_date
    
    current_date = datetime(
        start_dt.year, start_dt.month, start_dt.day,
        12, 0, tzinfo=timezone.utc
    )
    end_datetime = datetime(
        end_dt.year, end_dt.month, end_dt.day,
        12, 0, tzinfo=timezone.utc
    )
    
    all_weather = []
    
    while current_date <= end_datetime:
        weather = fetch_weather_batch(
            coordinates=[(lat, lon)],
            timestamp=current_date,
            params=params,
            rate_limit=rate_limit
        )
        
        if weather and weather[0] is not None:
            wd = weather[0]
            wd['days_from_fire_start'] = (current_date.date() - start_dt).days
            all_weather.append(wd)
        
        current_date += timedelta(days=1)
        time.sleep(rate_limit)
    
    return all_weather


def main():
    parser = argparse.ArgumentParser(
        description='Fetch weather data for a single fire event'
    )
    parser.add_argument(
        '--lat',
        type=float,
        default=None,
        help='Latitude of fire (default: auto-detect highest FRP)'
    )
    parser.add_argument(
        '--lon',
        type=float,
        default=None,
        help='Longitude of fire (default: auto-detect highest FRP)'
    )
    parser.add_argument(
        '--date',
        type=str,
        default=None,
        help='Date of fire (YYYY-MM-DD) (default: auto-detect highest FRP)'
    )
    parser.add_argument(
        '--months',
        type=int,
        default=2,
        help='Months before fire to fetch (default: 2)'
    )
    parser.add_argument(
        '--days-after',
        type=int,
        default=7,
        help='Days after fire to fetch (default: 7)'
    )
    parser.add_argument(
        '--rate',
        type=float,
        default=0.5,
        help='Rate limit in seconds (default: 0.5)'
    )
    parser.add_argument(
        '--output',
        type=str,
        default='data/single_fire_with_weather.parquet',
        help='Output parquet file'
    )
    
    args = parser.parse_args()
    
    AUSTRIA_BBOX = {
        'min_lat': 46.0,
        'max_lat': 49.0,
        'min_lon': 9.0,
        'max_lon': 17.0
    }
    
    print("="*70)
    print("Fetching Weather Data for Single Fire Event")
    print("="*70)
    
    # Load data
    print("\n1. Loading FIRMS data...")
    df = pl.read_parquet(DATA_DIR / 'harmonized.parquet')
    print(f"   Total rows: {len(df):,}")
    
    # Find fire location
    if args.lat and args.lon and args.date:
        fire_lat = args.lat
        fire_lon = args.lon
        fire_date = datetime.strptime(args.date, '%Y-%m-%d').date()
        print(f"\n2. Using specified fire:")
        print(f"   Location: ({fire_lat}, {fire_lon})")
        print(f"   Date: {fire_date}")
    else:
        print("\n2. Finding highest FRP fire in Austria 2020...")
        highest = find_highest_frp_fire(df, AUSTRIA_BBOX)
        fire_lat = float(highest['latitude'])
        fire_lon = float(highest['longitude'])
        fire_date = highest['acq_date']
        fire_frp = float(highest['frp'])
        print(f"   Location: ({fire_lat:.4f}, {fire_lon:.4f})")
        print(f"   Date: {fire_date}")
        print(f"   FRP: {fire_frp:.1f} MW")
    
    # Get all fires at this location to determine duration
    print("\n3. Determining fire duration...")
    all_fires_at_loc = get_all_fires_at_location(df, fire_lat, fire_lon)
    print(f"   Total detections at this location: {len(all_fires_at_loc)}")
    
    if len(all_fires_at_loc) > 0:
        fire_start = all_fires_at_loc['acq_date'].min()
        fire_end = all_fires_at_loc['acq_date'].max()
        duration_days = (fire_end - fire_start).days + 1
        print(f"   Fire period: {fire_start} to {fire_end}")
        print(f"   Duration: {duration_days} days")
    else:
        fire_start = fire_date
        fire_end = fire_date
        duration_days = 1
        print(f"   Single detection on {fire_date}")
    
    # Determine weather date range
    # Start: months before first detection
    weather_start = fire_start - timedelta(days=args.months * 30)
    # End: days after last detection
    weather_end = fire_end + timedelta(days=args.days_after)
    
    print(f"\n4. Weather data period:")
    print(f"   Start: {weather_start}")
    print(f"   End: {weather_end}")
    
    total_days = (weather_end - weather_start).days + 1
    estimated_hours = total_days * args.rate / 3600
    
    print(f"\n5. Estimated workload:")
    print(f"   Days to fetch: {total_days}")
    print(f"   At {args.rate}s/request: {estimated_hours:.1f} hours")
    
    # Confirm
    if total_days > 100:
        proceed = input(f"\n   Proceed with {total_days} days of weather data? (y/n): ")
        if proceed.lower() != 'y':
            print("   Aborted.")
            return
    
    # Fetch weather
    print(f"\n6. Fetching weather data...")
    weather_data = fetch_weather_time_series(
        lat=fire_lat,
        lon=fire_lon,
        start_date=weather_start,
        end_date=weather_end,
        params=DEFAULT_PARAMS,
        rate_limit=args.rate
    )
    
    print(f"\n   Retrieved {len(weather_data)} weather records")
    
    # Add fire metadata to each weather record
    for wd in weather_data:
        wd.update({
            'fire_latitude': fire_lat,
            'fire_longitude': fire_lon,
            'fire_start_date': fire_start,
            'fire_end_date': fire_end,
            'fire_duration_days': duration_days,
        })
        if 'fire_frp' in locals():
            wd['fire_max_frp'] = fire_frp
    
    # Create DataFrame
    print(f"\n7. Creating result DataFrame...")
    result_df = pl.DataFrame(weather_data)
    
    # Add fire detection flags to weather data
    # Extract fire dates as strings (to match weather data 'date' column which is string)
    fire_dates = all_fires_at_loc['acq_date'].dt.strftime('%Y-%m-%d').to_list()
    
    # Add fire detection flag based on date string
    result_df = result_df.with_columns(
        pl.col('date').is_in(fire_dates).alias('fire_detection')
    )
    
    # Sort by date
    result_df = result_df.sort('timestamp')
    
    print(f"   Total records: {len(result_df):,}")
    
    # Save
    print(f"\n8. Saving to {args.output}...")
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result_df.write_parquet(output_path)
    
    print(f"\n✅ Complete! Output saved to: {output_path}")
    print(f"\nColumns: {len(result_df.columns)}")
    print(f"\nSample data:")
    print(result_df.limit(5))
    print(f"\n... and {len(result_df) - 5} more rows")
    
    # Summary statistics
    print(f"\nWeather statistics:")
    temp_col = 't_2m_C'
    if temp_col in result_df.columns:
        print(f"  Temperature range: {result_df[temp_col].min():.1f}°C to {result_df[temp_col].max():.1f}°C")
    
    rh_col = 'rh_2m_p'
    if rh_col in result_df.columns:
        print(f"  Humidity range: {result_df[rh_col].min():.1f}% to {result_df[rh_col].max():.1f}%")
    
    precip_col = 'precip_24h_mm'
    if precip_col in result_df.columns:
        print(f"  Precipitation total: {result_df[precip_col].sum():.2f} mm")


if __name__ == "__main__":
    main()
