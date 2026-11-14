# Austria Weather Data for NASA Space Apps Challenge

This directory contains scripts to fetch historical weather data from the Meteomatics API for Austria (year 2020) and save it to CSV format for merging with NASA FIRMS fire data.

## Available Parameters

The following parameters are available through the Meteomatics API with your current credentials:

| Parameter | Unit | Description |
|-----------|------|-------------|
| `t_2m:C` | °C | Temperature at 2m height |
| `rh_2m:p` | % | Relative humidity at 2m height |
| `wind_speed_10m:ms` | m/s | Wind speed at 10m height |
| `wind_dir_10m:d` | ° | Wind direction at 10m height |
| `precip_1h:mm` | mm | Precipitation in the last hour |
| `precip_24h:mm` | mm | Precipitation in the last 24 hours |
| `evapotranspiration_24h:mm` | mm | Evapotranspiration in the last 24 hours |

## ⚠️ Forest Fire Risk Indices

**The following requested parameters are NOT available in the Meteomatics API:**
- Forest Fire Weather Index (FWI)
- Duff Moisture Code (DMC)
- Drought Code (DC)
- Initial Spread Index (ISI)
- Buildup Index (BUI)
- Fire Risk Index

### Alternatives for Fire Risk Data:

1. **Compute FWI from available data**: The Canadian Forest Fire Weather Index System can be computed from:
   - Temperature
   - Relative Humidity
   - Wind Speed
   - Precipitation
   - See: https://cwfis.cfs.nrcan.gc.ca/background/fwi

2. **NASA FIRMS Fire Data**: You already have this dataset, which includes active fire detections.

3. **Copernicus Emergency Management Service**: Provides fire risk maps for Europe.

4. **MODIS Fire Products**: NASA provides various fire-related products.

## Usage

### Quick Start

Fetch weather data for January 2020 with 0.5° resolution (~55km grid spacing):

```bash
cd /home/stephg/Projects/nasa-space-apps/Moonpies
data/fetch_austria_2020_practical.py --start 2020-01-01 --end 2020-01-31 --resolution 0.5
```

### Command Line Options

```
--start TEXT       Start date (YYYY-MM-DD) [default: 2020-01-01]
--end TEXT         End date (YYYY-MM-DD) [default: 2020-01-31]
--resolution FLOAT Grid resolution in degrees [default: 0.5]
--time-res TEXT    Time resolution: 'daily' or 'hourly' [default: daily]
--output TEXT      Output CSV file path [default: data/austria_weather_2020.csv]
--rate FLOAT       Rate limit in seconds between requests [default: 1.0]
--append           Append to existing CSV file
```

### Examples

1. **Fetch a single day at high resolution (0.1° ≈ 11km):**
   ```bash
   python data/fetch_austria_2020_practical.py \
       --start 2020-07-15 \
       --end 2020-07-15 \
       --resolution 0.1
   ```

2. **Fetch a month with hourly data:**
   ```bash
   python data/fetch_austria_2020_practical.py \
       --start 2020-07-01 \
       --end 2020-07-31 \
       --time-res hourly \
       --resolution 1.0
   ```

3. **Fetch full year with coarse resolution (faster):**
   ```bash
   python data/fetch_austria_2020_practical.py \
       --start 2020-01-01 \
       --end 2020-12-31 \
       --resolution 1.0
   ```

4. **Resume a previous fetch:**
   ```bash
   python data/fetch_austria_2020_practical.py \
       --start 2020-02-01 \
       --end 2020-02-29 \
       --append
   ```

## Grid Resolution Guide

| Resolution (°) | Approx. Distance | Grid Points for Austria | Daily Requests/Year |
|----------------|------------------|-------------------------|---------------------|
| 0.1 | ~11 km | ~150 | ~55,000 |
| 0.2 | ~22 km | ~35 | ~13,000 |
| 0.5 | ~55 km | ~8 | ~3,000 |
| 1.0 | ~110 km | ~4 | ~1,500 |
| 2.0 | ~220 km | ~2 | ~700 |

*Note: At 1 request/second, 55,000 requests = ~15 hours of continuous fetching*

## CSV Output Format

The CSV file contains the following columns:

```csv
lat,lon,timestamp,date,year,month,day,t_2m_C,rh_2m_p,wind_speed_10m_ms,wind_dir_10m_d,precip_1h_mm,precip_24h_mm,evapotranspiration_24h_mm
46.4,9.5,2020-01-01T12:00:00Z,2020-01-01,2020,1,1,3.4,19.8,1.0,162.8,0.0,0.0,0.69
46.4,11.5,2020-01-01T12:00:00Z,2020-01-01,2020,1,1,4.8,45.2,1.4,196.2,0.0,0.0,0.66
...
```

### Column Descriptions

- **lat**: Latitude in decimal degrees
- **lon**: Longitude in decimal degrees
- **timestamp**: UTC timestamp in ISO format
- **date**: Date in ISO format (YYYY-MM-DD)
- **year/month/day**: Date components for easy filtering
- **t_2m_C**: Temperature at 2m in Celsius
- **rh_2m_p**: Relative humidity at 2m in percent
- **wind_speed_10m_ms**: Wind speed at 10m in meters/second
- **wind_dir_10m_d**: Wind direction at 10m in degrees (0-360)
- **precip_1h_mm**: Precipitation in last hour in millimeters
- **precip_24h_mm**: Precipitation in last 24 hours in millimeters
- **evapotranspiration_24h_mm**: Evapotranspiration in last 24 hours in millimeters

## Merging with NASA FIRMS Data

The CSV includes `lat` and `lon` columns, which can be used to merge with NASA FIRMS fire data:

```python
import pandas as pd

# Load weather data
weather = pd.read_csv('austria_weather_2020.csv')

# Load FIRMS data (assuming it has latitude/longitude columns)
firm = pd.read_csv('firms_austria_2020.csv')

# Merge on latitude and longitude
merged = pd.merge(
    firm,
    weather,
    left_on=['latitude', 'longitude'],
    right_on=['lat', 'lon'],
    how='left'
)
```

For more accurate merging, you may need to:
1. Use spatial joins (e.g., with geopandas)
2. Match by nearest grid point
3. Account for different date formats

## Rate Limiting

The script includes rate limiting to avoid hitting API limits:
- Default: 1 request per second
- Adjust with `--rate` parameter
- Be aware of your Meteomatics API quota

## Error Handling

The script:
- Skips failed requests and continues
- Logs errors to stdout
- Saves successful data to CSV incrementally
- Can be resumed with `--append`

## Notes

1. **Historical Data Access**: Your Meteomatics account has access to historical data (2020).

2. **API Quota**: Be aware of your API request quota. Check your Meteomatics account for limits.

3. **Data Volume**: A full year at 0.1° resolution would require ~55,000 API requests. At 1 request/second, this takes ~15 hours.

4. **Fire Risk**: Since fire risk indices aren't available, consider:
   - Computing FWI from the available weather data
   - Using NASA FIRMS active fire data as a proxy
   - Finding alternative fire risk datasets

## Files

- `fetch_austria_2020_practical.py`: Main data fetching script
- `fetch_austria_2020.py`: Original version with parameter testing
- `austria_weather_2020.csv`: Output file (created when script runs)

## Requirements

- Python 3.13+
- `requests` library
- `python-dotenv` library
- Meteomatics API credentials in `meteo-api.env`
