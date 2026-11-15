# NASA SPACE APPS 2026 Challenge
## Topic: Harmonization of MODIS and VIIRS Hot Spots

### Overview


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

### Architecture and Design

Due to time constraint, 

#### Super Intelligence 

The following SI-tools were used in the scope of this challenge

| Tool | Application | 
| --- | --- |
| Brave Ask | Refine search results, summarise FAQ documents and code generation for frontend / web development |
| Mistral Vibe | Code generation, and analysis of Meteometic data |
| ChatGPT 5.6 | Unpack and analyse MODIS and VIIRS from FRIMS | 

### Project Structure

```text
Moonpies/
├── .gitignore
├── .python-version
├── LICENSE
├── README.md
├── meteo-api.env              # Meteomatics API credentials
├── pyproject.toml
├── uv.lock
├── data/
│   ├── README.md              # Weather data fetching guide
│   ├── download_firms_europe.py  # Download raw FIRMS data for Europe
│   ├── fetch_austria_2020.py
│   ├── fetch_austria_2020_practical.py
│   ├── harmonized.parquet         # Combined FIRMS data, generated
│   ├── harmonize_grid.parquet     # Grid mixed FIRMS data, generated, needed for web page
│   ├── single_fire_with_weather.parquet
│   └── unpack_zip.py # script for extracting country from yearly zip
├── docs/
│   ├── GLOSSARY.md
│   ├── REFERENCES.md
│   └── merge.md
├── examples/
│   ├── fetch_weather_for_firms.py
│   └── meteomatics_example.py
├── meteomatics/                # Meteomatics-related scripts
│   ├── add_weather_to_austria.py
│   ├── fetch_weather_for_high_frp_fires.py
│   ├── fetch_weather_for_single_fire.py
│   ├── fire_weather_visualization.html
│   ├── meteomatics-test.ipynb
│   └── visualize_fire_weather.py
├── src/
│   ├── __init__.py
│   ├── app.py
│   ├── explore.ipynb
│   └── moonpies/              # Python package
│       ├── __init__.py
│       ├── add_weather_to_harmonized.py
│       ├── consts.py
│       ├── data_ingestion.py
│       ├── merge.py
│       └── meteomatics.py    # Meteomatics API client
├── tests/
│   └── test_meteomatics.py
└── web/
    ├── europe_activity.json
    └── index.html
```

### Results


### Resources
#### Databases

**NASA Fire Information for Resource Management System**: [https://firms.modaps.eosdis.nasa.gov/](https://firms.modaps.eosdis.nasa.gov/) 
**Meteomatics API for weather data**: [https://www.meteomatics.com/en/weather-api/](https://www.meteomatics.com/en/weather-api/)

##### Meteomatics Data

For detailed information on available weather parameters, API usage, and data fetching options, see:
- [data/README.md](data/README.md) - Complete documentation on fetching Austria weather data
- [meteomatics module](src/moonpies/meteomatics.py) - Python API for Meteomatics

### Future Work

This challenge presents various potential avenues beyond the scope and constraints of the challenge. Below are several potential areas for exploration:
- Integration of URT-dataset from LANCE allows the potential of predicting the nonlinear propagation of the forest fire
- Integration of the anomolies to further strengthen the probabilistic model of the fire propagation:
    - Soil-moisture
    - Weather anomalies due to El-Nino and La-Nina 
    - Localised precipation
- Training a echo state networks ( in particular residual computing) hybrid neural network model trained on classical and quantum thermodynamics as well as quantum machine learning to accurately predict the propagation, direction, etc. of forest fires
- Integrating more information from Meteomatics to correlate periods of low rain and low humidity and strong winds to fire safety risks.

### Glossary

The abbreviations used in this challenge is  

| Abbreviations | Description | Reference |
| --- | --- | --- |

| FRIMS | Fire Information for Resource Management System  |[https://firms.modaps.eosdis.nasa.gov/](https://firms.modaps.eosdis.nasa.gov/) |
| MODIS | Moderate Resolution Imaging Spectroradiometer | [https://terra.nasa.gov/about/terra-instruments/modis](https://terra.nasa.gov/about/terra-instruments/modis) |
| LANCE | Land, Atmosphere Near real-time Capability for Earth observation | [https://www.earthdata.nasa.gov/data/projects/lance](https://www.earthdata.nasa.gov/data/projects/lance)  |
| VIIRS | Moderate Resolution Imaging Spectroradiometer | [https://terra.nasa.gov/about/terra-instruments/modis](https://terra.nasa.gov/about/terra-instruments/modis) |
