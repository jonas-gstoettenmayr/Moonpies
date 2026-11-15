# Created using Mistral Vibe
import io
from datetime import date
from pathlib import Path

import polars as pl
from flask import Flask, Response, jsonify, request, send_from_directory

from moonpies.consts import DATA_DIR, ROOT_DIR

DATA_FILE: Path = DATA_DIR / "harmonize_grid.parquet"

app = Flask(__name__, static_folder=str(ROOT_DIR / "web"), static_url_path="")


def _load() -> pl.DataFrame:
    """Load the harmonized hotspot dataset (one row per detected hotspot)

    Returns:
        pl.DataFrame: harmonize_grid.parquet with acq_date cast to Date
    """
    df = pl.read_parquet(DATA_FILE)
    return df.with_columns(pl.col("acq_date").cast(pl.Date))


_df = _load()
print(f"Loaded {_df.height:,} rows")

MIN_DATE: date = _df["acq_date"].min()
MAX_DATE: date = _df["acq_date"].max()

# Markers: when VIIRS coverage starts and when MODIS coverage ends (full date range)
_viirs = _df.filter(
    pl.col("satellites").list.eval(pl.element().str.starts_with("N")).list.any()
)
_modis = _df.filter(
    pl.col("satellites").list.contains("Terra")
    | pl.col("satellites").list.contains("Aqua")
)
MARKERS = {
    "viirs_start": _viirs["acq_date"].min().isoformat() if _viirs.height else None,
    "modis_end": _modis["acq_date"].max().isoformat() if _modis.height else None,
}
print(f"VIIRS starts {MARKERS['viirs_start']}, MODIS ends {MARKERS['modis_end']}")

# Years that actually have data (drives the calendar year dropdown)
YEARS: list[int] = sorted(_df["acq_date"].dt.year().unique().to_list())


def _with_country(df: pl.DataFrame, country: str | None) -> pl.DataFrame:
    """Keep only rows whose countries list contains the country (None/'europe' = all)"""
    if country and country.lower() != "europe":
        df = df.filter(pl.col("countries").list.contains(country))
    return df


def _with_satellite(df: pl.DataFrame, satellite: str | None) -> pl.DataFrame:
    """Keep only rows of one satellite system: 'modis' (Terra/Aqua) or 'viirs' (N*/SNPP)"""
    s = (satellite or "").lower()
    if s == "modis":
        df = df.filter(
            pl.col("satellites").list.contains("Terra")
            | pl.col("satellites").list.contains("Aqua")
        )
    elif s == "viirs":
        df = df.filter(
            pl.col("satellites")
            .list.eval(pl.element().str.starts_with("N") | (pl.element() == "SNPP"))
            .list.any()
        )
    return df


def _filter_range(
    df: pl.DataFrame, start: date, end: date, region: str | None = None
) -> pl.DataFrame:
    """Filter a frame by date range and region.

    region="europe" (or empty) keeps every row; any other value is treated as a
    country name and keeps only rows whose countries list contains it.
    """
    df = df.filter((pl.col("acq_date") >= start) & (pl.col("acq_date") <= end))
    return _with_country(df, region)


def _csv_frame(df: pl.DataFrame) -> pl.DataFrame:
    """Flatten list columns (satellites, countries, ...) so the frame can be written as CSV"""
    return df.with_columns(pl.col(pl.List(pl.String)).list.join(",").cast(pl.String))


# Frontend of the app
@app.route("/")
def index():
    return send_from_directory(str(ROOT_DIR / "web"), "index.html")


# Website health
@app.route("/health")
def health():
    """Debug to show website health

    Returns:
        _type_: Website status
    """
    return jsonify({"status": "ok"})


# Dataset bounds for the frontend date pickers
@app.route("/api/meta")
def meta():
    """Date range, row count and satellite coverage markers of the dataset

    Returns:
        _type_: JSON with min_date / max_date / rows / markers
    """
    return jsonify({
        "min_date": MIN_DATE.isoformat(),
        "max_date": MAX_DATE.isoformat(),
        "rows": _df.height,
        "years": YEARS,
        "markers": MARKERS,
    })


# Country selector list
@app.route("/api/countries")
def countries():
    """List the countries present in the dataset for the region selector

    Returns:
        _type_: Sorted list of country names
    """
    return jsonify({"countries": sorted(_df["countries"].explode().unique().to_list())})


# Calendar: hotspot count per day of one month
@app.route("/api/calendar")
def calendar():
    """Hotspot count per day for a given year/month (drives the side calendar).

    Optional ?country and ?satellite (modis/viirs) narrow the counts down.

    Returns:
        _type_: JSON with year, month, days=[{day, count}], total, max
    """
    year = int(request.args.get("year", MAX_DATE.year))
    month = int(request.args.get("month", MAX_DATE.month))
    df = _with_satellite(
        _with_country(_df, request.args.get("country")), request.args.get("satellite")
    ).filter(
        (pl.col("acq_date").dt.year() == year)
        & (pl.col("acq_date").dt.month() == month)
    )
    cal = (
        df.group_by(pl.col("acq_date").dt.day().alias("day"))
        .agg(pl.len().alias("count"))
        .sort("day")
    )
    return jsonify({
        "year": year,
        "month": month,
        "days": cal.to_dicts(),
        "total": int(cal["count"].sum()) if cal.height else 0,
        "max": int(cal["count"].max()) if cal.height else 0,
    })


# Map: all hotspots of a single day as compact columnar JSON
@app.route("/api/hotspots")
def hotspots():
    """All hotspots for one day (?date=YYYY-MM-DD) for the map.

    Optional ?country and ?satellite (modis/viirs) narrow the hotspots down.
    brightness is coalesced across MODIS (brightness) and VIIRS (bright_ti4/ti5).

    Returns:
        _type_: JSON with date, count and columnar arrays lat/lon/brightness/frp/...
    """
    d = date.fromisoformat(request.args.get("date", MAX_DATE.isoformat()))
    df = _with_satellite(
        _with_country(_df, request.args.get("country")), request.args.get("satellite")
    ).filter(pl.col("acq_date") == d)
    df = df.with_columns(
        pl.coalesce(
            [pl.col("brightness"), pl.col("bright_ti4"), pl.col("bright_ti5")]
        ).alias("brightness")
    )
    return jsonify({
        "date": d.isoformat(),
        "count": df.height,
        "lat": df["latitude"].round(4).to_list(),
        "lon": df["longitude"].round(4).to_list(),
        "brightness": df["brightness"].round(1).to_list(),
        "frp": df["frp"].round(1).to_list(),
        "satellites": df["satellites"].to_list(),
        "confidence": df["confidence_ordinal"].to_list(),
        "daynight": df["daynight"].to_list(),
        "countries": df["countries"].to_list(),
    })


# Export: scientist downloads the hotspots of a date range + region as CSV
@app.route("/api/export")
def export():
    """Export hotspots as CSV for ?start / ?end / ?region.

    region=europe exports all of Europe; any other value is a country name.
    The polars frame is filtered by date range and region before writing.

    Returns:
        _type_: CSV file download
    """
    start = date.fromisoformat(request.args.get("start", MIN_DATE.isoformat()))
    end = date.fromisoformat(request.args.get("end", MAX_DATE.isoformat()))
    region = request.args.get("region", "europe")
    df = _csv_frame(_filter_range(_df, start, end, region))
    buf = io.StringIO()
    df.write_csv(buf)
    filename = f"hotspots_{region.lower()}_{start.isoformat()}_{end.isoformat()}.csv"
    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# Load webpage
if __name__ == "__main__":
    app.run(debug=True, port=5000)
