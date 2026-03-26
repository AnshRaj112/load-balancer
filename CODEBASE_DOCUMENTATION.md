# HYDRA-LB Codebase Documentation

> **HYDRA-LB** — An LSTM-powered, proactive load balancer for SDN (Software-Defined Networking) using Ryu controllers and Mininet.

---

## Folder Structure

```
load-balancer/
├── controller/                  # SDN controller logic & load balancing
│   ├── __init__.py
│   ├── ryu_app.py               # Main Ryu controller application
│   ├── load_balancer.py          # Abstract base class for LB algorithms
│   ├── optimizer.py              # Proactive load optimization engine
│   ├── predictor.py              # LSTM inference wrapper for the controller
│   ├── telemetry.py              # Telemetry collection & CSV/Prometheus export
│   └── baselines/                # Baseline LB algorithms for comparison
│       ├── __init__.py
│       ├── round_robin.py        # Round Robin & Weighted Round Robin
│       └── least_load.py         # Least Connections, Weighted, Least Response Time
│
├── topology/                     # Network topology generators for Mininet
│   ├── __init__.py
│   ├── fat_tree.py               # Fat-Tree (k-ary) topology generator
│   ├── fat_tree_k4.py            # Pre-generated Fat-Tree k=4 topology script
│   └── leaf_spine.py             # Leaf-Spine topology generator
│
├── prediction/                   # LSTM model, training, and data pipeline
│   ├── __init__.py
│   ├── model.py                  # LSTM-based LoadPredictor model
│   ├── attention.py              # Temporal & multi-head attention mechanisms
│   ├── dataset.py                # PyTorch Dataset + synthetic data generator
│   ├── train.py                  # Training script
│   ├── data_collector.py         # Live telemetry collector for training data
│   ├── config.yaml               # ML model hyperparameters
│   ├── requirements-ml.txt       # ML-specific Python dependencies
│   └── ipynb/                    # Jupyter notebooks for model experimentation
│       ├── model.ipynb
│       └── model_fixed.ipynb
│
├── benchmarks/                   # Experiment runner & analysis framework
│   ├── __init__.py
│   ├── run_experiment.py         # Orchestrates benchmark runs & metric collection
│   ├── workloads.py              # Traffic workload definitions (steady, burst, etc.)
│   ├── run_mininet_workload.py   # Runs a workload inside Mininet via Docker
│   ├── retrain_model.py          # Continuous learning: collect data + retrain
│   ├── analyze_results.py        # Result analysis & publication-quality plotting
│   └── run_all.sh                # Shell script to run all benchmark combinations
│
├── tests/                        # Unit tests (pytest)
│   ├── __init__.py
│   ├── test_load_balancer.py     # Tests for LB algorithms & manager
│   ├── test_telemetry.py         # Tests for telemetry & metrics collection
│   └── test_topology.py          # Tests for topology generators
│
├── config/                       # Configuration files
│   ├── hydra_config.yaml         # Master HYDRA-LB config
│   ├── prometheus.yml            # Prometheus scrape config
│   └── grafana/                  # Grafana dashboard provisioning
│       └── provisioning/
│
├── scripts/                      # Automation shell scripts
│   ├── run_demo.sh               # Interactive demo launcher
│   ├── reproduce.sh              # Full reproducibility pipeline
│   └── collect_results.sh        # Collect logs & metrics from containers
│
├── models/                       # Trained model checkpoints
│   ├── best_model (5).pt
│   └── lstm_predictor.pt
│
├── data/                         # Data directories (metrics, results, training)
│   ├── metrics/                  # Runtime CSV metrics & migration logs
│   ├── results/                  # Benchmark experiment results (JSON + CSV)
│   └── training/                 # Synthetic/collected training data
│
├── docs/                         # Project documentation
│   └── demo_guide.md
│
├── paper/                        # Research paper assets
│   ├── hydra_lb_research_paper.md
│   └── figures/                  # Generated plots and diagrams (PNG)
│
├── docker-compose.yml            # Multi-container orchestration
├── Dockerfile.ryu                # Ryu controller container image
├── Dockerfile.mininet            # Mininet container image
├── requirements.txt              # Python dependencies
├── PLAN.md                       # Project development plan
├── README.md                     # Project README
├── .gitignore
└── HYDRA-LB Project Overview.pdf
```

---

## File-by-File Documentation

---

### `controller/ryu_app.py`

**Purpose:** Main Ryu SDN controller application — the core runtime for HYDRA-LB.

| Class / Function | Description |
|---|---|
| `MetricsHandler` | HTTP request handler exposing `/metrics` (Prometheus format), `/health`, and `POST /migrate` (accepts switch migration requests from peer controllers). |
| `MetricsHandler.do_GET()` | Serves Prometheus metrics or health check JSON. |
| `MetricsHandler.do_POST()` | Receives migration requests; claims MASTER role for the transferred switch. |
| `HydraController` | Main Ryu app: L2 learning switch + monitoring + LSTM prediction + proactive optimization. |
| `HydraController.__init__()` | Initializes metrics counters, predictor, optimizer, metrics HTTP server, and monitoring thread. |
| `HydraController._init_predictor()` | Loads the LSTM model for load prediction (if available). |
| `HydraController._init_optimizer()` | Initializes the `ProactiveOptimizer` with peer addresses and config from env vars. |
| `HydraController._start_metrics_server()` | Spawns a daemon thread running the Prometheus HTTP metrics server on port 9100. |
| `HydraController._start_monitoring_thread()` | Spawns a daemon thread that every 1s: requests stats, calculates rates & load score, updates predictions, runs the optimizer. |
| `HydraController._request_stats()` | Sends OpenFlow port and flow stats requests to all connected datapaths. |
| `HydraController._calculate_rates()` | Computes packet rate, byte rate, average/max latency from counters. |
| `HydraController._calculate_load_score()` | Computes a normalized 0–100 load score (weighted: 50% packet rate, 30% flow count, 20% switch count). |
| `HydraController._update_predictions()` | Feeds current metrics to the LSTM predictor and converts predictions to load scores. |
| `HydraController._run_optimizer()` | Calls the optimizer with local state; if a migration is recommended, executes it. |
| `HydraController._execute_migration()` | Performs physical switch migration via REST POST to the target peer controller + OpenFlow role change. |
| `HydraController._record_migration_event()` | Appends migration events to `migration_log.csv`. |
| `HydraController.get_metrics()` | Builds a Prometheus-format metrics string for all tracked metrics. |
| `HydraController.state_change_handler()` | Event handler: tracks switch connect/disconnect events. |
| `HydraController.set_role()` | Sends OpenFlow Role Request (MASTER/SLAVE) to a switch. |
| `HydraController.switch_features_handler()` | Registers a switch on connection and assigns initial MASTER/SLAVE role via modulo distribution. |
| `HydraController.add_flow()` | Installs a flow entry on a switch. |
| `HydraController._port_stats_reply_handler()` | Processes port stats replies; updates byte and packet totals. |
| `HydraController._flow_stats_reply_handler()` | Processes flow stats replies; updates per-switch flow counts. |
| `HydraController._packet_in_handler()` | Main packet-in handler: learns MACs, installs flows, forwards packets, tracks latency. |

---

### `controller/load_balancer.py`

**Purpose:** Abstract base class for load balancing algorithms and a manager for multiple VIPs.

| Class / Function | Description |
|---|---|
| `Server` | Dataclass representing a backend server (IP, port, weight, connections, health). |
| `LoadBalancerStats` | Dataclass for tracking LB statistics (requests, decisions, server counts). |
| `BaseLoadBalancer` | Abstract base class. Subclasses must implement `select_server()`. |
| `BaseLoadBalancer.__init__()` | Initializes server pool and stats. |
| `BaseLoadBalancer.select_server()` | **Abstract.** Selects a server for an incoming request. |
| `BaseLoadBalancer.get_healthy_servers()` | Returns list of servers where `healthy=True`. |
| `BaseLoadBalancer.mark_server_unhealthy()` | Marks a specific server as unhealthy. |
| `BaseLoadBalancer.mark_server_healthy()` | Marks a specific server as healthy. |
| `BaseLoadBalancer.add_server()` | Adds a new server to the pool. |
| `BaseLoadBalancer.remove_server()` | Removes a server from the pool by IP. |
| `BaseLoadBalancer.get_stats()` | Returns statistics dict with per-server details. |
| `BaseLoadBalancer.record_request()` | Increments request counters and active connections. |
| `BaseLoadBalancer.record_response()` | Decrements active connections for a server. |
| `LoadBalancerManager` | Manages multiple load balancer instances, one per VIP. |
| `LoadBalancerManager.register_vip()` | Creates and registers a LB instance for a virtual IP. |
| `LoadBalancerManager.get_balancer()` | Retrieves the LB instance for a VIP. |
| `LoadBalancerManager.select_server()` | Delegates server selection to the VIP's LB instance. |
| `LoadBalancerManager.get_all_stats()` | Returns stats for all registered VIPs. |

---

### `controller/optimizer.py`

**Purpose:** Proactive, variance-aware load optimizer using LSTM predictions. Core research contribution.

| Class / Function | Description |
|---|---|
| `ControllerState` | Dataclass: snapshot of a controller's current/predicted load, switch count, rates. |
| `MigrationDecision` | Dataclass: a decision to migrate a switch between controllers (from, to, reason, improvement). |
| `ProactiveOptimizer` | Main optimizer class. Collects cluster state, computes predicted variance, triggers migrations. |
| `ProactiveOptimizer.__init__()` | Configures threshold, cooldown, prediction horizon, migration cost weight, and peer addresses. |
| `ProactiveOptimizer.update_local_state()` | Updates the local controller's state snapshot. |
| `ProactiveOptimizer.fetch_peer_states()` | Fetches load state from peer controllers via HTTP `/metrics` endpoints. |
| `ProactiveOptimizer._parse_peer_metrics()` | Parses Prometheus text format to extract peer load, predictions, and switch count. |
| `ProactiveOptimizer.compute_variance()` | Computes load variance across a list of load values. |
| `ProactiveOptimizer.compute_imbalance_ratio()` | Computes max/min load ratio (1.0 = perfectly balanced). |
| `ProactiveOptimizer.optimize()` | **Core loop.** Fetches peers → computes current & predicted variance → triggers migration if predicted variance > threshold. Includes cooldown, marginal improvement, and migration cost checks. |
| `ProactiveOptimizer.get_metrics()` | Returns a dict of optimizer metrics for Prometheus. |
| `ProactiveOptimizer.get_prometheus_metrics()` | Generates Prometheus-format metrics string (variance, migration count, balance status). |

---

### `controller/predictor.py`

**Purpose:** Thread-safe inference wrapper that loads a trained LSTM model and serves predictions to the Ryu controller.

| Class / Function | Description |
|---|---|
| `LoadPredictorInference` | Maintains a sliding window of observations and runs inference on demand. |
| `LoadPredictorInference.__init__()` | Initializes observation buffer, loads model from checkpoint. |
| `LoadPredictorInference._load_model()` | Loads a PyTorch checkpoint, reconstructs the `LoadPredictor` model, sets eval mode. |
| `LoadPredictorInference.add_observation()` | Appends a new [packet_rate, flow_count, byte_rate, switch_count] observation. Pads buffer on first call. |
| `LoadPredictorInference.can_predict()` | Returns `True` if model is loaded and buffer is full (≥ lookback). |
| `LoadPredictorInference.predict()` | Runs inference: normalizes input → tensor → model forward → inverse transform → returns predictions array. |
| `LoadPredictorInference.get_predicted_load()` | Returns predicted load for a specific horizon step (1–5). |
| `LoadPredictorInference.get_all_predictions()` | Returns all predictions as `{t+1: val, t+2: val, ...}` dict. |
| `get_predictor()` | Module-level singleton factory for the global predictor instance. |

---

### `controller/telemetry.py`

**Purpose:** Telemetry collection, aggregation, and export (CSV + optional Prometheus).

| Class / Function | Description |
|---|---|
| `TelemetryCollector` | Collects per-switch and controller-level metrics (packet-in rate, flow count, bytes, LB decisions). |
| `TelemetryCollector.__init__()` | Sets up storage, counters, and initializes CSV files. |
| `TelemetryCollector._init_csv_files()` | Creates timestamped CSV files for switch metrics, controller metrics, and LB decisions. |
| `TelemetryCollector.register_switch()` | Registers a switch DPID for telemetry collection. |
| `TelemetryCollector.unregister_switch()` | Unregisters a switch from collection. |
| `TelemetryCollector.record_packet_in()` | Increments the packet-in counter for a switch. |
| `TelemetryCollector.record_port_stats()` | Records rx/tx byte stats for a switch. |
| `TelemetryCollector.record_flow_stats()` | Records flow count and byte count for a switch. |
| `TelemetryCollector.record_lb_decision()` | Records a load balancer routing decision. |
| `TelemetryCollector._calculate_packet_in_rate()` | Computes packet-in rate and resets counter. |
| `TelemetryCollector.get_switch_metrics()` | Returns latest metrics dict for a specific switch. |
| `TelemetryCollector.get_all_switch_metrics()` | Returns metrics for all registered switches. |
| `TelemetryCollector.get_controller_load()` | Sum of packet-in rates across all switches. |
| `TelemetryCollector.get_load_variance()` | Computes variance, mean, and per-switch loads. |
| `TelemetryCollector.export_metrics()` | Writes current metrics to CSV files. |
| `TelemetryCollector.get_metrics_summary()` | Returns a summary dict of all metrics. |
| `PrometheusExporter` | Optional Prometheus client exporter (uses `prometheus_client` library). |
| `PrometheusExporter.__init__()` | Registers Gauges/Counters and starts the HTTP server. |
| `PrometheusExporter.update_metrics()` | Pushes latest telemetry values to Prometheus. |

---

### `controller/baselines/round_robin.py`

**Purpose:** Round Robin and Weighted Round Robin LB implementations (baselines).

| Class / Function | Description |
|---|---|
| `RoundRobinBalancer` | Cycles through healthy servers sequentially. O(1) per selection. |
| `RoundRobinBalancer.select_server()` | Selects the next server in the rotation, skipping unhealthy ones. |
| `RoundRobinBalancer.reset()` | Resets the rotation index to 0. |
| `WeightedRoundRobinBalancer` | Smooth weighted round robin — servers with higher weights get proportionally more requests. |
| `WeightedRoundRobinBalancer.select_server()` | Selects using the smooth weighted round robin algorithm. |

---

### `controller/baselines/least_load.py`

**Purpose:** Least Connections, Weighted Least Connections, and Least Response Time LB implementations (baselines).

| Class / Function | Description |
|---|---|
| `LeastLoadBalancer` | Routes to the server with the fewest active connections. O(n) per selection. |
| `LeastLoadBalancer.select_server()` | Selects server with minimum `active_connections`. |
| `LeastLoadBalancer.get_connection_counts()` | Returns `{ip: connection_count}` dict. |
| `WeightedLeastConnectionsBalancer` | Selects by `connections / weight` ratio (lower is better). |
| `WeightedLeastConnectionsBalancer.select_server()` | Weighted selection factoring in server capacity. |
| `LeastResponseTimeBalancer` | Routes to the server with the lowest average response time. |
| `LeastResponseTimeBalancer.record_response_time()` | Records a response time sample for a server. |
| `LeastResponseTimeBalancer._get_avg_response_time()` | Computes the running average response time. |
| `LeastResponseTimeBalancer.select_server()` | Selects server with minimum average response time. |
| `LeastResponseTimeBalancer.get_response_time_stats()` | Returns stats (avg, min, max, samples) per server. |

---

### `topology/fat_tree.py`

**Purpose:** Generates a k-ary Fat-Tree data center topology for Mininet.

| Class / Function | Description |
|---|---|
| `FatTreeTopology` | Computes node counts for a k-ary Fat-Tree: core, aggregation, edge switches, and hosts. |
| `FatTreeTopology.__init__()` | Validates `k` (must be even), computes totals. |
| `FatTreeTopology.get_topology_info()` | Returns a topology summary dict. |
| `FatTreeTopology.generate_names()` | Generates switch names, host names, and all link tuples. |
| `FatTreeTopology.generate_mininet_script()` | Generates a complete Mininet Python script string. Optionally writes to file. |
| `create_fat_tree()` | Convenience factory function. |

---

### `topology/fat_tree_k4.py`

**Purpose:** Pre-generated Mininet script for a Fat-Tree k=4 topology (4 core, 8 aggregation, 8 edge switches, 16 hosts, 3 remote controllers).

| Function | Description |
|---|---|
| `create_topology()` | Creates and returns a fully wired Mininet network with 20 switches, 16 hosts, and 3 remote controllers. |
| `run()` | Starts the network, runs `pingAll`, opens CLI, then stops. |

---

### `topology/leaf_spine.py`

**Purpose:** Generates a Leaf-Spine data center topology for Mininet.

| Class / Function | Description |
|---|---|
| `LeafSpineTopology` | Builds a two-tier Leaf-Spine topology with configurable leaf/spine/host counts. |
| `LeafSpineTopology.__init__()` | Computes total switches, hosts, and links. |
| `LeafSpineTopology.get_topology_info()` | Returns topology info dict. |
| `LeafSpineTopology.generate_names()` | Generates spine/leaf switch names, host names, and links. |
| `LeafSpineTopology.generate_mininet_script()` | Generates a complete Mininet Python topology script. |
| `LeafSpineTopology.assign_switches_to_controllers()` | Round-robin assigns switches to N controllers. |
| `create_leaf_spine()` | Convenience factory function. |

---

### `prediction/model.py`

**Purpose:** LSTM-based load prediction model with temporal attention.

| Class / Function | Description |
|---|---|
| `LoadPredictor` | Two-layer LSTM with optional bidirectionality and temporal attention. Architecture: Input [batch, 30, 4] → LSTM1 (bidir, 256 hidden, 2 layers) → Attention → LSTM2 (128 hidden) → Dense → Output [batch, 3]. |
| `LoadPredictor.__init__()` | Builds LSTM layers, attention, dropout, and FC output layers. |
| `LoadPredictor.forward()` | Forward pass. Optionally returns attention weights. |
| `LoadPredictor.predict()` | Inference-mode prediction (eval + no_grad). |
| `LoadPredictorLite` | Lightweight single-layer LSTM without attention for constrained environments. |
| `LoadPredictorLite.forward()` | Simple LSTM → FC forward pass. |
| `create_model()` | Factory function to create a model from a config dict. |

---

### `prediction/attention.py`

**Purpose:** Temporal attention mechanisms for focusing on relevant past timesteps.

| Class / Function | Description |
|---|---|
| `TemporalAttention` | Single-head attention: projects hidden states → tanh energy → softmax scores → weighted context vector. |
| `TemporalAttention.forward()` | Returns `(context, attention_weights)`. |
| `MultiHeadTemporalAttention` | Multi-head self-attention with Q/K/V projections, scaled dot-product, and output projection. |
| `MultiHeadTemporalAttention.forward()` | Returns `(output, attention_weights)` with shape `[batch, num_heads, seq, seq]`. |

---

### `prediction/dataset.py`

**Purpose:** PyTorch Dataset and synthetic data generation for training.

| Class / Function | Description |
|---|---|
| `save_synthetic_data()` | Generates synthetic telemetry CSV with sine/cosine wave patterns + noise (packet_rate, flow_count, byte_rate, switch_count). |
| `LoadDataset` | PyTorch `Dataset` that loads a CSV, clips outliers, scales by 30x (to match inference scaling), and creates sliding window (X, y) pairs. Target is `packet_rate` for the next `horizon` steps. |

---

### `prediction/train.py`

**Purpose:** Training script for the LSTM load predictor.

| Function | Description |
|---|---|
| `train()` | Single training epoch: forward pass, MSE loss, gradient clipping, optimizer step. |
| `main()` | CLI entry point. Parses args, generates synthetic data if needed, creates DataLoader, trains for N epochs, saves checkpoint in the format expected by `predictor.py`. |

---

### `prediction/data_collector.py`

**Purpose:** Collects live telemetry from running controllers via their `/metrics` endpoints.

| Function | Description |
|---|---|
| `parse_prometheus_metrics()` | Parses Prometheus text format into a `{key: value}` dict. |
| `collect_from_controller()` | Fetches and parses metrics from a single controller endpoint. |
| `extract_features()` | Extracts the 4 relevant features (packet_rate, flow_count, byte_rate, switch_count) from raw metrics. |
| `collect_data()` | Main collection loop: polls endpoints at a given interval for a given duration, writes CSV. |
| `main()` | CLI entry point with `--output`, `--duration`, `--interval`, `--controller` args. |

---

### `benchmarks/run_experiment.py`

**Purpose:** Orchestrates benchmark experiments across strategies and workloads.

| Function | Description |
|---|---|
| `query_prometheus()` | Queries Prometheus for a given PromQL expression. |
| `collect_metrics_snapshot()` | Collects a full snapshot of all controller metrics from Prometheus. |
| `compute_experiment_metrics()` | Aggregates snapshots into summary statistics (variance, latency, throughput, migrations). |
| `run_single_experiment()` | Runs one experiment trial: starts workload in Mininet via Docker, collects metrics every 5s, saves raw JSON + summary JSON. |
| `run_experiments()` | Runs multiple trials: restarts cluster with the given strategy, optionally enables continuous learning, saves combined CSV. |
| `main()` | CLI entry point with `--strategy`, `--workload`, `--duration`, `--runs`, `--output`, `--continuous-learning`. |

---

### `benchmarks/workloads.py`

**Purpose:** Defines reproducible traffic patterns for evaluation.

| Class / Function | Description |
|---|---|
| `Workload` | Base class. Provides `_iperf_bg()` and `_ping_flood()` helpers. |
| `SteadyWorkload` | Uniform traffic from all hosts at constant bandwidth — baseline workload. |
| `BurstWorkload` | Alternating high/low bandwidth bursts at configurable intervals — tests reactive response. |
| `FlashCrowdWorkload` | Normal traffic followed by a sudden spike to 1/3 of hosts — tests proactive response. |
| `SkewedWorkload` | 70% heavy traffic to one segment, 30% light to the rest — tests sustained imbalance. |
| `WORKLOADS` | Registry dict mapping workload names to classes. |
| `get_workload()` | Factory function to create a workload by name. |

---

### `benchmarks/analyze_results.py`

**Purpose:** Loads experiment results and generates publication-quality plots + LaTeX tables.

| Function | Description |
|---|---|
| `load_combined_csvs()` | Loads all `*_combined.csv` files from the results directory. |
| `load_summary_jsons()` | Loads all `*_summary.json` files. |
| `aggregate_by_strategy_workload()` | Groups results by (strategy, workload) and computes mean ± std. |
| `plot_variance_comparison()` | Bar chart: load variance across strategies per workload. |
| `plot_latency_comparison()` | Bar chart: response latency across strategies per workload. |
| `plot_throughput_comparison()` | Bar chart: throughput across strategies per workload. |
| `generate_latex_table()` | Generates a LaTeX comparison table for the research paper. |
| `print_summary()` | Prints a human-readable summary to the console. |
| `main()` | CLI entry point with `--input`, `--output`, `--latex`. |

---

### `benchmarks/run_mininet_workload.py`

**Purpose:** Entry point designed to be called inside the Mininet Docker container via `docker exec`.

| Function | Description |
|---|---|
| `main()` | Generates the Fat-Tree topology if needed, creates the Mininet network, runs the specified workload, then tears down. |

---

### `benchmarks/retrain_model.py`

**Purpose:** Convenience pipeline: collect live data → retrain the LSTM model.

| Function | Description |
|---|---|
| `collect_data()` | Invokes `data_collector.py` to collect live telemetry. |
| `retrain()` | Backs up the existing model, invokes `train.py` with collected or synthetic data. |
| `main()` | CLI entry point with `--collect-duration`, `--data`, `--epochs`. |

---

### `tests/test_load_balancer.py`

**Purpose:** Unit tests for all load balancing algorithms and the LB manager.

| Test Class | What It Tests |
|---|---|
| `TestRoundRobinBalancer` | Basic round robin cycling, single server, no healthy servers, unhealthy server skipping, reset, stats. |
| `TestWeightedRoundRobinBalancer` | Weight-based distribution ratio (3:1). |
| `TestLeastLoadBalancer` | Basic selection, preference for less-loaded servers, connection tracking. |
| `TestLeastResponseTimeBalancer` | Response time recording, preference for faster servers. |
| `TestLoadBalancerManager` | VIP registration, server selection through manager, unknown VIP handling, multiple strategies, aggregated stats. |

---

### `tests/test_telemetry.py`

**Purpose:** Unit tests for telemetry collection, metrics collector, and CSV storage.

| Test Class | What It Tests |
|---|---|
| `TestTelemetryCollector` | Switch registration/unregistration, packet-in recording & rate calculation, flow stats, controller load, load variance, CSV export. |
| `TestMetricsCollector` | Controller load recording, variance recording, LB decisions, summary stats, JSON export. |
| `TestCSVStorage` | Writing switch metrics, controller metrics, LB decisions, and migration events to CSV. |

---

### `tests/test_topology.py`

**Purpose:** Unit tests for the Fat-Tree and Leaf-Spine topology generators.

| Test Class | What It Tests |
|---|---|
| `TestFatTreeTopology` | Node counts for k=4 and k=6, odd-k validation, name generation, link counts, Mininet script, topology info. |
| `TestLeafSpineTopology` | Default & custom counts, name generation, leaf-spine link count, controller assignment, Mininet script, topology info. |

---

### Configuration Files

| File | Description |
|---|---|
| `config/hydra_config.yaml` | Master config: controller settings (ID, ports, peers), topology type selection, LB strategy & VIPs, telemetry intervals, metrics storage, suppression/migration/anomaly detection settings (for future phases), logging. |
| `config/prometheus.yml` | Prometheus scrape config targeting 3 controller metrics endpoints (port 9100). |
| `docker-compose.yml` | Multi-container setup: 3 Ryu controllers, 1 Mininet node, Prometheus, Grafana. |
| `Dockerfile.ryu` | Docker image for the Ryu controller. |
| `Dockerfile.mininet` | Docker image for the Mininet node. |
| `requirements.txt` | Python dependencies for the controller runtime. |
| `prediction/requirements-ml.txt` | ML-specific dependencies (PyTorch, pandas, numpy, matplotlib, scikit-learn). |
| `prediction/config.yaml` | ML model hyperparameters (input_size, hidden_size, num_layers, etc.). |

---

### Shell Scripts

| Script | Description |
|---|---|
| `scripts/run_demo.sh` | Launches the full cluster, starts a burst workload, streams migration logs in real-time. |
| `scripts/reproduce.sh` | Full reproducibility: starts cluster → runs all benchmarks → generates paper figures & LaTeX tables. |
| `scripts/collect_results.sh` | Collects metrics, container logs, and stats into a timestamped output directory. |
| `benchmarks/run_all.sh` | Sequentially runs all strategy × workload combinations. |

---

### Data Files

| Directory | Contents |
|---|---|
| `data/metrics/` | Runtime CSV metrics: `controller_metrics_*.csv`, `switch_metrics_*.csv`, `lb_decisions_*.csv`, `migration_log.csv`. |
| `data/results/` | Benchmark outputs: per-strategy per-workload raw JSON snapshots, summary JSONs, and combined CSVs. |
| `data/training/` | `synthetic_telemetry.csv` — 10,000 synthetic training samples. |
| `models/` | Trained PyTorch model checkpoints (`lstm_predictor.pt`, `best_model (5).pt`). |
