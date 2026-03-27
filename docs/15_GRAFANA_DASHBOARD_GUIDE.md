# HYDRA-LB: Grafana Dashboard Guide

---

## 1. Accessing the Dashboard

### Prerequisites

Start the monitoring stack:

```bash
docker compose --profile monitoring up -d
```

### Login

| Field | Value |
|---|---|
| **URL** | `http://localhost:3000` |
| **Username** | `admin` |
| **Password** | `hydra` |

### Dashboard Location

Navigate to: **Dashboards → HYDRA-LB Controller Dashboard**

Direct URL: `http://localhost:3000/d/hydra-lb-main/hydra-lb-controller-dashboard`

---

## 2. Dashboard Panels

The HYDRA-LB dashboard is organized into rows of panels. Each panel visualizes a specific aspect of the system's real-time behavior.

### 2.1 Load Score Panel

**What it shows**: The composite load score (0–100) for each of the 3 controllers over time.

**Metric**: `hydra_load_score`

**How to read it**:
- **All lines close together** → Cluster is balanced, no migration needed
- **One line diverging upward** → That controller is becoming overloaded
- **Sudden drop on one line + rise on another** → Migration just occurred
- **Oscillating pattern** → Burst workload or cooldown-bounded migrations

**What to look for during experiments**:
| Scenario | Expected Pattern |
|---|---|
| Steady workload | Flat, overlapping lines around 20–40 |
| Burst workload | Periodic spikes on one controller, HYDRA-LB reduces peaks |
| Flash crowd | Sharp spike at t≈20s on one controller, migration follows |
| Post-migration | Overloaded controller's load drops, receiving controller's rises |

---

### 2.2 Prediction Horizon Panel

**What it shows**: The LSTM's predicted load score at t+3 compared to the actual load score that materializes 3 seconds later.

**Metrics**: `hydra_predicted_load_t3` (prediction) vs `hydra_load_score` (actual, shifted by 3s)

**How to read it**:
- **Prediction line leads the actual line** → Model is correctly anticipating load changes
- **Prediction tracks actual closely** → Good model accuracy
- **Large gap between lines** → Prediction error; may cause unnecessary or missed migrations
- **Prediction flat while actual spikes** → Model failed to anticipate the change (cold start or novel pattern)

**Key insight**: The 3-second gap between prediction and actual is the optimizer's "early warning window." This is the time available to execute a migration before congestion materializes.

---

### 2.3 Load Variance Panel

**What it shows**: Inter-controller load variance across the cluster, both current and predicted.

**Metrics**: `hydra_load_variance_current`, `hydra_load_variance_predicted`

**How to read it**:
- **Variance below threshold (30.0)** → Cluster is balanced; horizontal dashed line shows the threshold
- **Predicted variance exceeds threshold** → Migration will be triggered (if cooldown allows)
- **Variance spikes then drops** → Migration successfully reduced imbalance
- **Sustained high variance** → Either cooldown is blocking further migrations or the migration didn't help enough

**Threshold line**: A horizontal annotation at `variance = 30.0` marks the migration trigger point.

---

### 2.4 Packet Rate Panel

**What it shows**: Per-controller packet-in rate (packets/second).

**Metric**: `hydra_packet_rate`

**How to read it**:
- **Packet rate is the primary driver of load score** (50% weight)
- **Spikes correlate with workload changes** — burst phases, flash crowd onset
- **Rate drops to near-zero after flow installation** — switches handle packets in hardware
- **Persistent high rate** — controller is handling many unknown flows (new connections or flow timeout)

---

### 2.5 Migration Events Panel

**What it shows**: Cumulative migration count over time.

**Metric**: `hydra_migrations_triggered_total`

**How to read it**:
- **Step function increments** → Each step = one migration event
- **Steps spaced ≥30s apart** → Cooldown is working correctly
- **No steps under steady workload** → Optimizer correctly avoids unnecessary migrations
- **Multiple steps during burst/flash crowd** → System is actively rebalancing

**Correlation**: Each migration step should correspond to a load score crossover in the Load Score Panel (one controller drops, another rises).

---

### 2.6 Switch Count Panel

**What it shows**: Number of MASTER switches per controller.

**Metric**: `hydra_switch_count`

**How to read it**:
- **Initial distribution**: ~7, ~7, ~6 (20 switches across 3 controllers via modulo)
- **After migration**: One controller loses 1 switch, another gains 1
- **Multiple migrations**: Distribution may shift to 5/7/8 or similar

---

### 2.7 Flow Count Panel

**What it shows**: Number of installed OpenFlow flow rules per controller.

**Metric**: `hydra_flow_count`

**How to read it**:
- **Ramp up at experiment start** → Initial MAC learning phase
- **Plateau** → All host pairs have been learned; packets handled by OVS
- **Jump after migration** → New controller learns MAC addresses for migrated switch via flooding

---

### 2.8 Latency Panel

**What it shows**: Average and maximum PacketIn processing latency per controller.

**Metrics**: `hydra_latency_avg_ms`, `hydra_latency_max_ms`

**How to read it**:
- **Average latency 1–3ms** → Normal operation
- **Average latency >5ms** → Controller is under stress
- **Max latency spike** → Single expensive PacketIn event (e.g., ARP broadcast storm)
- **Latency drops after migration** → Offloading switches reduced processing burden

---

### 2.9 Resource Usage Panel

**What it shows**: CPU time and memory usage per controller.

**Metrics**: `hydra_cpu_seconds_total`, `hydra_memory_mb`

**How to read it**:
- **CPU rate (derivative)** → Higher = more PacketIn processing
- **Memory ~100–200 MB** → Normal for Ryu + PyTorch
- **Memory growth** → Potential leak (check MAC table size)

---

## 3. Reading the Dashboard During Experiments

### Steady Workload

```
Expected behavior:
- Load scores: flat, overlapping (~25–35)
- Variance: well below threshold
- Migrations: 0
- Interpretation: System correctly identifies no action is needed
```

### Burst Workload

```
Expected behavior:
- Load scores: periodic spikes every 10s on one controller
- Prediction line leads actual by ~3s
- Variance spikes above threshold during burst phase
- Migrations: 2–3 over 60s, each reducing the subsequent spike
- Interpretation: LSTM anticipates bursts, optimizer preemptively migrates
```

### Flash Crowd Workload

```
Expected behavior:
- Load scores: flat until t≈20s, then sharp spike on one controller
- Prediction catches the spike at t≈18s (3s lead time)
- Variance jumps from ~10 to >400
- Migration triggered at t≈20–22s
- Overloaded controller's load drops within 2–3s
- Interpretation: Proactive migration prevents sustained overload
```

### Skewed Workload

```
Expected behavior:
- Load scores: one controller consistently higher than others
- Variance sustained above threshold
- Migrations: 2 in first minute to redistribute switches
- Post-migration: loads converge closer together
- Interpretation: HYDRA-LB corrects initial assignment imbalance
```

---

## 4. Comparing Strategies Visually

Run experiments with different `LB_STRATEGY` values and compare dashboards:

| Visual Indicator | Round Robin | Least Load | HYDRA-LB |
|---|---|---|---|
| Load score spread | Wide, uneven | Narrower at start | Consistently narrow |
| Variance trajectory | Spikes unchecked | Reactive dips | Preemptive dips |
| Migration events | None (0) | None (0) | 2–4 targeted |
| Prediction line | N/A | N/A | Leads actual by 3s |
| Latency peaks | Highest under load | Moderate | Lowest under load |

---

## 5. Prometheus Queries

For custom dashboards or ad-hoc analysis, use these PromQL queries in Grafana's Explore panel:

### Load Score per Controller

```promql
hydra_load_score
```

### Load Variance (computed)

```promql
stddev(hydra_load_score) ^ 2
```

### Prediction Accuracy (error at t+3)

```promql
abs(hydra_predicted_load_t3 - hydra_load_score)
```

### Migration Rate (per minute)

```promql
rate(hydra_migrations_triggered_total[1m]) * 60
```

### Packet Rate Derivative (acceleration)

```promql
deriv(hydra_packet_rate[30s])
```

---

## 6. Troubleshooting

| Issue | Cause | Fix |
|---|---|---|
| Dashboard shows "No data" | Prometheus not scraping | Check `docker ps` for prometheus container; verify `prometheus.yml` targets |
| Metrics are stale (not updating) | Controller crashed or metrics server down | Check `docker logs hydra-controller-N` |
| Predictions show -1.0 | LSTM model not loaded or buffer not full | Wait 30s for the sliding window to fill; check MODEL_PATH |
| Variance always 0 | Only 1 controller reporting | Verify all 3 controllers are running and reachable |
| Grafana login fails | Default credentials changed | Try `admin`/`hydra`; reset via `docker exec grafana grafana-cli admin reset-admin-password hydra` |
