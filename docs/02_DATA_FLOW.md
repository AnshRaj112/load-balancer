# HYDRA-LB: Data Flow Document

---

## Overview

This document traces the **complete lifecycle of a packet** through the HYDRA-LB system — from the moment it enters the network to the point where a proactive migration decision modifies the control plane. Every module, function, and variable involved is documented.

---

## End-to-End Data Flow Diagram

```
   Host sends packet
        │
        ▼
   ┌─────────────┐
   │ OVS Switch   │  ← No matching flow → sends PacketIn via OpenFlow
   └──────┬───────┘
          │
          ▼
   ┌──────────────────────────────────────────────────────────────────┐
   │  ryu_app.py :: HydraController._packet_in_handler()             │
   │                                                                  │
   │  1. Learn MAC → self.mac_to_port[dpid][src] = in_port           │
   │  2. Lookup dst MAC → decide out_port (known or FLOOD)           │
   │  3. If known → install flow + send PacketOut                    │
   │  4. If unknown → FLOOD + send PacketOut                         │
   │  5. Increment: packet_in_count, bytes_total                      │
   │  6. Track: request_latencies.append(latency_ms)                  │
   └──────────────────────────────────────────────────────────────────┘
          │
          │  (Every 1 second — monitoring thread)
          ▼
   ┌──────────────────────────────────────────────────────────────────┐
   │  ryu_app.py :: _request_stats()                                  │
   │                                                                  │
   │  For each datapath:                                              │
   │    → OFPPortStatsRequest → gets port byte/packet counts          │
   │    → OFPFlowStatsRequest → gets flow entry counts                │
   └──────────────────────────────────────────────────────────────────┘
          │
          ▼
   ┌──────────────────────────────────────────────────────────────────┐
   │  ryu_app.py :: _port_stats_reply_handler()                       │
   │                 _flow_stats_reply_handler()                      │
   │                                                                  │
   │  Aggregate:                                                      │
   │    self.port_stats[dpid] = (total_bytes, total_packets)          │
   │    self.bytes_total = sum(all port_stats bytes)                   │
   │    self.data_packets_total = sum(all port_stats packets)          │
   │    self.switch_flow_counts[dpid] = len(flow_entries)             │
   │    self.flow_count = sum(all switch_flow_counts)                  │
   └──────────────────────────────────────────────────────────────────┘
          │
          ▼
   ┌──────────────────────────────────────────────────────────────────┐
   │  ryu_app.py :: _calculate_rates()                                │
   │                                                                  │
   │  packet_rate = (data_packets_total - last_data_packets_total)    │
   │                 / elapsed_seconds                                 │
   │  byte_rate = (bytes_total - last_bytes_total) / elapsed_seconds  │
   │  avg_latency_ms = mean(request_latencies)                        │
   │  max_latency_ms = max(request_latencies)                         │
   │  request_latencies = []  ← reset each interval                   │
   └──────────────────────────────────────────────────────────────────┘
          │
          ▼
   ┌──────────────────────────────────────────────────────────────────┐
   │  ryu_app.py :: _calculate_load_score()                           │
   │                                                                  │
   │  packet_score = min(100, packet_rate / 30.0)                     │
   │  flow_score   = min(100, flow_count * 10.0)                      │
   │  switch_score = min(100, switch_count * 20.0)                    │
   │                                                                  │
   │  load_score = (packet_score × 0.5)                               │
   │             + (flow_score   × 0.3)                               │
   │             + (switch_score × 0.2)                               │
   │                                                                  │
   │  Range: 0.0 – 100.0                                              │
   └──────────────────────────────────────────────────────────────────┘
          │
          ▼
   ┌──────────────────────────────────────────────────────────────────┐
   │  ryu_app.py :: _update_predictions()                             │
   │                                                                  │
   │  Scale inputs for LSTM compatibility:                            │
   │    scaled_packet_rate = packet_rate / 30.0                       │
   │    scaled_byte_rate   = byte_rate   / 30.0                       │
   │                                                                  │
   │  predictor.add_observation(                                      │
   │      packet_rate=scaled_packet_rate,                             │
   │      flow_count=flow_count,                                      │
   │      byte_rate=scaled_byte_rate,                                 │
   │      switch_count=switch_count                                   │
   │  )                                                               │
   │                                                                  │
   │  predictions = predictor.get_all_predictions()                   │
   │  → {"t+1": 42.3, "t+2": 45.1, "t+3": 50.7}                    │
   │                                                                  │
   │  For each t+i:                                                   │
   │    p_score = min(100, max(0, pred_scaled_pr))                    │
   │    predicted_load_score = p_score×0.5 + f_score×0.3 + s_score×0.2│
   │                                                                  │
   │  self.predicted_load = [score_t1, score_t2, ..., score_t5]      │
   └──────────────────────────────────────────────────────────────────┘
          │
          ▼
   ┌──────────────────────────────────────────────────────────────────┐
   │  ryu_app.py :: _run_optimizer()                                  │
   │                                                                  │
   │  optimizer.update_local_state(                                   │
   │      load_score, predicted_load, switch_count,                   │
   │      packet_rate, byte_rate, switch_dpids                        │
   │  )                                                               │
   │                                                                  │
   │  decision = optimizer.optimize()                                  │
   │                                                                  │
   │  If decision is not None:                                        │
   │    → _execute_migration(decision)                                │
   │    → _record_migration_event(decision)                           │
   └──────────────────────────────────────────────────────────────────┘
          │
          ▼
   ┌──────────────────────────────────────────────────────────────────┐
   │  optimizer.py :: ProactiveOptimizer.optimize()                   │
   │                                                                  │
   │  1. fetch_peer_states()                                          │
   │     → HTTP GET http://172.20.0.1x:9100/metrics                   │
   │     → parse Prometheus text → ControllerState objects             │
   │                                                                  │
   │  2. Filter healthy peers (last_update < 30s ago)                 │
   │     → Need at least 2 controllers                                │
   │                                                                  │
   │  3. Check migration cooldown (30s since last migration)          │
   │                                                                  │
   │  4. current_variance = variance(current_loads)                   │
   │                                                                  │
   │  5. predicted_variance = variance(predicted_loads at t+horizon)  │
   │     If horizon=3: uses predicted_load[2] for each controller     │
   │                                                                  │
   │  6. If predicted_variance ≤ threshold (30.0) → return None       │
   │                                                                  │
   │  7. max_load_cid = controller with highest predicted load        │
   │     min_load_cid = controller with lowest predicted load         │
   │                                                                  │
   │  8. migration_cost = 0.3 × load_diff                            │
   │     expected_improvement = load_diff - migration_cost            │
   │     If improvement ≤ 5.0 → return None                          │
   │                                                                  │
   │  9. Return MigrationDecision(from=max, to=min)                   │
   └──────────────────────────────────────────────────────────────────┘
          │
          ▼
   ┌──────────────────────────────────────────────────────────────────┐
   │  ryu_app.py :: _execute_migration(decision)                      │
   │                                                                  │
   │  If this controller is the overloaded one:                       │
   │    1. Select dpid = first switch in master_switches              │
   │    2. POST http://172.20.0.1x:9100/migrate                      │
   │       body: {"dpid": dpid, "from_controller": self.id}          │
   │    3. If 200 OK:                                                  │
   │       → Send OFPRoleRequest(SLAVE) to give up the switch        │
   │       → Remove from master_switches                              │
   │                                                                  │
   │  On the receiving controller (MetricsHandler.do_POST):           │
   │    1. Parse dpid and from_cid from POST body                     │
   │    2. Send OFPRoleRequest(MASTER) to claim the switch            │
   │    3. Add to master_switches                                      │
   │    4. Return 200 OK                                               │
   └──────────────────────────────────────────────────────────────────┘
          │
          ▼
   ┌──────────────────────────────────────────────────────────────────┐
   │  Post-Migration State                                            │
   │                                                                  │
   │  • Overloaded controller now SLAVE for migrated switch           │
   │    → No more PacketIn from that switch                           │
   │    → switch_count decremented → load_score decreases             │
   │                                                                  │
   │  • Receiving controller now MASTER for the new switch            │
   │    → Receives PacketIn → installs flows → handles traffic        │
   │    → switch_count incremented → load_score increases             │
   │                                                                  │
   │  • Event recorded to data/metrics/migration_log.csv              │
   └──────────────────────────────────────────────────────────────────┘
```

---

## Detailed Step-by-Step Trace

### Step 1: Packet Enters the Network

A host (e.g., `h1` at `10.0.0.1`) sends a packet to `h5` (`10.0.0.5`). The packet arrives at edge switch `e1_1`.

**If no flow rule exists**: OVS sends a `PacketIn` message to the MASTER controller via OpenFlow 1.3.

### Step 2: PacketIn Handling — `_packet_in_handler()`

```python
# ryu_app.py, line 611–671
def _packet_in_handler(self, ev):
    # Guard: only MASTER-ed switches
    if datapath.id not in self.master_switches:
        return

    self.packet_in_count += 1          # Global counter
    # Parse Ethernet
    pkt = packet.Packet(msg.data)
    eth = pkt.get_protocols(ethernet.ethernet)[0]
    # Learn source MAC
    self.mac_to_port[dpid][src] = in_port
    # Decide output
    if dst in self.mac_to_port[dpid]:
        out_port = self.mac_to_port[dpid][dst]   # Known → unicast
    else:
        out_port = ofproto.OFPP_FLOOD              # Unknown → flood
    # Install flow if unicast
    if out_port != FLOOD:
        self.add_flow(datapath, 1, match, actions)  # → flow_count += 1
    # Send packet
    datapath.send_msg(PacketOut(...))
    self.packet_out_count += 1
    # Track latency
    latency_ms = (time.time() - start_time) * 1000
    self.request_latencies.append(latency_ms)
```

**Simple explanation**: The controller learns where the source lives, figures out where to send the packet, optionally installs a shortcut (flow rule) so the switch handles future similar packets without asking again, and forwards it.

**Technical explanation**: The OFPP_FLOOD action causes OVS to send the packet out all ports except the ingress. The flow match uses `(in_port, eth_dst, eth_src)`, and subsequent packets matching this tuple are handled in hardware by OVS without a PacketIn.

### Step 3: Metrics Collection — `_request_stats()`

Every 1 second, the monitoring thread fires:

```python
# ryu_app.py, line 237–249
def _request_stats(self):
    for datapath in self.datapaths.values():
        req = parser.OFPPortStatsRequest(datapath, 0, ofp.OFPP_ANY)
        datapath.send_msg(req)
        req = parser.OFPFlowStatsRequest(datapath)
        datapath.send_msg(req)
```

OpenFlow stats replies are handled asynchronously by `_port_stats_reply_handler()` and `_flow_stats_reply_handler()`.

**Simple explanation**: The controller asks each of its switches "how many bytes/packets have you processed?" and "how many flow rules do you have?"

### Step 4: Rate Computation — `_calculate_rates()`

```python
# ryu_app.py, line 251–272
self.packet_rate = (data_packets_total - last_data_packets_total) / elapsed
self.byte_rate   = (bytes_total - last_bytes_total) / elapsed

# Latency stats
self.avg_latency_ms = mean(request_latencies)
self.request_latencies = []  # Reset
```

**Simple explanation**: Takes the difference in total counts since the last measurement and divides by time to get rates.

### Step 5: Load Score — `_calculate_load_score()`

```python
# ryu_app.py, line 274–282
packet_score = min(100, self.packet_rate / 30.0)
flow_score   = min(100, self.flow_count * 10.0)
switch_score = min(100, self.switch_count * 20.0)

self.load_score = packet_score * 0.5 + flow_score * 0.3 + switch_score * 0.2
```

**Example**: If packet_rate=900, flow_count=5, switch_count=3:
- packet_score = min(100, 900/30) = 30.0
- flow_score = min(100, 50) = 50.0
- switch_score = min(100, 60) = 60.0
- **load_score = 15.0 + 15.0 + 12.0 = 42.0**

### Step 6: LSTM Prediction — `_update_predictions()`

```python
# ryu_app.py, line 284–319
# Scale down to match training data distribution
scaled_pr = self.packet_rate / 30.0
scaled_br = self.byte_rate / 30.0

self.predictor.add_observation(scaled_pr, flow_count, scaled_br, switch_count)
predictions = self.predictor.get_all_predictions()
# → {"t+1": 31.5, "t+2": 33.2, "t+3": 36.1}
```

Inside `predictor.py`:
```python
# predictor.py :: predict()
obs_array = np.array(list(self.observations))    # Shape: [30, 4]
x = torch.tensor(obs_array).unsqueeze(0)          # Shape: [1, 30, 4]
predictions = self.model(x).squeeze().cpu().numpy() # Shape: [3]
```

### Step 7: Optimizer Decision — `optimizer.optimize()`

```python
# optimizer.py, line 214–314
# Fetch peer states via HTTP GET
self.fetch_peer_states()
# Compute predicted variance
predicted_loads = [state.predicted_load[horizon] for state in cluster]
predicted_variance = sum((l - mean)^2 for l in loads) / len(loads)
# Decision
if predicted_variance > 30.0:
    return MigrationDecision(from=max_load, to=min_load)
```

### Step 8: Migration Execution — `_execute_migration()`

```python
# ryu_app.py, line 349–381
# Send REST request to target
resp = requests.post("http://172.20.0.12:9100/migrate",
                     json={"dpid": 5, "from_controller": 1})
if resp.status_code == 200:
    # Demote self to SLAVE
    self.set_role(datapath, is_master=False)
    # → OFPRoleRequest(OFPCR_ROLE_SLAVE)
```

On the receiving end:
```python
# ryu_app.py :: MetricsHandler.do_POST()
# Promote to MASTER
self.controller.set_role(datapath, is_master=True)
# → OFPRoleRequest(OFPCR_ROLE_MASTER)
```

---

## Data Formats at Each Stage

| Stage | Data Format | Shape / Example |
|---|---|---|
| PacketIn | OpenFlow message | `msg.data` = raw Ethernet frame bytes |
| Port Stats | OFPPortStats | `stat.rx_bytes`, `stat.rx_packets` per port |
| Flow Stats | OFPFlowStats | List of flow entries per switch |
| Computed Rates | Python floats | `packet_rate=900.0`, `byte_rate=460800.0` |
| Load Score | Float 0–100 | `42.0` |
| LSTM Input | Tensor | `[1, 30, 4]` (batch, lookback, features) |
| LSTM Output | Tensor | `[1, 3]` (batch, horizon) |
| Predicted Load | List[float] | `[21.5, 23.2, 26.1, -1.0, -1.0]` |
| Peer Metrics | Prometheus text | Multi-line text with `hydra_*` metrics |
| Migration Decision | MigrationDecision | `from_controller=1, to_controller=3, dpid=5` |
| Migration RPC | HTTP POST JSON | `{"dpid": 5, "from_controller": 1}` |
| Role Request | OpenFlow msg | `OFPRoleRequest(MASTER/SLAVE, gen_id)` |

---

## Timing

| Event | Frequency | Trigger |
|---|---|---|
| PacketIn processing | Per-packet | Switch encounters unknown flow |
| Stats request | Every 1s | Monitoring thread loop |
| Rate calculation | Every 1s | After stats request |
| Load score computation | Every 1s | After rate calculation |
| LSTM prediction | Every 1s | After load score |
| Optimizer cycle | Every 1s | After prediction |
| Migration execution | At most once per 30s | Optimizer cooldown |
| Prometheus scrape | Every 5s | Prometheus config |
| Benchmark snapshot | Every 5s | Experiment runner |
