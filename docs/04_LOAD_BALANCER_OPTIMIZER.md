# HYDRA-LB: Load Balancer + Optimizer Documentation

---

## Part A: Load Balancer Framework (`controller/load_balancer.py`)

### 1. Architecture

The load balancer framework operates at the **server level** — distributing incoming requests across backend servers behind a Virtual IP (VIP). This is distinct from the optimizer, which operates at the **controller level**.

```
Client → VIP (10.0.0.100) → Load Balancer → Backend Server (10.0.0.1, 10.0.0.2, ...)
```

### 2. Data Models

#### `Server` Dataclass

```python
@dataclass
class Server:
    ip: str                        # Backend server IP
    port: int = 80                 # Service port
    weight: float = 1.0            # Server capacity weight
    active_connections: int = 0    # Current concurrent connections
    total_requests: int = 0        # Lifetime request count
    healthy: bool = True           # Health status
```

**Why `weight`?** Allows heterogeneous server pools. A server with weight=3 should handle 3× the requests of weight=1.

#### `LoadBalancerStats` Dataclass

```python
@dataclass
class LoadBalancerStats:
    total_requests: int = 0
    total_decisions: int = 0
    servers_count: int = 0
    healthy_servers: int = 0
```

### 3. `BaseLoadBalancer` — Abstract Base

Every load balancing algorithm inherits from this class and must implement:

```python
@abstractmethod
def select_server(self, src_ip=None, dst_port=None, **kwargs) -> Optional[str]:
    pass
```

The base class provides:

| Method | Purpose |
|---|---|
| `get_healthy_servers()` | Filters servers where `healthy=True` |
| `mark_server_unhealthy(ip)` | Marks a server as down |
| `mark_server_healthy(ip)` | Marks a server as recovered |
| `add_server(ip, port, weight)` | Dynamically adds to the pool |
| `remove_server(ip)` | Removes from the pool |
| `get_stats()` | Returns detailed per-server statistics |
| `record_request(ip)` | Increments `total_requests` and `active_connections` |
| `record_response(ip)` | Decrements `active_connections` |

### 4. `LoadBalancerManager`

Manages multiple VIP registrations:

```python
manager = LoadBalancerManager()
manager.register_vip('10.0.0.100', ['10.0.0.1', '10.0.0.2'], strategy='round_robin')
manager.register_vip('10.0.0.200', ['10.0.0.3', '10.0.0.4'], strategy='least_load')

# Route a request
server = manager.select_server('10.0.0.100')
# → '10.0.0.1'
```

### 5. Round Robin Implementation

**File**: `controller/baselines/round_robin.py`

#### `RoundRobinBalancer`

```python
def select_server(self, **kwargs):
    healthy_servers = self.get_healthy_servers()
    with self._lock:
        self._current_index = self._current_index % len(healthy_servers)
        selected = healthy_servers[self._current_index]
        self._current_index = (self._current_index + 1) % len(healthy_servers)
    self.record_request(selected.ip)
    return selected.ip
```

**Step-by-step**:
1. Get list of healthy servers
2. Modulo index → current server
3. Increment index
4. Record request

**Edge cases**:
- **No healthy servers** → Returns `None`
- **Server goes unhealthy mid-rotation** → Index modulo recalculates based on new list
- **Single server** → Always returns that server

#### `WeightedRoundRobinBalancer`

Uses the **smooth weighted round robin** algorithm:

```
For each selection:
  1. Add each server's weight to its current_weight
  2. Select server with highest current_weight
  3. Subtract total_weight from selected server's current_weight
```

**Example** (weights: A=3, B=1):

| Step | A.current | B.current | Selected | After subtraction |
|---|---|---|---|---|
| 1 | 3 | 1 | A (3>1) | A=-1, B=1 |
| 2 | 2 | 2 | A (2≥2) | A=-2, B=2 |
| 3 | 1 | 3 | B (3>1) | A=1, B=-1 |
| 4 | 4 | 0 | A (4>0) | A=0, B=0 |

Sequence: A, A, B, A → 3:1 ratio ✓

### 6. Least Load Implementations

**File**: `controller/baselines/least_load.py`

#### `LeastLoadBalancer`

```python
def select_server(self, **kwargs):
    healthy_servers = self.get_healthy_servers()
    selected = min(healthy_servers, key=lambda s: s.active_connections)
    self.record_request(selected.ip)
    return selected.ip
```

**Tie-breaking**: Python's `min()` returns the first element in case of ties → effectively FIFO tie-breaking.

#### `WeightedLeastConnectionsBalancer`

Selection criteria: `connections / weight` (lower is better)

```python
selected = min(healthy_servers, key=lambda s: s.active_connections / s.weight)
```

**Why divide?** A server with weight=2 and 4 connections is equivalently loaded to a server with weight=1 and 2 connections (both score = 2.0).

#### `LeastResponseTimeBalancer`

```python
def select_server(self, **kwargs):
    server_times = {s.ip: self._get_avg_response_time(s.ip) for s in healthy_servers}
    selected = min(healthy_servers, key=lambda s: (server_times[s.ip], s.active_connections))
```

**Tie-breaking**: When response times are equal, prefers the server with fewer connections.

**Limitation**: This is a placeholder. Response time data requires external instrumentation (e.g., health checks). It defaults to 0ms for servers without data, making new servers always preferred.

---

## Part B: Proactive Optimizer (`controller/optimizer.py`)

### 1. Purpose

The optimizer answers the question: **"Should we move a switch from controller A to controller B to prevent future imbalance?"**

It operates at the **controller level**, not the server level:

```
Controller 1: manages switches {1, 4, 7, 10}  → load=80
Controller 2: manages switches {2, 5, 8, 11}  → load=30
Controller 3: manages switches {3, 6, 9, 12}  → load=25

Optimizer: "Move switch 1 from C1 to C3 to reduce variance"
```

### 2. Data Models

#### `ControllerState`

```python
@dataclass
class ControllerState:
    controller_id: int
    current_load: float = 0.0
    predicted_load: List[float] = [0.0] * 5    # Predictions t+1..t+5
    switch_count: int = 0
    packet_rate: float = 0.0
    byte_rate: float = 0.0
    healthy: bool = True
    last_update: float = 0.0                    # Unix timestamp
```

#### `MigrationDecision`

```python
@dataclass
class MigrationDecision:
    switch_dpid: int              # Switch to migrate (-1 = TBD)
    from_controller: int          # Overloaded controller
    to_controller: int            # Underloaded controller
    reason: str                   # Human-readable reason
    predicted_improvement: float   # Expected variance reduction
    timestamp: float = 0.0
```

### 3. Configuration Parameters

| Parameter | Default | Effect |
|---|---|---|
| `variance_threshold` | 30.0 | Minimum predicted variance to trigger migration |
| `migration_cooldown` | 30s | Minimum time between consecutive migrations |
| `prediction_horizon` | 3 (proactive) / 0 (reactive) | Which future timestep to use |
| `migration_cost_weight` | 0.3 | Fraction of improvement consumed as migration cost |

### 4. The `optimize()` Decision Flow — Step by Step

```
                               START
                                 │
                      ┌──────────▼──────────┐
                      │ fetch_peer_states()  │
                      │ HTTP GET /metrics    │
                      └──────────┬──────────┘
                                 │
                      ┌──────────▼──────────┐
                      │ Filter healthy peers │
                      │ (last_update < 30s)  │
                      └──────────┬──────────┘
                                 │
                        < 2 healthy?
                       ╱              ╲
                    YES                NO
                    │                   │
              return None         ┌─────▼─────┐
          "insufficient_peers"    │ Cooldown   │
                                  │ check      │
                                  └─────┬─────┘
                                        │
                              last migration < 30s ago?
                             ╱                        ╲
                          YES                          NO
                          │                             │
                    return None               ┌─────────▼──────────┐
                   "cooldown"                 │ Compute current     │
                                              │ variance            │
                                              └─────────┬──────────┘
                                                        │
                                              ┌─────────▼──────────┐
                                              │ Compute predicted   │
                                              │ variance at t+H     │
                                              └─────────┬──────────┘
                                                        │
                                           predicted_var ≤ threshold?
                                          ╱                          ╲
                                       YES                            NO
                                       │                               │
                                 return None             ┌─────────────▼────────────┐
                                "balanced"               │ Find max/min load        │
                                                         │ controllers              │
                                                         └─────────────┬────────────┘
                                                                       │
                                                        max has ≤ 1 switch?
                                                       ╱                    ╲
                                                    YES                      NO
                                                    │                         │
                                              return None          ┌──────────▼──────────┐
                                        "no_switches_to_migrate"   │ Compute improvement  │
                                                                   │ = diff - 0.3×diff    │
                                                                   └──────────┬──────────┘
                                                                              │
                                                              improvement ≤ 5.0?
                                                             ╱                    ╲
                                                          YES                      NO
                                                          │                         │
                                                    return None          ┌──────────▼──────────┐
                                              "marginal_improvement"     │ CREATE               │
                                                                         │ MigrationDecision     │
                                                                         │ from=max, to=min      │
                                                                         └───────────────────────┘
```

### 5. Variance Computation

```python
def compute_variance(self, loads):
    mean = sum(loads) / len(loads)
    return sum((l - mean) ** 2 for l in loads) / len(loads)
```

**Example**:
- Loads: [80, 30, 25]
- Mean: 45.0
- Variance: ((80-45)² + (30-45)² + (25-45)²) / 3 = (1225 + 225 + 400) / 3 = **616.7**

This is **population variance** (divides by N, not N-1). Appropriate here because we have the entire cluster, not a sample.

### 6. Predicted Variance Computation

```python
if self.prediction_horizon > 0:
    h = min(self.prediction_horizon - 1, 4)  # 0-indexed
    for s in healthy_states.values():
        if s.predicted_load[h] > 0:
            predicted_loads.append(s.predicted_load[h])
        else:
            predicted_loads.append(s.current_load)  # Fallback
```

**For `prediction_horizon=3`**: Uses `predicted_load[2]` (index 2 = t+3).

**Fallback**: If a controller's prediction is unavailable (returns -1 or ≤ 0), the current load is used instead. This happens when:
- The predictor hasn't accumulated enough observations
- The model failed to load
- The controller is a baseline (no predictions)

### 7. Migration Cost Model

```python
load_diff = predicted_loads[max_idx] - predicted_loads[min_idx]
migration_cost = self.migration_cost_weight * load_diff    # 0.3 × diff
expected_improvement = load_diff - migration_cost           # 0.7 × diff

if expected_improvement <= 5.0:
    return None  # Not worth it
```

**Why a cost model?** Switch migration causes:
1. **Brief disruption**: The new MASTER needs to learn MAC addresses
2. **Rule re-installation**: New controller installs fresh flows
3. **State transfer overhead**: MAC table is not transferred (re-learned)

The `0.3` factor means that 30% of the theoretical improvement is "spent" on migration overhead. Only improvements > 5.0 points (after cost) are executed.

### 8. Peer State Collection

```python
def fetch_peer_states(self):
    for addr in self.peer_addresses:
        resp = requests.get(f"http://{addr}/metrics", timeout=2)
        self._parse_peer_metrics(resp.text, addr)
```

Parses Prometheus text format to extract:
- `hydra_load_score` → `current_load`
- `hydra_packet_rate` → `packet_rate`
- `hydra_switch_count` → `switch_count`
- `hydra_predicted_load_t1` through `t5` → `predicted_load[]`

**Timeout**: 2 seconds. If a peer is unreachable, it's silently skipped. This means the optimizer works with partial information if one controller is down.

### 9. Edge Cases & Failure Scenarios

| Scenario | Behavior |
|---|---|
| **Only 1 controller healthy** | `optimize()` returns None ("insufficient_peers") — can't balance with 1 |
| **All predictions unavailable** | Falls back to current loads (reactive mode) |
| **Overloaded controller has 1 switch** | No migration — can't give away its only switch |
| **Marginal improvement** | ≤5.0 after cost → skipped to avoid churn |
| **Rapid load changes** | Cooldown prevents second migration within 30s |
| **Peer metrics stale** | Controllers with `last_update > 30s` ago are excluded |
| **Network partition** | Peers become unreachable → insufficient_peers |
| **Model produces garbage predictions** | Large predicted variance → more migrations (potential issue) |

### 10. Prometheus Metrics from Optimizer

| Metric | Type | Description |
|---|---|---|
| `hydra_load_variance_current` | gauge | Current variance across cluster |
| `hydra_load_variance_predicted` | gauge | Predicted variance at t+H |
| `hydra_optimizer_runs_total` | counter | Total optimization cycles |
| `hydra_migrations_triggered_total` | counter | Total migrations triggered |
| `hydra_cluster_balanced` | gauge | 1 if balanced, 0 if not |
| `hydra_optimizer_peers` | gauge | Number of reachable peers |

### 11. Interaction Between Optimizer and Predictor

```
predictor.py                      optimizer.py                     ryu_app.py
    │                                  │                               │
    │  ← add_observation()  ───────────│───────── _update_predictions()│
    │  → get_all_predictions() ────────│                               │
    │       {"t+1": 42, "t+2": 45}    │                               │
    │                                  │                               │
    │                                  │ ← update_local_state() ──────│
    │                                  │   (load_score, predicted_load)│
    │                                  │                               │
    │                                  │ ← optimize() ────────────────│
    │                                  │   → MigrationDecision        │
    │                                  │                               │
    │                                  │               _execute_migration()
    │                                  │               _record_migration_event()
```

**Data flow**: The predictor produces raw predictions → the controller converts to predicted load scores → the optimizer consumes these to compute predicted variance → if variance exceeds threshold → migration decision → controller executes.
