# HYDRA-LB: API Reference

---

## Overview

Each HYDRA-LB controller exposes an HTTP server on **port 9100** that serves three endpoints. This API is used for inter-controller communication (optimizer), observability (Prometheus), and health checking.

**Base URL**: `http://<controller-ip>:9100`

| Controller | IP (Docker) | Base URL |
|---|---|---|
| Controller 1 | `172.20.0.10` | `http://172.20.0.10:9100` |
| Controller 2 | `172.20.0.11` | `http://172.20.0.11:9100` |
| Controller 3 | `172.20.0.12` | `http://172.20.0.12:9100` |

From the host machine, only Controller 1's port is mapped by default:
- `http://localhost:9100` → Controller 1

---

## Endpoints

### 1. `GET /metrics`

Returns all controller metrics in **Prometheus text exposition format**.

**Used by**: Prometheus scraper (every 5s), peer controllers' optimizer (every 1s)

#### Request

```http
GET /metrics HTTP/1.1
Host: 172.20.0.10:9100
```

#### Response

```
HTTP/1.1 200 OK
Content-Type: text/plain; charset=utf-8

# HELP hydra_controller_info Controller identity
# TYPE hydra_controller_info gauge
hydra_controller_info{controller_id="1"} 1

# HELP hydra_uptime_seconds Controller uptime
# TYPE hydra_uptime_seconds counter
hydra_uptime_seconds{controller_id="1"} 342.5

# HELP hydra_packet_in_total Total PacketIn events processed
# TYPE hydra_packet_in_total counter
hydra_packet_in_total{controller_id="1"} 15234

# HELP hydra_packet_out_total Total PacketOut messages sent
# TYPE hydra_packet_out_total counter
hydra_packet_out_total{controller_id="1"} 15234

# HELP hydra_packet_rate Current packet-in rate (packets/sec)
# TYPE hydra_packet_rate gauge
hydra_packet_rate{controller_id="1"} 892.3

# HELP hydra_byte_rate Current byte throughput (bytes/sec)
# TYPE hydra_byte_rate gauge
hydra_byte_rate{controller_id="1"} 460800.0

# HELP hydra_flow_count Number of installed flow rules
# TYPE hydra_flow_count gauge
hydra_flow_count{controller_id="1"} 42

# HELP hydra_switch_count Number of MASTER switches
# TYPE hydra_switch_count gauge
hydra_switch_count{controller_id="1"} 7

# HELP hydra_bytes_total Total bytes processed
# TYPE hydra_bytes_total counter
hydra_bytes_total{controller_id="1"} 15728640

# HELP hydra_mac_table_size Learned MAC addresses
# TYPE hydra_mac_table_size gauge
hydra_mac_table_size{controller_id="1"} 16

# HELP hydra_load_score Composite load score (0-100)
# TYPE hydra_load_score gauge
hydra_load_score{controller_id="1"} 42.5

# HELP hydra_cpu_seconds_total CPU time consumed
# TYPE hydra_cpu_seconds_total counter
hydra_cpu_seconds_total{controller_id="1"} 12.34

# HELP hydra_memory_mb Memory usage in MB
# TYPE hydra_memory_mb gauge
hydra_memory_mb{controller_id="1"} 128.5

# HELP hydra_latency_avg_ms Average PacketIn processing latency
# TYPE hydra_latency_avg_ms gauge
hydra_latency_avg_ms{controller_id="1"} 2.3

# HELP hydra_latency_max_ms Maximum PacketIn processing latency
# TYPE hydra_latency_max_ms gauge
hydra_latency_max_ms{controller_id="1"} 8.7

# HELP hydra_predicted_load Predicted load score at horizon t+N
# TYPE hydra_predicted_load gauge
hydra_predicted_load_t1{controller_id="1"} 44.2
hydra_predicted_load_t2{controller_id="1"} 46.8
hydra_predicted_load_t3{controller_id="1"} 50.1
hydra_predicted_load_t4{controller_id="1"} -1.0
hydra_predicted_load_t5{controller_id="1"} -1.0

# HELP hydra_load_variance_current Current load variance across cluster
# TYPE hydra_load_variance_current gauge
hydra_load_variance_current{controller_id="1"} 125.3

# HELP hydra_load_variance_predicted Predicted load variance at horizon
# TYPE hydra_load_variance_predicted gauge
hydra_load_variance_predicted{controller_id="1"} 210.7

# HELP hydra_optimizer_runs_total Total optimizer cycles
# TYPE hydra_optimizer_runs_total counter
hydra_optimizer_runs_total{controller_id="1"} 340

# HELP hydra_migrations_triggered_total Total migrations triggered
# TYPE hydra_migrations_triggered_total counter
hydra_migrations_triggered_total{controller_id="1"} 3

# HELP hydra_cluster_balanced Whether cluster is balanced (1=yes, 0=no)
# TYPE hydra_cluster_balanced gauge
hydra_cluster_balanced{controller_id="1"} 1

# HELP hydra_optimizer_peers Number of reachable peer controllers
# TYPE hydra_optimizer_peers gauge
hydra_optimizer_peers{controller_id="1"} 2
```

#### Metrics Summary Table

| Metric | Type | Range | Description |
|---|---|---|---|
| `hydra_controller_info` | gauge | 1 | Controller identity marker |
| `hydra_uptime_seconds` | counter | 0+ | Seconds since controller start |
| `hydra_packet_in_total` | counter | 0+ | Cumulative PacketIn count |
| `hydra_packet_out_total` | counter | 0+ | Cumulative PacketOut count |
| `hydra_packet_rate` | gauge | 0+ | Current packets per second |
| `hydra_byte_rate` | gauge | 0+ | Current bytes per second |
| `hydra_flow_count` | gauge | 0+ | Installed OpenFlow rules |
| `hydra_switch_count` | gauge | 0–20 | Switches where this controller is MASTER |
| `hydra_bytes_total` | counter | 0+ | Cumulative bytes processed |
| `hydra_mac_table_size` | gauge | 0+ | Entries in MAC learning table |
| `hydra_load_score` | gauge | 0–100 | Weighted composite load metric |
| `hydra_cpu_seconds_total` | counter | 0+ | Process CPU time |
| `hydra_memory_mb` | gauge | 0+ | Process memory in MB |
| `hydra_latency_avg_ms` | gauge | 0+ | Mean PacketIn processing time |
| `hydra_latency_max_ms` | gauge | 0+ | Max PacketIn processing time |
| `hydra_predicted_load_t1`–`t5` | gauge | 0–100 / -1 | Predicted load at future timesteps (-1 = unavailable) |
| `hydra_load_variance_current` | gauge | 0+ | Current inter-controller load variance |
| `hydra_load_variance_predicted` | gauge | 0+ | Predicted variance at horizon |
| `hydra_optimizer_runs_total` | counter | 0+ | Total optimization cycles executed |
| `hydra_migrations_triggered_total` | counter | 0+ | Total migrations triggered |
| `hydra_cluster_balanced` | gauge | 0 or 1 | Whether predicted variance ≤ threshold |
| `hydra_optimizer_peers` | gauge | 0–2 | Number of reachable peer controllers |

---

### 2. `GET /health`

Returns a JSON health check response.

**Used by**: Docker health checks, monitoring scripts

#### Request

```http
GET /health HTTP/1.1
Host: 172.20.0.10:9100
```

#### Response

```json
{
  "status": "healthy",
  "controller_id": 1,
  "switches": 7,
  "load_score": 42.5
}
```

| Field | Type | Description |
|---|---|---|
| `status` | string | Always `"healthy"` if the controller is responding |
| `controller_id` | int | Controller identifier (1, 2, or 3) |
| `switches` | int | Number of MASTER switches |
| `load_score` | float | Current composite load score |

---

### 3. `POST /migrate`

Requests this controller to take ownership (MASTER role) of a switch from another controller.

**Used by**: Peer controllers' optimizer when a migration decision is made

#### Request

```http
POST /migrate HTTP/1.1
Host: 172.20.0.12:9100
Content-Type: application/json

{
  "dpid": 5,
  "from_controller": 1
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `dpid` | int | Yes | Datapath ID of the switch to migrate |
| `from_controller` | int | Yes | ID of the sending (overloaded) controller |

#### Successful Response

```json
{
  "status": "ok",
  "message": "Migration accepted: switch 5 from controller 1"
}
```

**Status code**: `200 OK`

**Side effects**:
1. Receiving controller sends `OFPRoleRequest(MASTER)` to the switch
2. Switch is added to `master_switches` set
3. Controller begins receiving PacketIn events from this switch

#### Error Responses

| Status | Body | Cause |
|---|---|---|
| `400` | `{"error": "Missing dpid or from_controller"}` | Malformed request body |
| `404` | `{"error": "Switch 5 not found in datapaths"}` | Switch is not connected to this controller |
| `500` | `{"error": "Role change failed: <details>"}` | OpenFlow role request failed |

---

## Usage Examples

### cURL — Check Load Score

```bash
# From host (Controller 1 only)
curl -s http://localhost:9100/metrics | grep hydra_load_score
# hydra_load_score{controller_id="1"} 42.5

# From within Docker network (any controller)
curl -s http://172.20.0.11:9100/metrics | grep hydra_load_score
```

### cURL — Health Check

```bash
curl -s http://localhost:9100/health | python3 -m json.tool
```

### cURL — Trigger Manual Migration

```bash
# Move switch 5 from controller 1 to controller 3
curl -X POST http://172.20.0.12:9100/migrate \
  -H "Content-Type: application/json" \
  -d '{"dpid": 5, "from_controller": 1}'
```

### Python — Fetch Peer Metrics

```python
import requests

def get_peer_load(controller_ip, port=9100):
    resp = requests.get(f"http://{controller_ip}:{port}/metrics", timeout=2)
    for line in resp.text.split('\n'):
        if line.startswith('hydra_load_score'):
            return float(line.split()[-1])
    return None

# Check all controllers
for i in range(10, 13):
    load = get_peer_load(f"172.20.0.{i}")
    print(f"Controller at .{i}: load={load}")
```

---

## Internal Communication Flow

```
Controller 1 (Overloaded)              Controller 3 (Underloaded)
       │                                        │
       │  1. optimizer.optimize()                │
       │     → predicted_variance > 30.0         │
       │     → decision: from=1, to=3            │
       │                                         │
       │  2. POST /migrate                       │
       │     {"dpid": 5, "from_controller": 1}   │
       │ ──────────────────────────────────────►  │
       │                                         │  3. OFPRoleRequest(MASTER)
       │                                         │     → switch 5
       │                                         │
       │            200 OK                       │
       │ ◄──────────────────────────────────────  │
       │                                         │
       │  4. OFPRoleRequest(SLAVE)               │
       │     → switch 5                          │
       │                                         │
       │  5. Remove dpid 5 from master_switches  │
       │                                         │
```
