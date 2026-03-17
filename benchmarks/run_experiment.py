#!/usr/bin/env python3
"""
HYDRA-LB Benchmark: Experiment Runner

Runs a workload under a given LB strategy and collects metrics
from all controllers via Prometheus. Results are saved to CSV
for later analysis.

Usage:
    python benchmarks/run_experiment.py --strategy hydra_proactive --workload burst --runs 5
    python benchmarks/run_experiment.py --strategy round_robin --workload steady --duration 60
"""

import subprocess
import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    import requests
except ImportError:
    print("ERROR: 'requests' library required. pip install requests")
    sys.exit(1)


# Controller endpoints
CONTROLLERS = [
    {"id": 1, "metrics": "http://172.20.0.10:9100/metrics"},
    {"id": 2, "metrics": "http://172.20.0.11:9100/metrics"},
    {"id": 3, "metrics": "http://172.20.0.12:9100/metrics"},
]

PROMETHEUS_URL = "http://localhost:9090"

STRATEGIES = ['round_robin', 'least_load', 'hydra_proactive']


def query_prometheus(query):
    """Query Prometheus and return the result."""
    try:
        r = requests.get(
            f"{PROMETHEUS_URL}/api/v1/query",
            params={"query": query},
            timeout=5
        )
        if r.status_code == 200:
            data = r.json()
            return data.get("data", {}).get("result", [])
    except Exception as e:
        print(f"  Warning: Prometheus query failed: {e}")
    return []


def collect_metrics_snapshot():
    """Collect a snapshot of all key metrics from Prometheus."""
    snapshot = {
        "timestamp": datetime.now().isoformat(),
        "controllers": {}
    }
    
    metrics_to_collect = [
        ("load_score", "hydra_load_score"),
        ("packet_rate", "hydra_packet_rate"),
        ("byte_rate", "hydra_byte_rate"),
        ("flow_count", "hydra_flow_count"),
        ("switch_count", "hydra_switch_count"),
        ("packet_in_total", "hydra_packet_in_total"),
        ("latency_avg_ms", "hydra_latency_avg_ms"),
        ("latency_max_ms", "hydra_latency_max_ms"),
        ("cpu_seconds", "hydra_cpu_seconds_total"),
        ("memory_mb", "hydra_memory_mb"),
    ]
    
    # Optimizer metrics
    optimizer_metrics = [
        ("variance_current", "hydra_load_variance_current"),
        ("variance_predicted", "hydra_load_variance_predicted"),
        ("migrations_triggered", "hydra_migrations_triggered_total"),
        ("cluster_balanced", "hydra_cluster_balanced"),
        ("optimizer_runs", "hydra_optimizer_runs_total"),
    ]
    
    # Prediction metrics
    prediction_metrics = [
        (f"predicted_t{i+1}", f"hydra_predicted_load_t{i+1}")
        for i in range(5)
    ]
    
    all_metrics = metrics_to_collect + optimizer_metrics + prediction_metrics
    
    for name, prom_name in all_metrics:
        results = query_prometheus(prom_name)
        for r in results:
            cid = r["metric"].get("controller_id", "unknown")
            if cid not in snapshot["controllers"]:
                snapshot["controllers"][cid] = {}
            try:
                snapshot["controllers"][cid][name] = float(r["value"][1])
            except (IndexError, ValueError):
                pass
    
    return snapshot


def compute_experiment_metrics(snapshots):
    """Compute aggregate metrics from a list of snapshots."""
    if not snapshots:
        return {}
    
    # Extract per-controller load scores over time
    load_series = {}  # controller_id -> [load_scores]
    variance_series = []
    latency_series = []
    throughput_series = []
    
    for snap in snapshots:
        loads = []
        for cid, metrics in snap["controllers"].items():
            if cid not in load_series:
                load_series[cid] = []
            load = metrics.get("load_score", 0)
            load_series[cid].append(load)
            loads.append(load)
            
            latency_series.append(metrics.get("latency_avg_ms", 0))
            throughput_series.append(metrics.get("packet_rate", 0))
        
        # Compute variance of loads at this snapshot
        if len(loads) >= 2:
            mean_load = sum(loads) / len(loads)
            variance = sum((l - mean_load) ** 2 for l in loads) / len(loads)
            variance_series.append(variance)
    
    # Compute summary statistics
    def stats(series):
        if not series:
            return {"mean": 0, "std": 0, "min": 0, "max": 0}
        import math
        n = len(series)
        mean = sum(series) / n
        var = sum((x - mean) ** 2 for x in series) / max(n - 1, 1)
        return {
            "mean": round(mean, 4),
            "std": round(math.sqrt(var), 4),
            "min": round(min(series), 4),
            "max": round(max(series), 4),
        }
    
    # Get final migration count
    final_migrations = 0
    if snapshots:
        last = snapshots[-1]
        for cid, metrics in last["controllers"].items():
            final_migrations += metrics.get("migrations_triggered", 0)
    
    return {
        "load_variance": stats(variance_series),
        "latency_ms": stats(latency_series),
        "throughput_pps": stats(throughput_series),
        "total_migrations": final_migrations,
        "num_snapshots": len(snapshots),
        "per_controller_load": {
            cid: stats(scores) for cid, scores in load_series.items()
        },
    }


def run_single_experiment(strategy, workload, duration, run_id, output_dir):
    """Run a single experiment trial."""
    print(f"\n{'='*60}")
    print(f"  Run {run_id}: strategy={strategy}, workload={workload}, duration={duration}s")
    print(f"{'='*60}")
    
    # Collect metrics every 5 seconds during the experiment
    snapshots = []
    sample_interval = 5
    elapsed = 0
    
    # Start the mininet workload container inside Docker
    cmd = [
        "docker", "exec", "-d", "hydra-mininet", "python3", 
        "/app/benchmarks/run_mininet_workload.py", 
        "--workload", workload, "--duration", str(duration)
    ]
    print(f"  Starting workload inside Mininet: {' '.join(cmd)}")
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(10) # Wait for mininet to actually start traffic
    
    print(f"  Collecting metrics every {sample_interval}s...")
    
    while elapsed < duration:
        snap = collect_metrics_snapshot()
        snapshots.append(snap)
        
        # Brief status
        loads = []
        for cid, m in snap["controllers"].items():
            loads.append(m.get("load_score", 0))
        
        if loads:
            mean_l = sum(loads) / len(loads)
            max_l = max(loads)
            print(f"  t={elapsed:3d}s | avg_load={mean_l:.1f} | max_load={max_l:.1f} "
                  f"| controllers={len(loads)}")
        
        time.sleep(sample_interval)
        elapsed += sample_interval
    
    # Final snapshot
    snapshots.append(collect_metrics_snapshot())
    
    # Compute metrics
    results = compute_experiment_metrics(snapshots)
    results["strategy"] = strategy
    results["workload"] = workload
    results["duration"] = duration
    results["run_id"] = run_id
    results["timestamp"] = datetime.now().isoformat()
    
    # Save raw snapshots
    raw_path = os.path.join(output_dir, f"{strategy}_{workload}_run{run_id}_raw.json")
    with open(raw_path, 'w') as f:
        json.dump(snapshots, f, indent=2)
    
    # Save summary
    summary_path = os.path.join(output_dir, f"{strategy}_{workload}_run{run_id}_summary.json")
    with open(summary_path, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n  Results: variance={results['load_variance']['mean']:.2f} ± "
          f"{results['load_variance']['std']:.2f}, "
          f"latency={results['latency_ms']['mean']:.3f}ms, "
          f"migrations={results['total_migrations']}")
    
    return results


def run_experiments(strategy, workload, duration, runs, output_dir, continuous_learning=False):
    """Run multiple trials of an experiment."""
    os.makedirs(output_dir, exist_ok=True)
    
    all_results = []
    
    # Apply strategy to controller containers via environment variable
    print(f"\n  Applying strategy: {strategy} (restarting controllers...)")
    os.environ['LB_STRATEGY'] = strategy
    
    # Restart the controller containers with the new env var
    subprocess.run("docker compose down", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run("docker compose --profile monitoring up -d", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(15) # Wait for controllers to boot
    
    retrain_proc = None
    if continuous_learning:
        total_collection_duration = (duration * runs) + ((runs - 1) * 10) + 10
        print(f"\n  [Continuous Learning] Spawning background data collector & retraining pipeline ({total_collection_duration}s)...")
        python_exe = "/home/dev/projects/.venv/bin/python" if os.path.exists("/home/dev/projects/.venv/bin/python") else sys.executable
        retrain_cmd = [
            python_exe, "benchmarks/retrain_model.py",
            "--collect-duration", str(total_collection_duration),
            "--epochs", "20"
        ]
        # Run retraining pipeline continuously in background
        retrain_proc = subprocess.Popen(retrain_cmd)
        
    for run_id in range(1, runs + 1):
        result = run_single_experiment(strategy, workload, duration, run_id, output_dir)
        all_results.append(result)
        
        if run_id < runs:
            print(f"\n  Cooldown before next run (10s)...")
            time.sleep(10)
    
    # Save combined CSV
    csv_path = os.path.join(output_dir, f"{strategy}_{workload}_combined.csv")
    if all_results:
        with open(csv_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                'run_id', 'strategy', 'workload', 'duration',
                'variance_mean', 'variance_std',
                'latency_mean', 'latency_std',
                'throughput_mean', 'throughput_std',
                'total_migrations'
            ])
            for r in all_results:
                writer.writerow([
                    r['run_id'], r['strategy'], r['workload'], r['duration'],
                    r['load_variance']['mean'], r['load_variance']['std'],
                    r['latency_ms']['mean'], r['latency_ms']['std'],
                    r['throughput_pps']['mean'], r['throughput_pps']['std'],
                    r['total_migrations'],
                ])
    
    print(f"\n{'='*60}")
    print(f"  EXPERIMENT COMPLETE: {runs} runs of {strategy}/{workload}")
    print(f"  Results saved to: {output_dir}")
    print(f"{'='*60}")
    
    if retrain_proc:
        print("\n  [Continuous Learning] Waiting for background model retraining to finish...")
        retrain_proc.wait()
        print("  [Continuous Learning] Retraining complete. New model deployed.")
        
    return all_results


def main():
    parser = argparse.ArgumentParser(description='HYDRA-LB Benchmark Runner')
    parser.add_argument('--strategy', type=str, required=True,
                        choices=STRATEGIES,
                        help='Load balancing strategy to test')
    parser.add_argument('--workload', type=str, required=True,
                        choices=['steady', 'burst', 'flash_crowd', 'skewed'],
                        help='Traffic workload pattern')
    parser.add_argument('--duration', type=int, default=60,
                        help='Duration per run in seconds (default: 60)')
    parser.add_argument('--runs', type=int, default=3,
                        help='Number of repeated trials (default: 3)')
    parser.add_argument('--output', type=str, default='data/results',
                        help='Output directory (default: data/results)')
    parser.add_argument('--continuous-learning', action='store_true', default=False,
                        help='Automatically train model on live metrics collected during the experiment')
    
    args = parser.parse_args()
    
    print(f"\nHYDRA-LB Benchmark Runner")
    print(f"  Strategy: {args.strategy}")
    print(f"  Workload: {args.workload}")
    print(f"  Duration: {args.duration}s × {args.runs} runs")
    print(f"  Output:   {args.output}")
    print(f"  Cont. L.: {args.continuous_learning}")
    
    run_experiments(
        strategy=args.strategy,
        workload=args.workload,
        duration=args.duration,
        runs=args.runs,
        output_dir=args.output,
        continuous_learning=args.continuous_learning,
    )


if __name__ == '__main__':
    main()
