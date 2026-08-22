"""
Synthetic scenario data for Setu's demo: a fictional flood affecting a
cluster of East Delhi wards, overlaid on real-world coordinates.
All entities here are synthetic / for-demo-purposes, per SETU Phase 11/23.
"""
import random

# Roughly the Yamuna floodplain / East Delhi area (Mayur Vihar - Gandhi Nagar belt)
CENTER = (28.6280, 77.2870)

WARDS = [
    {"id": "W1", "name": "Ward 1 - Yamuna Bank",     "lat": 28.6390, "lon": 77.2790, "population": 21000, "vulnerability": 0.8},
    {"id": "W2", "name": "Ward 2 - Gandhi Nagar",     "lat": 28.6510, "lon": 77.2660, "population": 34000, "vulnerability": 0.4},
    {"id": "W3", "name": "Ward 3 - Mayur Vihar I",    "lat": 28.6070, "lon": 77.2930, "population": 42000, "vulnerability": 0.5},
    {"id": "W4", "name": "Ward 4 - Mayur Vihar II",   "lat": 28.6130, "lon": 77.3080, "population": 29000, "vulnerability": 0.5},
    {"id": "W5", "name": "Ward 5 - Trilokpuri",       "lat": 28.6010, "lon": 77.3010, "population": 38000, "vulnerability": 0.7},
    {"id": "W6", "name": "Ward 6 - Kalyanpuri",       "lat": 28.6180, "lon": 77.3160, "population": 26000, "vulnerability": 0.6},
    {"id": "W7", "name": "Ward 7 - Shakarpur",        "lat": 28.6360, "lon": 77.2970, "population": 19000, "vulnerability": 0.3},
    {"id": "W8", "name": "Ward 8 - Laxmi Nagar",      "lat": 28.6350, "lon": 77.2760, "population": 31000, "vulnerability": 0.3},
    {"id": "W9", "name": "Ward 9 - Khichripur",       "lat": 28.5940, "lon": 77.3070, "population": 8000,  "vulnerability": 0.9},
    {"id": "W10", "name": "Ward 10 - Anand Vihar",    "lat": 28.6470, "lon": 77.3150, "population": 24000, "vulnerability": 0.4},
]

HUBS = [
    {
        "id": "HUB-A", "name": "Mayur Vihar Relief Hub", "org": "Delhi DDMA",
        "lat": 28.6080, "lon": 77.2960,
        "inventory": {"medical": 60, "water": 400, "food": 500, "shelter_kit": 120},
    },
    {
        "id": "HUB-B", "name": "Gandhi Nagar Warehouse", "org": "Red Cross Delhi (NGO)",
        "lat": 28.6490, "lon": 77.2700,
        "inventory": {"medical": 30, "water": 600, "food": 300, "shelter_kit": 80},
    },
    {
        "id": "HUB-C", "name": "Kalyanpuri Field Depot", "org": "Delhi DDMA",
        "lat": 28.6160, "lon": 77.3140,
        "inventory": {"medical": 45, "water": 250, "food": 350, "shelter_kit": 60},
    },
]

VEHICLES = [
    {"id": "V1", "hub_id": "HUB-A", "type": "van", "capacity": 120},
    {"id": "V2", "hub_id": "HUB-A", "type": "van", "capacity": 120},
    {"id": "V3", "hub_id": "HUB-B", "type": "van", "capacity": 100},
    {"id": "V4", "hub_id": "HUB-B", "type": "boat", "capacity": 60},
    {"id": "V5", "hub_id": "HUB-C", "type": "van", "capacity": 110},
    {"id": "V6", "hub_id": "HUB-C", "type": "4x4", "capacity": 90},
]

SHELTERS = [
    {"id": "S1", "name": "Mayur Vihar Community Hall", "lat": 28.6055, "lon": 77.2915, "capacity": 500, "occupancy": 310},
    {"id": "S2", "name": "Gandhi Nagar Govt School",    "lat": 28.6525, "lon": 77.2635, "capacity": 350, "occupancy": 340},
    {"id": "S3", "name": "Kalyanpuri Sports Complex",   "lat": 28.6205, "lon": 77.3190, "capacity": 600, "occupancy": 180},
    {"id": "S4", "name": "Trilokpuri Marriage Hall",    "lat": 28.5985, "lon": 77.2965, "capacity": 250, "occupancy": 250},
]

# Road segments used only as flaggable "block points" between a ward and the
# nearest hub, since we don't have a full OSM road graph in this prototype -
# blocking one multiplies the effective travel cost on that hub<->ward leg.
ROAD_SEGMENTS = [
    {"id": "RD-1", "name": "NH24 underpass, Mayur Vihar",      "ward_id": "W3", "hub_id": "HUB-A"},
    {"id": "RD-2", "name": "Yamuna bridge approach, Ward 1",   "ward_id": "W1", "hub_id": "HUB-A"},
    {"id": "RD-3", "name": "Vikas Marg, Shakarpur",            "ward_id": "W7", "hub_id": "HUB-B"},
    {"id": "RD-4", "name": "Kalyanpuri main road",             "ward_id": "W6", "hub_id": "HUB-C"},
    {"id": "RD-5", "name": "Trilokpuri link road",             "ward_id": "W5", "hub_id": "HUB-C"},
]

CATEGORIES = ["medical", "water", "food", "shelter_kit"]
CRITICAL_CATEGORIES = {"medical"}

SOURCE_TYPES = {
    "agency_verified": 0.95,
    "ngo_field_worker": 0.8,
    "crowd_corroborated": 0.55,
    "crowd_single": 0.25,
}


def _rand_point_near(lat, lon, spread=0.006):
    return (lat + random.uniform(-spread, spread), lon + random.uniform(-spread, spread))


def seed_initial_demands(n=42, seed=42):
    """Generate the initial batch of demand reports for the live demo."""
    rng = random.Random(seed)
    demands = []
    for i in range(n):
        ward = rng.choice(WARDS)
        lat, lon = _rand_point_near(ward["lat"], ward["lon"])
        category = rng.choices(CATEGORIES, weights=[0.22, 0.33, 0.28, 0.17])[0]
        source = rng.choices(
            list(SOURCE_TYPES.keys()), weights=[0.15, 0.2, 0.35, 0.3]
        )[0]
        severity = rng.choices([1, 2, 3], weights=[0.5, 0.35, 0.15])[0]
        if category in CRITICAL_CATEGORIES and rng.random() < 0.4:
            severity = 3
        demands.append(dict(
            ward_id=ward["id"],
            lat=lat, lon=lon,
            category=category,
            severity=severity,
            population_affected=rng.randint(4, 60),
            vulnerability_flag=rng.random() < ward["vulnerability"],
            source_type=source,
            note=f"{category} needed, {ward['name']}",
        ))
    # Deliberately plant the Phase-8 worked example: a quiet-but-severe pocket
    # in Ward 9 that a naive nearest-resource approach would rank below louder,
    # closer, lower-severity requests.
    w9 = next(w for w in WARDS if w["id"] == "W9")
    lat, lon = _rand_point_near(w9["lat"], w9["lon"], spread=0.002)
    demands.append(dict(
        ward_id="W9", lat=lat, lon=lon, category="medical", severity=3,
        population_affected=12, vulnerability_flag=True,
        source_type="agency_verified",
        note="Elderly residents stranded, medical need, Khichripur (low-report-volume pocket)",
    ))
    return demands
