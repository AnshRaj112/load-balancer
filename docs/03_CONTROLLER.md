# HYDRA-LB: Controller Documentation

> **Focus**: `controller/ryu_app.py` — the main Ryu SDN controller application.

---

## 1. Overview

`ryu_app.py` is the heart of HYDRA-LB. It is a **672-line** Ryu application that combines:

- **L2 Learning Switch** — MAC learning and flow installation
- **Comprehensive Monitoring** — packet/flow/byte rate collection
- **LSTM-Based Prediction** — integration with the predictor module
- **Proactive Optimization** — integration with the optimizer module
- **Prometheus Metrics** — HTTP endpoint for monitoring
- **Migration Handling** — OpenFlow role management and REST RPC

---

## 2. Class Structure

```
MetricsHandler (BaseHTTPRequestHandler)
    ├── do_GET()    → /metrics, /health
    └── do_POST()   → /migrate

HydraController (app_manager.RyuApp)
    ├── Initialization
    │   ├── __init__()
    │   ├── _init_predictor()
    │   ├── _init_optimizer()
    │   ├── _start_metrics_server()
    │   └── _start_monitoring_thread()
    │
    ├── Monitoring Loop (every 1s)
    │   ├── _request_stats()
    │   ├── _calculate_rates()
    │   ├── _calculate_load_score()
    │   ├── _update_predictions()
    │   └── _run_optimizer()
    │
    ├── OpenFlow Event Handlers
    │   ├── state_change_handler()       → MAIN/DEAD dispatcher
    │   ├── switch_features_handler()    → CONFIG dispatcher
    │   ├── _port_stats_reply_handler()  → MAIN dispatcher
    │   ├── _flow_stats_reply_handler()  → MAIN dispatcher
    │   └── _packet_in_handler()         → MAIN dispatcher
    │
    ├── Flow Management
    │   ├── add_flow()
    │   └── set_role()
    │
    └── Migration
        ├── _execute_migration()
        └── _record_migration_event()
```

---

## 3. Startup Sequence

When the Ryu manager starts the `HydraController`, the `__init__` method executes the following sequence:

### Step 1: Core Initialization (Lines 124–142)

```python
self.mac_to_port = {}                    # {dpid: {mac: port}} — L2 learning table
self.controller_id = int(os.environ.get('CONTROLLER_ID', 1))
self.datapaths = {}                       # {dpid: datapath} — all connected switches
self.master_switches = set()              # DPIDs where this controller is MASTER

# Counters
self.packet_in_count = 0
self.packet_out_count = 0
self.flow_count = 0
self.switch_count = 0
self.bytes_total = 0
self.start_time = time.time()

# Rate metrics (computed each second)
self.packet_rate = 0.0
self.byte_rate = 0.0

# Latency tracking
self.request_latencies = []              # Accumulated per-interval
self.avg_latency_ms = 0.0
self.max_latency_ms = 0.0

# Load score (0-100)
self.load_score = 0.0
```

**Why**: These variables form the telemetry data that feeds the prediction pipeline. They are updated by the monitoring thread and consumed by the optimizer.

### Step 2: Predictor Initialization (Lines 170–185)

```python
def _init_predictor(self):
    model_path = os.environ.get('MODEL_PATH', '/app/models/lstm_predictor.pt')
    if os.path.exists(model_path):
        self.predictor = LoadPredictorInference(model_path)
```

- Looks for a trained PyTorch model at the configured path
- If found: creates a `LoadPredictorInference` instance
- If not found: `self.predictor = None`, system runs without predictions
- **Graceful degradation**: prediction is entirely optional

### Step 3: Optimizer Initialization (Lines 187–211)

```python
def _init_optimizer(self):
    lb_strategy = os.environ.get('LB_STRATEGY', 'hydra_proactive')

    if lb_strategy == 'round_robin':
        return  # No optimizer for baselines

    # Build peer address list
    peer_addrs = []
    for i in range(1, 4):
        if i != self.controller_id:
            peer_addrs.append(f"172.20.0.{9+i}:9100")

    self.optimizer = ProactiveOptimizer(
        controller_id=self.controller_id,
        peer_addresses=peer_addrs,
        variance_threshold=float(os.environ.get('VARIANCE_THRESHOLD', '30.0')),
        migration_cooldown=int(os.environ.get('MIGRATION_COOLDOWN', '30')),
        prediction_horizon=3 if lb_strategy == 'hydra_proactive' else 0
    )
```

- **Strategy-aware**: Only instantiates the optimizer for `hydra_proactive` or `least_load` strategies
- **Peer discovery**: Hardcoded Docker network IPs. Controller 1 → `172.20.0.10`, etc.
- **Prediction horizon**: `3` for proactive (uses t+3 prediction), `0` for reactive (uses current load)

### Step 4: HTTP Server & Monitoring Thread (Lines 213–235)

```python
MetricsHandler.controller = self        # Link handler to controller
self._start_metrics_server()            # Daemon thread, port 9100
self._start_monitoring_thread()         # Daemon thread, 1s loop
```

Two daemon threads are spawned:
1. **Metrics server**: `HTTPServer` on port 9100 serving Prometheus metrics
2. **Monitoring loop**: Runs every 1 second — the heartbeat of the system

---

## 4. The Monitoring Loop — Detailed

The monitoring thread runs `update_loop()` which calls five functions sequentially every second:

```python
def update_loop():
    while True:
        time.sleep(1)
        self._request_stats()          # Ask switches for stats
        self._calculate_rates()        # Compute packet/byte rates
        self._calculate_load_score()   # Weighted load metric
        self._update_predictions()     # Feed LSTM, get forecasts
        self._run_optimizer()          # Check for migration need
```

### 4.1 `_request_stats()` — Lines 237–249

Sends two OpenFlow requests to every connected switch:

1. **OFPPortStatsRequest** (port=OFPP_ANY): Returns `rx_bytes`, `rx_packets`, `tx_bytes`, `tx_packets` per port
2. **OFPFlowStatsRequest**: Returns the list of installed flow entries

The replies arrive asynchronously via event handlers.

**Why both?** Port stats give byte/packet counts (throughput). Flow stats give the number of installed rules (complexity/memory pressure on the switch).

### 4.2 `_calculate_rates()` — Lines 251–272

Computes deltas:

```python
self.packet_rate = (data_packets_total - last_data_packets_total) / elapsed
self.byte_rate   = (bytes_total - last_bytes_total) / elapsed
```

Also computes latency statistics:

```python
self.avg_latency_ms = sum(self.request_latencies) / len(self.request_latencies)
self.max_latency_ms = max(self.request_latencies)
self.request_latencies = []  # Reset for next interval
```

**Why reset latencies?** Each interval should report independent measurements. Accumulating would skew the average toward historical values.

### 4.3 `_calculate_load_score()` — Lines 274–282

The load score is a composite metric:

| Component | Formula | Weight | Rationale |
|---|---|---|---|
| Packet score | `min(100, packet_rate / 30)` | 50% | Primary indicator of traffic intensity |
| Flow score | `min(100, flow_count × 10)` | 30% | Indicates control plane complexity |
| Switch score | `min(100, switch_count × 20)` | 20% | More switches = more responsibility |

**Why `/30` for packet rate?** Mininet generates up to ~3000 pps. Dividing by 30 maps this to a 0–100 scale.

### 4.4 `_update_predictions()` — Lines 284–319

**Scaling (critical detail)**: The LSTM was trained on Google Cluster Traces where `packet_rate` values are normalized to a ~50–100 range. Live traffic produces 100s–1000s. The scaling factor of `/30.0` aligns live data with the training distribution:

```python
scaled_packet_rate = self.packet_rate / 30.0   # 900 pps → 30.0
scaled_byte_rate   = self.byte_rate / 30.0
```

The predictor returns raw predicted values (in the scaled domain). The controller then converts them back to load scores using the same weighted formula:

```python
pred_scaled_pr = predictions.get('t+3', -1)
p_score = min(100, max(0, pred_scaled_pr))
f_score = min(100, self.flow_count * 10.0)     # Current flow count assumed constant
s_score = min(100, self.switch_count * 20.0)   # Current switch count assumed constant
predicted_load_score = p_score * 0.5 + f_score * 0.3 + s_score * 0.2
```

**Important assumption**: Only `packet_rate` is predicted. `flow_count` and `switch_count` are assumed to remain constant at their current values for the prediction horizon. This is a simplification — flow count can change rapidly.

### 4.5 `_run_optimizer()` — Lines 321–347

Updates the optimizer with local state and calls `optimize()`:

```python
self.optimizer.update_local_state(
    load_score=self.load_score,
    predicted_load=self.predicted_load,
    switch_count=self.switch_count,
    packet_rate=self.packet_rate,
    byte_rate=self.byte_rate,
    switch_dpids=list(self.master_switches),
)

decision = self.optimizer.optimize()

if decision is not None:
    self._execute_migration(decision)
    self._record_migration_event(decision)
```

---

## 5. PacketIn Handling — Deep Dive

The `_packet_in_handler()` (lines 611–671) is the most frequently called method in the entire system:

### Guard Clause

```python
if datapath.id not in self.master_switches:
    return
```

**Why**: OVS should not send PacketIn to SLAVE controllers, but this guard prevents any stale messages from being processed after a migration.

### MAC Learning

```python
self.mac_to_port.setdefault(dpid, {})
self.mac_to_port[dpid][src] = in_port
```

**Data structure**: `{dpid: {mac_address: port_number}}` — standard L2 learning switch.

### Forwarding Decision

```python
if dst in self.mac_to_port[dpid]:
    out_port = self.mac_to_port[dpid][dst]   # Known destination → unicast
else:
    out_port = ofproto.OFPP_FLOOD              # Unknown → flood to all ports
```

### Flow Installation

```python
if out_port != ofproto.OFPP_FLOOD:
    match = parser.OFPMatch(in_port=in_port, eth_dst=dst, eth_src=src)
    self.add_flow(datapath, 1, match, actions, msg.buffer_id)
```

This installs a proactive flow rule so the switch handles future identical packets in hardware without sending PacketIn.

### Latency Tracking

```python
start_time = time.time()
# ... processing ...
latency_ms = (time.time() - start_time) * 1000
self.request_latencies.append(latency_ms)
```

Measures the time spent processing each PacketIn event. This correlates with controller CPU load — as the controller becomes busier, processing time increases.

---

## 6. Switch Connection & Role Management

### `switch_features_handler()` — Lines 533–552

Called when a switch first connects:

```python
if dpid not in self.datapaths:
    self.datapaths[dpid] = datapath
    # Modulo-based initial role assignment
    is_master = (dpid % 3) == (self.controller_id % 3)
    self.set_role(datapath, is_master)

# Install table-miss flow (send unknown packets to controller)
match = parser.OFPMatch()  # Match all
actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER)]
self.add_flow(datapath, 0, match, actions)
```

**Initial distribution**: Each switch is assigned to one controller using modulo arithmetic: Switch 1 → C1, Switch 2 → C2, Switch 3 → C3, Switch 4 → C1, etc. This ensures balanced initial distribution.

### `set_role()` — Lines 513–531

Sends an OpenFlow Role Request:

```python
role = ofp.OFPCR_ROLE_MASTER if is_master else ofp.OFPCR_ROLE_SLAVE
gen_id = int(time.time() * 1000000) & 0xffffffffffffffff  # Monotonic 64-bit
req = parser.OFPRoleRequest(datapath, role, gen_id)
datapath.send_msg(req)
```

The `generation_id` must be monotonically increasing for the role request to be accepted by OVS. Using microsecond timestamp ensures this.

---

## 7. Prometheus Metrics — `get_metrics()`

The controller generates Prometheus-format metrics (text/plain). The full list:

| Metric | Type | Description |
|---|---|---|
| `hydra_controller_info` | gauge | Controller identity |
| `hydra_uptime_seconds` | counter | Controller uptime |
| `hydra_packet_in_total` | counter | Total PacketIn events |
| `hydra_packet_out_total` | counter | Total PacketOut messages |
| `hydra_packet_rate` | gauge | Current packets/sec |
| `hydra_byte_rate` | gauge | Current bytes/sec |
| `hydra_flow_count` | gauge | Installed flow rules |
| `hydra_switch_count` | gauge | Connected switches (MASTER only) |
| `hydra_bytes_total` | counter | Total bytes processed |
| `hydra_mac_table_size` | gauge | Learned MAC addresses |
| `hydra_load_score` | gauge | Composite load score (0–100) |
| `hydra_cpu_seconds_total` | counter | CPU time used |
| `hydra_memory_mb` | gauge | Memory usage |
| `hydra_latency_avg_ms` | gauge | Average PacketIn latency |
| `hydra_latency_max_ms` | gauge | Maximum PacketIn latency |
| `hydra_predicted_load_t1`–`t5` | gauge | Predicted load scores |

Plus optimizer metrics if the optimizer is active.

---

## 8. Migration Logic — Execution Trace

### Scenario: Controller 1 is overloaded

```
t=0s: C1 load=80, C2 load=30, C3 load=25
      Predicted variance at t+3 = 625.0 (>> threshold 30.0)

Optimizer decision:
  from_controller = 1 (highest predicted load)
  to_controller   = 3 (lowest predicted load)

C1 executes migration:
  1. Selects dpid = list(master_switches)[0] → dpid=5
  2. POST http://172.20.0.12:9100/migrate
     Body: {"dpid": 5, "from_controller": 1}

C3 receives migration request (MetricsHandler.do_POST):
  3. Finds datapath for dpid=5
  4. Sends OFPRoleRequest(MASTER) to switch 5
  5. Adds 5 to master_switches
  6. Returns 200 OK

C1 receives 200 OK:
  7. Sends OFPRoleRequest(SLAVE) to switch 5
  8. Removes 5 from master_switches
  9. switch_count decremented

C1 records event:
  10. Writes to migration_log.csv:
      timestamp, from=1, to=3, reason="predicted_variance=625.0 > threshold=30.0",
      improvement=35.0, current_variance=625.0, predicted_variance=485.0

t=1s: C1 load=60, C2 load=30, C3 load=35  ← rebalanced!
```

---

## 9. Error Handling & Resilience

| Scenario | Handling |
|---|---|
| Model file not found | `self.predictor = None`; runs without predictions |
| Predictor import fails | `PREDICTOR_AVAILABLE = False`; graceful fallback |
| Optimizer import fails | `OPTIMIZER_AVAILABLE = False`; no proactive LB |
| Peer controller unreachable | `logger.debug()` warning; uses stale or no peer data |
| Migration RPC fails | `logger.error()`; migration is skipped |
| Switch disconnects | `state_change_handler()` removes from datapaths and master_switches |
| Buffer underflow (< 30 observations) | Predictor pads with first observation |

---

## 10. Thread Safety

The controller runs **3 concurrent threads**:

1. **Ryu event loop** (main thread) — handles OpenFlow events
2. **Monitoring thread** — runs `update_loop()`
3. **Metrics HTTP server** — serves `/metrics` and `/migrate`

**Shared state risks**:
- `self.packet_in_count` — written by event loop, read by monitoring → no lock (atomic int increments in CPython)
- `self.datapaths` — modified by event loop (`state_change_handler`), iterated by monitoring (`_request_stats`) → can cause `RuntimeError: dictionary changed size during iteration` (mitigated by `list(self.datapaths.values())`)
- `self.master_switches` — modified by set_role (from any thread), read by multiple → set operations are atomic in CPython
- `self.request_latencies` — appended by event loop, consumed by monitoring → potential race (reset happens in monitoring thread while event loop appends)

**Assessment**: The code relies on CPython's GIL for thread safety rather than explicit locks. This is pragmatic for a research prototype but would need proper locking for production.

---

## 11. Configuration via Environment Variables

| Variable | Default | Effect |
|---|---|---|
| `CONTROLLER_ID` | `1` | Unique controller identifier |
| `MODEL_PATH` | `/app/models/lstm_predictor.pt` | Path to trained LSTM model |
| `LB_STRATEGY` | `hydra_proactive` | Load balancing strategy |
| `VARIANCE_THRESHOLD` | `30.0` | Predicted variance threshold for migration |
| `MIGRATION_COOLDOWN` | `30` | Seconds between migrations |
