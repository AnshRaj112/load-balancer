#!/bin/bash
# HYDRA-LB Interactive Demonstration Script

set -e

echo "=========================================================="
echo "          HYDRA-LB: Intelligent Load Balancer             "
echo "                 Interactive Demo                         "
echo "=========================================================="

echo "[1/4] Stopping any existing containers..."
docker compose down -v 2>/dev/null || true

echo "[2/4] Starting the HYDRA-LB Cluster (3 Controllers + Mininet + Grafana)..."
docker compose up -d

echo "[3/4] Waiting for Ryu controllers and LSTM models to initialize (this takes ~15 seconds)..."
sleep 15

echo "----------------------------------------------------------"
echo "The cluster is now online!"
echo "Open your browser to the Live Dashboard:"
echo "➡️  http://localhost:3000/d/hydra-lb-main/hydra-lb-controller-dashboard"
echo "Login: admin / hydra"
echo "----------------------------------------------------------"

echo "[4/4] Injecting 'Burst' traffic workload into the network to trigger migrations..."
echo "Traffic will run for 3 minutes. Watch the Grafana dashboard to see physical switch handovers!"

# Start the Mininet workload in the background
docker exec hydra-mininet python3 /app/benchmarks/run_mininet_workload.py --workload burst --duration 180 &
WORKLOAD_PID=$!

echo ""
echo "Monitoring controller migration logs in real-time:"
echo "(Press Ctrl+C to stop the demonstration)"
echo "----------------------------------------------------------"

# Tail logs specifically looking for optimization and migration events
docker compose logs -f ryu-controller-1 ryu-controller-2 ryu-controller-3 | grep -i --line-buffered "MIGRATION\|PROACTIVE"

# Wait for workload to finish if not interrupted
wait $WORKLOAD_PID 2>/dev/null || true
echo "Demonstration complete. You can bring down the cluster using 'docker compose down'"
