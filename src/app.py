import io
from pathlib import Path

import pandas as pd
from flask import Flask, Response, jsonify, request, send_from_directory
from werkzeug.utils import secure_filename

from moonpies.consts import DATA_DIR, ROOT_DIR

DATA_FILE: Path = DATA_DIR / "harmonized.parquet"

app = Flask(__name__, static_folder=str(ROOT_DIR / "web"), static_url_path="")


def _load():
    """Load the dataset

    Returns:
        _type_: _description_
    """
    df = pd.read_parquet(DATA_FILE)
    df["acq_date"] = pd.to_datetime(df["acq_date"])
    df["sensor"] = df["instrument"]
    overlap = df[(df["acq_date"] >= "2012-07") & (df["acq_date"] <= "2025-12")]
    ratio = len(overlap[overlap["sensor"] == "VIIRS"]) / max(
        len(overlap[overlap["sensor"] == "MODIS"]), 1
    )
    df["harmonized_count"] = df["sensor"].map({"VIIRS": 1.0, "MODIS": ratio})
    return df


_df = _load()
print(f"Loaded {len(_df):,} rows")


# Frontend of the
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


# Calendar 
@app.route("/api/calendar")
def calendar():
    """Visualise the dataset in a calendar by year and month

    Returns:
        _type_: Input by year and date
    """
    start = request.args.get("start", "2001-01-01")
    end = request.args.get("end", "2025-12-30")

    df = _df[(_df["acq_date"] >= start) & (_df["acq_date"] <= end)].copy()
    df["year"] = df["acq_date"].dt.year
    df["month"] = df["acq_date"].dt.month
    cal = df.groupby(["year", "month"])["harmonized_count"].sum().reset_index()

    cy, cm = int(end[:4]), int(end[5:7])
    sm = cal[cal["month"] == cm]
    med = float(sm["harmonized_count"].median()) if len(sm) else 0.0
    cur = cal[(cal["year"] == cy) & (cal["month"] == cm)]
    cv = float(cur["harmonized_count"].values[0]) if len(cur) else 0.0

    return jsonify({
        "calendar": cal.to_dict(orient="records"),
        "anomaly": {"current": cv, "median": med, "ratio": cv / med if med > 0 else 0},
        "total": int(df["harmonized_count"].sum()),
    })



@app.route("/api/export")
def export():
    """Export the data in CSV
 format 
    Returns:
        _type_: _description_
    """
    start = request.args.get("start", "2001-01-01")
    end = request.args.get("end", "2025-12-30")
    df = _df[(_df["acq_date"] >= start) & (_df["acq_date"] <= end)]
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    buf.seek(0)
    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=austria_fires.csv"},
    )


@app.route("/api/ingest", methods=["POST"])
def ingest():
    """_summary_

    Returns:
        _type_: _description_
    """
    global _df
    f = request.files.get("file")
    if not f:
        return jsonify({"error": "no file"}), 400
    path = DATA_DIR / secure_filename(f.filename)
    f.save(path)
    if path.suffix == ".parquet":
        new = pd.read_parquet(path)
    else:
        new = pd.read_csv(path, parse_dates=["acq_date"])
    for col in ("acq_date", "instrument"):
        if col not in new.columns:
            return jsonify({"error": f"missing column: {col}"}), 400
    new.to_parquet(DATA_FILE, index=False)
    _df = _load()
    return jsonify({"rows": len(_df), "status": "ok"})


# ── OUTPUT: scientist downloads the harmonized dataset ───────────────────
@app.route("/api/data")
def data_out():
    fmt = request.args.get("format", "csv")
    if fmt == "parquet":
        buf = io.BytesIO()
        _df.to_parquet(buf, index=False)
        buf.seek(0)
        return Response(buf.getvalue(), mimetype="application/octet-stream",
                        headers={"Content-Disposition": "attachment; filename=harmonized.parquet"})
    else:
        buf = io.StringIO()
        _df.to_csv(buf, index=False)
        buf.seek(0)
        return Response(buf.getvalue(), mimetype="text/csv",
                        headers={"Content-Disposition": "attachment; filename=harmonized.csv"})


# Load webpage
if __name__ == "__main__":
    app.run(debug=True, port=5000)   