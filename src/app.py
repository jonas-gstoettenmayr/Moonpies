import io
import os
import pandas as pd
from pathlib import Path
from flask import Flask, Response, jsonify, request, send_from_directory, send_file

BASE = Path(__file__).resolve().parent.parent
app = Flask(__name__, static_folder=str(BASE/"web"), static_url_path="")

# Load or ingest data from source
_df = pd.read_parquet(BASE/"data"/"harmonized.parquet")
_df["acq_date"] = pd.to_datetime(_df["acq_date"])
_df["sensor"] = _df["instrument"]   

# Random period - ToDO fixed period after working
overlap = _df[(_df["acq_date"] >= "2012-07") & (_df["acq_date"] <= "2025-12")]

# Evaluate the regions overlap by multiple sensors
ratio = len(overlap[overlap["sensor"] == "VIIRS"]) / max(
    len(overlap[overlap["sensor"] == "MODIS"]), 1
)

# 
_df["harmonized_count"] = _df["sensor"].map({"VIIRS": 1.0, "MODIS": ratio})
print(f"Loaded {len(_df):,} rows | ratio={ratio:.2f}")

# Data routing 
@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/api/calendar")
def calendar():
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


@app.route("/")
def index():
    return send_from_directory(str(BASE / "web"), "index.html")


if __name__ == "__main__":
    app.run(debug=True, port=5000)


# @app.route("/hello")
# def hello_api() -> Response:
#     greet = os.getenv("GREET", "stranger")
#     return jsonify({"message": f"Hello from Flask, {greet}!"})


# @app.route("/health")
# def healthcheck_api() -> Response:
#     return jsonify({"status": "ok"})

    