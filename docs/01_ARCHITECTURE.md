# HYDRA-LB: Architecture Document

---

## 1. Problem Definition

### The Core Problem: Reactive Load Balancing in SDN

In a multi-controller Software-Defined Networking (SDN) environment, switches are distributed across controllers. As traffic patterns shift (bursts, flash crowds, skewed loads), some controllers become overloaded while others sit idle. Traditional load balancers — Round Robin, Least Connections — are **reactive**: they only respond to imbalance **after** it has already occurred, leading to:

- **High tail latency** during congestion spikes
- **Packet drops** before the system corrects itself
- **Oscillation** as reactive rebalancing overshoots

### HYDRA-LB's Approach: Proactive, Prediction-Driven Balancing

HYDRA-LB introduces an **LSTM-based prediction engine** that forecasts controller load 3–5 seconds into the future. A **proactive optimizer** uses these predictions to trigger switch migrations *before* congestion materializes. This transforms SDN load balancing from a reactive control loop into a predictive one.

### Research Question

> Can LSTM-based load prediction, combined with variance-aware optimization, reduce inter-controller load imbalance and improve tail latency compared to reactive baselines?

---

## 2. System Overview

HYDRA-LB is a complete experimental platform comprising:

| Layer | Components | Purpose |
|---|---|---|
| **Control Plane** | `ryu_app.py`, `optimizer.py`, `predictor.py` | Run OpenFlow controllers, predict load, decide migrations |
| **Data Plane** | Mininet + Open vSwitch | Emulate network switches and hosts |
| **ML Pipeline** | `model.py`, `attention.py`, `dataset.py`, `train.py` | Train and serve the LSTM prediction model |
| **Load Balancing** | `load_balancer.py`, `round_robin.py`, `least_load.py` | Implement baseline and research LB algorithms |
| **Observability** | `telemetry.py`, Prometheus, Grafana | Collect, store, and visualize metrics |
| **Benchmarking** | `run_experiment.py`, `workloads.py`, `analyze_results.py` | Run reproducible experiments |
| **Infrastructure** | Docker Compose, Dockerfiles | Container orchestration |

---

## 3. Major Components

### 3.1 Controller (`controller/ryu_app.py`)

The **HydraController** is a Ryu SDN application that:

1. **Acts as an L2 learning switch** — learns MAC addresses, installs OpenFlow flows
2. **Collects telemetry** — requests port/flow stats from switches every 1 second
3. **Computes a load score** — weighted combination of packet rate (50%), flow count (30%), and switch count (20%)
4. **Runs LSTM prediction** — feeds metrics to the predictor, receives load forecasts for t+1 through t+5
5. **Runs the optimizer** — checks if predicted load variance exceeds threshold, triggers migration if needed
6. **Serves Prometheus metrics** — HTTP endpoint on port 9100 for monitoring
7. **Handles migrations** — sends/receives OpenFlow role requests and REST API calls to peer controllers

**Key design decision**: The controller runs a monitoring thread every 1 second that sequentially: requests stats → calculates rates → computes load score → updates predictions → runs optimizer. This creates a tight 1-second control loop.

### 3.2 Load Balancer Framework (`controller/load_balancer.py`)

Provides an **abstract base class** (`BaseLoadBalancer`) that defines the interface all LB algorithms must implement:

```python
@abstractmethod
def select_server(self, src_ip=None, dst_port=None, **kwargs) -> Optional[str]:
    """Select a backend server for the incoming request."""
    pass
```

The `LoadBalancerManager` maintains a registry of `VIP → LoadBalancer` mappings, enabling different VIPs to use different strategies.

**Design decision**: The LB framework handles server-level load balancing (distributing requests across backend servers), while the optimizer handles controller-level load balancing (distributing switches across controllers). These are two distinct levels of balancing.

### 3.3 Baselines (`controller/baselines/`)

Two baseline strategies implemented for fair comparison:

| Algorithm | File | Selection Logic | Complexity |
|---|---|---|---|
| Round Robin | `round_robin.py` | Cycles through servers sequentially | O(1) |
| Weighted Round Robin | `round_robin.py` | Smooth WRR based on server weights | O(n) |
| Least Connections | `least_load.py` | Server with fewest active connections | O(n) |
| Weighted Least Connections | `least_load.py` | `connections / weight` ratio | O(n) |
| Least Response Time | `least_load.py` | Server with lowest avg response time | O(n) |

These are all **reactive** — they don't use predictions. Their purpose is to provide a lower bound for comparison.

### 3.4 Topology (`topology/`)

Generates network topologies for Mininet:

- **Fat-Tree** (`fat_tree.py`): Standard data center topology. k=4 gives 20 switches, 16 hosts. Used for all experiments.
- **Leaf-Spine** (`leaf_spine.py`): Two-tier topology with predictable latency. Alternative topology.
- **Fat-Tree k=4 Script** (`fat_tree_k4.py`): Pre-generated Mininet script connecting 3 remote Ryu controllers.

**Design decision**: Fat-Tree k=4 is the default because it provides enough switches (20) to demonstrate load imbalance across 3 controllers while being small enough to run on a laptop.

### 3.5 Telemetry (`controller/telemetry.py`)

Thread-safe telemetry collection:

- **Per-switch metrics**: packet-in rate, flow count, byte count, rx/tx bytes
- **Controller-level aggregates**: total load, load variance
- **CSV export**: Timestamped metrics files for offline analysis
- **Optional Prometheus export**: Via `prometheus_client` library

**Design decision**: Telemetry is CSV-first for simplicity and reproducibility. Prometheus is optional because it adds deployment complexity.

### 3.6 Prediction Engine (`prediction/`)

The ML pipeline:

- **Model** (`model.py`): Bidirectional 2-layer LSTM with temporal attention. Input: [batch, 30, 4] → Output: [batch, 3] (predicts next 3 timesteps of `packet_rate`).
- **Attention** (`attention.py`): Temporal attention mechanism that weighs past timesteps by relevance.
- **Dataset** (`dataset.py`): Sliding window dataset with support for Google Cluster Traces and synthetic data generation.
- **Training** (`train.py`): MSE loss, Adam optimizer, gradient clipping.
- **Inference** (`predictor.py`): Thread-safe wrapper maintaining a sliding window of 30 observations.
- **Data Collection** (`data_collector.py`): Scrapes live controller metrics for training data.

**Design decision**: The model is trained on Google Cluster Traces (real datacenter workload data) and predicts `packet_rate` (not a composite load score) because it's the most volatile and predictable metric. The controller converts predictions back to load scores using the same weighted formula.

### 3.7 Optimizer (`controller/optimizer.py`)

The **ProactiveOptimizer** is the core research contribution:

1. Fetches load + predictions from peer controllers via HTTP
2. Computes predicted load variance at horizon t+3 (or t+5)
3. If predicted variance > threshold → identifies overloaded/underloaded controllers
4. Computes migration cost vs expected improvement
5. Triggers migration if improvement > 5.0 points

**Design decisions**:
- **Variance-based**: Uses statistical variance instead of simple max-min ratio. Variance captures spread across all controllers, not just extremes.
- **Prediction horizon t+3**: Provides 3 seconds of lead time for migration execution.
- **Cooldown**: 30-second cool-down between migrations prevents oscillation.
- **Migration cost**: 30% of load difference is subtracted as migration cost to prevent marginal migrations.

### 3.8 Benchmarking (`benchmarks/`)

Complete experiment framework:

- **Workloads** (`workloads.py`): `steady`, `burst`, `flash_crowd`, `skewed` traffic patterns
- **Experiment Runner** (`run_experiment.py`): Orchestrates trials, collects Prometheus metrics every 5s
- **Analysis** (`analyze_results.py`): Generates publication-quality plots and LaTeX tables
- **Continuous Learning** (`retrain_model.py`): Collect live data → retrain model pipeline

### 3.9 Tests (`tests/`)

Pytest-based unit tests:

- `test_load_balancer.py`: 12 tests for all LB algorithms and manager
- `test_telemetry.py`: 11 tests for telemetry collection, metrics, CSV storage
- `test_topology.py`: 10 tests for Fat-Tree and Leaf-Spine generators

---

## 4. Component Interaction Map

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          HYDRA-LB SYSTEM                                    │
│                                                                             │
│  ┌───────────────────── Controller Node (×3) ──────────────────────┐       │
│  │                                                                   │       │
│  │  ┌─────────────┐    ┌──────────────┐    ┌───────────────────┐   │       │
│  │  │  ryu_app.py  │───▶│ predictor.py │───▶│  optimizer.py     │   │       │
│  │  │              │    │              │    │                   │   │       │
│  │  │ • L2 switch  │    │ • Sliding    │    │ • Fetch peer      │   │       │
│  │  │ • PacketIn   │    │   window     │    │   states          │   │       │
│  │  │ • Stats      │    │ • LSTM       │    │ • Compute         │   │       │
│  │  │ • Metrics    │    │   inference  │    │   variance        │   │       │
│  │  │   server     │    │ • Load       │    │ • Trigger         │   │       │
│  │  │              │    │   forecast   │    │   migration       │   │       │
│  │  └──────┬───────┘    └──────────────┘    └────────┬──────────┘   │       │
│  │         │                                          │              │       │
│  │         │ OpenFlow                     REST POST /migrate         │       │
│  │         ▼                                          ▼              │       │
│  │  ┌─────────────┐                          ┌──────────────┐       │       │
│  │  │ telemetry.py│                          │ Peer         │       │       │
│  │  │             │                          │ Controllers  │       │       │
│  │  │ • CSV export│                          │ (port 9100)  │       │       │
│  │  │ • Prometheus│                          └──────────────┘       │       │
│  │  └─────────────┘                                                  │       │
│  └───────────────────────────────────────────────────────────────────┘       │
│                                                                             │
│  ┌──────────────────── Data Plane ───────────────────────┐                  │
│  │                                                        │                  │
│  │  Mininet + Open vSwitch (Fat-Tree k=4)                │                  │
│  │  20 switches, 16 hosts                                 │                  │
│  │  OpenFlow 1.3 connections to all 3 controllers         │                  │
│  │                                                        │                  │
│  └────────────────────────────────────────────────────────┘                  │
│                                                                             │
│  ┌──────────────── ML Pipeline ──────────────────┐                          │
│  │                                                │                          │
│  │  dataset.py → train.py → model.py             │                          │
│  │       ▲                      │                 │                          │
│  │       │                      ▼                 │                          │
│  │  data_collector.py    models/lstm_predictor.pt │                          │
│  │                                                │                          │
│  └────────────────────────────────────────────────┘                          │
│                                                                             │
│  ┌──────── Observability ─────────┐  ┌────── Benchmarks ──────┐            │
│  │ Prometheus (scrapes :9100)     │  │ run_experiment.py       │            │
│  │ Grafana (dashboard :3000)      │  │ workloads.py            │            │
│  └────────────────────────────────┘  │ analyze_results.py      │            │
│                                      └─────────────────────────┘            │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 5. Baseline vs Research Contribution

| Aspect | Baselines (Round Robin, Least Load) | HYDRA-LB (Research) |
|---|---|---|
| **Decision basis** | Current state only | Predicted state (t+3 to t+5) |
| **When it acts** | After imbalance occurs | Before imbalance occurs |
| **Scope** | Server-level balancing | Controller-level + server-level |
| **Intelligence** | Stateless/simple heuristics | LSTM + temporal attention |
| **Oscillation control** | None | Cooldown + migration cost |
| **Cluster awareness** | Single controller | Multi-controller peer coordination |

---

## 6. Key Design Decisions & Reasoning

### Why Ryu Framework?

Ryu is a Python-based SDN framework that supports OpenFlow 1.3. Python was chosen for rapid prototyping and easy ML integration (PyTorch). Ryu's event-driven architecture maps cleanly to the monitoring loop.

### Why 3 Controllers?

- **2 controllers**: Trivially balanced
- **3 controllers**: Minimum for interesting load variance (one can be overloaded while others are balanced)
- **4+ controllers**: Acceptable but adds container overhead for experiments

### Why OpenFlow Role Requests for Migration?

OpenFlow 1.3 supports MASTER/SLAVE roles natively. A switch can connect to multiple controllers simultaneously, but only the MASTER receives PacketIn messages and can install flows. Migration = changing which controller is MASTER. No data plane disruption.

### Why Variance as the Imbalance Metric?

- **Max-Min Ratio**: Only captures the two extremes. Ignoring middle controllers.
- **Standard Deviation**: Scale-dependent (higher absolute loads always look worse).
- **Variance**: Captures the full distribution of load, is computationally cheap, and provides a natural threshold for "balanced enough."

### Why Predict `packet_rate` Instead of `load_score`?

The load score is a derived metric (packet_rate * 0.5 + ...). Predicting the raw `packet_rate` is easier for the LSTM because:
1. It's the primary volatile signal
2. `flow_count` and `switch_count` change infrequently and are easier to extrapolate
3. The controller can reconstruct the full load score from the predicted packet_rate

---

## 7. Deployment Architecture

```
Docker Compose Stack:
┌──────────────────────────────────────────────────────┐
│                                                      │
│  ryu-controller-1 (172.20.0.10)  ← CONTROLLER_ID=1  │
│  ryu-controller-2 (172.20.0.11)  ← CONTROLLER_ID=2  │
│  ryu-controller-3 (172.20.0.12)  ← CONTROLLER_ID=3  │
│                                                      │
│  Each runs: ryu_app.py + predictor + optimizer       │
│  Each exposes: OpenFlow on 6653, Metrics on 9100     │
│                                                      │
│  hydra-mininet (172.20.0.20)                         │
│  Runs: Mininet + OVS + Fat-Tree k=4 topology         │
│  Connects to all 3 controllers on port 6653          │
│                                                      │
│  [monitoring profile]                                │
│  prometheus (localhost:9090) ← scrapes :9100          │
│  grafana (localhost:3000)   ← reads prometheus        │
│                                                      │
└──────────────────────────────────────────────────────┘
```

All containers share a Docker network (`172.20.0.0/24`). Each controller knows its peers via hardcoded addresses. The Mininet container connects to all 3 controllers via OpenFlow, enabling each switch to have multiple controller connections.

---

## 8. Technology Stack Summary

| Purpose | Technology | Version |
|---|---|---|
| SDN Framework | Ryu | 4.34+ |
| OpenFlow Protocol | OpenFlow | 1.3 |
| Network Emulation | Mininet + OVS | 2.3.0+ |
| ML Framework | PyTorch | 2.0+ |
| Metrics Format | Prometheus text format | — |
| Visualization | Grafana | 10.x |
| Container Runtime | Docker + Compose | v2 |
| Language | Python | 3.10+ |
| Testing | pytest | 7.x |
| Analysis | matplotlib | 3.x |
