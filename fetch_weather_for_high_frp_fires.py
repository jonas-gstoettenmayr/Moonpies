#!/usr/bin/env python3
"""
Fetch weather data for high FRP fire events in Austria 2020.

This script:
1. Identifies high FRP fire events in Austria for 2020
2. For each fire, fetches weather data for:
   - ~2 months BEFORE the fire (to analyze pre-fire conditions)
   - The DURATION of the fire (all detection dates)
   - ~1 week AFTER the fire (to see post-fire conditions)
3. Returns a parquet file with fire data + weather data merged

Usage:
    python fetch_weather_for_high_frp_fires.py --min-frp 50 --output high_frp_fires_with_weather.parquet
    
Options:
    --min-frp FLOAT    Minimum FRP threshold (default: 50 MW)
    --months INT       Months before fire to fetch (default: 2)
    --days-after INT   Days after fire to fetch (default: 7)
    --tolerance FLOAT  Coordinate tolerance in degrees (default: 0.01)
    --rate FLOAT       Rate limit in seconds (default: 0.5)
    --output FILE      Output parquet file
    --test             Test with small subset
"""

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Dict, Optional
import time

import polars as pl

from moonpies.meteomatics import fetch_weather_batch, DEFAULT_PARAMS


def find_high_frp_fires(
    df: pl.DataFrame,
    min_frp: float = 50.0,
    austria_bbox: Optional[Dict[str, float]] = None
) -> pl.DataFrame:
    """
    Find high FRP fire events in Austria.
    
    Args:
        df: Input DataFrame with FIRMS data
        min_frp: Minimum FRP threshold in MW
        austria_bbox: Optional bounding box to filter to Austria
    
    Returns:
        DataFrame with high FRP fires, grouped by fire event
    """
    # Filter to Austria if bbox provided
    if austria_bbox:
        df = df.filter(
            (pl.col('latitude') >= austria_bbox['min_lat']) &
            (pl.col('latitude') <= austria_bbox['max_lat']) &
            (pl.col('longitude') >= austria_bbox['min_lon']) &
            (pl.col('longitude') <= austria_bbox['max_lon'])
        )
    
    # Filter by FRP
    high_frp = df.filter(pl.col('frp') >= min_frp)
    
    # Group by location and date to identify fire events
    # A fire event is multiple detections at the same location on the same day
    fire_events = (
        high_frp
        .group_by(['latitude', 'longitude', 'acq_date'])
        .agg(
            pl.col('frp').max().alias('max_frp'),
            pl.col('frp').sum().alias('total_frp'),
            pl.col('frp').count().alias('detection_count'),
            pl.col('brightness').max().alias('max_brightness'),
            pl.col('satellite').first().alias('satellite'),
            pl.col('confidence').first().alias('confidence'),
            pl.col('acq_time').first().alias('first_acq_time'),
        )
        .sort('max_frp', descending=True)
    )
    
    return fire_events


def get_fire_duration(
    df: pl.DataFrame,
    fire_event: Dict,
    tolerance: float = 0.01
) -> Dict:
    """
    Determine the duration of a fire event.
    
    Args:
        df: Full FIRMS DataFrame
        fire_event: Dictionary with fire event info (lat, lon, date)
        tolerance: Tolerance for matching nearby fires
    
    Returns:
        Dictionary with start_date, end_date, and duration_days
    """
    lat = fire_event['latitude']
    lon = fire_event['longitude']
    event_date = fire_event['acq_date']
    
    # Find all fires near this location (within tolerance)
    multiplier = 1.0 / tolerance
    nearby = df.filter(
        ((pl.col('latitude') * multiplier).cast(int) == (lat * multiplier).cast(int)) &
        ((pl.col('longitude') * multiplier).cast(int) == (lon * multiplier).cast(int))
    )
    
    if len(nearby) == 0:
        return {
            'start_date': event_date,
            'end_date': event_date,
            'duration_days': 1
        }
    
    # Get date range
    start_date = nearby['acq_date'].min()
    end_date = nearby['acq_date'].max()
    duration_days = (end_date - start_date).dt.days + 1
    
    return {
        'start_date': start_date,
        'end_date': end_date,
        'duration_days': duration_days
    }


def fetch_weather_for_fire_event(
    fire_event: Dict,
    months_before: int = 2,
    days_after: int = 7,
    params: Optional[List[str]] = None,
    rate_limit: float = 0.5
) -> List[Dict]:
    """
    Fetch weather data for a fire event, including pre-fire and post-fire periods.
    
    Args:
        fire_event: Dictionary with fire event info (lat, lon, date)
        months_before: Number of months before fire to fetch weather
        days_after: Number of days after fire to fetch weather
        params: Weather parameters to fetch
        rate_limit: Rate limit in seconds
    
    Returns:
        List of weather data dictionaries
    """
    lat = fire_event['latitude']
    lon = fire_event['longitude']
    fire_date = fire_event['acq_date']
    
    if params is None:
        params = DEFAULT_PARAMS
    
    # Determine date range
    start_date = fire_date - timedelta(days=months_before * 30)
    end_date = fire_date + timedelta(days=days_after)
    
    # Convert to datetime objects for iteration
    current_date = datetime(start_date.year, start_date.month, start_date.day, 12, 0, tzinfo=timezone.utc)
    end_datetime = datetime(end_date.year, end_date.month, end_date.day, 12, 0, tzinfo=timezone.utc)
    
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
            wd['fire_lat'] = lat
            wd['fire_lon'] = lon
            wd['fire_date'] = fire_date
            wd['days_from_fire'] = (current_date.date() - fire_date).days
            all_weather.append(wd)
        
        current_date += timedelta(days=1)
        time.sleep(rate_limit)
    
    return all_weather


def main():
    parser = argparse.ArgumentParser(
        description='Fetch weather data for high FRP fire events'
    )
    parser.add_argument(
        '--min-frp',
        type=float,
        default=50.0,
        help='Minimum FRP threshold in MW (default: 50)'
    )
    parser.add_argument(
        '--months',
        type=int,
        default=2,
        help='Months before fire to fetch weather (default: 2)'
    )
    parser.add_argument(
        '--days-after',
        type=int,
        default=7,
        help='Days after fire to fetch weather (default: 7)'
    )
    parser.add_argument(
        '--tolerance',
        type=float,
        default=0.01,
        help='Coordinate tolerance in degrees (default: 0.01)'
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
        default='data/high_frp_fires_with_weather.parquet',
        help='Output parquet file (default: data/high_frp_fires_with_weather.parquet)'
    )
    parser.add_argument(
        '--test',
        action='store_true',
        help='Test with small subset'
    )
    
    args = parser.parse_args()
    
    # Austria bounding box
    AUSTRIA_BBOX = {
        'min_lat': 46.0,
        'max_lat': 49.0,
        'min_lon': 9.0,
        'max_lon': 17.0
    }
    
    print("="*70)
    print("Fetching Weather Data for High FRP Fire Events")
    print("="*70)
    
    # Load data
    print("\n1. Loading FIRMS data...")
    df = pl.read_parquet('data/harmonized.parquet')
    print(f"   Total rows: {len(df):,}")
    
    # Filter to 2020 Austria
    print("\n2. Filtering to Austria 2020...")
    df_2020 = df.filter(
        (pl.col('acq_date') >= datetime(2020, 1, 1).date()) &
        (pl.col('acq_date') <= datetime(2020, 12, 31).date())
    )
    df_austria = df_2020.filter(
        (pl.col('latitude') >= AUSTRIA_BBOX['min_lat']) &
        (pl.col('latitude') <= AUSTRIA_BBOX['max_lat']) &
        (pl.col('longitude') >= AUSTRIA_BBOX['min_lon']) &
        (pl.col('longitude') <= AUSTRIA_BBOX['max_lon'])
    )
    print(f"   Austria 2020 rows: {len(df_austria):,}")
    
    # Find high FRP fires
    print(f"\n3. Finding high FRP fires (>= {args.min_frp} MW)...")
    high_frp_fires = find_high_frp_fires(df_austria, min_frp=args.min_frp)
    print(f"   Found {len(high_frp_fires)} high FRP fire events")
    
    # Show top fires
    print(f"\n   Top 10 fires by max FRP:")
    print(high_frp_fires.limit(10))
    
    # Process each fire
    if args.test:
        high_frp_fires = high_frp_fires.limit(1)
        print(f"\n   Test mode: processing only 1 fire")
    
    all_results = []
    
    for i, fire_row in enumerate(high_frp_fires.iter_rows(named=True)):
        print(f"\n4. Processing fire {i+1}/{len(high_frp_fires)}:")
        print(f"   Location: ({fire_row['latitude']:.4f}, {fire_row['longitude']:.4f})")
        print(f"   Date: {fire_row['acq_date']}")
        print(f"   Max FRP: {fire_row['max_frp']:.1f} MW")
        print(f"   Detections: {fire_row['detection_count']}")
        
        # Fetch weather for this fire
        weather_data = fetch_weather_for_fire_event(
            fire_row,
            months_before=args.months,
            days_after=args.days_after,
            params=DEFAULT_PARAMS,
            rate_limit=args.rate
        )
        
        print(f"   Retrieved {len(weather_data)} weather records")
        
        # Add fire info to each weather record
        for wd in weather_data:
            wd.update({
                'fire_max_frp': fire_row['max_frp'],
                'fire_total_frp': fire_row['total_frp'],
                'fire_detection_count': fire_row['detection_count'],
                'fire_brightness': fire_row['max_brightness'],
                'fire_satellite': fire_row['satellite'],
                'fire_confidence': fire_row['confidence'],
            })
            all_results.append(wd)
        
        # Save progress
        if (i + 1) % 5 == 0:
            progress_df = pl.DataFrame(all_results)
            progress_path = f"{args.output}.progress.parquet"
            progress_df.write_parquet(progress_path)
            print(f"   Saved progress to {progress_path}")
    
    # Create final DataFrame
    print(f"\n5. Creating final DataFrame...")
    result_df = pl.DataFrame(all_results)
    
    # Sort by fire date and days from fire
    result_df = result_df.sort(['fire_date', 'days_from_fire'])
    
    print(f"   Total weather records: {len(result_df):,}")
    
    # Save
    print(f"\n6. Saving to {args.output}...")
    result_df.write_parquet(args.output)
    
    print(f"\n✅ Complete! Output saved to: {args.output}")
    print(f"\nColumns in output: {len(result_df.columns)}")
    print(f"Sample data:")
    print(result_df.limit(5))


if __name__ == "__main__":
    main()
