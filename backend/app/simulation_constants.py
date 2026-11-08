"""Assumptions for City Simulation. Every number here is a stated lab assumption."""

ACCESS_RADIUS_M = 400.0  # walking distance used for 'has green space nearby'
CANOPY_RADIUS_M = 3.0  # mature crown radius of one planted tree
TREES_PER_SITE = 25
MAX_SITES = 60
MAX_CANDIDATES = 500
SAMPLE_SEED = 42

DISCLAIMER = (
    "Scenario results come from simple geometry on the data currently loaded: building "
    "centres, green-space polygons and a demonstration ward grid. They show how a "
    "proposal changes coverage under the stated assumptions. They are not forecasts "
    "of health, temperature, flooding or any other real-world outcome."
)

ASSUMPTIONS = [
    f"A building has green-space access if its centre is within {ACCESS_RADIUS_M:.0f} m (straight line, not walking route) of green space.",
    f"A planting site of {TREES_PER_SITE} trees is treated as a small green space (disc area = trees x crown area).",
    f"Crown radius {CANOPY_RADIUS_M:.0f} m per mature tree. Young saplings cover far less and survival is not modelled.",
    "Building centres, not residents, are counted. Population and building height are not available.",
    "Ward polygons are a demonstration grid, not official Paurashava wards.",
    "Green spaces come from OSM (incomplete) or labelled demonstration polygons.",
    "Distances use a local flat-earth approximation around the study centre (error well under 1% here).",
]
