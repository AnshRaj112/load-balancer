# HYDRA-LB: Benchmarking Document

---

## 1. Overview

The benchmarking framework allows reproducible comparison of load balancing strategies under controlled traffic conditions. It consists of:

| File | Purpose |
|---|---|
| `benchmarks/workloads.py` | Traffic pattern definitions (4 workloads) |
| `benchmarks/run_experiment.py` | Experiment orchestrator |
| `benchmarks/run_mininet_workload.py` | Mininet-side workload executor |
| `benchmarks/analyze_results.py` | Results analysis & visualization |
| `benchmarks/retrain_model.py` | Continuous learning pipeline |
| `benchmarks/run_all.sh` | Full suite runner |

---

## 2. Workload Definitions

### 2.1 Base Class

All workloads inherit from `Workload`:

```python
class Workload:
    def __init__(self, duration=60, seed=42):
        self.duration = duration
        random.seed(seed)        # Reproducible randomness

    def generate(self, net):     # Override in subclasses
        raise NotImplementedError

    def _iperf_bg(self, net, src, dst, bw="5M", duration=10, port=5001):
        """Run iperf in background between two hosts."""
        dst_host.cmd(f'iperf -s -p {port} &')   # Start server
        src_host.cmd(f'iperf -c {dst_ip} -p {port} -b {bw} -t {duration} &')
```

### 2.2 Workload Types

#### Steady (Baseline)

```
Traffic: Uniform, constant bandwidth from all hosts
Pattern: ─────────────────────────────────
Purpose: Baseline for comparison. All strategies should perform similarly.
```

```python
class SteadyWorkload(Workload):
    def generate(self, net):
        # Each host sends 5Mbps to its neighbor
        for i in range(n):
            self._iperf_bg(net, hosts[i], hosts[(i+1)%n], bw="5M", duration=self.duration)
        time.sleep(self.duration)
```

#### Burst (Alternating High/Low)

```
Traffic: Alternating high (20M) and low (1M) phases every 10 seconds
Pattern: ▃▃▃▃▃▃▃▃████████▃▃▃▃▃▃▃▃████████▃▃▃▃▃▃▃▃
Purpose: Tests reactive vs proactive response. Proactive should anticipate the burst.
```

```python
class BurstWorkload(Workload):
    def generate(self, net):
        while elapsed < self.duration:
            bw = "20M" if burst_high else "1M"
            for h in hosts: h.cmd('killall iperf')      # Kill previous
            for i in range(n):
                self._iperf_bg(net, hosts[i], hosts[(i+1)%n], bw=bw)
            time.sleep(self.burst_interval)               # 10 seconds
            burst_high = not burst_high
```

#### Flash Crowd (Spike to Segment)

```
Traffic: Normal 2M for 20s, then sudden 30M spike to 1/3 of hosts
Pattern: ──────────▃▃▃▃▃██████████████▃▃▃────────
Purpose: Tests proactive response. HYDRA-LB should predict the spike and pre-migrate.
```

```python
class FlashCrowdWorkload(Workload):
    def generate(self, net):
        # Phase 1: Normal traffic everywhere
        for i in range(n):
            self._iperf_bg(net, hosts[i], hosts[(i+1)%n], bw="2M")
        time.sleep(self.spike_start)    # Wait 20s

        # Phase 2: Spike on first 1/3 of hosts
        target_hosts = hosts[:max(1, n // 3)]
        for h in target_hosts:
            self._iperf_bg(net, h, dst, bw="30M", duration=self.spike_duration)
```

#### Skewed (Sustained Imbalance)

```
Traffic: 70% heavy (15M) to segment 1, 30% light (3M) to rest
Pattern: Segment 1: ██████████████████
         Segment 2: ▃▃▃▃▃▃▃▃▃▃▃▃▃▃▃▃
Purpose: Tests sustained imbalance handling. HYDRA-LB should redistribute.
```

```python
class SkewedWorkload(Workload):
    def generate(self, net):
        heavy_count = max(1, n // 3)
        for i in range(n):
            bw = "15M" if i < heavy_count else "3M"
            self._iperf_bg(net, hosts[i], hosts[(i+1)%n], bw=bw)
```

### 2.3 Factory

```python
WORKLOADS = {
    'steady': SteadyWorkload,
    'burst': BurstWorkload,
    'flash_crowd': FlashCrowdWorkload,
    'skewed': SkewedWorkload,
}

get_workload('burst', duration=120)  # → BurstWorkload(duration=120)
```

---

## 3. Experiment Pipeline

### 3.1 `run_experiment.py` — End-to-End Flow

```
Step 1: Set LB_STRATEGY environment variable
Step 2: docker compose down + docker compose up -d
Step 3: Wait 15s for controllers to boot
Step 4: docker exec hydra-mininet → start workload
Step 5: Wait 10s for traffic to begin
Step 6: Collect Prometheus metrics every 5s for duration
Step 7: Compute aggregate statistics
Step 8: Save raw snapshots (JSON) + summary (JSON) + combined (CSV)
Step 9: Repeat for --runs trials
```

### 3.2 Metrics Collected

Each 5-second snapshot collects:

| Metric | Source | Description |
|---|---|---|
| `load_score` | `hydra_load_score` | Composite load (0–100) |
| `packet_rate` | `hydra_packet_rate` | Packets/sec |
| `byte_rate` | `hydra_byte_rate` | Bytes/sec |
| `flow_count` | `hydra_flow_count` | Installed flows |
| `switch_count` | `hydra_switch_count` | Managed switches |
| `packet_in_total` | `hydra_packet_in_total` | Cumulative PacketIn |
| `latency_avg_ms` | `hydra_latency_avg_ms` | Average processing latency |
| `latency_max_ms` | `hydra_latency_max_ms` | Maximum latency |
| `cpu_seconds` | `hydra_cpu_seconds_total` | CPU time consumed |
| `memory_mb` | `hydra_memory_mb` | Memory usage |
| `variance_current` | `hydra_load_variance_current` | Current load variance |
| `variance_predicted` | `hydra_load_variance_predicted` | Predicted variance |
| `migrations_triggered` | `hydra_migrations_triggered_total` | Migration count |
| `cluster_balanced` | `hydra_cluster_balanced` | Balance status (0/1) |
| `predicted_t1`–`t5` | `hydra_predicted_load_t*` | LSTM predictions |

### 3.3 Aggregate Statistics

```python
def compute_experiment_metrics(snapshots):
    # Per-controller load over time
    load_series = {cid: [load_scores...]}

    # Variance across controllers at each snapshot
    variance_series = [compute_variance(loads_at_t) for t in snapshots]

    # Summary stats: mean, std, min, max
    return {
        "load_variance": stats(variance_series),
        "latency_ms": stats(latency_series),
        "throughput_pps": stats(throughput_series),
        "total_migrations": final_migration_count,
    }
```

---

## 4. Result Storage

### Directory Structure

```
data/results/
├── hydra_proactive_burst_run1_raw.json      # All snapshots (raw data)
├── hydra_proactive_burst_run1_summary.json   # Computed aggregate stats
├── hydra_proactive_burst_run2_raw.json
├── hydra_proactive_burst_run2_summary.json
├── hydra_proactive_burst_combined.csv        # All runs in one CSV
├── round_robin_burst_combined.csv
└── least_load_burst_combined.csv
```

### Combined CSV Format

```csv
run_id,strategy,workload,duration,variance_mean,variance_std,latency_mean,latency_std,throughput_mean,throughput_std,total_migrations
1,hydra_proactive,burst,60,12.34,5.67,2.345,0.891,1500.0,200.0,3
2,hydra_proactive,burst,60,11.89,4.23,2.178,0.756,1520.0,180.0,2
3,hydra_proactive,burst,60,13.01,6.12,2.456,0.934,1480.0,210.0,3
```

---

## 5. Analysis Scripts

### `analyze_results.py`

#### Plots Generated

1. **`variance_comparison.png`**: Grouped bar chart showing load variance for each (strategy, workload) combination. Lower is better for HYDRA-LB.

2. **`latency_comparison.png`**: Grouped bar chart showing average response latency. Lower is better.

3. **`throughput_comparison.png`**: Grouped bar chart showing throughput. Higher is better.

All plots use publication-quality settings:
```python
plt.rcParams.update({
    'font.size': 12, 'font.family': 'serif',
    'figure.figsize': (8, 5), 'savefig.dpi': 300,
})
```

#### LaTeX Table

```bash
python benchmarks/analyze_results.py --input data/results/ --output paper/figures/ --latex
```

Generates `comparison_table.tex`:
```latex
\begin{table}[htbp]
\centering
\caption{Performance Comparison of Load Balancing Strategies}
\begin{tabular}{llccc}
\toprule
Workload & Strategy & Variance ($\sigma^2$) & Latency (ms) & Migrations \\
\midrule
Burst & Round Robin & $25.30 \pm 4.50$ & $3.456 \pm 1.230$ & $0$ \\
Burst & Least Load & $18.20 \pm 3.10$ & $2.890 \pm 0.780$ & $0$ \\
Burst & HYDRA-LB (Ours) & $12.34 \pm 5.67$ & $2.345 \pm 0.891$ & $3$ \\
\bottomrule
\end{tabular}
\end{table}
```

---

## 6. How to Reproduce Results

### Step-by-Step

```bash
# 1. Start the cluster
docker compose --profile monitoring up -d
sleep 20

# 2. Run all benchmarks
bash benchmarks/run_all.sh

# 3. Generate figures
python benchmarks/analyze_results.py --input data/results/ --output paper/figures/ --latex

# 4. View results
ls paper/figures/
# → variance_comparison.png, latency_comparison.png, throughput_comparison.png, comparison_table.tex
```

### One-Command Reproducibility

```bash
bash scripts/reproduce.sh
```

This script handles Steps 1–3 automatically.

---

## 7. Fair Comparison Methods

### Controlled Variables

| Factor | How It's Controlled |
|---|---|
| **Topology** | Same Fat-Tree k=4 for all experiments |
| **Traffic** | Same workload definitions, same random seed (42) |
| **Controller count** | Always 3 controllers |
| **Duration** | Configurable, same across strategies |
| **Warm-up** | 15s wait for controller initialization |
| **Traffic start delay** | 10s wait after workload command, before metric collection |
| **Metric collection** | Every 5s from Prometheus (same for all) |
| **Repetitions** | Default 3 runs per configuration |

### What Varies Between Strategies

| Strategy | Prediction | Migration | Controller Coordination |
|---|---|---|---|
| Round Robin | ✗ | ✗ | ✗ |
| Least Load | ✗ | ✗ | ✗ |
| HYDRA-LB | ✓ (LSTM) | ✓ (Proactive) | ✓ (REST) |

### Statistical Significance

The framework computes:
- **Mean ± Standard Deviation** across runs
- Error bars in plots represent ±1σ
- Minimum 3 runs recommended; 5+ for publication

**Limitation**: No formal hypothesis testing (t-test, ANOVA) is implemented. This would strengthen the paper.
