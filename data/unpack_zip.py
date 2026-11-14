#!/usr/bin/env python3
"Usage python data/unpack_zip.py portugal"

# Created using Mistral Large 4
import argparse
import zipfile
from pathlib import Path

current_dir = Path(__file__).parent

def get_sensor_folder(filename):
    """Determine sensor folder from filename."""
    lower = filename.lower()
    if 'snpp' in lower or 'viirs-snpp' in lower:
        return 'viirs-snpp'
    elif 'viirs' in lower:
        return 'viirs'
    elif 'modis' in lower:
        return 'modis'
    return None

def main():
    parser = argparse.ArgumentParser(description='Extract CSV files whose names contain a word from ZIP archives')
    parser.add_argument('word', help='Word to search for in CSV filenames')
    args = parser.parse_args()

    search_word = args.word.lower()

    zip_files = [f for f in current_dir.iterdir() if f.suffix == ".zip"]

    for zip_file in zip_files:
        with zipfile.ZipFile(zip_file, 'r') as z:
            for info in z.infolist():
                if not info.filename.lower().endswith('.csv'):
                    continue

                if search_word in info.filename.lower():
                    sensor = get_sensor_folder(info.filename)
                    if sensor:
                        sensor_dir = current_dir / sensor
                        sensor_dir.mkdir(parents=True, exist_ok=True)
                        dest = sensor_dir / Path(info.filename).name
                        dest.write_bytes(z.read(info.filename))
                        print(f"Extracted: {info.filename} -> {sensor}/")

if __name__ == '__main__':
    main()
