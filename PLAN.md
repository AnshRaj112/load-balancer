# HYDRA-LB+ Project Plan

## Executive Summary

**HYDRA-LB+** (Hybrid Dynamic Resource-Aware Load Balancer) is a research-grade, multi-controller SDN load balancer designed for high-performance data center networks. It combines predictive load forecasting, variance-aware optimization, and security-aware anomaly detection into a unified system.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Architecture](#2-architecture)
3. [Technology Stack](#3-technology-stack)
4. [Project Phases](#4-project-phases)
5. [Running the Application](#5-running-the-application)
6. [Using with Existing Domains/IPs](#6-using-with-existing-domainsips)
7. [Monitoring with Prometheus & Grafana](#7-monitoring-with-prometheus--grafana)
8. [Configuration Reference](#8-configuration-reference)
9. [Testing & Validation](#9-testing--validation)
10. [Research Contributions](#10-research-contributions)

---

## 1. Project Overview

### Problem Statement

Traditional SDN load balancers suffer from:
- **Reactive decisions**: Only respond after congestion occurs
- **Single-point bottlenecks**: Central controller becomes overwhelmed
- **Static algorithms**: Round-robin ignores actual server load
- **Security vulnerabilities**: Susceptible to DDoS amplification attacks

### Solution: HYDRA-LB+

A novel load balancer that addresses these issues through:

| Feature | Description |
|---------|-------------|
| **Predictive Forecasting** | LSTM-based model predicts load 5+ steps ahead |
| **Variance-Aware Optimization** | Minimizes load imbalance across controllers |
| **Migration Cost Modeling** | Avoids expensive switch migrations |
| **Entropy-Based Anomaly Detection** | Filters malicious traffic before processing |
| **Hierarchical Control** | Local heuristics + global optimization |

### Key Metrics Improved

- **Load Variance**: Target 40-60% reduction vs Round Robin
- **Response Latency**: Target 20-30% improvement
- **Throughput**: Near-linear scaling with topology size
- **Attack Resilience**: Maintain performance during DDoS

---

## 2. Architecture

### System Components

```
┌─────────────────────────────────────────────────────────────────┐
│                      HYDRA-LB+ Control Plane                     │
├─────────────────┬─────────────────┬─────────────────────────────┤
│   Controller 1  │   Controller 2  │        Controller 3          │
│   ┌───────────┐ │   ┌───────────┐ │   ┌───────────┐              │
│   │ Ryu App   │ │   │ Ryu App   │ │   │ Ryu App   │              │
│   ├───────────┤ │   ├───────────┤ │   ├───────────┤              │
│   │ Predictor │ │   │ Predictor │ │   │ Predictor │              │
│   ├───────────┤ │   ├───────────┤ │   ├───────────┤              │
│   │ Optimizer │ │   │ Optimizer │ │   │ Optimizer │              │
│   ├───────────┤ │   ├───────────┤ │   ├───────────┤              │
│   │ Telemetry │ │   │ Telemetry │ │   │ Telemetry │              │
│   └─────┬─────┘ │   └─────┬─────┘ │   └─────┬─────┘              │
│         │       │         │       │         │                    │
└─────────┼───────┴─────────┼───────┴─────────┼────────────────────┘
          │                 │                 │
          ▼                 ▼                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                     OpenFlow Network (Mininet)                   │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐             │
│  │ Switch 1│══│ Switch 2│══│ Switch 3│══│ Switch N│             │
│  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘             │
│       │            │            │            │                   │
│  ┌────┴────┐  ┌────┴────┐  ┌────┴────┐  ┌────┴────┐             │
│  │ Hosts   │  │ Hosts   │  │ Hosts   │  │ Hosts   │             │
│  └─────────┘  └─────────┘  └─────────┘  └─────────┘             │
└─────────────────────────────────────────────────────────────────┘
```

### Data Flow

1. **Packet arrives** at switch → Switch doesn't know where to forward
2. **Packet-in to controller** → Controller processes request
3. **Telemetry recorded** → Metrics collected for prediction
4. **LB decision made** → Select optimal backend server
5. **Flow rule installed** → Future packets forwarded directly
6. **Periodic optimization** → Rebalance if variance exceeds threshold

---

## 3. Technology Stack

| Layer | Technology | Purpose |
|-------|------------|---------|
| **Controller** | Ryu SDN Framework | OpenFlow management |
| **Emulation** | Mininet | Network topology simulation |
| **Switching** | Open vSwitch (OVS) | OpenFlow-compatible switch |
| **ML Framework** | PyTorch | LSTM/Attention models |
| **Optimization** | SciPy / Custom | Variance minimization |
| **Monitoring** | Prometheus | Metrics collection |
| **Visualization** | Grafana | Dashboards and alerts |
| **Containers** | Docker Compose | Environment orchestration |
| **Language** | Python 3.11+ | All components |

---

## 4. Project Phases

### Phase 1: Core Infrastructure ✅ COMPLETE

| Item | Status | Description |
|------|--------|-------------|
| Docker Environment | ✅ | 3 controllers + Mininet + monitoring |
| Ryu Controller | ✅ | OpenFlow handling, L2 learning |
| Baselines | ✅ | Round Robin, Least Connections |
| Topologies | ✅ | Fat-Tree, Leaf-Spine generators |
| Telemetry | ✅ | Per-switch metrics collection |
| Metrics Storage | ✅ | CSV + SQLite backends |
| Unit Tests | ✅ | 29 tests passing |

### Phase 2: Prediction Module 🔄 NEXT

| Item | Description |
|------|-------------|
| LSTM Model | 2-layer LSTM with attention mechanism |
| Data Pipeline | Time-series preprocessing (sliding window) |
| Training | Synthetic data + Google Cluster traces |
| Integration | Hook into Ryu app for proactive LB |
| Evaluation | MAE, MAPE, prediction horizon analysis |

**Model Architecture:**
```
Input: [packet_rate, flow_count, byte_rate] × 10 timesteps
   ↓
LSTM Layer 1 (hidden=64)
   ↓
Attention Mechanism (temporal)
   ↓
LSTM Layer 2 (hidden=32)
   ↓
Dense Layer → Output: predicted_load[t+1...t+5]
```

### Phase 3: Optimization Engine

| Item | Description |
|------|-------------|
| Variance Objective | Minimize Σ(load_i - mean_load)² |
| Migration Cost | Add penalty for switch reassignments |
| Solver | Gradient descent with constraints |
| Thresholds | Trigger optimization when variance > 50% |

### Phase 4: Security Layer

| Item | Description |
|------|-------------|
| Entropy Calculator | Measure packet distribution entropy |
| Anomaly Detection | Flag low-entropy (attack) traffic |
| Suppression | Rate-limit suspicious sources |
| Whitelist | Protect known-good traffic |

### Phase 5: Evaluation & Paper

| Item | Description |
|------|-------------|
| Benchmark Suite | Standard workloads + attack scenarios |
| Comparison | vs Round Robin, Least Load, ECMP |
| Analysis | Statistical significance tests |
| Paper | Target: IEEE/ACM networking venue |

---

## 5. Running the Application

### Prerequisites

- Docker Engine 20.10+
- Docker Compose v2.0+
- 8GB RAM minimum (16GB recommended)
- Linux host (or WSL2 on Windows)

### Quick Start

```bash
# 1. Navigate to project directory
cd /home/dev/lb/hydra-lb

# 2. Start the basic testbed (3 controllers + Mininet)
./scripts/start_testbed.sh

# 3. Start with monitoring (adds Prometheus + Grafana)
./scripts/start_testbed.sh --monitoring

# 4. Start in foreground mode (see all logs)
./scripts/start_testbed.sh --foreground

# 5. Rebuild images after code changes
./scripts/start_testbed.sh --rebuild
```

### Verify Services

```bash
# Check container status
docker ps

# Expected output:
# CONTAINER ID   IMAGE              STATUS    PORTS
# xxxxx         hydra-controller   Up        0.0.0.0:6653->6653/tcp, 0.0.0.0:8080->8080/tcp
# xxxxx         hydra-controller   Up        0.0.0.0:6654->6653/tcp, 0.0.0.0:8081->8080/tcp
# xxxxx         hydra-controller   Up        0.0.0.0:6655->6653/tcp, 0.0.0.0:8082->8080/tcp
# xxxxx         hydra-mininet      Up        (network mode: host for OVS)
```

### Run a Network Topology

```bash
# Enter Mininet container
docker exec -it hydra-mininet bash

# Option 1: Start Fat-Tree k=4 (20 switches, 16 hosts)
python3 /app/topology/fat_tree.py 4

# Option 2: Start Leaf-Spine (4 leaves, 2 spines)
python3 /app/topology/leaf_spine.py 4 2 4

# Inside Mininet CLI, test connectivity
mininet> pingall
mininet> iperf h1 h16
```

### Generate Test Traffic

```bash
# Inside Mininet container
./scripts/run_traffic.sh -d 60 -p uniform -b 10M

# Traffic patterns:
#   uniform - Steady traffic from all hosts
#   burst   - Alternating high/low bursts
#   random  - Random source, duration, bandwidth
```

### Stop the Testbed

```bash
./scripts/stop_testbed.sh
```

---

## 6. Using with Existing Domains/IPs

### Scenario: Load Balance Real Backend Servers

If you have actual servers (e.g., web servers at 192.168.1.10, 192.168.1.11, 192.168.1.12), you can configure HYDRA-LB to distribute traffic.

### Step 1: Configure Virtual IP (VIP)

Edit `config/hydra_config.yaml`:

```yaml
load_balancer:
  enabled: true
  strategy: round_robin  # or least_load, weighted_round_robin
  
  virtual_ips:
    # VIP that clients connect to
    - vip: "10.0.0.100"
      port: 80
      protocol: tcp
      # Backend servers (your existing IPs)
      servers:
        - ip: "192.168.1.10"
          port: 80
          weight: 1.0
        - ip: "192.168.1.11"
          port: 80
          weight: 1.0
        - ip: "192.168.1.12"
          port: 80
          weight: 2.0  # Gets 2x traffic
          
    # HTTPS VIP
    - vip: "10.0.0.101"
      port: 443
      protocol: tcp
      servers:
        - ip: "192.168.1.10"
          port: 443
        - ip: "192.168.1.11"
          port: 443
```

### Step 2: Configure Health Checks

```yaml
health_check:
  enabled: true
  interval: 10  # seconds
  timeout: 5    # seconds
  type: tcp     # tcp, http, or https
  
  # For HTTP health checks
  http_path: "/health"
  http_expected_status: 200
```

### Step 3: DNS Configuration

Point your domain to the VIP:

```
; DNS Zone file
www.example.com.    IN    A    10.0.0.100
api.example.com.    IN    A    10.0.0.100
```

Or use a local hosts file for testing:
```
10.0.0.100    www.example.com
10.0.0.100    api.example.com
```

### Step 4: Connect Physical/Cloud Switches

For production use with real OpenFlow switches:

1. **Configure your switch to connect to HYDRA-LB controllers:**
   ```
   # On OpenFlow switch (varies by vendor)
   set openflow controller tcp:172.20.0.10:6653
   set openflow controller tcp:172.20.0.11:6653
   set openflow controller tcp:172.20.0.12:6653
   ```

2. **Update docker-compose.yml to expose ports externally:**
   ```yaml
   controller-1:
     ports:
       - "0.0.0.0:6653:6653"  # Expose to all interfaces
   ```

### Step 5: Session Persistence (Sticky Sessions)

For stateful applications:

```yaml
load_balancer:
  session_persistence:
    enabled: true
    type: source_ip  # or cookie
    timeout: 3600    # seconds
```

---

## 7. Monitoring with Prometheus & Grafana

### Start Monitoring Stack

```bash
./scripts/start_testbed.sh --monitoring
```

### Access Points

| Service | URL | Default Credentials |
|---------|-----|---------------------|
| Prometheus | http://localhost:9090 | None |
| Grafana | http://localhost:3000 | admin / admin |

### Prometheus Metrics Collected

HYDRA-LB exposes these metrics at `/metrics` (port 9100):

```prometheus
# HELP hydra_packet_in_rate Packet-in messages per second per switch
# TYPE hydra_packet_in_rate gauge
hydra_packet_in_rate{controller_id="1", switch_dpid="1"} 125.5

# HELP hydra_flow_count Active flows per switch
# TYPE hydra_flow_count gauge
hydra_flow_count{controller_id="1", switch_dpid="1"} 50

# HELP hydra_controller_load Total packet-in rate for controller
# TYPE hydra_controller_load gauge
hydra_controller_load{controller_id="1"} 450.2

# HELP hydra_load_variance Load variance across switches
# TYPE hydra_load_variance gauge
hydra_load_variance{controller_id="1"} 125.8

# HELP hydra_lb_decisions_total Total load balancer decisions made
# TYPE hydra_lb_decisions_total counter
hydra_lb_decisions_total{controller_id="1", vip="10.0.0.100"} 10542

# HELP hydra_response_time_seconds Response time histogram
# TYPE hydra_response_time_seconds histogram
hydra_response_time_seconds_bucket{le="0.01"} 8500
hydra_response_time_seconds_bucket{le="0.05"} 9800
hydra_response_time_seconds_bucket{le="0.1"} 10200

# HELP hydra_migrations_total Total switch migrations
# TYPE hydra_migrations_total counter
hydra_migrations_total{from_controller="1", to_controller="2"} 5

# HELP hydra_server_connections Active connections per server
# TYPE hydra_server_connections gauge
hydra_server_connections{server="192.168.1.10"} 45
```

### Grafana Dashboards

#### Dashboard 1: Controller Overview

**Panels:**

| Panel | Query | Visualization |
|-------|-------|---------------|
| **Controller Load** | `hydra_controller_load` | Time series (stacked) |
| **Load Variance** | `hydra_load_variance` | Gauge (0-500 range) |
| **Packet-In Rate** | `sum(hydra_packet_in_rate) by (controller_id)` | Time series |
| **Active Switches** | `count(hydra_flow_count) by (controller_id)` | Stat panel |

**Example Queries:**

```promql
# Total system load
sum(hydra_controller_load)

# Load imbalance ratio (max/min)
max(hydra_controller_load) / min(hydra_controller_load)

# Rate of change in load
rate(hydra_packet_in_rate[5m])

# 95th percentile response time
histogram_quantile(0.95, rate(hydra_response_time_seconds_bucket[5m]))
```

#### Dashboard 2: Load Balancer Performance

| Panel | Query | Visualization |
|-------|-------|---------------|
| **Decisions/sec** | `rate(hydra_lb_decisions_total[1m])` | Time series |
| **Server Distribution** | `hydra_server_connections` | Pie chart |
| **Response Time P95** | `histogram_quantile(0.95, ...)` | Time series |
| **Unhealthy Servers** | `hydra_server_health == 0` | Alert list |

#### Dashboard 3: Network Topology

| Panel | Query | Visualization |
|-------|-------|---------------|
| **Switch Flow Counts** | `hydra_flow_count` | Heatmap |
| **Per-Switch Packet Rate** | `hydra_packet_in_rate` | Bar gauge |
| **Migration Events** | `increase(hydra_migrations_total[1h])` | Time series |

### Grafana Alerts

Configure alerts in Grafana:

```yaml
# Alert: High Load Variance
- alert: HighLoadVariance
  expr: hydra_load_variance > 200
  for: 2m
  annotations:
    summary: "Load variance is high ({{ $value }})"
    
# Alert: Controller Overload
- alert: ControllerOverload
  expr: hydra_controller_load > 1000
  for: 1m
  annotations:
    summary: "Controller {{ $labels.controller_id }} is overloaded"
    
# Alert: Server Down
- alert: ServerDown
  expr: hydra_server_health == 0
  for: 30s
  annotations:
    summary: "Server {{ $labels.server }} is unhealthy"
```

### Prometheus Configuration

The Prometheus scrape config (`config/prometheus.yml`):

```yaml
global:
  scrape_interval: 5s
  evaluation_interval: 5s

scrape_configs:
  - job_name: 'hydra-controller-1'
    static_configs:
      - targets: ['172.20.0.10:9100']
    
  - job_name: 'hydra-controller-2'
    static_configs:
      - targets: ['172.20.0.11:9100']

  - job_name: 'hydra-controller-3'
    static_configs:
      - targets: ['172.20.0.12:9100']

# Optional: Recording rules for common calculations
rule_files:
  - 'recording_rules.yml'
```

### Recording Rules (Optional)

Create `config/recording_rules.yml`:

```yaml
groups:
  - name: hydra_aggregations
    rules:
      - record: hydra:total_load
        expr: sum(hydra_controller_load)
        
      - record: hydra:load_imbalance_ratio
        expr: max(hydra_controller_load) / min(hydra_controller_load)
        
      - record: hydra:avg_response_time
        expr: rate(hydra_response_time_seconds_sum[5m]) / rate(hydra_response_time_seconds_count[5m])
```

---

## 8. Configuration Reference

### Main Config: `config/hydra_config.yaml`

```yaml
#################################################
# HYDRA-LB+ Configuration
#################################################

# Controller settings
controller:
  id: 1                      # Unique controller ID (1-3)
  openflow_port: 6653        # OpenFlow listen port
  rest_port: 8080            # REST API port
  stats_interval: 5          # Stats polling interval (seconds)
  
  # Multi-controller coordination
  peers:
    - host: "172.20.0.11"
      port: 6654
    - host: "172.20.0.12"
      port: 6655

# Network topology
topology:
  type: fat_tree             # fat_tree or leaf_spine
  k: 4                       # Fat-tree parameter
  # For leaf_spine:
  # num_leaves: 4
  # num_spines: 2
  # hosts_per_leaf: 4

# Load balancing
load_balancer:
  enabled: true
  strategy: round_robin      # round_robin, least_load, weighted_rr
  
  virtual_ips:
    - vip: "10.0.0.100"
      servers:
        - ip: "10.0.0.1"
        - ip: "10.0.0.2"
        - ip: "10.0.0.3"
        - ip: "10.0.0.4"

# Telemetry collection
telemetry:
  enabled: true
  export_interval: 10        # Export metrics every N seconds
  prometheus_port: 9100      # Prometheus exporter port

# Metrics storage
metrics:
  output_dir: "/app/data/metrics"
  format: csv                # csv or sqlite
  retention_days: 7

# Prediction module (Phase 2)
prediction:
  enabled: false
  model_path: "/app/models/lstm_model.pt"
  lookback_window: 10
  prediction_horizon: 5
  retrain_interval: 3600     # Retrain every hour

# Optimization (Phase 3)
optimization:
  enabled: false
  variance_threshold: 0.5    # Trigger when variance > 50%
  migration_cost_weight: 0.3

# Anomaly detection (Phase 4)
security:
  enabled: false
  entropy_threshold: 0.3
  rate_limit: 1000           # Max packet-in/sec per source
```

---

## 9. Testing & Validation

### Unit Tests

```bash
# Activate virtual environment
cd /home/dev/lb/hydra-lb
source .venv/bin/activate

# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_topology.py -v

# Run with coverage
pytest tests/ --cov=controller --cov=topology --cov=metrics
```

### Integration Tests

```bash
# Start testbed
./scripts/start_testbed.sh

# Run integration tests (inside container)
docker exec hydra-controller-1 python3 -m pytest /app/tests/integration/ -v
```

### Performance Benchmarks

```bash
# Run benchmark suite
docker exec hydra-mininet python3 /app/benchmarks/run_all.py

# Specific benchmarks
docker exec hydra-mininet python3 /app/benchmarks/throughput.py
docker exec hydra-mininet python3 /app/benchmarks/latency.py
docker exec hydra-mininet python3 /app/benchmarks/convergence.py
```

---

## 10. Research Contributions

### Novel Contributions

1. **Unified Framework**: First system to combine prediction, optimization, and security in one SDN load balancer

2. **Cost-Aware Migration**: Migration decisions consider actual overhead, not just load balance

3. **Entropy-Based Filtering**: Pre-filter malicious traffic using information-theoretic measures

4. **Hierarchical Control**: Local fast decisions + global slow optimization for scalability

### Comparison with Existing Work

| Feature | HYDRA-LB+ | LOADS | ODLB | ECMP |
|---------|-----------|-------|------|------|
| Predictive | ✅ LSTM | ❌ | ❌ | ❌ |
| Multi-Controller | ✅ | ✅ | ❌ | N/A |
| Security-Aware | ✅ Entropy | ✅ | ❌ | ❌ |
| Migration Cost | ✅ | ❌ | ❌ | N/A |
| Open Source | ✅ | ❌ | ❌ | N/A |

### Target Venues

- IEEE Transactions on Network and Service Management (TNSM)
- ACM CoNEXT / SIGCOMM
- IEEE INFOCOM
- Elsevier Computer Networks

---

## Appendix A: Troubleshooting

### Common Issues

**Container won't start:**
```bash
# Check logs
docker logs hydra-controller-1

# Verify ports aren't in use
lsof -i :6653
```

**Mininet can't connect to controller:**
```bash
# Verify controller is listening
docker exec hydra-controller-1 netstat -tlnp | grep 6653

# Check OVS connectivity
docker exec hydra-mininet ovs-vsctl show
```

**No metrics in Prometheus:**
```bash
# Check exporter is running
curl http://localhost:9100/metrics

# Verify Prometheus targets
# Go to Prometheus UI → Status → Targets
```

---

## Appendix B: File Reference

| File | Purpose |
|------|---------|
| `docker-compose.yml` | Container orchestration |
| `Dockerfile.ryu` | Controller image |
| `Dockerfile.mininet` | Network emulator image |
| `config/hydra_config.yaml` | Main configuration |
| `config/prometheus.yml` | Prometheus scrape config |
| `controller/ryu_app.py` | Main OpenFlow application |
| `controller/telemetry.py` | Metrics collection |
| `controller/load_balancer.py` | LB base class |
| `controller/baselines/*.py` | Baseline algorithms |
| `topology/fat_tree.py` | Fat-Tree generator |
| `topology/leaf_spine.py` | Leaf-Spine generator |
| `metrics/collector.py` | Central aggregation |
| `metrics/storage.py` | CSV/SQLite storage |
| `scripts/*.sh` | Utility scripts |
| `tests/*.py` | Unit tests |

---

*Document Version: 1.0*  
*Last Updated: January 31, 2026*
