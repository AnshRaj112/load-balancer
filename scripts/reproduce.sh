#!/bin/bash
# HYDRA-LB Reproducibility Guide

set -e

echo "============================================================"
echo " Starting HYDRA-LB Reproducibility Script"
echo "============================================================"

# Failsafe: check if docker is running
if ! docker info > /dev/null 2>&1; then
    echo "ERROR: Docker daemon is not running or not accessible."
    echo "Please start Docker and try again."
    exit 1
fi

# Failsafe: Ensure cluster is up with monitoring profile
echo "[1/4] Checking Docker cluster status..."
if ! docker ps | grep -q 'hydra-grafana'; then
    echo "Starting HYDRA-LB cluster (including Grafana & Prometheus)..."
    docker compose --profile monitoring up -d
    echo "Waiting for cluster components to initialize (20s)..."
    sleep 20
else
    echo "Docker cluster is already running."
fi

# Step 2: Run benchmarks
echo ""
echo "[2/4] Executing Benchmark Suite..."
chmod +x benchmarks/run_all.sh
./benchmarks/run_all.sh

# Step 3: Analyze results and generate figures
echo ""
echo "[3/4] Generating Paper Figures (Requires Matplotlib)..."
if [ ! -d ".venv" ]; then
    echo "Creating Python virtual environment for analysis dependencies..."
    python3 -m venv .venv
fi

source .venv/bin/activate
pip install -q matplotlib
python3 benchmarks/analyze_results.py --input data/results/ --output paper/figures/ --latex
deactivate

# Step 4: Summary output
echo ""
echo "============================================================"
echo " Reproducibility Execution Complete!"
echo "============================================================"
echo " - Raw evaluation data saved to: data/results/"
echo " - Compiled figures (PNG) saved to: paper/figures/"
echo " - LaTeX table saved as: paper/figures/comparison_table.tex"
echo " - Live Grafana Dashboard: http://localhost:3000"
echo "   (Login: admin / hydra)"
echo "============================================================"
