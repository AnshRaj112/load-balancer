# HYDRA-LB: Execution Guide

---

## 1. Prerequisites

### Software Requirements

| Software | Purpose | Version |
|---|---|---|
| Docker Desktop | Container runtime | 20.x+ |
| Docker Compose | Multi-container orchestration | v2+ |
| Python | Analysis scripts, model training | 3.10+ |
| Git | Version control | 2.x+ |
| pip | Python package manager | 21+ |

### Hardware Requirements

| Resource | Minimum | Recommended |
|---|---|---|
| CPU | 4 cores | 8 cores |
| RAM | 4 GB | 8 GB |
| Disk | 2 GB | 5 GB |
| Network | Localhost only | — |

### Python Libraries (for analysis / ML training on host)

```bash
pip install torch numpy pandas matplotlib scikit-learn requests prometheus_client
```

---

## 2. Installation

### Step 1: Clone the Repository

```bash
git clone <repo-url>
cd load-balancer
```

### Step 2: Verify Docker

```bash
docker info          # Should show Docker Engine running
docker compose version   # Should show v2.x
```

### Step 3: Build Docker Images

```bash
docker compose build
```

This builds two images:
- **`hydra-ryu`** (from `Dockerfile.ryu`): Ryu controller + PyTorch + project code
- **`hydra-mininet`** (from `Dockerfile.mininet`): Mininet + OVS + project code

**Expected build time**: 5–15 minutes (PyTorch download is large).

---

## 3. Environment Configuration

### Environment Variables (set in `docker-compose.yml` or per-container)

| Variable | Values | Effect |
|---|---|---|
| `CONTROLLER_ID` | `1`, `2`, `3` | Unique controller identity |
| `MODEL_PATH` | `/app/models/lstm_predictor.pt` | Path to LSTM model checkpoint |
| `LB_STRATEGY` | `hydra_proactive`, `round_robin`, `least_load` | Load balancing algorithm |
| `VARIANCE_THRESHOLD` | `30.0` (default), any float | Predicted variance above which migration triggers |
| `MIGRATION_COOLDOWN` | `30` (default), any int | Minimum seconds between migrations |

### Changing Strategy Before Running

Edit `docker-compose.yml`:

```yaml
ryu-controller-1:
  environment:
    - CONTROLLER_ID=1
    - LB_STRATEGY=hydra_proactive    # ← change here
    - MODEL_PATH=/app/models/lstm_predictor.pt
```

Or set via command line:

```bash
LB_STRATEGY=round_robin docker compose up -d
```

---

## 4. Running the System

### Method 1: Quick Demo (Recommended for First Run)

```bash
bash scripts/run_demo.sh
```

This script:
1. Stops any existing containers (`docker compose down`)
2. Starts the full cluster (3 controllers + Mininet)
3. Waits 15 seconds for initialization
4. Injects a "burst" workload for 3 minutes
5. Streams migration logs in real-time

**Expected output**:
```
[1/4] Stopping any existing containers...
[2/4] Starting the HYDRA-LB Cluster (3 Controllers + Mininet + Grafana)...
[3/4] Waiting for Ryu controllers and LSTM models to initialize...
----------------------------------------------------------
The cluster is now online!
Open your browser to the Live Dashboard:
➡️  http://localhost:3000/d/hydra-lb-main/hydra-lb-controller-dashboard
Login: admin / hydra
----------------------------------------------------------
[4/4] Injecting 'Burst' traffic workload into the network to trigger migrations...
```

### Method 2: Manual Start

```bash
# Start all services
docker compose up -d

# Verify all containers are running
docker ps --filter "name=hydra"
```

**Expected output**:
```
CONTAINER ID   IMAGE            STATUS          PORTS                    NAMES
abc123         hydra-ryu        Up 30 seconds   0.0.0.0:6653->6653/tcp   hydra-controller-1
def456         hydra-ryu        Up 30 seconds                            hydra-controller-2
ghi789         hydra-ryu        Up 30 seconds                            hydra-controller-3
jkl012         hydra-mininet    Up 28 seconds                            hydra-mininet
```

### Method 3: With Monitoring Stack (Prometheus + Grafana)

```bash
docker compose --profile monitoring up -d
```

Adds:
- **Prometheus**: `http://localhost:9090` — metrics storage
- **Grafana**: `http://localhost:3000` — dashboards (login: `admin` / `hydra`)

---

## 5. Running the Mininet Topology

Mininet starts automatically with the Docker container. To interact:

```bash
# Access the Mininet CLI
docker exec -it hydra-mininet python3 /app/topology/fat_tree_k4.py
```

Or run a traffic workload:
```bash
# Steady traffic for 60 seconds
docker exec hydra-mininet python3 /app/benchmarks/run_mininet_workload.py --workload steady --duration 60

# Burst traffic for 120 seconds
docker exec hydra-mininet python3 /app/benchmarks/run_mininet_workload.py --workload burst --duration 120

# Flash crowd (spike at t=20s)
docker exec hydra-mininet python3 /app/benchmarks/run_mininet_workload.py --workload flash_crowd --duration 90

# Skewed (70/30 distribution)
docker exec hydra-mininet python3 /app/benchmarks/run_mininet_workload.py --workload skewed --duration 60
```

---

## 6. Running Experiments

### Single Experiment

```bash
python benchmarks/run_experiment.py \
    --strategy hydra_proactive \
    --workload burst \
    --duration 60 \
    --runs 3 \
    --output data/results
```

This:
1. Restarts the cluster with the specified strategy
2. Waits 15s for initialization
3. Runs the workload inside Mininet
4. Collects metrics every 5 seconds from Prometheus
5. Repeats for `--runs` trials
6. Saves combined CSV + per-run JSON to `data/results/`

### Full Benchmark Suite

```bash
bash benchmarks/run_all.sh
```

Runs all combinations:
- Strategies: `round_robin`, `least_load`, `hydra_proactive`
- Workloads: `steady`, `burst`, `flash_crowd`, `skewed`
- 3 runs each = 36 experiment runs

**Expected time**: ~1 hour (each run is 60s + 10s cooldown + 15s restart)

### Analyzing Results

```bash
python benchmarks/analyze_results.py \
    --input data/results/ \
    --output paper/figures/ \
    --latex
```

Generates:
- `variance_comparison.png` — bar chart of load variance
- `latency_comparison.png` — bar chart of latency
- `throughput_comparison.png` — bar chart of throughput
- `comparison_table.tex` — LaTeX table for the paper

---

## 7. Training the LSTM Model

### Train on Google Cluster Traces (Default)

```bash
cd prediction
python train.py --generate-data --epochs 20 --output ../models/lstm_predictor.pt
```

### Train on Live Collected Data

```bash
# Step 1: Collect data while traffic is running
python prediction/data_collector.py --duration 300 --output data/training/

# Step 2: Train
python prediction/train.py --data data/training/telemetry_*.csv --epochs 100
```

### Automated Pipeline

```bash
python benchmarks/retrain_model.py --collect-duration 300 --epochs 100
```

---

## 8. Running Tests

```bash
# Install test dependencies
pip install pytest

# Run all tests
cd load-balancer
python -m pytest tests/ -v

# Run specific test file
python -m pytest tests/test_load_balancer.py -v
python -m pytest tests/test_telemetry.py -v
python -m pytest tests/test_topology.py -v
```

**Expected output**:
```
tests/test_load_balancer.py::TestRoundRobinBalancer::test_round_robin_basic PASSED
tests/test_load_balancer.py::TestRoundRobinBalancer::test_round_robin_single_server PASSED
...
tests/test_topology.py::TestLeafSpineTopology::test_leaf_spine_topology_info PASSED

========================= 33 passed in 2.5s ==========================
```

---

## 9. Verifying the System is Working

### Check 1: Controllers are Connected to Switches

```bash
docker logs hydra-controller-1 2>&1 | grep -i "switch"
```

**Expected**:
```
Switch connected: dpid=1
Switch connected: dpid=4
Switch connected: dpid=7
...
Set MASTER role for switch 1
```

### Check 2: Metrics are Being Collected

```bash
curl http://localhost:9100/metrics 2>/dev/null | head -20
```

**Expected**:
```
# HELP hydra_load_score Current controller load score
# TYPE hydra_load_score gauge
hydra_load_score{controller_id="1"} 42.5
hydra_packet_rate{controller_id="1"} 900.0
...
```

### Check 3: Predictions are Active

```bash
docker logs hydra-controller-1 2>&1 | grep -i "predict"
```

**Expected**:
```
Loaded LSTM model from /app/models/lstm_predictor.pt
Predictions: t+1=35.2 t+2=37.1 t+3=40.5
```

### Check 4: Migrations are Happening

```bash
docker logs hydra-controller-1 2>&1 | grep -i "MIGRAT"
```

**Expected** (during burst/flash_crowd workloads):
```
[PROACTIVE] Predicted variance 625.0 > threshold 30.0
[MIGRATION] Migrating switch 5 from controller 1 to controller 3
[MIGRATION] Switch 5 role changed to SLAVE
```

### Check 5: Health Endpoint

```bash
curl http://localhost:9100/health
```

**Expected**:
```json
{"status": "healthy", "controller_id": 1, "switches": 7, "load_score": 42.5}
```

---

## 10. Stopping the System

```bash
# Stop all containers
docker compose down

# Stop and remove volumes (clean state)
docker compose down -v
```

---

## 11. Common Startup Issues

| Issue | Cause | Fix |
|---|---|---|
| "port 6653 already in use" | Another process using OpenFlow port | `netstat -tlnp | grep 6653` and stop it |
| "OVS failed to connect" | Controllers not ready yet | Increase sleep time before starting Mininet |
| "Model file not found" | Model not trained yet | Run `python prediction/train.py --generate-data` |
| "No module named ryu" | Docker image not built correctly | Rebuild: `docker compose build --no-cache` |
| "Memory allocation error" | k too large for available RAM | Use k=4 (default) or allocate more RAM to Docker |
