import copy
import os
import random
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

import seed
import optimizer as opt

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR.parent / "frontend"

app = FastAPI(title="Setu — Disaster Relief Coordination API")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# In-memory state. This is a hackathon-scale prototype (Phase 12 of the design
# doc explicitly allows this) - a production deployment would move this to
# PostgreSQL/PostGIS per the documented schema (Phase 14).
# ---------------------------------------------------------------------------

def fresh_state():
    now = time.time()
    raw_reports = []
    for d in seed.seed_initial_demands():
        raw_reports.append({
            "id": str(uuid.uuid4())[:8],
            "added_at": now - random.uniform(5, 180) * 60,
            **d,
        })
    return {
        "started_at": now,
        "hubs": copy.deepcopy(seed.HUBS),
        "vehicles": copy.deepcopy(seed.VEHICLES),
        "shelters": copy.deepcopy(seed.SHELTERS),
        "road_segments": copy.deepcopy(seed.ROAD_SEGMENTS),
        "raw_reports": raw_reports,
        "demands": [],          # last computed deduplicated demand clusters
        "allocations": [],      # current recommended/approved allocations
        "routes": {},           # vehicle_id -> route
        "audit_log": [],
        "policy_weights": dict(opt.DEFAULT_WEIGHTS),
        "last_optimized_at": None,
        "last_solve_time": None,
        "baseline_kpis": None,
        "event_log": [],
    }


STATE = fresh_state()


@app.on_event("startup")
def _startup():
    _reoptimize("initial scenario load")


def now_iso():
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


def blocked_pairs():
    return {(r["hub_id"], r["ward_id"]) for r in STATE["road_segments"] if r.get("blocked")}


def log_event(text):
    STATE["event_log"].insert(0, {"t": now_iso(), "text": text})
    STATE["event_log"] = STATE["event_log"][:40]


def explain_allocation(alloc, demand, hubs_by_id):
    hub = hubs_by_id[alloc["hub_id"]]
    others = []
    for hid, h in hubs_by_id.items():
        if hid == hub["id"]:
            continue
        if h["inventory"].get(demand["category"], 0) >= demand["quantity_needed"]:
            d = opt.haversine_km(h["lat"], h["lon"], demand["lat"], demand["lon"])
            others.append((hid, d))
    parts = []
    if alloc["blocked"]:
        parts.append(f"{hub['name']} selected despite a flagged road segment on this leg — routed around the block")
    elif others and min(o[1] for o in others) < alloc["distance_km"] - 0.15:
        nearer_id, nearer_d = min(others, key=lambda o: o[1])
        parts.append(
            f"{hub['name']} chosen ({alloc['distance_km']}km) over closer {hubs_by_id[nearer_id]['name']} "
            f"({round(nearer_d,2)}km) — priority-weighted assignment (capacity at the nearer hub already "
            f"committed to higher-priority demand, or this demand outranked it) outweighed pure distance"
        )
    else:
        parts.append(f"Nearest hub with matching stock — {hub['name']}, {alloc['distance_km']}km")
    if demand["is_critical"]:
        parts.append("Tier 1 (life-safety) demand")
    parts.append(f"confidence {demand['confidence']}, {demand['report_count']} corroborating report(s)")
    return "; ".join(parts)


def compute_baseline(demands, hubs):
    """Naive nearest-available-resource, no confidence gate, no fairness, no dedup priority order (arrival order) — the 'today' proxy from Phase 23."""
    hubs_copy = copy.deepcopy(hubs)
    hub_by_id = {h["id"]: h for h in hubs_copy}
    served_critical, total_critical = 0, 0
    for d in demands:
        if d["is_critical"]:
            total_critical += 1
        best = None
        for h in hubs_copy:
            if h["inventory"].get(d["category"], 0) >= d["quantity_needed"]:
                dist = opt.haversine_km(h["lat"], h["lon"], d["lat"], d["lon"])
                if best is None or dist < best[1]:
                    best = (h["id"], dist)
        if best:
            hub_by_id[best[0]]["inventory"][d["category"]] -= d["quantity_needed"]
            if d["is_critical"]:
                served_critical += 1
    unmet_pct = round(100 * (1 - served_critical / total_critical), 1) if total_critical else 0.0
    return {"critical_unmet_pct": unmet_pct, "label": "Baseline (nearest-available, today's manual process)"}


def compute_ward_fairness(demands, allocations):
    by_ward = {}
    for i, d in enumerate(demands):
        if not d["is_critical"]:
            continue
        w = d["ward_id"]
        by_ward.setdefault(w, {"total": 0, "unmet": 1000})
        by_ward[w]["total"] += 1
    served_idx = {a["demand_index"] for a in allocations}
    for i, d in enumerate(demands):
        if not d["is_critical"]:
            continue
        w = d["ward_id"]
        by_ward[w].setdefault("unmet_count", 0)
        if i not in served_idx:
            by_ward[w]["unmet_count"] = by_ward[w].get("unmet_count", 0) + 1
    shares = []
    for w, v in by_ward.items():
        shares.append(v.get("unmet_count", 0) / v["total"])
    if not shares:
        return 0.0
    return round((max(shares) - min(shares)) * 100, 1)


def _reoptimize(reason):
    now = time.time()
    for r in STATE["raw_reports"]:
        r["age_minutes"] = (now - r["added_at"]) / 60
    demands = opt.build_demands(
        STATE["raw_reports"], seed.SOURCE_TYPES, STATE["policy_weights"], lambda: now
    )
    for i, d in enumerate(demands):
        d["_global_index"] = i

    hubs = STATE["hubs"]
    vehicles = STATE["vehicles"]
    bp = blocked_pairs()

    allocations, routes, solve_time = opt.run_full_solve(demands, hubs, vehicles, bp)

    hubs_by_id = {h["id"]: h for h in hubs}
    approved_before = {a["demand_key"]: a for a in STATE["allocations"] if a["status"] == "approved"}

    new_allocs = []
    for a in allocations:
        d = demands[a["demand_index"]]
        key = f"{d['ward_id']}:{d['category']}:{round(d['lat'],3)}:{round(d['lon'],3)}"
        if key in approved_before:
            new_allocs.append(approved_before[key])  # keep dispatched allocations stable
            continue
        alloc_id = str(uuid.uuid4())[:8]
        explanation = explain_allocation(a, d, hubs_by_id)
        route = None
        for veh_id, r in routes.items():
            if r["hub_id"] == a["hub_id"] and any(
                wp.get("demand_index") == d["_global_index"] for wp in r["waypoints"]
            ):
                route = r
                break
        new_allocs.append({
            "id": alloc_id,
            "demand_key": key,
            "demand": d,
            "hub_id": a["hub_id"],
            "distance_km": a["distance_km"],
            "blocked": a["blocked"],
            "explanation": explanation,
            "status": "recommended",
            "vehicle_id": route["vehicle_id"] if route else None,
            "route": route,
            "created_at": now_iso(),
        })

    held = [d for d in demands if d["confidence"] < 0.4]

    STATE["demands"] = demands
    STATE["allocations"] = new_allocs
    STATE["routes"] = routes
    STATE["last_optimized_at"] = now_iso()
    STATE["last_solve_time"] = solve_time
    STATE["held_for_corroboration"] = held
    if STATE["baseline_kpis"] is None:
        STATE["baseline_kpis"] = compute_baseline(demands, hubs)
    STATE["fairness_deviation_pct"] = compute_ward_fairness(demands, allocations)
    log_event(f"Re-optimized ({reason}) — {len(new_allocs)} allocations, {solve_time}s solve time")


# ---------------------------------------------------------------------------
# API models
# ---------------------------------------------------------------------------

class DemandIn(BaseModel):
    ward_id: str
    category: str
    severity: int = 2
    population_affected: int = 20
    vulnerability_flag: bool = False
    source_type: str = "agency_verified"
    note: str = "Manually entered demand"


class OverrideIn(BaseModel):
    new_hub_id: str
    reason_code: str


class PolicyIn(BaseModel):
    severity: float | None = None
    population: float | None = None
    vulnerability: float | None = None
    freshness: float | None = None
    confidence_penalty: float | None = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/state")
def get_state():
    return {
        "hubs": STATE["hubs"],
        "vehicles": STATE["vehicles"],
        "wards": seed.WARDS,
        "road_segments": STATE["road_segments"],
        "allocations": STATE["allocations"],
        "held_for_corroboration": STATE.get("held_for_corroboration", []),
        "audit_log": STATE["audit_log"][:50],
        "event_log": STATE["event_log"],
        "policy_weights": STATE["policy_weights"],
        "last_optimized_at": STATE["last_optimized_at"],
        "last_solve_time": STATE["last_solve_time"],
        "raw_report_count": len(STATE["raw_reports"]),
        "demand_cluster_count": len(STATE["demands"]),
        "fairness_deviation_pct": STATE.get("fairness_deviation_pct"),
        "baseline_kpis": STATE["baseline_kpis"],
    }


@app.get("/api/shelters")
def get_shelters():
    """Public, read-only, no auth — the citizen-facing shelter locator."""
    return {"shelters": STATE["shelters"], "hubs": [
        {"id": h["id"], "name": h["name"], "lat": h["lat"], "lon": h["lon"]} for h in STATE["hubs"]
    ]}


@app.post("/api/optimize")
def optimize():
    _reoptimize("manual")
    return get_state()


@app.post("/api/demand")
def add_demand(d: DemandIn):
    ward = next((w for w in seed.WARDS if w["id"] == d.ward_id), None)
    if not ward:
        raise HTTPException(404, "Unknown ward")
    lat, lon = seed._rand_point_near(ward["lat"], ward["lon"], spread=0.003)
    STATE["raw_reports"].append({
        "id": str(uuid.uuid4())[:8], "added_at": time.time(), "age_minutes": 0,
        "ward_id": d.ward_id, "lat": lat, "lon": lon, "category": d.category,
        "severity": d.severity, "population_affected": d.population_affected,
        "vulnerability_flag": d.vulnerability_flag, "source_type": d.source_type,
        "note": d.note,
    })
    log_event(f"New {d.source_type.replace('_',' ')} report: {d.category} in {ward['name']}")
    _reoptimize("new demand entered")
    return get_state()


@app.post("/api/simulate/crowd_report")
def simulate_crowd_report():
    """Injects a burst of noisy, partly-duplicate crowdsourced reports — the Phase 22 demo beat."""
    ward = random.choice(seed.WARDS)
    category = random.choice(["water", "food", "medical"])
    burst_n = random.randint(3, 6)
    notes = [
        f"{category} shortage reported near {ward['name']}",
        f"people need {category} in {ward['name']} urgently",
        f"{ward['name']} residents asking for {category}",
    ]
    for _ in range(burst_n):
        lat, lon = seed._rand_point_near(ward["lat"], ward["lon"], spread=0.0025)
        STATE["raw_reports"].append({
            "id": str(uuid.uuid4())[:8], "added_at": time.time(), "age_minutes": 0,
            "ward_id": ward["id"], "lat": lat, "lon": lon, "category": category,
            "severity": random.choice([1, 2]),
            "population_affected": random.randint(5, 40),
            "vulnerability_flag": random.random() < ward["vulnerability"],
            "source_type": random.choice(["crowd_single", "crowd_corroborated"]),
            "note": random.choice(notes),
        })
    log_event(f"Simulated {burst_n} crowdsourced reports near {ward['name']} — clustering into one demand")
    _reoptimize("crowdsourced burst")
    return get_state()


@app.post("/api/simulate/critical")
def simulate_critical():
    """Injects a sudden Tier-1 critical demand (e.g. trapped occupants)."""
    ward = random.choice(seed.WARDS)
    lat, lon = seed._rand_point_near(ward["lat"], ward["lon"], spread=0.001)
    STATE["raw_reports"].append({
        "id": str(uuid.uuid4())[:8], "added_at": time.time(), "age_minutes": 0,
        "ward_id": ward["id"], "lat": lat, "lon": lon, "category": "medical",
        "severity": 3, "population_affected": random.randint(15, 45),
        "vulnerability_flag": True, "source_type": "agency_verified",
        "note": f"Trapped occupants reported, {ward['name']} — urgent rescue/medical",
    })
    log_event(f"CRITICAL: new Tier-1 medical emergency reported in {ward['name']}")
    _reoptimize("critical emergency")
    return get_state()


@app.post("/api/roadblock/{segment_id}/toggle")
def toggle_roadblock(segment_id: str):
    seg = next((r for r in STATE["road_segments"] if r["id"] == segment_id), None)
    if not seg:
        raise HTTPException(404, "Unknown road segment")
    seg["blocked"] = not seg.get("blocked", False)
    log_event(f"Road segment '{seg['name']}' marked {'BLOCKED' if seg['blocked'] else 'reopened'}")
    _reoptimize("road status change")
    return get_state()


@app.post("/api/allocation/{alloc_id}/approve")
def approve_allocation(alloc_id: str):
    alloc = next((a for a in STATE["allocations"] if a["id"] == alloc_id), None)
    if not alloc:
        raise HTTPException(404, "Unknown allocation")
    hub = next(h for h in STATE["hubs"] if h["id"] == alloc["hub_id"])
    cat = alloc["demand"]["category"]
    qty = alloc["demand"]["quantity_needed"]
    if hub["inventory"].get(cat, 0) < qty:
        raise HTTPException(400, "Insufficient stock at hub for this allocation")
    hub["inventory"][cat] -= qty
    alloc["status"] = "approved"
    STATE["audit_log"].insert(0, {
        "id": str(uuid.uuid4())[:8], "t": now_iso(), "actor": "coordinator",
        "action": "approve", "allocation_id": alloc_id,
        "detail": f"Approved: {hub['name']} -> {alloc['demand']['ward_id']} ({cat}, {qty} units)",
        "reason_code": None,
    })
    log_event(f"Coordinator approved dispatch: {hub['name']} -> {alloc['demand']['ward_id']}")
    return get_state()


@app.post("/api/allocation/{alloc_id}/reject")
def reject_allocation(alloc_id: str):
    alloc = next((a for a in STATE["allocations"] if a["id"] == alloc_id), None)
    if not alloc:
        raise HTTPException(404, "Unknown allocation")
    alloc["status"] = "rejected"
    STATE["audit_log"].insert(0, {
        "id": str(uuid.uuid4())[:8], "t": now_iso(), "actor": "coordinator",
        "action": "reject", "allocation_id": alloc_id,
        "detail": f"Rejected recommendation for {alloc['demand']['ward_id']}",
        "reason_code": "coordinator_rejected",
    })
    log_event(f"Coordinator rejected recommendation for {alloc['demand']['ward_id']}")
    return get_state()


@app.post("/api/allocation/{alloc_id}/override")
def override_allocation(alloc_id: str, body: OverrideIn):
    alloc = next((a for a in STATE["allocations"] if a["id"] == alloc_id), None)
    if not alloc:
        raise HTTPException(404, "Unknown allocation")
    new_hub = next((h for h in STATE["hubs"] if h["id"] == body.new_hub_id), None)
    if not new_hub:
        raise HTTPException(404, "Unknown hub")
    old_hub_id = alloc["hub_id"]
    alloc["hub_id"] = body.new_hub_id
    alloc["distance_km"] = round(opt.haversine_km(
        new_hub["lat"], new_hub["lon"], alloc["demand"]["lat"], alloc["demand"]["lon"]
    ), 2)
    alloc["status"] = "overridden"
    alloc["explanation"] = f"Coordinator override: reassigned from {old_hub_id} to {new_hub['name']} — {body.reason_code}"
    STATE["audit_log"].insert(0, {
        "id": str(uuid.uuid4())[:8], "t": now_iso(), "actor": "coordinator",
        "action": "override", "allocation_id": alloc_id,
        "detail": f"Overrode {old_hub_id} -> {new_hub['name']} for {alloc['demand']['ward_id']}",
        "reason_code": body.reason_code,
    })
    log_event(f"Coordinator override: {alloc['demand']['ward_id']} reassigned to {new_hub['name']} ({body.reason_code})")
    return get_state()


@app.post("/api/policy")
def update_policy(body: PolicyIn):
    for k, v in body.dict(exclude_none=True).items():
        STATE["policy_weights"][k] = v
    log_event("Allocation policy weights updated by admin")
    _reoptimize("policy weights changed")
    return get_state()


@app.post("/api/reset")
def reset():
    global STATE
    STATE = fresh_state()
    _reoptimize("scenario reset")
    return get_state()


@app.get("/api/health")
def health():
    return {"ok": True}


# Serve the frontend
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
