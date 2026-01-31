#!/bin/bash
# HYDRA-LB: Start Testbed Script
# 
# This script starts the complete HYDRA-LB testbed environment.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

echo "=== HYDRA-LB Testbed Startup ==="
echo "Project directory: $PROJECT_DIR"

# Check Docker
if ! command -v docker &> /dev/null; then
    echo "Error: Docker is not installed"
    exit 1
fi

if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo "Error: Docker Compose is not installed"
    exit 1
fi

# Parse arguments
PROFILE=""
DETACH="-d"
REBUILD=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --monitoring)
            PROFILE="--profile monitoring"
            shift
            ;;
        --foreground|-f)
            DETACH=""
            shift
            ;;
        --rebuild|-r)
            REBUILD="--build"
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --monitoring    Start Prometheus and Grafana"
            echo "  --foreground    Run in foreground (don't detach)"
            echo "  --rebuild       Rebuild Docker images"
            echo "  --help          Show this help"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Create data directories
echo "Creating data directories..."
mkdir -p data/metrics

# Start services
echo "Starting Docker containers..."
if docker compose version &> /dev/null; then
    docker compose up $DETACH $REBUILD $PROFILE
else
    docker-compose up $DETACH $REBUILD $PROFILE
fi

if [ -n "$DETACH" ]; then
    echo ""
    echo "=== HYDRA-LB Testbed Started ==="
    echo ""
    echo "Controllers:"
    echo "  - Controller 1: http://localhost:8080 (OpenFlow: 6653)"
    echo "  - Controller 2: http://localhost:8081 (OpenFlow: 6654)"
    echo "  - Controller 3: http://localhost:8082 (OpenFlow: 6655)"
    echo ""
    echo "To access Mininet CLI:"
    echo "  docker exec -it hydra-mininet bash"
    echo "  python3 /app/topology/fat_tree.py"
    echo ""
    echo "To view logs:"
    echo "  docker logs -f hydra-controller-1"
    echo ""
    echo "To stop the testbed:"
    echo "  ./scripts/stop_testbed.sh"
fi
