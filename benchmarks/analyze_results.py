#!/usr/bin/env python3
"""
HYDRA-LB Benchmark: Results Analysis & Visualization

Loads experiment results and generates publication-quality plots
and statistical comparisons for the research paper.

Usage:
    python benchmarks/analyze_results.py --input data/results/ --output paper/figures/
    python benchmarks/analyze_results.py --input data/results/ --latex
"""

import argparse
import csv
import json
import math
import os
import sys
from pathlib import Path

try:
    import matplotlib
    matplotlib.use('Agg')  # Non-interactive backend
    import matplotlib.pyplot as plt
    import matplotlib.ticker as mticker
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    print("Warning: matplotlib not available, skipping plots")

# Publication style
if MATPLOTLIB_AVAILABLE:
    plt.rcParams.update({
        'font.size': 12,
        'font.family': 'serif',
        'axes.labelsize': 13,
        'axes.titlesize': 14,
        'legend.fontsize': 11,
        'xtick.labelsize': 11,
        'ytick.labelsize': 11,
        'figure.figsize': (8, 5),
        'figure.dpi': 150,
        'savefig.dpi': 300,
    })

# Strategy display names and colors
STRATEGY_LABELS = {
    'round_robin': 'Round Robin',
    'least_load': 'Least Load',
    'hydra_proactive': 'HYDRA-LB (Ours)',
}

STRATEGY_COLORS = {
    'round_robin': '#e74c3c',
    'least_load': '#f39c12',
    'hydra_proactive': '#2ecc71',
}


def load_combined_csvs(input_dir):
    """Load all *_combined.csv files from the results directory."""
    results = []
    input_path = Path(input_dir)
    
    for csv_file in sorted(input_path.glob("*_combined.csv")):
        with open(csv_file) as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Convert numeric fields
                for key in ['run_id', 'duration']:
                    if key in row:
                        row[key] = int(row[key])
                for key in ['variance_mean', 'variance_std', 'latency_mean', 
                            'latency_std', 'throughput_mean', 'throughput_std',
                            'total_migrations']:
                    if key in row:
                        row[key] = float(row[key])
                results.append(row)
    
    return results


def load_summary_jsons(input_dir):
    """Load all *_summary.json files."""
    results = []
    input_path = Path(input_dir)
    
    for json_file in sorted(input_path.glob("*_summary.json")):
        with open(json_file) as f:
            results.append(json.load(f))
    
    return results


def aggregate_by_strategy_workload(results):
    """Aggregate results by (strategy, workload) pair."""
    agg = {}
    
    for r in results:
        key = (r['strategy'], r['workload'])
        if key not in agg:
            agg[key] = {
                'strategy': r['strategy'],
                'workload': r['workload'],
                'variance_means': [],
                'latency_means': [],
                'throughput_means': [],
                'migrations': [],
            }
        
        agg[key]['variance_means'].append(r.get('variance_mean', 0))
        agg[key]['latency_means'].append(r.get('latency_mean', 0))
        agg[key]['throughput_means'].append(r.get('throughput_mean', 0))
        agg[key]['migrations'].append(r.get('total_migrations', 0))
    
    # Compute mean ± std for each group
    for key, d in agg.items():
        for metric in ['variance_means', 'latency_means', 'throughput_means', 'migrations']:
            values = d[metric]
            n = len(values)
            mean = sum(values) / max(n, 1)
            var = sum((v - mean) ** 2 for v in values) / max(n - 1, 1) if n > 1 else 0
            std = math.sqrt(var)
            base = metric.replace('_means', '').replace('s', '')
            d[f'{base}_mean'] = round(mean, 4)
            d[f'{base}_std'] = round(std, 4)
    
    return agg


def plot_variance_comparison(agg, workloads, output_dir):
    """Bar chart: Load variance comparison across strategies."""
    if not MATPLOTLIB_AVAILABLE:
        return
    
    fig, ax = plt.subplots(figsize=(10, 6))
    
    x = range(len(workloads))
    width = 0.25
    strategies = ['round_robin', 'least_load', 'hydra_proactive']
    
    for i, strat in enumerate(strategies):
        means = []
        stds = []
        for wl in workloads:
            key = (strat, wl)
            if key in agg:
                means.append(agg[key].get('variance_mean_mean', agg[key].get('variance_mean', 0)))
                stds.append(agg[key].get('variance_mean_std', agg[key].get('variance_std', 0)))
            else:
                means.append(0)
                stds.append(0)
        
        offset = (i - 1) * width
        bars = ax.bar(
            [xi + offset for xi in x], means, width,
            yerr=stds, capsize=4,
            label=STRATEGY_LABELS.get(strat, strat),
            color=STRATEGY_COLORS.get(strat, '#999'),
            alpha=0.85, edgecolor='white', linewidth=0.5
        )
    
    ax.set_xlabel('Workload Pattern')
    ax.set_ylabel('Load Variance (σ²)')
    ax.set_title('Load Variance Comparison Across Strategies')
    ax.set_xticks(x)
    ax.set_xticklabels([w.replace('_', ' ').title() for w in workloads])
    ax.legend(framealpha=0.9)
    ax.grid(axis='y', alpha=0.3)
    ax.set_axisbelow(True)
    
    path = os.path.join(output_dir, 'variance_comparison.png')
    plt.savefig(path)
    plt.close()
    print(f"  Saved: {path}")


def plot_latency_comparison(agg, workloads, output_dir):
    """Bar chart: Latency comparison across strategies."""
    if not MATPLOTLIB_AVAILABLE:
        return
    
    fig, ax = plt.subplots(figsize=(10, 6))
    
    x = range(len(workloads))
    width = 0.25
    strategies = ['round_robin', 'least_load', 'hydra_proactive']
    
    for i, strat in enumerate(strategies):
        means = []
        stds = []
        for wl in workloads:
            key = (strat, wl)
            if key in agg:
                means.append(agg[key].get('latency_mean_mean', agg[key].get('latency_mean', 0)))
                stds.append(agg[key].get('latency_mean_std', agg[key].get('latency_std', 0)))
            else:
                means.append(0)
                stds.append(0)
        
        offset = (i - 1) * width
        ax.bar(
            [xi + offset for xi in x], means, width,
            yerr=stds, capsize=4,
            label=STRATEGY_LABELS.get(strat, strat),
            color=STRATEGY_COLORS.get(strat, '#999'),
            alpha=0.85, edgecolor='white', linewidth=0.5
        )
    
    ax.set_xlabel('Workload Pattern')
    ax.set_ylabel('Average Latency (ms)')
    ax.set_title('Response Latency Comparison')
    ax.set_xticks(x)
    ax.set_xticklabels([w.replace('_', ' ').title() for w in workloads])
    ax.legend(framealpha=0.9)
    ax.grid(axis='y', alpha=0.3)
    ax.set_axisbelow(True)
    
    path = os.path.join(output_dir, 'latency_comparison.png')
    plt.savefig(path)
    plt.close()
    print(f"  Saved: {path}")


def plot_throughput_comparison(agg, workloads, output_dir):
    """Bar chart: Throughput comparison."""
    if not MATPLOTLIB_AVAILABLE:
        return
    
    fig, ax = plt.subplots(figsize=(10, 6))
    
    x = range(len(workloads))
    width = 0.25
    strategies = ['round_robin', 'least_load', 'hydra_proactive']
    
    for i, strat in enumerate(strategies):
        means = []
        stds = []
        for wl in workloads:
            key = (strat, wl)
            if key in agg:
                means.append(agg[key].get('throughput_mean_mean', agg[key].get('throughput_mean', 0)))
                stds.append(agg[key].get('throughput_mean_std', agg[key].get('throughput_std', 0)))
            else:
                means.append(0)
                stds.append(0)
        
        offset = (i - 1) * width
        ax.bar(
            [xi + offset for xi in x], means, width,
            yerr=stds, capsize=4,
            label=STRATEGY_LABELS.get(strat, strat),
            color=STRATEGY_COLORS.get(strat, '#999'),
            alpha=0.85, edgecolor='white', linewidth=0.5
        )
    
    ax.set_xlabel('Workload Pattern')
    ax.set_ylabel('Throughput (packets/sec)')
    ax.set_title('Throughput Comparison')
    ax.set_xticks(x)
    ax.set_xticklabels([w.replace('_', ' ').title() for w in workloads])
    ax.legend(framealpha=0.9)
    ax.grid(axis='y', alpha=0.3)
    ax.set_axisbelow(True)
    
    path = os.path.join(output_dir, 'throughput_comparison.png')
    plt.savefig(path)
    plt.close()
    print(f"  Saved: {path}")


def generate_latex_table(agg, workloads, output_dir):
    """Generate a LaTeX-ready comparison table."""
    strategies = ['round_robin', 'least_load', 'hydra_proactive']
    
    lines = []
    lines.append(r"\begin{table}[htbp]")
    lines.append(r"\centering")
    lines.append(r"\caption{Performance Comparison of Load Balancing Strategies}")
    lines.append(r"\label{tab:comparison}")
    lines.append(r"\begin{tabular}{llccc}")
    lines.append(r"\toprule")
    lines.append(r"Workload & Strategy & Variance ($\sigma^2$) & Latency (ms) & Migrations \\")
    lines.append(r"\midrule")
    
    for wl in workloads:
        first = True
        for strat in strategies:
            key = (strat, wl)
            if key in agg:
                d = agg[key]
                wl_label = wl.replace('_', ' ').title() if first else ""
                strat_label = STRATEGY_LABELS.get(strat, strat)
                
                var_str = f"${d.get('variance_mean', 0):.2f} \\pm {d.get('variance_std', 0):.2f}$"
                lat_str = f"${d.get('latency_mean', 0):.3f} \\pm {d.get('latency_std', 0):.3f}$"
                mig_str = f"${d.get('migration_mean', 0):.0f}$"
                
                lines.append(f"{wl_label} & {strat_label} & {var_str} & {lat_str} & {mig_str} \\\\")
                first = False
        lines.append(r"\midrule")
    
    lines[-1] = r"\bottomrule"
    lines.append(r"\end{tabular}")
    lines.append(r"\end{table}")
    
    table_str = '\n'.join(lines)
    
    path = os.path.join(output_dir, 'comparison_table.tex')
    with open(path, 'w') as f:
        f.write(table_str)
    
    print(f"  Saved LaTeX table: {path}")
    print(table_str)


def print_summary(agg, workloads):
    """Print a human-readable summary."""
    strategies = ['round_robin', 'least_load', 'hydra_proactive']
    
    print(f"\n{'='*70}")
    print(f"  BENCHMARK RESULTS SUMMARY")
    print(f"{'='*70}")
    
    for wl in workloads:
        print(f"\n  Workload: {wl}")
        print(f"  {'Strategy':<20} {'Variance':>12} {'Latency (ms)':>15} {'Migrations':>12}")
        print(f"  {'-'*60}")
        
        for strat in strategies:
            key = (strat, wl)
            if key in agg:
                d = agg[key]
                var_m = d.get('variance_mean_mean', d.get('variance_mean', 0))
                var_s = d.get('variance_mean_std', d.get('variance_std', 0))
                lat_m = d.get('latency_mean_mean', d.get('latency_mean', 0))
                lat_s = d.get('latency_mean_std', d.get('latency_std', 0))
                mig = d.get('migration_mean', 0)
                
                label = STRATEGY_LABELS.get(strat, strat)
                print(f"  {label:<20} {var_m:>6.2f}±{var_s:<5.2f} "
                      f"{lat_m:>7.3f}±{lat_s:<7.3f} {mig:>8.0f}")


def main():
    parser = argparse.ArgumentParser(description='HYDRA-LB Benchmark Analysis')
    parser.add_argument('--input', type=str, default='data/results',
                        help='Directory containing experiment results')
    parser.add_argument('--output', type=str, default='paper/figures',
                        help='Directory to save figures')
    parser.add_argument('--latex', action='store_true',
                        help='Generate LaTeX table')
    
    args = parser.parse_args()
    os.makedirs(args.output, exist_ok=True)
    
    print(f"\nHYDRA-LB Benchmark Analysis")
    print(f"  Input:  {args.input}")
    print(f"  Output: {args.output}")
    
    # Load results
    results = load_combined_csvs(args.input)
    
    if not results:
        print("\n  No results found! Run experiments first:")
        print("    python benchmarks/run_experiment.py --strategy round_robin --workload steady")
        return
    
    # Aggregate
    agg = aggregate_by_strategy_workload(results)
    workloads = sorted(set(r['workload'] for r in results))
    
    # Print summary
    print_summary(agg, workloads)
    
    # Generate plots
    if MATPLOTLIB_AVAILABLE:
        print(f"\n  Generating plots...")
        plot_variance_comparison(agg, workloads, args.output)
        plot_latency_comparison(agg, workloads, args.output)
        plot_throughput_comparison(agg, workloads, args.output)
    
    # Generate LaTeX
    if args.latex:
        generate_latex_table(agg, workloads, args.output)
    
    print(f"\n  Done! Figures saved to {args.output}")


if __name__ == '__main__':
    main()
