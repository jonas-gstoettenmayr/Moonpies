from moonpies import fetch_data, harmonize
from moonpies.consts import DATA_DIR


def main():
    
    data_dict = fetch_data()
    keys = list(data_dict.keys())
    for k, v in data_dict.items():
        data_dict[k] = v.filter(v["type"] == 0)
        
    grid_merged = harmonize(data_dict[keys[0]], data_dict[keys[1]], grid_res=0.1)
    grid_merged.write_parquet(DATA_DIR/"harmonize_grid.parquet")
    
    
if __name__ == "__main__":
    main()