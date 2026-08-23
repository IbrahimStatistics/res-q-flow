# Setu (सेतु)

### Disaster Relief Resource-Demand Matching & Routing

[Live Demo](https://res-q-flow.onrender.com/)

Setu is a disaster-relief decision-support prototype that continuously matches relief resources to incoming demand and generates routing recommendations.

The system is designed around a **human-in-the-loop workflow**: optimization proposes decisions, while coordinators review, approve, override, or reject them before dispatch.

The current prototype simulates a flood-response scenario in **East Delhi** using synthetic data.

---

## ✨ Features

* **Resource Management**

  * Relief hubs
  * Vehicles
  * Shelters
  * Wards

* **Demand Management**

  * Synthetic emergency requests
  * Crowdsourced reports
  * Duplicate-report detection
  * Geo-proximity and text-similarity clustering

* **Priority Scoring**

  * Severity
  * Urgency
  * Demand confidence
  * Population/context factors
  * Configurable policy weights

* **Resource Allocation**

  * Google OR-Tools CP-SAT
  * Capacity constraints
  * Demand-resource matching
  * Priority-aware optimization

* **Vehicle Routing**

  * Capacitated Vehicle Routing Problem (CVRP)
  * Per-hub routing
  * Dynamic route updates

* **Rolling-Horizon Optimization**

  * Re-optimizes when the scenario changes
  * New demand
  * Report bursts
  * Road blocks
  * Critical emergencies
  * Policy changes

* **Human-in-the-Loop**

  * Approve recommendations
  * Override recommendations
  * Reject recommendations
  * Reason codes for overrides

* **Auditability**

  * Immutable action log
  * Coordinator decisions
  * Override reasons
  * Optimization events

* **Fairness Monitoring**

  * Tracks deviation in unmet critical demand between wards

* **Baseline Comparison**

  * Compares Setu against a nearest-available-resource baseline

* **Public Shelter Locator**

  * Read-only citizen-facing shelter view
  * No coordinator access required

---

## 🖥️ Demo

**Live application:** https://res-q-flow.onrender.com/

The application includes two primary experiences:

### Coordinator Console

Used by relief coordinators to:

* Monitor demand
* View available resources
* Run optimization
* Review recommendations
* Approve or override allocations
* Monitor routes
* Simulate road blocks
* Inject emergency demand
* Inspect KPIs
* Review the audit log
* Modify optimization policy weights

### Public Shelter Locator

A simplified, read-only interface for citizens to locate available relief shelters.

---

## 🧠 How It Works

Setu follows a continuous feedback loop:

```text
Demand / Reports
       ↓
Deduplication & Clustering
       ↓
Priority & Confidence Scoring
       ↓
Resource Allocation
       ↓
Route Optimization
       ↓
Coordinator Review
       ↓
Approve / Override / Reject
       ↓
Dispatch Recommendation
       ↓
Scenario Changes
       ↓
Re-optimization
```

The key idea is that the system does **not** generate a plan once and stop.

Whenever the operational state changes, the optimizer can generate a new recommendation.

---

## ⚙️ Optimization

### Priority Scoring

Demand priority is calculated using a transparent weighted formula rather than a black-box machine-learning model.

The weights can be modified from the **Policy** panel during runtime.

This makes the prioritization logic visible and auditable.

### Resource Allocation

Allocation is formulated as a constrained optimization problem using:

**Google OR-Tools CP-SAT**

The intended optimization hierarchy is:

```text
Life Safety
    ↓
Response Time
    ↓
Fairness
    ↓
Resource Efficiency
```

The current prototype implements this as a **weighted-sum formulation** rather than a strict lexicographic optimization.

### Vehicle Routing

Routes are generated using the Google OR-Tools Routing Library with a capacitated vehicle-routing formulation.

Each relief hub independently handles its assigned vehicles and demand.

---

## 🔄 Rolling-Horizon Re-optimization

The optimizer reacts to changes in the operational state.

| Event                | System Response |
| -------------------- | --------------- |
| New demand           | Re-optimize     |
| Crowdsourced reports | Re-optimize     |
| Road block           | Re-optimize     |
| Critical emergency   | Re-optimize     |
| Policy change        | Re-optimize     |

This allows the prototype to demonstrate a continuously updated response plan instead of a static allocation.

---

## 👤 Human-in-the-Loop

Setu is designed as a **decision-support system**, not an autonomous dispatcher.

```text
Optimization Recommendation
            │
      ┌─────┼─────┐
      ↓     ↓     ↓
   Approve Override Reject
      │      │      │
      ↓      ↓      ↓
  Dispatch Modified  No
           Dispatch Dispatch
```

Overrides require a reason code, and coordinator actions are recorded in the audit log.

---

## ⚖️ Fairness

The prototype monitors the maximum deviation in **unmet critical-demand share across wards**.

This provides an additional signal for identifying whether the allocation is disproportionately neglecting a particular area.

Fairness is displayed alongside other operational KPIs.

---

## 🆚 Baseline vs Setu

Setu evaluates its allocation against a simple baseline strategy:

> **Assign the nearest available resource.**

The same demand scenario is evaluated using both approaches:

```text
Scenario
   ├── Nearest Available Resource
   │
   └── Setu Optimizer
```

The dashboard then compares their results using the available prototype KPIs.

---

## 📊 KPIs

The dashboard currently exposes metrics such as:

* Critical unmet demand
* Baseline vs Setu comparison
* Optimization solve time
* Fairness metrics
* Resource utilization
* Current operational state

> **Important:** KPI values are generated from synthetic simulation data. They should not be interpreted as validated performance improvements from a real disaster.

---

## 🗺️ Mapping

The application uses **Leaflet** for map rendering and CartoDB map tiles for the basemap.

The Python backend itself does not require internet access for the optimization logic.

Without internet access:

* Resource markers still work
* Demand markers still work
* Routes still work
* Priority queue still works
* Optimization still works
* KPIs still work
* Audit logs still work

Only the underlying street-map tiles become unavailable.

---

## 🛠️ Tech Stack

| Layer        | Technology              |
| ------------ | ----------------------- |
| Backend      | Python, FastAPI         |
| Optimization | Google OR-Tools CP-SAT  |
| Routing      | Google OR-Tools Routing |
| Frontend     | HTML, CSS, JavaScript   |
| Maps         | Leaflet                 |
| Fonts        | IBM Plex                |
| Server       | Uvicorn                 |
| Data         | Synthetic scenario data |

The frontend is intentionally lightweight and does not require a Node.js build pipeline.

---

## 📁 Project Structure

```text
.
├── backend/
│   ├── main.py
│   ├── optimizer.py
│   ├── seed.py
│   └── requirements.txt
│
└── frontend/
    ├── index.html
    └── vendor/
        ├── leaflet/
        └── fonts/
```

### Key Files

**`backend/main.py`**

FastAPI application, API endpoints, application state, KPIs, and audit logging.

**`backend/optimizer.py`**

Contains demand deduplication, priority scoring, resource allocation, and vehicle routing.

**`backend/seed.py`**

Creates the synthetic East Delhi flood scenario.

**`frontend/index.html`**

Coordinator Console and Public Shelter Locator.

---

## 🚀 Run Locally

### Requirements

* Python 3.10+
* pip

No Node.js installation or frontend build step is required.

### 1. Clone the repository

```bash
git clone <repository-url>
cd <repository-directory>
```

### 2. Install dependencies

```bash
cd backend
pip install -r requirements.txt
```

### 3. Start the server

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

### 4. Open the application

Visit:

```text
http://localhost:8000
```

A single FastAPI process serves both the API and frontend.

---

## 🎬 Suggested Demo

For a quick demonstration of the core workflow:

### 1. Start with the Coordinator Console

The application loads a pre-populated synthetic East Delhi flood scenario.

### 2. Simulate Crowdsourced Reports

Use **Simulate crowdsourced reports** to generate noisy incoming reports.

The system clusters duplicate reports and updates the corresponding demand confidence.

### 3. Run Optimization

Click **Optimize now**.

Inspect:

* Priority queue
* Resource allocations
* Vehicle routes
* KPIs

### 4. Test Human Approval

Approve one recommendation and override another.

Provide a reason code for the override and inspect the **Audit** tab.

### 5. Simulate a Road Block

Open **Road blocks** and toggle a road segment.

The system recalculates affected recommendations and routes.

### 6. Inject a Critical Emergency

Use **Inject critical emergency**.

A new high-priority demand is introduced and another optimization cycle is triggered.

### 7. Inspect KPIs

Open the **KPIs** panel and compare:

* Baseline vs Setu
* Critical unmet demand
* Solve time
* Fairness metrics

### 8. Test Policy Changes

Open **Policy** and modify the priority weights.

The recommendation set updates based on the new policy.

### 9. Open the Public Shelter Locator

Switch to the public-facing shelter view to demonstrate the citizen-side experience.

---

## ⚠️ Current Limitations

This is a hackathon-scale prototype and intentionally simplifies several production concerns.

### Optimization

The intended lexicographic objective is currently implemented as a weighted-sum approximation.

### Routing

Road blocks are currently represented using penalties on specific hub-to-ward legs rather than a complete real-world road graph.

### Data

The prototype uses synthetic disaster data and simulated crowdsourced reports.

### Persistence

Application state is stored in memory.

Restarting the server or using **Reset Scenario** clears the current state.

### Architecture

The current implementation is single-process and does not include:

* Persistent database storage
* Multi-user concurrency
* Authentication
* Role-based access control
* Distributed optimization
* Production fault tolerance
* Production observability

---

## 🔮 Future Scope

Potential extensions include:

* Real SMS and social-media ingestion
* IDRN / Sachet integration
* Real-time OSM-based routing
* Persistent PostgreSQL storage
* Authentication and RBAC
* Offline field application
* Multi-coordinator collaboration
* Real-time disaster-data integration
* Advanced fairness constraints
* Strict lexicographic multi-objective optimization
* Production monitoring and observability

---

## 📌 Project Status

**Current:** Hackathon MVP / Prototype

The current version demonstrates the core operational loop:

> **Demand → Prioritization → Allocation → Routing → Human Review → Re-optimization**

It is intended for demonstration, experimentation, and evaluation rather than real-world emergency deployment.

---

## ⚠️ Disclaimer

Setu is a prototype decision-support system.

All disaster scenarios, demand data, and crowdsourced inputs used by the current implementation are synthetic or simulated.

**Setu must not be used to make real-world disaster-response or emergency-relief decisions.**

---

## 📄 License

This project is currently provided for demonstration and evaluation.

If the repository is intended for public release, add an appropriate open-source license such as the **MIT License**.
