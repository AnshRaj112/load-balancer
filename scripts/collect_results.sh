#!/bin/bash
# HYDRA-LB: Collect Results Script
#
# Collects and organizes experiment results.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

RESULTS_DIR="$PROJECT_DIR/results"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTPUT_DIR="$RESULTS_DIR/experiment_$TIMESTAMP"

echo "=== HYDRA-LB Results Collection ==="

# Create output directory
mkdir -p "$OUTPUT_DIR"

# Copy metrics from data directory
if [ -d "$PROJECT_DIR/data/metrics" ]; then
    echo "Copying metrics..."
    cp -r "$PROJECT_DIR/data/metrics"/* "$OUTPUT_DIR/" 2>/dev/null || true
fi

# Collect container logs
echo "Collecting container logs..."
for container in hydra-controller-1 hydra-controller-2 hydra-controller-3 hydra-mininet; do
    if docker ps -a --format '{{.Names}}' | grep -q "^${container}$"; then
        docker logs "$container" > "$OUTPUT_DIR/${container}.log" 2>&1 || true
    fi
done

# Get container stats
echo "Collecting container stats..."
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}" \
    hydra-controller-1 hydra-controller-2 hydra-controller-3 > "$OUTPUT_DIR/container_stats.txt" 2>/dev/null || true

# Generate summary
echo "Generating summary..."
cat > "$OUTPUT_DIR/summary.txt" << EOF
HYDRA-LB Experiment Results
===========================

Timestamp: $TIMESTAMP
Date: $(date)

Containers:
$(docker ps --filter "name=hydra" --format "  - {{.Names}}: {{.Status}}")

Files:
$(ls -la "$OUTPUT_DIR" | tail -n +4)
EOF

echo ""
echo "Results collected to: $OUTPUT_DIR"
echo ""
echo "Files:"
ls -la "$OUTPUT_DIR"
