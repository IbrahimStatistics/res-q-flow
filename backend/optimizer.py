"""
Setu's decision core.

Deliberately NOT machine learning (see SETU doc Phase 15):
  - Priority score: a transparent, tunable weighted formula.
  - Dedup: geo-proximity clustering + classical keyword-overlap similarity.
  - Allocation: OR-Tools CP-SAT constrained assignment (Stage A).
  - Routing: OR-Tools Routing capacitated VRP (Stage B).
Both stages are re-solved on every /api/optimize call (the "rolling horizon"),
warm-started conceptually by always re-deriving from current live state.
"""
import math
import time
from ortools.sat.python import cp_model
from ortools.constraint_solver import routing_enums_pb2, pywrapcp

CRITICAL_CATEGORIES = {"medical"}
BLOCKED_ROAD_PENALTY = 12.0  # multiplier applied to a hub<->ward leg on a blocked segment

DEFAULT_WEIGHTS = {
    "severity": 22.0,
    "population": 0.35,
    "vulnerability": 15.0,
    "freshness": 10.0,
    "confidence_penalty": 25.0,
}


def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(min(1, math.sqrt(a)))


def word_set(text):
    return set(w.lower().strip(".,!?") for w in text.split() if len(w) > 2)


def text_similarity(a, b):
    """Classical Jaccard keyword-overlap similarity - not an ML model."""
    sa, sb = word_set(a), word_set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def dedup_cluster(reports, geo_threshold_km=0.35, text_threshold=0.3):
    """
    Cluster raw demand reports into deduplicated Demand clusters using
    geo-proximity (ST_DWithin-style) + keyword-overlap text similarity.
    Each corroborating report inside a cluster raises its confidence.
    """
    clusters = []  # each: {reports: [...], lat, lon, category}
    for r in reports:
        placed = False
        for c in clusters:
            same_category = c["category"] == r["category"]
            dist = haversine_km(c["lat"], c["lon"], r["lat"], r["lon"])
            close = dist <= geo_threshold_km
            # Text similarity only breaks a tie at the edge of the geo radius
            # (e.g. two reports of the same incident straddling the threshold) -
            # it never merges reports that are simply far apart, even if worded alike.
            borderline_close = dist <= geo_threshold_km * 2
            similar_text = borderline_close and text_similarity(c["reports"][0]["note"], r["note"]) >= text_threshold
            if same_category and (close or similar_text):
                c["reports"].append(r)
                # recentre cluster on running average location
                n = len(c["reports"])
                c["lat"] = (c["lat"] * (n - 1) + r["lat"]) / n
                c["lon"] = (c["lon"] * (n - 1) + r["lon"]) / n
                placed = True
                break
        if not placed:
            clusters.append({"reports": [r], "lat": r["lat"], "lon": r["lon"], "category": r["category"]})
    return clusters


def confidence_for_cluster(cluster, source_types):
    reports = cluster["reports"]
    base = max(source_types.get(r["source_type"], 0.25) for r in reports)
    corroboration_bonus = min(0.35, 0.08 * (len(reports) - 1))
    return round(min(0.99, base + corroboration_bonus), 2)


def freshness_decay(age_minutes, half_life_minutes=90):
    return 0.5 ** (age_minutes / half_life_minutes)


def priority_score(cluster, confidence, age_minutes, weights):
    reports = cluster["reports"]
    severity = max(r["severity"] for r in reports)
    population = sum(r["population_affected"] for r in reports) / len(reports)
    vulnerability = 1.0 if any(r["vulnerability_flag"] for r in reports) else 0.0
    fresh = freshness_decay(age_minutes)
    score = (
        weights["severity"] * severity
        + weights["population"] * population
        + weights["vulnerability"] * vulnerability
        + weights["freshness"] * fresh
        - weights["confidence_penalty"] * (1 - confidence)
    )
    return round(score, 2), dict(
        severity=severity, population_affected=round(population, 1),
        vulnerability_flag=bool(vulnerability), freshness=round(fresh, 2),
    )


def build_demands(raw_reports, source_types, weights, now_minutes_fn):
    """Full Stage-0 pipeline: dedup -> confidence -> priority, for a list of raw reports (each carrying a report timestamp in minutes-ago)."""
    clusters = dedup_cluster(raw_reports)
    demands = []
    for i, c in enumerate(clusters):
        confidence = confidence_for_cluster(c, source_types)
        age = min(r["age_minutes"] for r in c["reports"])
        score, breakdown = priority_score(c, confidence, age, weights)
        category = c["category"]
        total_qty = max(r["population_affected"] for r in c["reports"])
        demands.append(dict(
            cluster_index=i,
            lat=c["lat"], lon=c["lon"],
            category=category,
            confidence=confidence,
            priority_score=score,
            is_critical=category in CRITICAL_CATEGORIES,
            report_count=len(c["reports"]),
            ward_id=c["reports"][0].get("ward_id"),
            quantity_needed=max(10, int(total_qty * 0.6)),
            **breakdown,
        ))
    demands.sort(key=lambda d: -d["priority_score"])
    return demands


def effective_distance(hub, demand, blocked_pairs):
    d = haversine_km(hub["lat"], hub["lon"], demand["lat"], demand["lon"])
    if (hub["id"], demand.get("ward_id")) in blocked_pairs:
        d *= BLOCKED_ROAD_PENALTY
    return d


def solve_allocation(demands, hubs, blocked_pairs, min_confidence=0.4, fairness_weight=6.0):
    """
    Stage A - CP-SAT constrained assignment.
    Approximates the SETU lexicographic objective (life-safety > response time
    > fairness > efficiency) as a single weighted-sum objective with large
    tier gaps between the weight scales, which is the standard practical
    relaxation of lexicographic multi-objective optimization at this problem
    size (exact lexicographic solving would mean re-solving CP-SAT once per
    tier; the weighted-sum approximation is used here for a demo-friendly
    solve time).
    """
    model = cp_model.CpModel()
    n_d, n_h = len(demands), len(hubs)
    if n_d == 0 or n_h == 0:
        return []

    # x[d][h] = 1 if demand d is served by hub h
    x = {}
    for i in range(n_d):
        for j in range(n_h):
            x[i, j] = model.NewBoolVar(f"x_{i}_{j}")

    # Each demand served by at most one hub (unmet demand is allowed - Tier 1
    # objective below is what discourages leaving critical demand unmet).
    for i in range(n_d):
        model.Add(sum(x[i, j] for j in range(n_h)) <= 1)
        # Below the confidence floor, hold for corroboration - never auto-dispatch.
        if demands[i]["confidence"] < min_confidence:
            for j in range(n_h):
                model.Add(x[i, j] == 0)

    # Hub capacity: total quantity served can't exceed hub's stock of that category.
    for j, hub in enumerate(hubs):
        for category, stock in hub["inventory"].items():
            model.Add(
                sum(x[i, j] * demands[i]["quantity_needed"]
                    for i in range(n_d) if demands[i]["category"] == category)
                <= stock
            )
        # category compatibility: a hub can't serve a category it has zero stock of
        for i in range(n_d):
            if hub["inventory"].get(demands[i]["category"], 0) <= 0:
                model.Add(x[i, j] == 0)

    # Fairness proxy: per-ward unmet critical demand, penalized.
    ward_ids = sorted(set(d["ward_id"] for d in demands))
    unmet_ward_penalty = []
    for w in ward_ids:
        idxs = [i for i in range(n_d) if demands[i]["ward_id"] == w and demands[i]["is_critical"]]
        if not idxs:
            continue
        unmet = model.NewIntVar(0, len(idxs), f"unmet_{w}")
        model.Add(unmet == sum(1 - sum(x[i, j] for j in range(n_h)) for i in idxs))
        unmet_ward_penalty.append(unmet)

    SCALE = 100  # keep CP-SAT in clean integer space
    terms = []
    for i in range(n_d):
        for j in range(n_h):
            dist = effective_distance(hubs[j], demands[i], blocked_pairs)
            # Tier1: life-safety coverage (huge weight on critical demand served)
            tier1 = (100000 if demands[i]["is_critical"] else 0)
            # base value of serving this demand at all, scaled by priority
            value = int((demands[i]["priority_score"] * 50 + tier1) * SCALE)
            # Tier2: response time - subtract distance cost
            cost = int(dist * 40 * SCALE)
            terms.append(x[i, j] * (value - cost))

    fairness_terms = [-int(fairness_weight * 1000 * SCALE) * u for u in unmet_ward_penalty]

    model.Maximize(sum(terms) + sum(fairness_terms))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 4.0
    solver.parameters.num_search_workers = 8
    status = solver.Solve(model)

    allocations = []
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        for i in range(n_d):
            for j in range(n_h):
                if solver.Value(x[i, j]) == 1:
                    allocations.append(dict(
                        demand_index=i, hub_id=hubs[j]["id"],
                        distance_km=round(effective_distance(hubs[j], demands[i], blocked_pairs), 2),
                        blocked=(hubs[j]["id"], demands[i]["ward_id"]) in blocked_pairs,
                    ))
    return allocations


def solve_routes(allocations, demands, hubs, vehicles, blocked_pairs):
    """
    Stage B - capacitated VRP per hub using OR-Tools Routing, one route per
    vehicle, respecting vehicle capacity. Blocked hub<->ward legs are modeled
    as a heavy time-penalty edge, which the solver then routes around by
    reordering / reassigning stops away from that leg where a cheaper
    alternative exists.
    """
    routes_by_vehicle = {}
    hubs_by_id = {h["id"]: h for h in hubs}

    for hub in hubs:
        hub_allocs = [a for a in allocations if a["hub_id"] == hub["id"]]
        if not hub_allocs:
            continue
        hub_vehicles = [v for v in vehicles if v["hub_id"] == hub["id"]]
        if not hub_vehicles:
            continue

        stops = [demands[a["demand_index"]] for a in hub_allocs]
        # node 0 = depot (hub), nodes 1..n = stops
        coords = [(hub["lat"], hub["lon"])] + [(s["lat"], s["lon"]) for s in stops]
        n = len(coords)

        def dist_matrix_fn(from_idx, to_idx):
            lat1, lon1 = coords[from_idx]
            lat2, lon2 = coords[to_idx]
            d = haversine_km(lat1, lon1, lat2, lon2)
            if from_idx == 0 and to_idx > 0:
                ward = stops[to_idx - 1]["ward_id"]
                if (hub["id"], ward) in blocked_pairs:
                    d *= BLOCKED_ROAD_PENALTY
            return int(d * 1000)  # meters, integer for OR-Tools

        manager = pywrapcp.RoutingIndexManager(n, len(hub_vehicles), 0)
        routing = pywrapcp.RoutingModel(manager)

        def distance_callback(from_index, to_index):
            return dist_matrix_fn(manager.IndexToNode(from_index), manager.IndexToNode(to_index))

        transit_idx = routing.RegisterTransitCallback(distance_callback)
        routing.SetArcCostEvaluatorOfAllVehicles(transit_idx)

        demand_qty = [0] + [s["quantity_needed"] for s in stops]

        def demand_callback(from_index):
            return demand_qty[manager.IndexToNode(from_index)]

        demand_idx = routing.RegisterUnaryTransitCallback(demand_callback)
        routing.AddDimensionWithVehicleCapacity(
            demand_idx, 0, [v["capacity"] for v in hub_vehicles], True, "Capacity"
        )

        search_params = pywrapcp.DefaultRoutingSearchParameters()
        search_params.first_solution_strategy = (
            routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
        )
        search_params.time_limit.FromSeconds(3)
        solution = routing.SolveWithParameters(search_params)

        if not solution:
            continue

        for v_idx, vehicle in enumerate(hub_vehicles):
            index = routing.Start(v_idx)
            waypoints = []
            eta_km = 0.0
            while not routing.IsEnd(index):
                node = manager.IndexToNode(index)
                if node != 0:
                    s = stops[node - 1]
                    waypoints.append(dict(lat=s["lat"], lon=s["lon"], ward_id=s["ward_id"],
                                           category=s["category"], demand_index=s.get("_global_index")))
                prev_index = index
                index = solution.Value(routing.NextVar(index))
                eta_km += dist_matrix_fn(manager.IndexToNode(prev_index), manager.IndexToNode(index)) / 1000
            if waypoints:
                routes_by_vehicle[vehicle["id"]] = dict(
                    vehicle_id=vehicle["id"], hub_id=hub["id"],
                    waypoints=waypoints, distance_km=round(eta_km, 2),
                    eta_minutes=round(eta_km / 30 * 60 + 5 * len(waypoints), 1),  # ~30km/h + 5min per stop
                )
    return routes_by_vehicle


def run_full_solve(demands, hubs, vehicles, blocked_pairs, min_confidence=0.4):
    t0 = time.time()
    allocations = solve_allocation(demands, hubs, blocked_pairs, min_confidence=min_confidence)
    routes = solve_routes(allocations, demands, hubs, vehicles, blocked_pairs)
    solve_time = round(time.time() - t0, 2)
    return allocations, routes, solve_time
