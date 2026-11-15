"""
Example: Fetch weather data for FIRMS fire detection points.

This script demonstrates how to:
1. Load FIRMS fire detection data (MODIS, VIIRS, VIIRS-SNPP)
2. Fetch weather data for each unique fire location
3. Merge the weather data with the fire data
4. Save the results to CSV

Usage:
    python examples/fetch_weather_for_firms.py --date 2020-07-15

Note: This will make API requests to Meteomatics. Be aware of rate limits.
"""

import argparse
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

from moonpies import get_weather_for_firms, merge_weather_with_firms

# Project directories
DATA_DIR = Path(__file__).resolve().parents[1] / "data"
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "output"
OUTPUT_DIR.mkdir(exist_ok=True)


def load_firms_data():
    """Load all FIRMS datasets."""
    datasets = {}
    
    # MODIS
    modis_path = DATA_DIR / "modis" / "modis_2020_Austria.csv"
    if modis_path.exists():
        datasets['modis'] = pl.read_csv(modis_path)
        print(f"Loaded MODIS data: {len(datasets['modis']):,} rows")
    
    # VIIRS (JPSS1)
    viirs_path = DATA_DIR / "viirs" / "viirs-jpss1_2020_Austria.csv"
    if viirs_path.exists():
        datasets['viirs'] = pl.read_csv(viirs_path)
        print(f"Loaded VIIRS-JPSS1 data: {len(datasets['viirs']):,} rows")
    
    # VIIRS (SNPP)
    snpp_path = DATA_DIR / "viirs-snpp" / "viirs-snpp_2020_Austria.csv"
    if snpp_path.exists():
        datasets['snpp'] = pl.read_csv(snpp_path)
        print(f"Loaded VIIRS-SNPP data: {len(datasets['snpp']):,} rows")
    
    return datasets


def add_date_columns(df: pl.DataFrame, date_col: str = 'acq_date') -> pl.DataFrame:
    """Add year, month, day columns from acquisition date."""
    if date_col in df.columns:
        return df.with_columns(
            pl.col(date_col).str.slice(0, 4).cast(int).alias('year'),
            pl.col(date_col).str.slice(5, 2).cast(int).alias('month'),
            pl.col(date_col).str.slice(8, 2).cast(int).alias('day'),
        )
    return df


def main():
    parser = argparse.ArgumentParser(
        description='Fetch weather data for FIRMS fire detections'
    )
    parser.add_argument(
        '--date',
        type=str,
        required=True,
        help='Date to fetch weather for (YYYY-MM-DD)'
    )
    parser.add_argument(
        '--hour',
        type=int,
        default=12,
        help='Hour of day for weather data (UTC) [default: 12]'
    )
    parser.add_argument(
        '--rate',
        type=float,
        default=1.0,
        help='Rate limit in seconds between API requests [default: 1.0]'
    )
    parser.add_argument(
        '--output',
        type=str,
        default=None,
        help='Output CSV path (default: output/firms_with_weather_{date}.csv)'
    )
    parser.add_argument(
        '--test',
        action='store_true',
        help='Test with a small subset of data (5 points)'
    )
    
    args = parser.parse_args()
    
    # Parse date
    year, month, day = map(int, args.date.split('-'))
    timestamp = datetime(year, month, day, args.hour, 0, tzinfo=timezone.utc)
    
    print(f"Fetching weather data for {timestamp.isoformat()}")
    print("=" * 60)
    
    # Load FIRMS data
    print("\n1. Loading FIRMS data...")
    datasets = load_firms_data()
    
    if not datasets:
        print("No FIRMS data found. Please ensure CSV files are in:")
        print(f"  {DATA_DIR / 'modis'}")
        print(f"  {DATA_DIR / 'viirs'}")
        print(f"  {DATA_DIR / 'viirs-snpp'}")
        return
    
    # Process each dataset
    all_weather = []
    all_firms = []
    
    for sensor_name, df in datasets.items():
        print(f"\n2. Processing {sensor_name} data...")
        
        # Add date columns
        df = add_date_columns(df)
        
        # Filter by date if test mode
        if args.test:
            df = df.limit(5)
            print(f"   Using {len(df)} test points")
        
        # Get weather data
        weather_data = get_weather_for_firms(
            df,
            timestamp,
            lat_col='latitude',
            lon_col='longitude',
            rate_limit=args.rate
        )
        
        # Merge with fire data
        merged = merge_weather_with_firms(
            df,
            weather_data,
            lat_col='latitude',
            lon_col='longitude'
        )
        
        # Add sensor column
        merged = merged.with_columns(pl.lit(sensor_name).alias('sensor'))
        
        all_weather.extend([w for w in weather_data if w is not None])
        all_firms.append(merged)
    
    # Combine all datasets
    if len(all_firms) > 1:
        final_df = pl.concat(all_firms)
    elif len(all_firms) == 1:
        final_df = all_firms[0]
    else:
        final_df = pl.DataFrame()
    
    print(f"\n3. Results:")
    print(f"   Total fire detections: {len(final_df):,}")
    print(f"   Columns: {len(final_df.columns)}")
    print(f"   Weather columns: {[c for c in final_df.columns if c not in ['latitude', 'longitude', 'sensor']]}")
    
    # Save output
    if args.output:
        output_path = Path(args.output)
    else:
        output_path = OUTPUT_DIR / f"firms_with_weather_{args.date}.csv"
    
    final_df.write_csv(output_path)
    print(f"\n✅ Data saved to: {output_path}")
    
    # Show sample
    print(f"\n4. Sample data:")
    print(final_df.limit(5))


if __name__ == "__main__":
    main()
