# HYDRA-LB: Hybrid Dynamic Load Balancer for SDN

A research-grade, multi-controller SDN load balancer combining:
- **Multi-Controller Load Balancing** with real-time monitoring
- **Predictive load forecasting** (LSTM/Attention-based) [Planned]
- **Variance-aware optimization** with migration cost modeling [Planned]
- **Entropy-based anomaly detection** for DDoS resilience [Planned]

## 🚀 Quick Start

### Prerequisites
- Docker and Docker Compose
- Python 3.10+

### Run the Guided Demo

```bash
cd hydra-lb
./scripts/demo.sh
```

This interactive script starts all services, runs load balancing tests across all 3 controllers, and guides you through the monitoring dashboard.

### Manual Start

```bash
# Start all services with monitoring
docker compose --profile monitoring up -d

# Verify all services are healthy
docker compose ps

# Stop everything
docker compose --profile monitoring down
```

## 📊 Monitoring Dashboard

| Component | URL | Credentials |
|-----------|-----|-------------|
| **Grafana Dashboard** | http://localhost:3000 | admin / hydra |
| Prometheus | http://localhost:9090 | - |
| Controller 1 API | http://localhost:8080 | - |
| Controller 2 API | http://localhost:8081 | - |
| Controller 3 API | http://localhost:8082 | - |

The dashboard shows real-time metrics from all 3 controllers:
- Packet-In Rate (per controller)
- Connected Switches
- Flow Count
- Total Packets Processed

## 🧪 Testing

### Multi-Controller Load Balancing Test

```bash
docker exec hydra-mininet python3 /app/scripts/multi_controller_test.py
```

This tests that all 3 controllers can independently handle traffic.

### Quick Network Test

```bash
docker exec hydra-mininet mn \
  --controller=remote,ip=172.20.0.10,port=6653 \
  --topo=tree,depth=2,fanout=3 \
  --test=pingall
```

### Interactive Mininet Session

```bash
docker exec -it hydra-mininet bash
mn --controller=remote,ip=172.20.0.10,port=6653 --topo=tree,depth=2,fanout=3
mininet> pingall
mininet> iperf h1 h9
mininet> exit
```

## 📁 Project Structure

```
hydra-lb/
├── controller/              # SDN Controller
│   ├── ryu_app.py          # Main controller with L2 switch + metrics
│   ├── telemetry.py        # Flow statistics collection
│   └── load_balancer.py    # Load balancer algorithms
├── topology/               # Network Topologies
│   ├── fat_tree.py        # Data center fat-tree topology
│   └── leaf_spine.py      # Leaf-spine topology
├── scripts/               # Automation Scripts
│   ├── demo.sh            # Guided demo walkthrough
│   ├── multi_controller_test.py  # Test all 3 controllers
│   ├── start_testbed.sh   # Start services
│   └── stop_testbed.sh    # Stop services
├── config/                # Configuration
│   ├── prometheus.yml     # Prometheus scrape config
│   └── grafana/           # Grafana provisioning (persistent dashboard)
├── metrics/               # Metrics storage
└── data/                  # Output data
```

## 🔧 Configuration

### Controller Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `CONTROLLER_ID` | Controller identifier (1, 2, or 3) | 1 |
| `CONTROLLER_PORT` | OpenFlow port | 6653 |

### Grafana Dashboard

The dashboard is automatically provisioned from `config/grafana/provisioning/`. Changes persist across container restarts.

## 🛣️ Roadmap

### ✅ Phase 1: Core Infrastructure (Complete)
- [x] Docker-based multi-controller setup
- [x] Ryu OpenFlow 1.3 controller with L2 learning switch
- [x] Prometheus metrics endpoint (port 9100)
- [x] Grafana dashboard with auto-provisioning
- [x] Multi-controller load balancing verification
- [x] Network topology support (tree, single, fat-tree)

### 🔲 Phase 2: Prediction Module
- [ ] LSTM-based load forecasting
- [ ] Attention mechanism for time series
- [ ] Historical data collection pipeline
- [ ] Model training infrastructure

### 🔲 Phase 3: Optimization Engine
- [ ] Variance-aware load distribution
- [ ] Migration cost modeling
- [ ] Dynamic switch-to-controller assignment

### 🔲 Phase 4: Security Layer
- [ ] Entropy-based anomaly detection
- [ ] DDoS traffic filtering
- [ ] Suspicious flow quarantine

### 🔲 Phase 5: Evaluation
- [ ] Benchmark suite
- [ ] Comparison with baselines
- [ ] Paper and documentation

## 🐧 Arch Linux Users

See [ARCH_LINUX_GUIDE.md](ARCH_LINUX_GUIDE.md) for compatibility notes and fixes.

## 📄 License

Research use only. See LICENSE file for details.

## 📚 References

- Dynamic Load Balancing in Multi-Controller SDN
- LOADS: Load Optimization and Anomaly Detection Scheme
- PSO-GWO-BP for Cloud Server Load Prediction
- PHAL: Predictive Health-Aware Load Balancing
