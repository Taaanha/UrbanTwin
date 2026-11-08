"""Lab placeholder rates and quantity rules. Not a PWD/LGED schedule."""

DISCLAIMER = (
    "All costs are indicative lab placeholders in BDT. They are not official "
    "Paurashava, LGED, or PWD rates, and they are not a tender estimate."
)

RATE_SOURCE = (
    "No verified local schedule of rates was available for this lab. "
    "Amounts are round placeholder figures for comparing options only."
)

CONTINGENCY_PCT = 0.10
RANGE_PCT = 0.25

SEVERITY_POINTS = {"critical": 40, "high": 30, "medium": 18, "low": 8}
SAFETY_POINTS = {
    "pothole": 15,
    "damaged_road": 15,
    "broken_sidewalk": 12,
    "flooding": 12,
    "waterlogging": 12,
    "blocked_drainage": 10,
}

# quantity, unit, action, notes — quantities are assumed, not surveyed
QUANTITIES = {
    "pothole": (4.0, "m2", "patch_repair", "Assumed 4 m² patch. Not measured on site."),
    "damaged_road": (30.0, "m2", "surface_repair", "Assumed 10 m × 3 m overlay. Not a surveyed road length."),
    "broken_sidewalk": (10.0, "m2", "footpath_repair", "Assumed 10 m² of footpath. Not measured."),
    "blocked_drainage": (15.0, "m", "drain_clearing", "Assumed 15 m of drain clearing. OSM drains may be missing."),
    "waterlogging": (20.0, "m", "drain_clearing", "Assumed 20 m of drain work. Not a hydrology model."),
    "garbage": (1.0, "load", "waste_collection", "Assumed one truck-load. Volume was not weighed."),
    "illegal_waste": (1.0, "load", "waste_collection", "Assumed one truck-load. Volume was not weighed."),
    "damaged_infrastructure": (1.0, "lump", "spot_repair", "Lump-sum placeholder. No bill of quantities."),
    "vegetation_loss": (10.0, "sapling", "tree_planting", "Assumed 10 saplings. Not a planting design."),
    "flooding": (20.0, "m", "drain_clearing", "Assumed drain work. Not a flood-risk assessment."),
    "other": (1.0, "lump", "spot_repair", "Lump-sum placeholder."),
}

# action_code, category, unit, amount_bdt, notes
DEFAULT_RATES = [
    ("patch_repair", "pothole", "m2", 2500, "Placeholder per m² of patch."),
    ("surface_repair", "damaged_road", "m2", 1800, "Placeholder per m² of overlay."),
    ("footpath_repair", "broken_sidewalk", "m2", 1600, "Placeholder per m² of footpath."),
    ("drain_clearing", "blocked_drainage", "m", 900, "Placeholder per metre of clearing."),
    ("drain_clearing", "waterlogging", "m", 900, "Same placeholder as drainage clearing."),
    ("drain_clearing", "flooding", "m", 900, "Same placeholder as drainage clearing."),
    ("waste_collection", "garbage", "load", 8000, "Placeholder per truck-load."),
    ("waste_collection", "illegal_waste", "load", 8000, "Placeholder per truck-load."),
    ("spot_repair", "damaged_infrastructure", "lump", 25000, "Placeholder lump sum."),
    ("tree_planting", "vegetation_loss", "sapling", 450, "Placeholder per sapling."),
    ("spot_repair", "other", "lump", 15000, "Placeholder lump sum."),
]

SHARE_LABOUR = 0.40
SHARE_MATERIALS = 0.40
SHARE_EQUIPMENT = 0.10
