# Created using Mistral Vibe
"""Merge NASA FIRMS MODIS and VIIRS active-fire hotspot records into one table.

Data context (NASA Space Apps 2026 - "Harmonization of MODIS and VIIRS Hot Spots")
---------------------------------------------------------------------------------
Both CSVs in ``data/`` come from NASA FIRMS (Fire Information for Resource
Management System) and describe the same thing - an actively burning pixel
("hotspot") seen from space - but the two sensors record it differently:

* MODIS (Terra/Aqua, Collection 6.1): ~1 km pixels. Extra columns
  ``brightness`` (4 um channel 21/22, Kelvin) and ``bright_t31`` (11 um
  channel 31, Kelvin). ``confidence`` is an integer 0-100 (%).
* VIIRS (Suomi-NPP/NOAA-20/NOAA-21, Collection 2): 375 m pixels. Extra columns
  ``bright_ti4`` (3.74 um I4 band, Kelvin) and ``bright_ti5`` (11.45 um I5
  band, Kelvin). ``confidence`` is a category: "l" (low), "n" (nominal),
  "h" (high).

Because of the resolution gap (1 km vs 375 m) VIIRS detects roughly 3-5x more
pixels for the same fire, so raw row counts of the two files are NOT directly
comparable - that is the core of the challenge. The 4 um / 11 um brightness
channels of the two sensors are spectrally similar but not identical, so both
sets of columns are kept (they carry slightly different information).

How they are harmonized here
----------------------------
``merge(modis, viirs)`` produces a *harmonized union*: one row per detection,
both sensors in a single DataFrame with one common schema:

1. ``acq_date`` is parsed to a real ``Date`` (FIRMS ships it as "YYYY-MM-DD"
   string) so dates from both files sort/compare correctly.
2. ``confidence`` is unified to the VIIRS letter classes: MODIS 0-100 is
   binned into "l" / "n" / "h" (NASA publishes no official numeric cutoffs;
   the bin edges are parameters, defaults 30 / 80).
3. ``version`` is cast to String (MODIS "6.03" vs VIIRS "2" are different
   collection schemes, so they are kept as labels, not numbers).
4. The sensor-specific brightness columns are kept side by side; each row
   has nulls in the columns of the other sensor.
5. Both frames are projected onto one common column order and concatenated
   vertically (``pl.concat``) - a union, no rows are lost or matched away.
   Only one frame may be given (``merge(df)``); it is still normalized onto
   the same common schema (the sensor is auto-detected from its columns).
6. Optional: with ``grid_res`` (meters) both sensors are projected to a
   proper equal-area CRS (default EPSG:3035, LAEA Europe) via pyproj and
   snapped to a square grid in meter space (e.g. grid_res=1000 -> 1 km
   cells), then aggregated per (acq_date, satellite, cell). Projecting first
   means cells are truly equal-area across all of Europe, so DataFrames from
   different countries/years (concatenated by the caller with pl.concat)
   are gridded consistently. This puts both sensors on the *same effective
   resolution*, which is what makes their counts comparable for the
   burning-activity calendar. Detections in the same cell on the same day
   are merged into ONE row across all sensors. List columns record the
   reporters/variants: ``satellites``, ``versions``, ``daynight`` (sorted
   unique lists, single-element if only one value) and ``countries`` (if the
   input has a ``country`` column); ``confidence_ordinal`` is the max
   ordinal (l=0, n=1, h=2); the four brightness columns are averaged over
   non-nulls. scan*track (the actual pixel area in km^2, which grows toward
   the swath edge) is used to add ``frp_density`` = MW per km^2 of detected
   pixel. Cell centers are returned both as x/y meters and as
   latitude/longitude (transformed back to EPSG:4326).
"""

# from __future__ import annotations

import polars as pl
from pyproj import Transformer

# Common output schema. Sensor-specific brightness columns are kept next to
# each other; rows from the "other" sensor simply have nulls there.
COMMON_COLUMNS = [
    "latitude",
    "longitude",
    "acq_date",
    "acq_time",
    "daynight",
    "satellite",
    "instrument",
    "confidence",
    "version",
    "type",
    "frp",
    "brightness",   # MODIS 4 um (ch 21/22) - null for VIIRS rows
    "bright_t31",   # MODIS 11 um (ch 31)    - null for VIIRS rows
    "bright_ti4",   # VIIRS 3.74 um (I4)     - null for MODIS rows
    "bright_ti5",   # VIIRS 11.45 um (I5)    - null for MODIS rows
    "scan",
    "track",
]

# Columns every input must provide (the rest are sensor-specific extras).
_REQUIRED = [
    "latitude", "longitude", "acq_date", "acq_time", "daynight",
    "satellite", "instrument", "confidence", "version", "type", "frp",
    "scan", "track",
]


def _parse_acq_date(df: pl.DataFrame) -> pl.DataFrame:
    """Step 1: parse acq_date from 'YYYY-MM-DD' string to pl.Date."""
    if df["acq_date"].dtype == pl.String:
        return df.with_columns(pl.col("acq_date").str.to_date("%Y-%m-%d"))
    return df


def _modis_confidence_to_class(
    df: pl.DataFrame, low_max: int, high_min: int
) -> pl.DataFrame:
    """Step 2a: bin MODIS numeric confidence (0-100) into VIIRS classes.

    NASA does not publish official numeric cutoffs for the low/nominal/high
    classes, so the edges are parameters: < low_max -> "l",
    >= high_min -> "h", otherwise "n".
    """
    if df["confidence"].dtype == pl.String:
        # already categorical (e.g. pre-processed) - just normalize case
        return df.with_columns(pl.col("confidence").str.to_lowercase())
    return df.with_columns(
        pl.when(pl.col("confidence") < low_max)
        .then(pl.lit("l"))
        .when(pl.col("confidence") >= high_min)
        .then(pl.lit("h"))
        .otherwise(pl.lit("n"))
        .alias("confidence")
    )


def _normalize(
    df: pl.DataFrame,
    *,
    is_modis: bool,
    low_max: int,
    high_min: int,
) -> pl.DataFrame:
    """Bring one sensor's frame onto the common schema (steps 1-4)."""
    missing = [c for c in _REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"input is missing required columns: {missing}")

    df = _parse_acq_date(df)
    if is_modis:
        df = _modis_confidence_to_class(df, low_max, high_min)
        # VIIRS-only brightness columns -> explicit nulls so both frames
        # have identical columns before the concat.
        df = df.with_columns(
            pl.lit(None).cast(pl.Float64).alias("bright_ti4"),
            pl.lit(None).cast(pl.Float64).alias("bright_ti5"),
        )
    else:
        # VIIRS confidence is already l/n/h; make sure it is a clean string.
        df = df.with_columns(pl.col("confidence").cast(pl.String).str.to_lowercase())
        # MODIS-only brightness columns -> explicit nulls.
        df = df.with_columns(
            pl.lit(None).cast(pl.Float64).alias("brightness"),
            pl.lit(None).cast(pl.Float64).alias("bright_t31"),
        )

    # version is a collection label, not a comparable number ("6.03" vs "2")
    df = df.with_columns(pl.col("version").cast(pl.String))

    # Step 4: project onto the common column order, keeping any extra columns
    # the caller added (e.g. country) so they survive the union and the grid.
    extras = [c for c in df.columns if c not in COMMON_COLUMNS]
    return df.select(COMMON_COLUMNS + extras)


def _to_grid(df: pl.DataFrame, grid_res: float, crs: str) -> pl.DataFrame:
    """Step 6: project to an equal-area CRS, snap to a meter grid, aggregate.

    Both sensors end up on the same effective resolution: grid_res meters in
    the projected CRS (default EPSG:3035, LAEA Europe - equal-area for all of
    Europe, so country/year files concatenated by the caller are gridded
    consistently). Cells are square in meters, so no latitude correction is
    needed. scan*track (actual pixel area in km^2, growing toward the swath
    edge) adds frp_density = MW per km^2 of detected pixel.

    Grouping is per (acq_date, cell) across ALL sensors: detections near each
    other on the same day merge into one row. List columns record the reporters
    and variants: ``satellites``, ``versions``, ``daynight`` (sorted unique
    lists; single-element if only one value) and ``countries`` (only if the
    input has a ``country`` column). ``confidence_ordinal`` is the max
    ordinal in the group (l=0, n=1, h=2). Brightness columns are averaged
    over the non-null values (each sensor's own column). FRP is summed and the
    raw count is kept as n_detections. Cell centers are returned as x/y
    meters and as latitude/longitude (transformed back to EPSG:4326).
    """
    # df = df.filter(df["type"] == 0)
    fwd = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    inv = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)

    # project lon/lat -> x/y meters (pyproj works on plain lists, no numpy needed)
    x, y = fwd.transform(df["longitude"].to_list(), df["latitude"].to_list())
    df = df.with_columns(
        pl.Series("x", x),
        pl.Series("y", y),
        # actual pixel area in km^2 (scan/track grow toward the swath edge)
        pixel_area=pl.col("scan") * pl.col("track"),
        # ordinal confidence: l=0, n=1, h=2 (max wins within the group)
        conf_ord=pl.when(pl.col("confidence") == "h")
        .then(2)
        .when(pl.col("confidence") == "n")
        .then(1)
        .otherwise(0),
    ).with_columns(
        x_cell=(pl.col("x") / grid_res).round(0).cast(pl.Int64),
        y_cell=(pl.col("y") / grid_res).round(0).cast(pl.Int64),
    )
    aggs: dict[str, pl.Expr] = {
        "x": pl.col("x_cell").first() * grid_res,
        "y": pl.col("y_cell").first() * grid_res,
        # all satellites/versions/day-night flags that reported this cell-day
        "satellites": pl.col("satellite").unique(),
        "versions": pl.col("version").unique(),
        "daynight": pl.col("daynight").unique(),
        "confidence_ordinal": pl.col("conf_ord").max(),
        # brightness temperatures: mean over the non-null values per sensor column
        "brightness": pl.col("brightness").mean(),
        "bright_t31": pl.col("bright_t31").mean(),
        "bright_ti4": pl.col("bright_ti4").mean(),
        "bright_ti5": pl.col("bright_ti5").mean(),
        "frp": pl.col("frp").sum(),
        "frp_density": (pl.col("frp") / pl.col("pixel_area")).sum(),
        "pixel_area": pl.col("pixel_area").sum(),
        "n_detections": pl.len(),
    }
    if "country" in df.columns:
        aggs["countries"] = pl.col("country").unique()
    g = (
        df.group_by(["acq_date", "x_cell", "y_cell"])
        .agg(**aggs)
        .drop("x_cell", "y_cell")
        .with_columns(
            pl.col("satellites").list.sort(),
            pl.col("versions").list.sort(),
            pl.col("daynight").list.sort(),
        )
    )
    if "countries" in g.columns:
        g = g.with_columns(pl.col("countries").list.sort())
    # cell centers back to lon/lat for display on web maps
    lon, lat = inv.transform(g["x"].to_list(), g["y"].to_list())
    g = g.with_columns(pl.Series("latitude", lat), pl.Series("longitude", lon))
    out_cols = [
        "acq_date",
        "latitude", "longitude", "x", "y",
        "satellites", "versions", "daynight", "confidence_ordinal",
        "brightness", "bright_t31", "bright_ti4", "bright_ti5",
        "frp", "frp_density", "pixel_area", "n_detections",
    ]
    if "countries" in g.columns:
        out_cols.append("countries")
    return g.select(out_cols)


def _detect_is_modis(df: pl.DataFrame) -> bool:
    """Guess whether a frame is MODIS or VIIRS from its columns/instrument."""
    cols = set(df.columns)
    if "bright_ti4" in cols or "bright_ti5" in cols:
        return False
    if "brightness" in cols or "bright_t31" in cols:
        return True
    if "instrument" in cols:
        return any("MODIS" in str(v).upper() for v in df["instrument"].unique().to_list())
    raise ValueError("cannot tell MODIS from VIIRS: no brightness or instrument columns")


def harmonize(
    modis: pl.DataFrame | None = None,
    viirs: pl.DataFrame | None = None,
    *,
    grid_res: float | None = None,
    grid_crs: str = "EPSG:3035",
    types: list[int] | None = None,
    confidence_low_max: int = 30,
    confidence_high_min: int = 80,
) -> pl.DataFrame:
    """Merge MODIS and/or VIIRS FIRMS hotspot DataFrames into one table.

    Parameters
    ----------
    modis, viirs:
        DataFrames as read from the FIRMS CSVs (e.g. ``data/modis/*.csv``
        and ``data/viirs*/*.csv``). Either or both may be given:
        ``harmonize(modis, viirs)`` merges both sensors; ``harmonize(df)``
        with a single frame still normalizes it onto the same common schema
        (the sensor is auto-detected from its columns). Multiple VIIRS
        satellites, countries or years can simply be ``pl.concat``-ed by
        the caller before passing them in - harmonize() only needs the
        common schema.
    grid_res:
        If given (meters in the projected CRS, e.g. 1000 = 1 km cells), both
        sensors are projected to ``grid_crs`` and snapped to a square meter
        grid, then aggregated per (acq_date, cell) so they end up at the
        same effective resolution. Detections in the same cell on the same
        day merge into one row across all sensors; the ``satellites`` list
        column records which satellites reported it. scan/track are used to
        add frp_density (MW per km^2 of pixel). If None (default), the raw
        harmonized union is returned - one row per detection.
    grid_crs:
        Equal-area projected CRS used in grid mode. Default "EPSG:3035"
        (ETRS89 / LAEA Europe) - equal-area across Europe, so concatenated
        country/year files are gridded consistently.
    types:
        Optional FIRMS ``type`` filter applied after the union. Codes:
        0 = presumed vegetation fire, 1 = active volcano, 2 = other static
        land source (industrial, gas flares), 3 = offshore. For a
        wildfire/agricultural burning calendar pass ``types=[0]`` to drop
        persistent industrial/offshore hotspots. None (default) keeps all.
    confidence_low_max, confidence_high_min:
        Bin edges mapping MODIS numeric confidence (0-100) to the VIIRS
        classes: < low_max -> "l", >= high_min -> "h", else "n".

    Returns
    -------
    pl.DataFrame
        Harmonized union sorted by acq_date (grid-aggregated if grid_res
        was given).
    """
    # Steps 1-4: normalize each given sensor onto the common schema. A single
    # frame is fine too - its sensor is auto-detected from its columns.
    frames = []
    for df in (modis, viirs):
        if df is None:
            continue
        if not isinstance(df, pl.DataFrame):
            raise TypeError("harmonize() expects polars DataFrames: harmonize(modis, viirs)")
        frames.append(
            _normalize(
                df, is_modis=_detect_is_modis(df),
                low_max=confidence_low_max, high_min=confidence_high_min,
            )
        )
    if not frames:
        raise ValueError(
            "harmonize() needs at least one DataFrame: harmonize(modis) or harmonize(modis, viirs)"
        )

    # Step 5: vertical concat = union, one row per detection, no row matching.
    # Align schemas first: an extra column present in only one frame (e.g.
    # country on one country's file) becomes a typed null column in the other.
    all_cols: list[str] = []
    dtypes: dict[str, pl.DataType] = {}
    for f in frames:
        for c in f.columns:
            if c not in all_cols:
                all_cols.append(c)
            dtypes.setdefault(c, f.schema[c])
    frames = [
        f.with_columns(
            [pl.lit(None).cast(dtypes[c]).alias(c) for c in all_cols if c not in f.columns]
        ).select(all_cols)
        for f in frames
    ]
    merged = pl.concat(frames, how="vertical")

    # Optional type filter (e.g. types=[0] keeps only vegetation fires).
    if types is not None:
        merged = merged.filter(pl.col("type").is_in(types))

    # Step 6 (optional): common projected grid so both sensors share one
    # resolution (country/year files are concatenated by the caller).
    if grid_res is not None:
        merged = _to_grid(merged, grid_res, grid_crs)
        merged = merged.sort("acq_date", "y", "x")
    else:
        merged = merged.sort("acq_date", "satellite", "latitude", "longitude")

    return merged


if __name__ == "__main__":
    from moonpies.consts import DATA_DIR

    # Demo: concat several country files (Austria + Portugal) and both VIIRS
    # satellites, then merge with MODIS - raw union first, then on a 1 km
    # grid in EPSG:3035 (LAEA Europe). Add more country/year CSVs to the
    # globs the same way.
    def read_with_country(paths) -> pl.DataFrame:
        # tag each file with its country (last part of the file name)
        return pl.concat(
            [pl.read_csv(p).with_columns(pl.lit(p.stem.split("_")[-1]).alias("country")) for p in paths]
        )

    modis = read_with_country(sorted((DATA_DIR / "modis").glob("*.csv")))
    viirs = pl.concat(
        [
            read_with_country(sorted((DATA_DIR / "viirs").glob("*.csv"))),
            read_with_country(sorted((DATA_DIR / "viirs-snpp").glob("*.csv"))),
        ]
    )

    merged = harmonize(modis, viirs)
    print(f"raw union: {merged.shape[0]} rows (modis {modis.height} + viirs {viirs.height})")
    print(merged.head(3))
    print("confidence classes:", merged["confidence"].value_counts().sort("confidence"))

    only_modis = harmonize(modis)
    print(f"\nsingle frame (MODIS only): {only_modis.shape[0]} rows, same schema: {only_modis.columns == merged.columns}")

    gridded = harmonize(modis, viirs, grid_res=1000)
    print(f"\n1 km grid (EPSG:3035): {gridded.shape[0]} cell-days, columns: {gridded.columns}")
    print(gridded.head(3))

    veg = harmonize(modis, viirs, grid_res=1000, types=[0])
    print(f"\nvegetation fires only (type=0), 1 km grid: {veg.shape[0]} cell-days")
