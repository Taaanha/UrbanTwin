"""Download the elevation tiles for the study area once and cache them (backend/data/dem_noakhali.npz).

Run from the backend folder, on a machine with internet:
    python -m scripts.fetch_dem
"""

from app.services import flood


def main() -> None:
    try:
        dem = flood.fetch_dem()
    except flood.DemUnavailable as exc:
        raise SystemExit(f"Failed: {exc}")
    info = flood.status()
    print(f"Saved {info['cells']} cells. Ground height {info['ground_min_m']} to {info['ground_max_m']} m (median {info['ground_median_m']} m).")
    print("Source:", dem["source"])


if __name__ == "__main__":
    main()
