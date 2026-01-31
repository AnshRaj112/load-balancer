#!/bin/bash
# HYDRA-LB: Stop Testbed Script

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

echo "=== Stopping HYDRA-LB Testbed ==="

if docker compose version &> /dev/null; then
    docker compose down --remove-orphans
else
    docker-compose down --remove-orphans
fi

echo "Testbed stopped."
