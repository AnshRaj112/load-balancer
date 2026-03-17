#!/bin/bash
# HYDRA-LB Complete Benchmark Suite

set -e

DURATION=30
RUNS=1
STRATEGIES=("round_robin" "least_load" "hydra_proactive")
WORKLOADS=("steady" "burst" "skewed" "flash_crowd")

echo "============================================================"
echo " Starting HYDRA-LB Full Evaluation Benchmark Suite"
echo " Strategies: ${STRATEGIES[*]}"
echo " Workloads:  ${WORKLOADS[*]}"
echo " Duration per run: ${DURATION}s"
echo " Runs per configuration: ${RUNS}"
echo "============================================================"

for strategy in "${STRATEGIES[@]}"; do
    for workload in "${WORKLOADS[@]}"; do
        echo ""
        echo ">>> Running Benchmark: Strategy=$strategy, Workload=$workload <<<"
        python3 benchmarks/run_experiment.py --strategy $strategy --workload $workload --duration $DURATION --runs $RUNS
        
        # Give the cluster a moment to cool down between runs
        sleep 5
    done
done

echo ""
echo "============================================================"
echo " All benchmarks complete!"
echo " Results are saved in data/results/"
echo " To analyze: python3 benchmarks/analyze_results.py --input data/results/ --output paper/figures/"
echo "============================================================"
