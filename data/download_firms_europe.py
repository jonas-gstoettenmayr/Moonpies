"""Download NASA FIRMS yearly country summaries for Europe.

The FIRMS country page loads its files from a public manifest. This script
uses that manifest instead of scraping the page's JavaScript-rendered HTML.
"""

from __future__ import annotations

import argparse
import csv
import io
import re
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


MANIFEST_URL = (
    "https://firms.modaps.eosdis.nasa.gov/data/country/"
    "yearly_summary_files.txt"
)
DATA_URL = "https://firms.modaps.eosdis.nasa.gov/data/country/{filename}"

EUROPEAN_COUNTRIES = frozenset(
    """
    Albania Andorra Austria Belarus Belgium Bosnia_and_Herzegovina Bulgaria
    Croatia Cyprus Czech_Republic Denmark Estonia Faroe_Islands Finland France
    Germany Gibraltar Greece Guernsey Holy_See Hungary Iceland Ireland
    Isle_of_Man Italy Jersey Kosovo Latvia Liechtenstein Lithuania Luxembourg
    Macedonia_Former_Yugoslav_Republic_of Malta Moldova Monaco Montenegro
    Netherlands Norway Poland Portugal Romania Russian_Federation San_Marino
    Serbia Slovakia Slovenia Spain Svalbard_and_Jan_Mayen Sweden Switzerland
    Turkey Ukraine United_Kingdom
    """.split()
)

FILENAME_RE = re.compile(
    r"(?P<sensor>modis|viirs-jpss1|viirs-jpss2|viirs-noaa21)"
    r"_(?P<year>\d{4})_(?P<country>.+)\.csv$"
)


def fetch(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": "Moonpies FIRMS downloader"})
    with urlopen(request, timeout=60) as response:
        return response.read()


def manifest_files(start_year: int, end_year: int) -> list[str]:
    """Return European CSV filenames in the requested inclusive year range."""
    content = fetch(MANIFEST_URL).decode("utf-8-sig")
    files = []
    for row in csv.DictReader(io.StringIO(content)):
        filename = (row.get("filename") or "").strip()
        match = FILENAME_RE.fullmatch(filename)
        if not match:
            continue
        year = int(match["year"])
        if start_year <= year <= end_year and match["country"] in EUROPEAN_COUNTRIES:
            files.append(filename)
    return sorted(files, key=lambda name: (int(FILENAME_RE.fullmatch(name)["year"]), name))


def download(files: list[str], output_dir: Path, overwrite: bool) -> int:
    downloaded = 0
    for filename in files:
        match = FILENAME_RE.fullmatch(filename)
        if match is None:
            raise ValueError(f"Unexpected manifest filename: {filename}")

        destination = (
            output_dir
            / match["year"]
            / match["sensor"]
            / filename
        )
        if destination.exists() and not overwrite:
            print(f"Skipping existing {destination}")
            continue

        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".part")
        try:
            temporary.write_bytes(fetch(DATA_URL.format(filename=filename)))
            temporary.replace(destination)
        except (HTTPError, URLError, OSError):
            temporary.unlink(missing_ok=True)
            raise

        downloaded += 1
        print(f"Downloaded {destination}")
    return downloaded


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-year", type=int, required=True)
    parser.add_argument("--end-year", type=int)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "firms_europe",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="redownload files that already exist",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    end_year = args.end_year if args.end_year is not None else args.start_year
    if args.start_year > end_year:
        raise ValueError("--start-year must be less than or equal to --end-year")

    files = manifest_files(args.start_year, end_year)
    print(f"Found {len(files)} European files in {args.start_year}-{end_year}.")
    downloaded = download(files, args.output_dir, args.overwrite)
    print(f"Downloaded {downloaded} file(s) to {args.output_dir}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (HTTPError, URLError, OSError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1)
