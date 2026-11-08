"""Study envelope for Noakhali Paurashava (Maijdee).

OSM does not currently publish an official Paurashava polygon or ward
polygons. This envelope is sized to the published municipal area
(~21–24 km²) around Maijdee and is NOT a cadastral boundary.
"""

from __future__ import annotations

# west, south, east, north (WGS84 / EPSG:4326)
STUDY_BBOX = (91.075, 22.847, 91.123, 22.891)
STUDY_CENTER = (91.099, 22.869)
OSM_UPAZILA_RELATION_ID = 14326635
OSM_LICENSE = "ODbL 1.0"
CRS = "EPSG:4326"
