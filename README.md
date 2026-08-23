https://res-q-flow.onrender.com/

Setu (सेतु) — Disaster Relief Resource-Demand Matching Prototype

A working prototype of the core loop described in the SETU / SIH 2026 PS33 design document: a continuously re-solved, explainable, human-approved allocation-and-routing recommendation system, built for a synthetic East Delhi flood scenario.

Phase-12 Hackathon MVP: This is not the full 25-phase production system. It runs entirely on your machine, with no external services required at runtime except map tiles.

🚀 What's Implemented
Resource Registry — 3 relief hubs, 6 vehicles, 4 shelters, and 10 wards (backend/seed.py)
Demand Intake & Deduplication — Synthetic and simulated crowdsourced reports, deduplicated by geo-proximity and keyword-overlap text similarity (backend/optimizer.py :: dedup_cluster)
Priority & Confidence Scoring — Transparent, tunable weighted formula with live-editable weights in the Policy tab
Allocation Optimizer — Google OR-Tools CP-SAT constrained assignment (solve_allocation)
Routing — Google OR-Tools Routing Library, using a capacitated VRP per hub (solve_routes)
Rolling-Horizon Re-optimization — Automatically re-solves after:
New demand
Crowdsourced report bursts
Road-block toggles
Critical-emergency injection
Policy-weight changes
Human-in-the-Loop — Every recommendation must be approved, overridden, or rejected before dispatch
Immutable Audit Log — Coordinator actions are recorded with reason codes
Fairness Metric — Tracks maximum deviation in unmet critical-demand share across wards
Baseline-vs-Setu Comparison — Compares the optimizer against a naive nearest-available-resource baseline
Public Shelter Locator — Separate, read-only citizen-facing view with no login
❌ What's Not Implemented

These features are intentionally outside the Phase-12 MVP scope:

No real SMS/social-media ingestion — crowdsourced reports are simulated
No real IDRN/Sachet integration
No Flutter offline field app
No production database — state is in-memory and resets when the server restarts or when Reset scenario is clicked
No authentication/RBAC — this is a single-role demonstration console
🛠️ Requirements
Python 3.10+
pip

No Node.js or frontend build step is required.

The frontend is a single static HTML file with Leaflet and IBM Plex fonts vendored in:

frontend/vendor/


There is no CDN dependency for the application shell.

▶️ Run Locally
1. Clone the repository
git clone <your-repository-url>
cd <your-repository-directory>

2. Install backend dependencies
cd backend
pip install -r requirements.txt

3. Start the server
uvicorn main:app --host 0.0.0.0 --port 8000

4. Open the application

Visit:

http://localhost:8000


That's it.

A single FastAPI process serves both the API and frontend.

🗺️ Map Tiles

The application uses CartoDB's free dark map tiles:

basemaps.cartocdn.com


Map tiles require internet access from your browser, but the Python backend does not require internet access.

If you're demoing without internet:

The application still runs
Hubs still render
Vehicles still render
Demand markers still render
Routes still render
Priority queue still works
Optimizer still works
Audit log still works
KPIs still render

Only the underlying street-map imagery will be unavailable.

For a fully offline basemap, replace the L.tileLayer(...) URL in:

frontend/index.html


with a locally hosted tile set.

🎬 Suggested Demo Flow

The following sequence mirrors the design document's Phase 22 demo.

1. Open the Coordinator Console

The application loads with a pre-populated synthetic East Delhi flood scenario.

2. Simulate Crowdsourced Reports

Click:

Simulate crowdsourced reports

A burst of noisy reports will be generated and clustered into a demand with an updated confidence score.

3. Inspect the Priority Queue

Look for the high-severity-but-quiet Ward 9 demand.

It should rank at or near the top instead of simply prioritizing the closest or loudest request.

4. Approve and Override Recommendations

Click:

Optimize now

Then:

Approve one recommendation
Override another
Enter a reason code

Open the Audit tab to see the actions recorded.

5. Toggle a Road Block

Open:

Road blocks ▾

Toggle a road segment.

Affected allocations should re-route live and appear with a dashed red route on the map.

6. Inject a Critical Emergency

Click:

Inject critical emergency

A new Tier-1 demand will appear and trigger another optimization cycle.

7. Inspect KPIs

Open the KPIs tab.

Look at:

Baseline vs Setu critical-unmet-demand comparison
Last solve time
Fairness metrics

The solve-time figure is measured from the actual optimization run rather than being a static estimate.

8. Open the Public Shelter Locator

Switch to:

Public Shelter Locator

This demonstrates the citizen-facing, read-only shelter view.

9. Change the Policy

Open:

Policy

Move one of the weight sliders.

The recommendation set should update live, demonstrating that the priority formula is a visible and auditable policy artifact rather than a black box.

📊 Important: Interpreting the KPIs

All KPI values are:

Prototype simulation results using synthetic data.

They are labeled as such in the UI.

For presentations, demos, and judging, they should not be presented as measurements from a real disaster or as validated real-world performance improvements.

📁 Project Structure
.
├── backend/
│   ├── main.py
│   │   └── FastAPI application, state, endpoints, KPIs, audit log
│   │
│   ├── optimizer.py
│   │   └── Deduplication, scoring, CP-SAT allocation, VRP routing
│   │
│   ├── seed.py
│   │   └── Synthetic East Delhi flood scenario
│   │
│   └── requirements.txt
│
└── frontend/
    ├── index.html
    │   └── Coordinator Console + Public Shelter Locator
    │
    └── vendor/
        └── Vendored Leaflet + IBM Plex fonts

🧠 Optimization Approach
Priority Scoring

Demand priority is calculated using a transparent weighted formula rather than a black-box ML model.

The weights are exposed through the Policy tab and can be modified during runtime.

Allocation

Resource allocation uses:

Google OR-Tools CP-SAT

The design document describes a lexicographic objective:

Life Safety
    ↓
Response Time
    ↓
Fairness
    ↓
Efficiency


For this MVP, the objective is implemented as a weighted-sum relaxation of the lexicographic formulation.

This is a practical simplification for the prototype scale.

Routing

Vehicle routing uses the Google OR-Tools Routing Library with a capacitated vehicle-routing formulation per relief hub.

🔄 Rolling-Horizon Re-optimization

The optimizer automatically re-solves whenever the system state changes.

Examples include:

New demand
    ↓
Re-optimize

Crowdsourced report burst
    ↓
Re-optimize

Road block
    ↓
Re-optimize

Critical emergency
    ↓
Re-optimize

Policy change
    ↓
Re-optimize


This is the core feedback loop demonstrated by the prototype.

👤 Human-in-the-Loop

Setu does not automatically dispatch every optimization result.

Each recommendation requires coordinator action:

Recommendation
      │
      ├── Approve ──→ Dispatch
      │
      ├── Override ─→ Dispatch modified decision
      │
      └── Reject ───→ No dispatch


Overrides require a reason code and all coordinator actions are recorded in the audit log.

This keeps the optimizer in a decision-support role rather than treating it as an autonomous dispatcher.

⚖️ Fairness

The prototype tracks the maximum deviation in unmet critical-demand share across wards.

This provides a live indication of whether the allocation is disproportionately neglecting a particular ward.

The fairness metric is displayed in the KPI panel.

🆚 Baseline vs Setu

The system computes a naive baseline using the:

Nearest available resource

strategy.

The same demand set is evaluated against both:

Baseline allocation
Setu optimized allocation

This allows the KPI panel to show a live comparison rather than relying on a manually claimed improvement.

⚠️ Known Limitations
1. Weighted-Sum Objective

The design document specifies a lexicographic optimization objective.

The prototype approximates this using a weighted sum rather than solving each objective tier independently.

This is a deliberate simplification.

2. Simplified Road Network

Road blocks are modeled as a heavy penalty on a specific:

Hub ↔ Ward


leg.

The prototype does not contain a complete OSM road-network graph or real-world routing engine.

3. In-Memory State

All application state is stored in memory.

Restarting the backend resets the scenario.

Clicking Reset scenario also resets the state.

4. Single-Process Architecture

This is a hackathon prototype and does not provide:

Multi-user concurrency
Persistent storage
Distributed optimization
Production fault tolerance
Authentication
Role-based access control
🔮 Future Scope

Potential extensions beyond the Phase-12 MVP include:

Real SMS and social-media ingestion
IDRN/Sachet integration
Real-time road-network routing
OSM-based routing graphs
Persistent PostgreSQL-backed state
Authentication and RBAC
Flutter-based offline field application
Multi-coordinator collaboration
Production-grade observability
Real disaster-data integrations
More sophisticated fairness constraints
Full lexicographic multi-objective optimization
⚠️ Disclaimer

Setu is a prototype for demonstration and evaluation.

It uses synthetic disaster data and simulated inputs. It is not a production emergency-response system and should not be used to make real-world disaster-relief decisions.

📜 License

Add your project's license here, for example:

MIT License


if the repository is intended to be released under MIT.
