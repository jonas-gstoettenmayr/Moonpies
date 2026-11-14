# Merging MODIS & VIIRS hotspots — `moonpies.merge`

Created using Mistral Vibe. Code: `src/moonpies/merge.py` (`merge(modis, viirs, ...)`).

## 1. Challenge context

NASA Space Apps Challenge 2026 — **"Harmonization of MODIS and VIIRS Hot Spots"**:

> "Satellites have tracked active fire hotspots for more than two decades, but the record
> is split across sensors whose data cannot be compared directly … Your challenge is to
> build a web application that harmonizes these records into a **burning activity
> calendar** based on active fire hotspots, enabling early warning and emergency
> responders, scientists, and land managers to examine historical fire patterns,
> unusual conditions, and critical periods within a selected area of interest."

Both CSVs in `data/` are NASA **FIRMS** exports. **Each row is one hotspot**: the center
of one satellite pixel flagged as containing ≥1 actively burning fire (or other thermal
anomaly). A row is *not* "a fire" — one fire can span several pixels, and one pixel can
contain several fires.

## 2. Data context — what differs between the two sensors

| Column | MODIS (Terra/Aqua, C6.1) | VIIRS (S-NPP/NOAA-20/NOAA-21, C2) | Notes |
|---|---|---|---|
| `latitude`, `longitude` | center of ~1 km pixel | center of 375 m pixel | same meaning, different resolution |
| `brightness` | 4 µm ch 21/22, Kelvin | — (null) | MODIS-only column |
| `bright_t31` | 11 µm ch 31, Kelvin | — (null) | MODIS-only column |
| `bright_ti4` | — (null) | 3.74 µm I4 band, Kelvin | VIIRS-only column |
| `bright_ti5` | — (null) | 11.45 µm I5 band, Kelvin | VIIRS-only column |
| `scan`, `track` | along-scan / along-track pixel size in km (1.0–4.4 / 1.0–1.9 in our data) | same, ~0.32–0.79 km | pixels grow toward the swath edge ("bow-tie"); `scan*track` ≈ pixel area in km² |
| `acq_date`, `acq_time` | date + UTC HHMM overpass time | same | string date in the CSVs |
| `satellite` | `Terra`, `Aqua` | `N`, `N20`, `N21` | |
| `instrument` | `MODIS` | `VIIRS` | |
| `confidence` | integer 0–100 (%) | category `l`/`n`/`h` | different encodings of the same idea |
| `version` | `6.03` (float) | `2` (int) | collection label, not a comparable number |
| `frp` | fire radiative power, MW | same | the intensity measure |
| `daynight` | `D`/`N` | `D`/`N` | |
| `type` | 0 vegetation fire, 1 volcano, 2 other static land (industrial/gas flares), 3 offshore | same codes | see §5 |

**Why the raw files are not comparable:** VIIRS (375 m) detects roughly 3–5× more
pixels than MODIS (1 km) for the same fire. Austria 2020: 468 MODIS vs 4,599 VIIRS rows.
Joining them naively makes fire activity look like it jumped when the sensor changed.

## 3. What `merge()` does — step by step, with reasoning

```python
import polars as pl
from moonpies import merge

# concat country/year files yourself, then merge the two sensors:
modis = pl.concat([pl.read_csv(p) for p in modis_csvs])   # e.g. Austria + Portugal, 2020 + 2021
viirs = pl.concat([pl.read_csv(p) for p in viirs_csvs])   # all VIIRS satellites

merged = merge(modis, viirs)                        # raw harmonized union
grid   = merge(modis, viirs, grid_res=1000)         # + 1 km grid in EPSG:3035 (LAEA Europe)
veg    = merge(modis, viirs, grid_res=1000, types=[0])  # vegetation fires only
```

1. **Parse `acq_date` to a real `Date`** — FIRMS ships `"YYYY-MM-DD"` strings; a real
   date type makes sorting, grouping and calendar joins correct.
2. **Unify `confidence` to the VIIRS letter classes** — MODIS 0–100 is binned into
   `l`/`n`/`h` (`<30 → l`, `>=80 → h`, else `n`; edges are parameters
   `confidence_low_max`/`confidence_high_min` because NASA publishes no official numeric
   cutoffs). VIIRS values are lowercased. One comparable quality column for both sensors.
3. **Cast `version` to String** — `6.03` vs `2` are different collection schemes; keep
   as provenance labels, not numbers.
4. **Keep both brightness channel pairs side by side** — MODIS ch21/22 (≈3.9 µm) vs VIIRS
   I4 (3.74 µm), and ch31 (≈11.0 µm) vs I5 (11.45 µm), are spectrally similar but not
   identical, so both carry information. Each row has nulls in the other sensor's
   columns.
5. **Project both frames onto one common column order and `pl.concat` vertically** — a
   *union*: one row per detection, no rows matched away or lost. `satellite`/`instrument`
   keep the origin of each row.
6. **Optional grid (`grid_res` in meters, projected CRS)** — see §4. Country/year
   files are concatenated by the caller with `pl.concat` before calling `merge()`.

Optional **`types=[...]` filter** is applied after the union (see §5).

Output is sorted by `acq_date, satellite, latitude, longitude`.

## 4. The grid math (step 6) — projected meter grid

Instead of gridding in degrees, `merge()` **projects lon/lat to a proper equal-area CRS
with pyproj** (default `grid_crs="EPSG:3035"`, ETRS89 / LAEA Europe — equal-area across
all of Europe, centered at 52°N 10°E), then snaps in **meter space**:

```
fwd = Transformer.from_crs("EPSG:4326", grid_crs, always_xy=True)
x, y   = fwd.transform(longitude, latitude)        # meters
x_cell = round(x / grid_res)                        # cell index in meters
y_cell = round(y / grid_res)
```

All detections sharing `(acq_date, satellite, instrument, x_cell, y_cell)` collapse into
one row at the cell center (`x_cell*grid_res`, `y_cell*grid_res`), with `frp` summed and
`n_detections` counted. Cell centers are transformed back to EPSG:4326, so the output has
both `x`/`y` (meters, for equal-area analysis) and `latitude`/`longitude` (degrees, for
web maps). Grouping keeps `satellite` separate so one fire seen by two sensors is not
double-counted in a cell-day.

Because cells are square in meters in an equal-area CRS, **no latitude correction is
needed** — files from different countries and years (concatenated by the caller with
`pl.concat`) are gridded consistently across all of Europe.

**Pixel-size correction via `scan`/`track`.** FRP is reported *per pixel*, and pixels
grow toward the swath edge, so `pixel_area = scan*track` (km²) is computed per detection
and the grid adds:

- `frp_density = sum(frp / pixel_area)` — MW per km² of detected pixel, so a big
  swath-edge pixel does not contribute more FRP than a nadir pixel;
- `pixel_area = sum(scan*track)` — total detected km² in the cell.

Choosing `grid_res = 1000` (1 km ≈ one MODIS pixel) is what neutralizes the resolution
gap: one MODIS pixel and the ~7 VIIRS sub-pixels of the same fire land in the same cell.
Note the grid still does not fully equalize *counts* (VIIRS will report more
`n_detections` per cell); for a single comparable activity number you can additionally
rescale VIIRS toward MODIS over their overlap period (empirical factor ≈ 0.27 in other
teams' work). `frp`/`frp_density` sums are the more directly comparable quantities.

## 5. Which variables matter for the burning-activity calendar

- **Each row = one hotspot pixel**, so the calendar is built by aggregating rows per
  (day, cell): count + FRP sum. Core variables: `acq_date`, `latitude`/`longitude`
  (→ cell), `frp`, `n_detections`, `satellite`/`instrument`.
- **`type` filter — yes, filter it.** Codes: `0` presumed vegetation fire, `1` active
  volcano, `2` other static land source (industrial sites, gas flares), `3` offshore
  (oil rigs). For a wildfire/agricultural burning calendar, `types=[0]` is the sensible
  default: type 2/3 are *persistent* sources that would light up the calendar every
  single day and are not "burning activity". In Austria 2020 the grid drops from 2,482
  to 311 cell-days with `types=[0]` — most detections there are industrial/static.
- **`confidence`** — keep `n`+`h` for early warning to reduce false alarms; keep `l` too
  if maximum detectability matters more than false alarms.
- **`daynight`** — nighttime detections are more reliable (lower thermal background,
  and VIIRS has improved nighttime performance); useful as a secondary calendar layer.
- **`brightness`/`bright_ti4` (4 µm)** and **`bright_t31`/`bright_ti5` (11 µm)** —
  brightness temperatures in Kelvin; useful for QA/plots, not needed for a basic calendar.
- **`scan`/`track`** — used for the pixel-area correction (§4).

## 6. Projection choices

Grid mode uses a **proper projection** (implemented): lon/lat → EPSG:3035 (LAEA Europe)
meters via `pyproj`, square meter cells, cell centers transformed back to EPSG:4326 for
display. `grid_crs` is a parameter, so alternatives are one argument away:

| CRS | Use case |
|---|---|
| `EPSG:3035` (default) | Europe-wide equal-area (LAEA Europe) — right for this challenge's area of interest |
| `EPSG:54009` (Mollweide) / `EPSG:6933` (EASE-Grid 2.0) | global equal-area |
| H3 hex grid (via `h3` package) | discrete global grid, no projection distortion at all; good if the app must work worldwide |

Polars does not project natively; `pyproj` does the transform (on plain Python lists, so
no numpy dependency), then the same divide–round–group logic applies in meter space.

## 7. Verification

- Synthetic checks (`AgentScratchPad/verify_merge.py`, gitignored): confidence bin
  edges (29→`l`, 80→`h`), null brightness columns per sensor, date parsing, `types`
  filter, missing-column error, and projection checks — (lat 52, lon 10) projects to
  exactly x=4321000, y=3210000 (the EPSG:3035 center) and back; two points ~343 m apart
  share a 1 km cell while one ~686 m away does not; `frp_density`/`pixel_area`
  hand-computed (43.25 MW/km², 0.41 km²). All pass.
- Real data (Austria + Portugal 2020, concatenated): raw union 14,173 rows
  (1,817 MODIS + 12,356 VIIRS); 1 km EPSG:3035 grid → 8,000 cell-days; `types=[0]` →
  5,216 cell-days.
- `pytest tests/`: 1 passed, 2 skipped (pre-existing skips).

## 8. Assumptions & limitations

- MODIS 0–100 → `l`/`n`/`h` bin edges (30/80) are our choice; NASA publishes no official
  numeric mapping. Exposed as parameters.
- EPSG:3035 is equal-area for Europe; for a global app switch `grid_crs` (§6) or use H3.
- Snapping is a hard partition: two detections a few meters apart can land in different
  cells if they straddle a boundary. A distance-based spatial join avoids this at higher
  compute cost.
- Grid mode groups per satellite, so MODIS and VIIRS rows in the same cell-day stay
  separate (no double counting); pool sensors in the group-by if a single per-cell row
  is wanted.
- pyproj transforms run on plain Python lists (no numpy dependency).
