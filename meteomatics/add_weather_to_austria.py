#!/usr/bin/env python3
"""
Add Meteomatics weather data to Austria FIRMS data from harmonized.parquet.

This script:
1. Filters harmonized.parquet to Austria region (lat 46-49, lon 9-17)
2. Optionally filters to specific date range (e.g., year 2020)
3. Identifies unique (latitude, longitude, date) combinations with tolerance
4. Fetches weather data for each unique location+date from Meteomatics API
5. Merges weather data back to FIRMS data
6. Saves result as parquet file

Usage:
    python add_weather_to_austria.py --year 2020 --tolerance 0.01
    
    Options:
        --year YYYY       Filter to specific year (default: all years)
        --start YYYY-MM-DD  Start date
        --end YYYY-MM-DD    End date
        --tolerance FLOAT  Coordinate tolerance in degrees (default: 0.01)
        --rate FLOAT      Rate limit in seconds (default: 0.5)
        --output FILE     Output file (default: data/austria_with_weather.parquet)
        --test            Use small subset for testing
"""

import argparse
from datetime import datetime
from pathlib import Path

import polars as pl

from moonpies.add_weather_to_harmonized import (
    get_unique_locations_dates,
    create_weather_lookup,
    DEFAULT_PARAMS
)


DATA_DIR = Path(__file__).resolve().parents[1] / "data"
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "output"


def filter_austria(df: pl.DataFrame) -> pl.DataFrame:
    """Filter DataFrame to Austria region."""
    return df.filter(
        (pl.col('latitude') >= 46) & 
        (pl.col('latitude') <= 49) &
        (pl.col('longitude') >= 9) & 
        (pl.col('longitude') <= 17)
    )


def main():
    parser = argparse.ArgumentParser(
        description='Add weather data to Austria FIRMS data'
    )
    parser.add_argument(
        '--year',
        type=int,
        default=None,
        help='Filter to specific year'
    )
    parser.add_argument(
        '--start',
        type=str,
        default=None,
        help='Start date (YYYY-MM-DD)'
    )
    parser.add_argument(
        '--end',
        type=str,
        default=None,
        help='End date (YYYY-MM-DD)'
    )
    parser.add_argument(
        '--tolerance',
        type=float,
        default=0.01,
        help='Coordinate tolerance in degrees (default: 0.01 ≈ 1.1km)'
    )
    parser.add_argument(
        '--rate',
        type=float,
        default=0.5,
        help='Rate limit in seconds between API requests (default: 0.5)'
    )
    parser.add_argument(
        '--output',
        type=str,
        default='data/austria_with_weather.parquet',
        help='Output file path'
    )
    parser.add_argument(
        '--test',
        action='store_true',
        help='Use small subset for testing'
    )
    
    args = parser.parse_args()
    
    input_path = DATA_DIR / "harmonized.parquet"
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    print("="*70)
    print("Adding Meteomatics Weather Data to Austria FIRMS Data")
    print("="*70)
    
    # Step 1: Load data
    print(f"\n1. Loading data from {input_path}...")
    df = pl.read_parquet(input_path)
    print(f"   Total rows: {len(df):,}")
    
    # Step 2: Filter to Austria
    print(f"\n2. Filtering to Austria region...")
    df = filter_austria(df)
    print(f"   Austria rows: {len(df):,}")
    
    # Step 3: Filter by date
    if args.year:
        year_start = datetime(args.year, 1, 1).date()
        year_end = datetime(args.year, 12, 31).date()
        df = df.filter(
            (pl.col('acq_date') >= year_start) & 
            (pl.col('acq_date') <= year_end)
        )
        print(f"   Filtered to year {args.year}: {len(df):,}")
    
    if args.start:
        start_date = datetime.strptime(args.start, '%Y-%m-%d').date()
        df = df.filter(pl.col('acq_date') >= start_date)
        print(f"   Filtered to start date {args.start}: {len(df):,}")
    
    if args.end:
        end_date = datetime.strptime(args.end, '%Y-%m-%d').date()
        df = df.filter(pl.col('acq_date') <= end_date)
        print(f"   Filtered to end date {args.end}: {len(df):,}")
    
    # Test mode: use small subset
    if args.test:
        df = df.limit(100)
        print(f"   Test mode: using {len(df)} rows")
    
    # Step 4: Get unique locations+dates
    print(f"\n3. Identifying unique locations+dates with tolerance {args.tolerance}°...")
    unique_locations = get_unique_locations_dates(df, tolerance=args.tolerance)
    print(f"   Unique combinations: {len(unique_locations):,}")
    
    # Estimate
    estimated_requests = len(unique_locations)
    estimated_hours = estimated_requests * args.rate / 3600
    print(f"\n4. Estimated workload:")
    print(f"   API requests: {estimated_requests:,}")
    print(f"   At {args.rate}s/request: {estimated_hours:.1f} hours")
    
    # Confirm
    if estimated_requests > 100 and not args.test:
        proceed = input(f"\n   Proceed with {estimated_requests:,} requests? (y/n): ")
        if proceed.lower() != 'y':
            print("   Aborted.")
            return
    
    # Step 5: Fetch weather data
    print(f"\n5. Fetching weather data...")
    weather_lookup = create_weather_lookup(
        unique_locations,
        params=DEFAULT_PARAMS,
        rate_limit=args.rate,
        progress_callback=lambda p, t: print(f"   Progress: {p}/{t} ({p/t*100:.1f}%)", end='\r')
    )
    print(f"\n   Retrieved {len(weather_lookup):,} weather records")
    
    # Step 6: Merge with FIRMS data
    print(f"\n6. Merging weather data with FIRMS records...")
    multiplier = 1.0 / args.tolerance
    
    df_with_rounded = df.with_columns(
        ((pl.col('latitude') * multiplier).cast(int) / multiplier).alias('rounded_lat'),
        ((pl.col('longitude') * multiplier).cast(int) / multiplier).alias('rounded_lon'),
    )
    
    result = df_with_rounded.join(
        weather_lookup,
        on=['rounded_lat', 'rounded_lon', 'acq_date'],
        how='left'
    ).drop(['rounded_lat', 'rounded_lon'])
    
    # Step 7: Save
    print(f"\n7. Saving result to {output_path}...")
    result.write_parquet(output_path)
    
    # Stats
    weather_cols = [c for c in result.columns if c in [p.replace(':', '_').replace('/', '_') for p in DEFAULT_PARAMS]]
    if weather_cols:
        records_with_weather = result.filter(pl.col(weather_cols[0]).is_not_null()).n_rows
        print(f"   Total records: {len(result):,}")
        print(f"   Records with weather: {records_with_weather:,}")
        print(f"   Coverage: {records_with_weather/len(result)*100:.1f}%")
    
    print(f"\n✅ Complete! Output saved to: {output_path}")


if __name__ == "__main__":
    main()
