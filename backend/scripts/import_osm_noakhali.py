"""Download OpenStreetMap features for the UrbanTwin Noakhali study area.

Run from D:\\Urbantwin\\backend:

    .\\.venv\\Scripts\\python.exe scripts\\import_osm_noakhali.py
"""

from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import requests
from geoalchemy2.shape import from_shape
from shapely.geometry import (
    GeometryCollection,
    LineString,
    MultiLineString,
    MultiPolygon,
    Point,
    Polygon,
    box,
)
from shapely.ops import linemerge, polygonize, unary_union

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.database import SessionLocal, init_db  # noqa: E402
from app.geo_constants import (  # noqa: E402
    CRS,
    OSM_LICENSE,
    OSM_UPAZILA_RELATION_ID,
    STUDY_BBOX,
)
from app.models.geo import (  # noqa: E402
    AdminBoundary,
    Building,
    DataSource,
    Drain,
    Road,
    StudyArea,
    Ward,
    WaterBody,
)

OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]
USER_AGENT = "UrbanTwin/0.1 (university lab; OSM ODbL attribution)"
RAW_DIR = ROOT.parent / "datasets" / "raw"
PROCESSED_DIR = ROOT.parent / "datasets" / "processed"

WEST, SOUTH, EAST, NORTH = STUDY_BBOX
STUDY_POLYGON = box(WEST, SOUTH, EAST, NORTH)


def osm_api_map(west: float, south: float, east: float, north: float) -> dict:
    url = f"https://api.openstreetmap.org/api/0.6/map?bbox={west},{south},{east},{north}"
    print(f"  OSM API map {url}")
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=120)
    response.raise_for_status()
    return osm_xml_to_payload(response.text)


def osm_api_relation_full(relation_id: int) -> dict:
    url = f"https://api.openstreetmap.org/api/0.6/relation/{relation_id}/full"
    print(f"  OSM API relation {url}")
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=120)
    response.raise_for_status()
    return osm_xml_to_payload(response.text)


def osm_xml_to_payload(xml_text: str) -> dict:
    root = ET.fromstring(xml_text)
    nodes: dict[int, tuple[float, float]] = {}
    elements: list[dict] = []
    for node in root.findall("node"):
        node_id = int(node.attrib["id"])
        lon = float(node.attrib["lon"])
        lat = float(node.attrib["lat"])
        nodes[node_id] = (lon, lat)
        elements.append({"type": "node", "id": node_id, "lon": lon, "lat": lat})
    for way in root.findall("way"):
        refs = [int(nd.attrib["ref"]) for nd in way.findall("nd")]
        tags = {tag.attrib["k"]: tag.attrib["v"] for tag in way.findall("tag")}
        geometry = [{"lon": nodes[ref][0], "lat": nodes[ref][1]} for ref in refs if ref in nodes]
        elements.append(
            {
                "type": "way",
                "id": int(way.attrib["id"]),
                "nodes": refs,
                "tags": tags,
                "geometry": geometry,
            }
        )
    for relation in root.findall("relation"):
        tags = {tag.attrib["k"]: tag.attrib["v"] for tag in relation.findall("tag")}
        members = []
        for member in relation.findall("member"):
            member_type = member.attrib.get("type")
            ref = int(member.attrib["ref"])
            role = member.attrib.get("role", "")
            item: dict = {"type": member_type, "ref": ref, "role": role}
            if member_type == "way":
                way = next((el for el in elements if el["type"] == "way" and el["id"] == ref), None)
                if way:
                    item["geometry"] = way["geometry"]
            members.append(item)
        elements.append(
            {
                "type": "relation",
                "id": int(relation.attrib["id"]),
                "tags": tags,
                "members": members,
            }
        )
    return {"elements": elements}


def overpass(query: str) -> dict:
    last_error: Exception | None = None
    for url in OVERPASS_URLS:
        try:
            print(f"  Overpass {url} ...")
            response = requests.post(
                url,
                data={"data": query},
                headers={"User-Agent": USER_AGENT},
                timeout=300,
            )
            response.raise_for_status()
            return response.json()
        except Exception as exc:  # noqa: BLE001 — try the next mirror
            last_error = exc
    raise RuntimeError(f"Overpass request failed: {last_error}") from last_error


def way_lookup(elements: list[dict]) -> tuple[dict[int, tuple[float, float]], list[dict]]:
    nodes = {
        el["id"]: (el["lon"], el["lat"])
        for el in elements
        if el.get("type") == "node" and "lon" in el
    }
    ways = [el for el in elements if el.get("type") == "way"]
    return nodes, ways


def coords_for_way(way: dict, nodes: dict[int, tuple[float, float]]) -> list[tuple[float, float]]:
    if "geometry" in way:
        return [(pt["lon"], pt["lat"]) for pt in way["geometry"]]
    return [nodes[nid] for nid in way.get("nodes", []) if nid in nodes]


def as_line(coords: list[tuple[float, float]]) -> LineString | None:
    if len(coords) < 2:
        return None
    line = LineString(coords)
    return None if line.is_empty else line


def as_polygon(coords: list[tuple[float, float]]) -> Polygon | None:
    if len(coords) < 4:
        return None
    if coords[0] != coords[-1]:
        coords = coords + [coords[0]]
    polygon = Polygon(coords)
    if not polygon.is_valid:
        polygon = polygon.buffer(0)
    if polygon.is_empty:
        return None
    if isinstance(polygon, MultiPolygon):
        polygon = max(polygon.geoms, key=lambda g: g.area)
    return polygon if isinstance(polygon, Polygon) else None


def relation_polygon(relation: dict) -> MultiPolygon | Polygon | None:
    rings: list[LineString] = []
    for member in relation.get("members", []):
        if member.get("type") != "way" or "geometry" not in member:
            continue
        if member.get("role") not in ("outer", "", None):
            continue
        coords = [(pt["lon"], pt["lat"]) for pt in member["geometry"]]
        line = as_line(coords)
        if line is not None:
            rings.append(line)
    if not rings:
        return None
    merged = linemerge(rings)
    polygons = list(polygonize(merged))
    if not polygons:
        return None
    geom = unary_union(polygons)
    if geom.is_empty:
        return None
    return geom


def explode(geom):
    if geom is None or geom.is_empty:
        return []
    if isinstance(geom, GeometryCollection):
        items = []
        for part in geom.geoms:
            items.extend(explode(part))
        return items
    if isinstance(geom, (MultiLineString, MultiPolygon)):
        return [part for part in geom.geoms if not part.is_empty]
    return [geom]


def clip(geom, mask):
    if geom is None or geom.is_empty:
        return []
    inter = geom.intersection(mask)
    return explode(inter)


def record_source(db, layer: str, limitations: str, steps: str, is_demo: bool) -> None:
    existing = db.query(DataSource).filter(DataSource.layer == layer).one_or_none()
    payload = dict(
        layer=layer,
        source_name="OpenStreetMap" if not is_demo else "UrbanTwin synthetic demonstration",
        license=OSM_LICENSE if not is_demo else "Not official municipal data",
        crs=CRS,
        acquired_at=datetime.now(timezone.utc),
        limitations=limitations,
        processing_steps=steps,
        is_demo=is_demo,
    )
    if existing:
        for key, value in payload.items():
            setattr(existing, key, value)
    else:
        db.add(DataSource(**payload))


def import_study_area(db) -> None:
    db.query(StudyArea).delete()
    db.add(
        StudyArea(
            name="Noakhali Paurashava study area (approximate)",
            geom=from_shape(STUDY_POLYGON, srid=4326),
            is_demo=False,
            notes=(
                "Envelope around Maijdee sized to published Paurashava area "
                "(about 21–24 km²). Not an official cadastral or gazette boundary. "
                "OSM had no Paurashava polygon at import time."
            ),
        )
    )
    record_source(
        db,
        "study_area",
        "Not an official municipal boundary. Used only to clip OSM features.",
        "Constructed WGS84 bounding box around Maijdee (22.847–22.891 N, 91.075–91.123 E).",
        is_demo=False,
    )


def import_upazila(db, payload: dict) -> None:
    db.query(AdminBoundary).delete()
    relations = [el for el in payload.get("elements", []) if el.get("type") == "relation"]
    if not relations:
        record_source(
            db,
            "admin_boundaries",
            "OSM upazila polygon was not returned.",
            "Overpass relation query.",
            is_demo=False,
        )
        return
    rel = relations[0]
    geom = relation_polygon(rel)
    if geom is None:
        return
    if isinstance(geom, Polygon):
        geom = MultiPolygon([geom])
    tags = rel.get("tags", {})
    db.add(
        AdminBoundary(
            name=tags.get("name:en") or tags.get("name") or "Noakhali Sadar Upazila",
            admin_level=tags.get("admin_level"),
            osm_id=rel.get("id"),
            geom=from_shape(geom, srid=4326),
            is_demo=False,
            source="OpenStreetMap",
        )
    )
    record_source(
        db,
        "admin_boundaries",
        "This is the Sadar Upazila, which is larger than the Paurashava.",
        f"Overpass relation/{OSM_UPAZILA_RELATION_ID}; assembled outer ways; stored EPSG:4326.",
        is_demo=False,
    )


def import_demo_wards(db) -> None:
    db.query(Ward).delete()
    minx, miny, maxx, maxy = STUDY_POLYGON.bounds
    cols, rows = 3, 3
    width = (maxx - minx) / cols
    height = (maxy - miny) / rows
    number = 1
    for row in range(rows):
        for col in range(cols):
            cell = box(
                minx + col * width,
                maxy - (row + 1) * height,
                minx + (col + 1) * width,
                maxy - row * height,
            )
            db.add(
                Ward(
                    name=f"Ward {number} (demonstration grid)",
                    ward_number=number,
                    geom=from_shape(cell, srid=4326),
                    is_demo=True,
                    notes=(
                        "Demonstration cell only. Noakhali Paurashava has 9 official wards, "
                        "but OSM did not contain ward polygons. Do not treat this geometry "
                        "as a government ward boundary."
                    ),
                )
            )
            number += 1
    record_source(
        db,
        "wards",
        "Synthetic 3x3 grid. Not BBS/LGED/municipal ward boundaries.",
        "Split the study envelope into nine equal cells, numbered north to south.",
        is_demo=True,
    )


def import_osm_ways(db, payload: dict) -> dict[str, int]:
    nodes, ways = way_lookup(payload.get("elements", []))
    db.query(Road).delete()
    db.query(Building).delete()
    db.query(WaterBody).delete()
    db.query(Drain).delete()
    counts = {"roads": 0, "buildings": 0, "water_bodies": 0, "drains": 0}

    for way in ways:
        tags = way.get("tags") or {}
        coords = coords_for_way(way, nodes)
        osm_id = way.get("id")

        if tags.get("highway"):
            line = as_line(coords)
            for part in clip(line, STUDY_POLYGON):
                if not isinstance(part, LineString):
                    continue
                db.add(
                    Road(
                        name=tags.get("name") or tags.get("name:en"),
                        highway=tags.get("highway"),
                        osm_id=osm_id,
                        geom=from_shape(part, srid=4326),
                        properties={"highway": tags.get("highway")},
                        is_demo=False,
                    )
                )
                counts["roads"] += 1
            continue

        if tags.get("building"):
            polygon = as_polygon(coords)
            for part in clip(polygon, STUDY_POLYGON):
                if not isinstance(part, Polygon) or part.area == 0:
                    continue
                db.add(
                    Building(
                        name=tags.get("name") or tags.get("name:en"),
                        osm_id=osm_id,
                        geom=from_shape(part, srid=4326),
                        properties={"building": tags.get("building")},
                        is_demo=False,
                    )
                )
                counts["buildings"] += 1
            continue

        waterway = tags.get("waterway")
        if waterway in {"drain", "ditch"}:
            line = as_line(coords)
            for part in clip(line, STUDY_POLYGON):
                if not isinstance(part, LineString):
                    continue
                db.add(
                    Drain(
                        name=tags.get("name"),
                        waterway=waterway,
                        osm_id=osm_id,
                        geom=from_shape(part, srid=4326),
                        properties={"waterway": waterway},
                        is_demo=False,
                    )
                )
                counts["drains"] += 1
            continue

        if waterway or tags.get("natural") == "water" or tags.get("water"):
            geom = as_polygon(coords) if coords[0] == coords[-1] and len(coords) >= 4 else as_line(coords)
            for part in clip(geom, STUDY_POLYGON):
                if isinstance(part, Point):
                    continue
                db.add(
                    WaterBody(
                        name=tags.get("name"),
                        waterway=waterway or tags.get("natural") or tags.get("water"),
                        osm_id=osm_id,
                        geom=from_shape(part, srid=4326),
                        properties={k: tags.get(k) for k in ("waterway", "natural", "water") if tags.get(k)},
                        is_demo=False,
                    )
                )
                counts["water_bodies"] += 1

    record_source(
        db,
        "roads",
        "OSM completeness varies. Missing streets are not proof they do not exist.",
        "Overpass highway=* in study bbox; clip to envelope; EPSG:4326.",
        is_demo=False,
    )
    record_source(
        db,
        "buildings",
        "Building footprints are incomplete in many Bangladeshi towns.",
        "Overpass building=* closed ways; clip to envelope.",
        is_demo=False,
    )
    record_source(
        db,
        "water_bodies",
        "Not street-level flood mapping. Small ponds may be missing or generalised.",
        "Overpass waterway/natural=water/water tags; clip to envelope.",
        is_demo=False,
    )
    record_source(
        db,
        "drains",
        "OSM drain tagging in Noakhali is sparse. Absence of a drain is not evidence.",
        "Overpass waterway=drain|ditch; clip to envelope.",
        is_demo=False,
    )
    return counts


def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    init_db()

    print("Downloading OSM map extract via api.openstreetmap.org ...")
    ways_payload = osm_api_map(WEST, SOUTH, EAST, NORTH)
    (RAW_DIR / "noakhali_osm_ways.json").write_text(
        json.dumps({"attribution": "© OpenStreetMap contributors", "bbox": STUDY_BBOX}),
        encoding="utf-8",
    )

    print(f"Downloading OSM upazila relation {OSM_UPAZILA_RELATION_ID} ...")
    try:
        rel_payload = osm_api_relation_full(OSM_UPAZILA_RELATION_ID)
    except Exception as exc:  # noqa: BLE001
        print(f"Upazila download failed ({exc}); continuing without it.")
        rel_payload = {"elements": []}

    db = SessionLocal()
    try:
        import_study_area(db)
        import_upazila(db, rel_payload)
        import_demo_wards(db)
        counts = import_osm_ways(db, ways_payload)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    catalog = {
        "place": "Noakhali Paurashava / Maijdee (study envelope)",
        "crs": CRS,
        "license": OSM_LICENSE,
        "acquired_at": datetime.now(timezone.utc).isoformat(),
        "bbox": {"west": WEST, "south": SOUTH, "east": EAST, "north": NORTH},
        "counts": counts,
        "limitations": [
            "No official Paurashava polygon in OSM at import time.",
            "Wards are a labelled demonstration grid.",
            "OSM is volunteered data and is incomplete.",
        ],
    }
    (PROCESSED_DIR / "noakhali_osm_catalog.json").write_text(
        json.dumps(catalog, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(catalog, indent=2))
    print("Import complete.")


if __name__ == "__main__":
    main()
