# Moonpies

## Overview

Repository of the Moonpies team for the 2026 NASA space apps challenge.

Team members:

- Jonas Gstöttenmayr (<jojo.gstoettenmayr@gmail.com>)
- Stephanie Gstöttenmayr (<stephanie.gstoettenmayr@gmail.com>)
- David Thomas Lee (<lee.davidtom@proton.me>)
- Gabriel Boboc (<boboc.gabriel04@gmail.com>)

## Quickstart Guide: Meteomatics Weather Data

This guide helps you fetch and analyze weather data from the Meteomatics API for fire risk analysis.

### Prerequisites

- Python ≥ 3.11
- [uv](https://docs.astral.sh/uv/) package manager
- Meteomatics API credentials (provided in `meteo-api.env`)

### Setup Environment

```bash
# Install dependencies using uv
uv sync

# Activate the virtual environment
source .venv/bin/activate
```

### Prepare data

```bash
# Get data from NASA
uv run python data/download_firms_europe.py

# After previous one is done
# Process the data
uv run src/process_data.py
```

### Starting webpage

The main application provides a web interface for exploring fire and weather data correlations.

```bash
# 2. Run the server
uv run python src/app.py

# 3. Open in browser
# http://localhost:5000
```

## Additional Exploration with Meteomatics

### Example: Fetch Weather for a Single Fire Event

Fetch weather data for the highest FRP fire in Austria 2020:

```bash
# Fetch 2 months before, fire day, and 7 days after
uv run python meteomatics/fetch_weather_for_single_fire.py \
    --months 2 \
    --days-after 7 \
    --rate 0.5

# Output: data/single_fire_with_weather.parquet
```

This creates a parquet file with:

- 60+ days of weather data
- Selection of weather parameters (temperature, humidity, wind speed, wind direction, precipitation 1h, precipitation 24h, evaporation)
- Fire metadata (FRP, location, date)
- Fire detection flag

### Option 2: Fetch Weather for Multiple High FRP Fires

```bash
# Fetch weather for all fires with FRP >= 50 MW
python meteomatics/fetch_weather_for_high_frp_fires.py \
    --min-frp 50 \
    --months 2 \
    --days-after 7 \
    --rate 0.5

# Output: data/high_frp_fires_with_weather.parquet
```

### Option 3: Visualize Weather Data

Create an interactive HTML visualization:

```bash
# Generate HTML with map and charts
uv run python meteomatics/visualize_fire_weather.py
```

This creates:

- Interactive map showing fire location in Austria
- Time series charts of all weather parameters
- Summary statistics
- Fire day highlighted

## Results

The project merges NASA FIRMS fire data of MODIS and VIIRS sensors to analyze fire risk factors. It harmonizes spatial and temporal datasets for Europe and provides processed outputs for analysis. The Flask web interface enables interactive exploration through maps and time series visualizations. Users can examine correlations between weather parameters and fire events.


## Architecture and Design

### Overview

The application follows a pipeline architecture: data ingestion → processing → visualization.

NASA FIRMS fire data and Meteomatics weather data are fetched independently, then merged based on spatial and temporal alignment. The processed data powers a Flask web application for interactive exploration.

### Key Components

- **Data Ingestion**: `data/` and `src/moonpies/data_ingestion.py` handle fetching and harmonizing raw FIRMS data
- **Weather Integration**: `src/moonpies/meteomatics.py` provides the Meteomatics API client
- **Data Processing**: Scripts in `src/moonpies/` merge fire and weather data, calculate correlations
- **Web Interface**: `src/app.py` serves a Flask application with interactive maps and charts

### Project Structure

```text
Moonpies/
├── data/               # Raw and processed data, data fetching scripts
├── src/                # Core application and processing logic
│   ├── app.py          # Flask web server
│   └── moonpies/       # Python package with data processing modules
├── meteomatics/        # Weather data fetching and visualization scripts
├── web/                # Static web assets
└── docs/               # Documentation
```

### References
All references used in this Hackathon can be found in [References](/docs/ REFERENCES.md)

### Glossary
All abbreviations and terms used in this Hackathon can be found in [Glossary](/docs/GLOSSARY.md)

### Future Work

Integrating more information from Meteomatics to correlate periods of low rain and low humidity and strong winds to fire safety risks.


## Contributing


## Resources

### Data bases

**NASA Fire Information for Resource Management System**: https://firms.modaps.eosdis.nasa.gov/
**Meteomatics API for weather data**: https://www.meteomatics.com/en/weather-api/

### Inspiration
