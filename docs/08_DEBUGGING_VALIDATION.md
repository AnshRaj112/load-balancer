# HYDRA-LB: Debugging + Validation Guide

---

## 1. Overview

This document provides strategies for verifying, debugging, and troubleshooting every major subsystem in HYDRA-LB. Each section includes:
- **How to verify** the component is working correctly
- **Expected log output** for healthy operation
- **Common errors**, their root causes, and fixes

---

## 2. Verifying Telemetry

### What to Check

The telemetry pipeline collects packet rates, flow counts, and byte counts from switches. Verify that:
1. Switches are registered with the controller
2. Port/flow stats replies are being received
3. Rates are being computed correctly

### Expected Logs

```
# Healthy telemetry (in controller logs)
Stats request sent to 7 switches
Port stats: dpid=1, rx_bytes=1250000, tx_bytes=980000
Flow stats: dpid=1, flow_count=25
Rates: packet_rate=450.0 pps, byte_rate=125000.0 Bps
```

### Prometheus Verification

```bash
curl http://localhost:9100/metrics | grep hydra_packet_rate
# → hydra_packet_rate{controller_id="1"} 450.0

curl http://localhost:9100/metrics | grep hydra_flow_count
# → hydra_flow_count{controller_id="1"} 25
```

### Common Issues

| Problem | Symptom | Root Cause | Fix |
|---|---|---|---|
| `packet_rate = 0` always | No PacketIn events | Switches not connecting or no traffic | Check OVS connectivity: `docker exec hydra-mininet ovs-vsctl show` |
| `flow_count = 0` always | No flows installed | Table-miss flow not installed | Check `switch_features_handler` ran successfully |
| `byte_rate` spikes then drops | Stats counter reset | Switch reconnection | This is normal after migration; counters reset |
| Rate values are NaN/Inf | Division by zero in elapsed time | Monitoring loop runs faster than expected | Add guard: `elapsed = max(elapsed, 0.001)` |

### Debugging Strategy

```bash
# Check if switches are connected
docker exec hydra-mininet ovs-vsctl show
# Should show: Bridge "s1" → Controller "tcp:172.20.0.10:6653" → is_connected: true

# Check OpenFlow flow table
docker exec hydra-mininet ovs-ofctl dump-flows s1 -O OpenFlow13
# Should show: table=0, match=..., actions=output:X

# Check packet counters directly
docker exec hydra-mininet ovs-ofctl dump-ports s1 -O OpenFlow13
```

---

## 3. Verifying Prediction

### What to Check

1. Model is loaded successfully
2. Observation buffer is being filled
3. Predictions are being generated

### Expected Logs

```
# Model loading (during startup)
Loaded LSTM model from /app/models/lstm_predictor.pt
Model config: input_size=4, hidden_size=128, num_layers=2, bidirectional=True

# During operation
Buffer: 30/30 observations
Prediction: [35.2, 37.1, 40.5] (t+1, t+2, t+3)
```

### Prometheus Verification

```bash
curl http://localhost:9100/metrics | grep hydra_predicted
# → hydra_predicted_load_t1{controller_id="1"} 35.2
# → hydra_predicted_load_t2{controller_id="1"} 37.1
# → hydra_predicted_load_t3{controller_id="1"} 40.5
```

### Common Issues

| Problem | Symptom | Root Cause | Fix |
|---|---|---|---|
| `predicted_load_t* = -1.0` | Predictions unavailable | Model not loaded or buffer not full | Wait 30s, check `MODEL_PATH` env var |
| Predictions are constant | Same value for t+1, t+2, t+3 | Buffer filled with identical values | Wait for real data to fill buffer (~30s) |
| Predictions are wildly off | Very large or negative values | Scale mismatch between training and live data | Adjust `/30.0` scaling in `_update_predictions()` |
| Model loads but crashes on predict | Shape mismatch | Model trained with wrong `input_size` | Retrain with `input_size=4` |
| `RuntimeError: expected Float` | Tensor type error | Input data contains NaN | Add `np.nan_to_num()` before tensor conversion |

### Debugging Strategy

```python
# Add to predictor.py::predict() for debugging
print(f"Input shape: {obs_array.shape}")
print(f"Input mean: {obs_array.mean(axis=0)}")
print(f"Input std: {obs_array.std(axis=0)}")
print(f"Normalized range: [{obs_normalized.min():.2f}, {obs_normalized.max():.2f}]")
print(f"Raw predictions: {predictions}")
```

---

## 4. Verifying Load Balancing

### What to Check

1. Load scores are being computed
2. Server selection is working correctly
3. Requests are distributed according to the strategy

### Expected Logs

```
# Load score computation
Load score: 42.5 (packet=30.0×0.5, flow=50.0×0.3, switch=60.0×0.2)
```

### Testing LB Algorithms

```python
# Quick test: run from project root
python -m pytest tests/test_load_balancer.py -v

# Specific test
python -m pytest tests/test_load_balancer.py::TestRoundRobinBalancer::test_round_robin_basic -v
```

### Common Issues

| Problem | Symptom | Root Cause | Fix |
|---|---|---|---|
| All traffic goes to one server | Round robin broken | `_current_index` not incrementing | Check `select_server()` threading |
| `select_server()` returns None | No healthy server | All servers marked unhealthy | Check health check logic; mark servers healthy |
| Weighted distribution is wrong | 3:1 ratio is 2:1 | Weight values incorrect | Verify `WeightedRoundRobinBalancer` weights |

---

## 5. Verifying Migration

### What to Check

This is the most critical and complex subsystem:
1. Optimizer detects imbalance
2. Migration decision is generated
3. REST RPC succeeds
4. OpenFlow role changes are applied
5. Traffic shifts to new controller

### Expected Logs (Full Migration Trace)

```
# On the overloaded controller (Controller 1):
[OPTIMIZER] Cluster state: C1=80.0, C2=30.0, C3=25.0
[OPTIMIZER] Current variance: 616.7
[OPTIMIZER] Predicted variance (t+3): 685.2 > threshold 30.0
[OPTIMIZER] Migration: switch 5 from C1 to C3 (improvement: 35.0)
[MIGRATION] POST http://172.20.0.12:9100/migrate {"dpid": 5, "from_controller": 1}
[MIGRATION] Response: 200 OK
[MIGRATION] Setting SLAVE role for switch 5
[MIGRATION] Switch 5 removed from master_switches (remaining: 6)

# On the receiving controller (Controller 3):
[MIGRATE] Received migration request: dpid=5, from_controller=1
[MIGRATE] Setting MASTER role for switch 5
[MIGRATE] Switch 5 added to master_switches (total: 8)
```

### Migration Log File

```bash
cat data/metrics/migration_log.csv
```

**Expected format**:
```csv
timestamp,from_controller,to_controller,switch_dpid,reason,improvement,current_variance,predicted_variance
2025-01-01T12:00:30,1,3,5,predicted_variance=685.2 > threshold=30.0,35.0,616.7,685.2
```

### Common Issues

| Problem | Symptom | Root Cause | Fix |
|---|---|---|---|
| No migrations happen | No migration logs | Variance below threshold | Lower `VARIANCE_THRESHOLD` or increase traffic imbalance |
| Migrations oscillate | A→B then B→A then A→B | Cooldown too short | Increase `MIGRATION_COOLDOWN` (default 30s) |
| Migration RPC fails | `ConnectionError` in logs | Peer controller unreachable | Check Docker network: `docker network inspect hydra-net` |
| Role request ignored | PacketIn still from old controller | Generation ID too low | Check `gen_id` is monotonically increasing |
| Switch doesn't switch | No PacketIn on new controller | 200 OK but role not applied | Check OVS: `ovs-vsctl get-controller <bridge>` |

### Debugging Strategy

```bash
# Check controller-switch role mapping
docker exec hydra-mininet ovs-vsctl list controller
# Look for: role=master, role=slave

# Check which controller is MASTER for a specific switch
docker exec hydra-mininet ovs-ofctl dump-flows s5 -O OpenFlow13
# The cookie field may indicate which controller installed the flow

# Tail migration events
docker logs -f hydra-controller-1 2>&1 | grep -i "MIGRAT\|PROACTIVE\|VARIANCE"
```

---

## 6. Debugging Per Module

### 6.1 `ryu_app.py` Debugging

```bash
# Full controller debug logs
docker logs -f hydra-controller-1

# Filter to specific subsystem
docker logs -f hydra-controller-1 2>&1 | grep "load_score"
docker logs -f hydra-controller-1 2>&1 | grep "PREDICT"
docker logs -f hydra-controller-1 2>&1 | grep "OPTIMIZER"
docker logs -f hydra-controller-1 2>&1 | grep "PacketIn"
```

### 6.2 `optimizer.py` Debugging

Key values to monitor:
```
- self.current_variance    → Are loads actually imbalanced?
- self.predicted_variance  → Does the LSTM predict future imbalance?
- len(healthy_states)      → Are all peers reachable?
- self.last_migration_time → Is cooldown blocking?
```

### 6.3 `predictor.py` Debugging

```python
# Check buffer state
print(f"Buffer length: {len(self.observations)}")
print(f"Last 3 observations: {list(self.observations)[-3:]}")
print(f"Can predict: {self.can_predict()}")
```

### 6.4 `telemetry.py` Debugging

```bash
# Check if CSV files are being written
ls -la data/metrics/
# Should show: controller_metrics_*.csv, switch_metrics_*.csv

# Check file contents
head -5 data/metrics/controller_metrics_*.csv
```

### 6.5 Topology Debugging

```bash
# Verify all switches are running
docker exec hydra-mininet ovs-vsctl show | grep Bridge | wc -l
# Should show: 20 (for k=4)

# Verify host connectivity
docker exec hydra-mininet python3 -c "
from topology.fat_tree_k4 import create_topology
net = create_topology()
net.start()
net.pingAll()
net.stop()
"
```

---

## 7. System-Wide Troubleshooting

### Issue: Nothing Happens After Starting

**Checklist**:
1. Are containers running? `docker ps`
2. Are switches connecting? `docker logs hydra-controller-1 | grep "Switch connected"`
3. Is the model loaded? `docker logs hydra-controller-1 | grep "LSTM"`
4. Is traffic flowing? Start a workload manually
5. Check health: `curl http://localhost:9100/health`

### Issue: High CPU Usage

**Possible causes**:
1. Too many switches (k too high)
2. Too much traffic (flooding)
3. Optimizer polling peers too frequently (every 1s × 3 HTTP requests)

**Fix**: Reduce k, lower traffic, or increase monitoring interval.

### Issue: Inconsistent Results Between Runs

**Possible causes**:
1. Stale flows from previous run
2. MAC table not cleared
3. Model checkpoint from different architecture

**Fix**:
```bash
docker compose down -v    # Remove volumes (clears state)
docker compose up -d      # Fresh start
sleep 15                  # Wait for initialization
```

---

## 8. Quick Reference: Key Metrics to Watch

| Metric | Healthy Range | Alert If |
|---|---|---|
| `hydra_load_score` | 0–80 | > 90 (overloaded) |
| `hydra_packet_rate` | 0–3000 | > 5000 (extreme load) |
| `hydra_switch_count` | 5–10 | 0 (no switches) or 20 (all switches on one controller) |
| `hydra_load_variance_current` | 0–50 | > 100 (severe imbalance) |
| `hydra_migrations_triggered_total` | 0–5/hour | > 20/hour (thrashing) |
| `hydra_latency_avg_ms` | 0.1–5.0 | > 50 (controller overloaded) |
| `hydra_predicted_load_t*` | 0–100 | -1.0 (predictions unavailable) |
