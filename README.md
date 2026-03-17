# HYDRA-LB: Proactive Control-Plane Load Balancer for Distributed SDNs

A predictive load balancing system for Software-Defined Networks that uses an **Attention-Enhanced Bidirectional LSTM** to forecast controller load and proactively migrate OpenFlow switches before saturation occurs.

## Key Features

- **LSTM Prediction Engine** — Bi-LSTM with Temporal Attention forecasts controller load 5 seconds ahead using real-time telemetry (packet rate, flow count, byte rate, switch count)
- **Proactive Optimizer** — Cost-benefit heuristic evaluates migration trade-offs and triggers preemptive switch-to-controller reassignments
- **Physical OpenFlow Migrations** — Executes actual `OFPT_ROLE_REQUEST` commands to transfer switch ownership between controllers
- **Real-Time Monitoring** — Prometheus + Grafana dashboard visualizing load scores, predictions, cluster variance, and migration events
- **Benchmark Framework** — Automated evaluation across 4 traffic patterns (Steady, Burst, Flash Crowd, Skewed) comparing HYDRA-LB vs Round Robin vs Least Load

## Architecture

```
┌─────────────────────────────────────────────┐
│               Data Plane (Mininet)           │
│    s1──s2──s3──s4──s5──s6──s7   (OVS)       │
└──────────┬──────────┬──────────┬────────────┘
           │          │          │
    ┌──────┴──┐ ┌─────┴───┐ ┌───┴──────┐
    │  Ryu C1 │ │  Ryu C2 │ │  Ryu C3  │
    │ LSTM +  │ │ LSTM +  │ │ LSTM +   │
    │Optimizer│ │Optimizer│ │Optimizer │
    └────┬────┘ └────┬────┘ └────┬─────┘
         │  HTTP Peer Exchange   │
         └───────────┬───────────┘
                     │
          ┌──────────┴──────────┐
          │ Prometheus + Grafana│
          └─────────────────────┘
```

## Project Structure

```
load-balancer/
├── controller/             # Ryu SDN controller application
│   ├── ryu_app.py          # Main controller with monitoring + prediction
│   ├── optimizer.py        # Proactive variance-aware optimizer
│   ├── predictor.py        # LSTM inference wrapper
│   └── baselines/          # Round Robin & Least Load strategies
├── prediction/             # PyTorch ML pipeline
│   ├── model.py            # Bi-LSTM + Temporal Attention architecture
│   ├── attention.py        # Temporal attention mechanism
│   ├── train.py            # Model training script
│   ├── dataset.py          # Telemetry dataset & synthetic data generator
│   └── data_collector.py   # Live metric collection for training
├── benchmarks/             # Evaluation framework
│   ├── run_experiment.py   # Automated experiment runner
│   ├── workloads.py        # Traffic pattern generators
│   ├── analyze_results.py  # Results analysis & plot generation
│   └── retrain_model.py    # Convenience script for retraining
├── topology/               # Mininet network topology
├── models/                 # Pre-trained model checkpoints (.pt)
├── config/                 # Prometheus, Grafana provisioning
├── paper/                  # Research paper (Markdown + figures)
├── data/                   # Collected metrics & experiment results
├── docker-compose.yml      # Full stack deployment
├── Dockerfile.ryu          # Controller container
└── Dockerfile.mininet      # Data plane container
```

## Quick Start

### Prerequisites

- Docker & Docker Compose
- Python 3.8+ with PyTorch (for local training/inference)

### 1. Start the Full Stack

```bash
# Start controllers + Mininet + monitoring
docker compose --profile monitoring up -d

# Verify all containers are running
docker ps
```

### 2. Run a Benchmark

```bash
# Run HYDRA-LB under burst traffic (30s, 1 run)
python3 benchmarks/run_experiment.py \
    --strategy hydra_proactive \
    --workload burst \
    --duration 30 \
    --runs 1

# Compare against baselines
python3 benchmarks/run_experiment.py --strategy round_robin --workload burst --duration 30 --runs 1
python3 benchmarks/run_experiment.py --strategy least_load --workload burst --duration 30 --runs 1
```

### 3. Analyze Results

```bash
python3 benchmarks/analyze_results.py \
    --input data/results \
    --output paper/figures
```

### 4. View the Dashboard

Open [http://localhost:3000](http://localhost:3000) (Grafana, password: `hydra`)

## LSTM Model

| Parameter | Value |
|-----------|-------|
| Architecture | Bidirectional LSTM + Temporal Attention |
| Input | 4 features × 30 timestep lookback |
| Output | 5-step prediction horizon (t+1 to t+5) |
| Hidden Size | 256 (BiLSTM) → 128 (Refinement LSTM) |
| Attention | Learned temporal attention (size 64) |
| Parameters | ~1.8M |

## Key Results

Under **Burst** traffic, HYDRA-LB reduces cluster load variance by **97.7%** compared to Round Robin and Least Load, using only 1 targeted migration vs 6 reactive ones.

| Strategy | Variance (σ²) | Migrations |
|----------|:-------------:|:----------:|
| Round Robin | 772.00 | 0 |
| Least Load | 766.74 | 6 |
| **HYDRA-LB** | **18.07** | **1** |

## License

This project is part of academic research. See the [research paper](paper/hydra_lb_research_paper.md) for full details.
