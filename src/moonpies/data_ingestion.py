from collections import defaultdict

import polars as pl

from moonpies.consts import DATA_DIR


def fetch_data():
    europe = DATA_DIR/"europe"

    sensors:defaultdict[str, list] = defaultdict(list)

    for year in europe.iterdir():
        for sensor in year.iterdir():
            # if "viirs" not in sensor.name:
            #     continue 
            for file in sensor.iterdir():
                df = pl.read_csv(file, schema_overrides={
                        "scan": pl.Float64,
                        "track": pl.Float64,
                        "latitude": pl.Float64,
                        "longitude": pl.Float64,
                        "brightness": pl.Float64,
                        "bright_t31": pl.Float64,
                        "frp": pl.Float64,
                    })
                
                name = file.with_suffix("").name
                df = df.with_columns(
                    pl.lit(name[name.find("_",name.find("_") + 1 )+1:]).alias("country")
                )
                sensors[sensor.name].append(df)
                
    for k,v in sensors.items():
        sensors[k] = pl.concat(v)
    return sensors
        
if __name__ == "__main__":
    data = fetch_data()
    print(data)