"""
Add Meteomatics weather data to harmonized FIRMS parquet file.

This script:
1. Reads the harmonized.parquet file
2. Identifies unique (latitude, longitude, date) combinations
3. Fetches weather data for each unique location+date
4. Matches weather data to FIRMS data with a coordinate tolerance
5. Saves the result as a new parquet file

Usage:
    python -m moonpies.add_weather_to_harmonized \
        --input data/harmonized.parquet \
        --output data/harmonized_with_weather.parquet \
        --tolerance 0.01 \
        --start-date 2020-01-01 \
        --end-date 2020-12-31

Note: This is a large operation. For 2020 data only, it will still be
significant. Consider running for specific months first.
"""

import argparse
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple, Union
import time

import polars as pl

from moonpies.meteomatics import fetch_weather_batch, DEFAULT_PARAMS


def get_unique_locations_dates(
    df: pl.DataFrame,
    lat_col: str = 'latitude',
    lon_col: str = 'longitude',
    date_col: str = 'acq_date',
    tolerance: float = 0.01
) -> pl.DataFrame:
    """
    Get unique location+date combinations, rounded to tolerance.
    
    Args:
        df: Input DataFrame with FIRMS data
        lat_col: Name of latitude column
        lon_col: Name of longitude column
        date_col: Name of date column
        tolerance: Coordinate tolerance in degrees for grouping
    
    Returns:
        DataFrame with unique rounded_lat, rounded_lon, date combinations
    """
    # Round coordinates to tolerance
    multiplier = 1.0 / tolerance
    
    unique_df = (
        df
        .with_columns(
            ((pl.col(lat_col) * multiplier).cast(int) / multiplier).alias('rounded_lat'),
            ((pl.col(lon_col) * multiplier).cast(int) / multiplier).alias('rounded_lon'),
        )
        .select(['rounded_lat', 'rounded_lon', date_col])
        .unique()
    )
    
    return unique_df


def create_weather_lookup(
    unique_locations: pl.DataFrame,
    params: List[str] = None,
    rate_limit: float = 0.5,
    progress_callback: Optional[callable] = None
) -> pl.DataFrame:
    """
    Create a weather lookup table for unique location+date combinations.
    
    Args:
        unique_locations: DataFrame with rounded_lat, rounded_lon, acq_date columns
        params: List of weather parameters to fetch
        rate_limit: Seconds between API requests
        progress_callback: Function to call with progress updates
    
    Returns:
        DataFrame with weather data for each unique location+date
    """
    if params is None:
        params = DEFAULT_PARAMS
    
    # Group by date
    dates = unique_locations['acq_date'].unique().sort()
    
    all_weather = []
    total_combinations = len(unique_locations)
    processed = 0
    
    for date in dates:
        # Get locations for this date
        date_locations = unique_locations.filter(pl.col('acq_date') == date)
        
        # Convert to timestamp (use noon UTC for daily data)
        timestamp = datetime(
            date.year, date.month, date.day,
            12, 0, tzinfo=timezone.utc
        )
        
        # Get coordinates
        coordinates = list(zip(
            date_locations['rounded_lat'].to_list(),
            date_locations['rounded_lon'].to_list()
        ))
        
        print(f"Fetching weather for {date}: {len(coordinates)} locations")
        
        # Fetch weather for these coordinates
        weather_data = fetch_weather_batch(
            coordinates=coordinates,
            timestamp=timestamp,
            params=params,
            rate_limit=rate_limit,
            progress_callback=lambda i, total, result: None
        )
        
        # Process results
        for i, wd in enumerate(weather_data):
            if wd is not None:
                # Add rounded coordinates and date for matching
                wd['rounded_lat'] = date_locations['rounded_lat'].to_list()[i]
                wd['rounded_lon'] = date_locations['rounded_lon'].to_list()[i]
                wd['acq_date'] = date
                all_weather.append(wd)
            
            processed += 1
            if progress_callback:
                progress_callback(processed, total_combinations)
        
        # Rate limit between dates
        time.sleep(rate_limit)
    
    if not all_weather:
        return pl.DataFrame()
    
    return pl.DataFrame(all_weather)


def add_weather_to_harmonized(
    input_path: Union[str, Path],
    output_path: Union[str, Path],
    tolerance: float = 0.01,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    params: Optional[List[str]] = None,
    rate_limit: float = 0.5,
    batch_size: Optional[int] = None
) -> None:
    """
    Main function to add weather data to harmonized FIRMS file.
    
    Args:
        input_path: Path to input harmonized.parquet file
        output_path: Path to save output parquet file
        tolerance: Coordinate tolerance in degrees for matching (default: 0.01 ≈ 1.1km)
        start_date: Optional start date (YYYY-MM-DD) to filter data
        end_date: Optional end date (YYYY-MM-DD) to filter data
        params: List of weather parameters to fetch (default: DEFAULT_PARAMS)
        rate_limit: Seconds between API requests (default: 0.5)
        batch_size: Process data in batches of this size (for memory efficiency)
    """
    input_path = Path(input_path)
    output_path = Path(output_path)
    
    print("="*70)
    print("Adding Meteomatics Weather Data to Harmonized FIRMS File")
    print("="*70)
    
    # Read input file
    print(f"\n1. Reading input file: {input_path}")
    df = pl.read_parquet(input_path)
    print(f"   Loaded {len(df):,} rows")
    print(f"   Columns: {len(df.columns)}")
    
    # Filter by date if specified
    if start_date or end_date:
        print(f"\n2. Filtering by date range...")
        if start_date:
            start_dt = datetime.strptime(start_date, '%Y-%m-%d').date()
            df = df.filter(pl.col('acq_date') >= start_dt)
            print(f"   Filtered to dates >= {start_date}")
        if end_date:
            end_dt = datetime.strptime(end_date, '%Y-%m-%d').date()
            df = df.filter(pl.col('acq_date') <= end_dt)
            print(f"   Filtered to dates <= {end_date}")
        print(f"   Remaining: {len(df):,} rows")
    
    # Get unique locations+dates
    print(f"\n3. Identifying unique locations+dates with tolerance {tolerance}°...")
    unique_locations = get_unique_locations_dates(df, tolerance=tolerance)
    print(f"   Found {len(unique_locations):,} unique location+date combinations")
    
    # Estimate API requests and time
    estimated_requests = len(unique_locations)
    estimated_hours = estimated_requests * rate_limit / 3600
    
    print(f"\n4. Estimated workload:")
    print(f"   API requests: {estimated_requests:,}")
    print(f"   At {rate_limit}s/request: {estimated_hours:.1f} hours ({estimated_hours/24:.2f} days)")
    
    # Ask for confirmation if many requests
    if estimated_requests > 1000:
        proceed = input(f"\n   Proceed with {estimated_requests:,} requests? (y/n): ")
        if proceed.lower() != 'y':
            print("   Aborted.")
            return
    
    # Create weather lookup table
    print(f"\n5. Fetching weather data...")
    weather_lookup = create_weather_lookup(
        unique_locations,
        params=params,
        rate_limit=rate_limit,
        progress_callback=lambda p, t: print(f"   Progress: {p}/{t} ({p/t*100:.1f}%)", end='\r')
    )
    
    print(f"\n   Retrieved {len(weather_lookup):,} weather records")
    
    # Add rounded coordinates to original dataframe
    print(f"\n6. Matching weather data to FIRMS records...")
    multiplier = 1.0 / tolerance
    
    df_with_rounded = df.with_columns(
        ((pl.col('latitude') * multiplier).cast(int) / multiplier).alias('rounded_lat'),
        ((pl.col('longitude') * multiplier).cast(int) / multiplier).alias('rounded_lon'),
    )
    
    # Join with weather data
    result = df_with_rounded.join(
        weather_lookup,
        on=['rounded_lat', 'rounded_lon', 'acq_date'],
        how='left'
    )
    
    # Drop rounded coordinate columns
    result = result.drop(['rounded_lat', 'rounded_lon'])
    
    print(f"\n7. Saving result...")
    result.write_parquet(output_path)
    
    # Count how many records got weather data
    weather_cols = [c for c in result.columns if c in [p.replace(':', '_').replace('/', '_') for p in (params or DEFAULT_PARAMS)]]
    if weather_cols:
        records_with_weather = result.filter(pl.col(weather_cols[0]).is_not_null()).n_rows
        print(f"   Total records: {len(result):,}")
        print(f"   Records with weather data: {records_with_weather:,}")
        print(f"   Coverage: {records_with_weather/len(result)*100:.1f}%")
    
    print(f"\n✅ Complete! Output saved to: {output_path}")
    
    return result


def main():
    parser = argparse.ArgumentParser(
        description='Add Meteomatics weather data to harmonized FIRMS parquet file'
    )
    parser.add_argument(
        '--input',
        type=str,
        default='data/harmonized.parquet',
        help='Input parquet file (default: data/harmonized.parquet)'
    )
    parser.add_argument(
        '--output',
        type=str,
        default='data/harmonized_with_weather.parquet',
        help='Output parquet file (default: data/harmonized_with_weather.parquet)'
    )
    parser.add_argument(
        '--tolerance',
        type=float,
        default=0.01,
        help='Coordinate tolerance in degrees (default: 0.01 ≈ 1.1km)'
    )
    parser.add_argument(
        '--start-date',
        type=str,
        default=None,
        help='Start date (YYYY-MM-DD) to filter data'
    )
    parser.add_argument(
        '--end-date',
        type=str,
        default=None,
        help='End date (YYYY-MM-DD) to filter data'
    )
    parser.add_argument(
        '--rate',
        type=float,
        default=0.5,
        help='Rate limit in seconds between API requests (default: 0.5)'
    )
    
    args = parser.parse_args()
    
    add_weather_to_harmonized(
        input_path=args.input,
        output_path=args.output,
        tolerance=args.tolerance,
        start_date=args.start_date,
        end_date=args.end_date,
        params=DEFAULT_PARAMS,
        rate_limit=args.rate
    )


if __name__ == "__main__":
    main()
