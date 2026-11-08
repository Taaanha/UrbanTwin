"""Import OSM green-space polygons for the Noakhali study area (optional, needs internet).

Run from D:\\Urbantwin\\backend:

    .\\.venv\\Scripts\\python.exe scripts\\import_osm_green.py

Only closed ways are imported (parks, gardens, grass, woods...). Relations are
skipped, and OSM green space in Bangladesh is incomplete, so City Simulation
results must be read with that in mind.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from geoalchemy2.shape import from_shape  # noqa: E402
from shapely.geometry import Polygon  # noqa: E402

from import_osm_noakhali import (  # noqa: E402
    EAST,
    NORTH,
    SOUTH,
    STUDY_POLYGON,
    WEST,
    as_polygon,
    clip,
    coords_for_way,
    osm_api_map,
    record_source,
    way_lookup,
)

from app.database import SessionLocal  # noqa: E402
from app.models.simulation import GreenSpace  # noqa: E402

LEISURE = {"park", "garden", "recreation_ground", "nature_reserve", "playground"}
LANDUSE = {"grass", "forest", "meadow", "village_green", "recreation_ground", "orchard", "greenfield"}
NATURAL = {"wood", "scrub", "grassland", "heath"}


def green_kind(tags: dict[str, str]) -> str | None:
    """Returns a label if the OSM tags describe urban green space, else None."""
    if tags.get("leisure") in LEISURE:
        return f"leisure={tags['leisure']}"
    if tags.get("landuse") in LANDUSE:
        return f"landuse={tags['landuse']}"
    if tags.get("natural") in NATURAL:
        return f"natural={tags['natural']}"
    return None


def import_green(db, payload: dict) -> int:
    nodes, ways = way_lookup(payload.get("elements", []))
    db.query(GreenSpace).filter(GreenSpace.is_demo.is_(False)).delete()
    count = 0
    for way in ways:
        tags = way.get("tags") or {}
        kind = green_kind(tags)
        if kind is None:
            continue
        polygon = as_polygon(coords_for_way(way, nodes))
        for part in clip(polygon, STUDY_POLYGON):
            if not isinstance(part, Polygon) or part.area == 0:
                continue
            db.add(
                GreenSpace(
                    name=tags.get("name") or tags.get("name:en"),
                    kind=kind,
                    osm_id=way.get("id"),
                    geom=from_shape(part, srid=4326),
                    is_demo=False,
                    properties={k: tags[k] for k in ("leisure", "landuse", "natural") if k in tags},
                )
            )
            count += 1
    record_source(
        db,
        "green_spaces",
        "OSM green space is incomplete; closed ways only; farmland excluded. Tree canopy is not measured.",
        "OSM map API bbox; filtered leisure/landuse/natural tags; clipped to study envelope; EPSG:4326.",
        is_demo=False,
    )
    return count


def main() -> None:
    print("Downloading OSM extract ...")
    payload = osm_api_map(WEST, SOUTH, EAST, NORTH)
    db = SessionLocal()
    try:
        count = import_green(db, payload)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    print(f"Imported {count} green-space polygons (ODbL, (c) OpenStreetMap contributors).")


if __name__ == "__main__":
    main()
