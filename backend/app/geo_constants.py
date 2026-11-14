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


# Mauza/area names inside each Noakhali Paurashava ward (from the municipality's ward breakdown).
# "(partial)" areas straddle two wards. Used only for display names; the ward polygons themselves
# are still the demonstration grid unless official boundaries are loaded.
WARD_AREAS: dict[int, str] = {
    1: "Madhusudanpur, Maijdee (partial)",
    2: "Anantapur, Chandrapur, Fatehpur, Maijdee (partial)",
    3: "Lakshminarayanpur (partial)",
    4: "Joykrishnapur, Uttar Fakirpur, Alipur (partial), Krishrampur (partial)",
    5: "Guptangk, Harinarayanpur, Lawyers Colony, Poshim Madhuri, Purba Madhuri, Lakshminarayanpur (partial), Poshim Rajarampur (partial)",
    6: "Gopairamshankar, Purba Ramchandrapur, Sahapur, Ujjalpur, Ayubpur (partial), Kashirampur (partial)",
    7: "Madhya Karimpur, Sreepur, Taj Mohabbatpur",
    8: "Chhotto Sreepur, Matipur, Sonapur",
    9: "Mohabbatpur, Poshim Badaripur, Salla Ghatia, Uttar Lakshmipur, Uttar Narayanpur, Jalialpur (partial)",
}


def ward_display_name(number: int) -> str:
    areas = WARD_AREAS.get(number)
    return f"Ward {number} · {areas} (demonstration grid)" if areas else f"Ward {number} (demonstration grid)"
