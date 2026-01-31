#!/bin/bash
# HYDRA-LB: Traffic Generation Script
#
# Generates test traffic using iperf and custom patterns.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Default values
DURATION=60
PATTERN="uniform"
BANDWIDTH="10M"
HOSTS=""

usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -d, --duration SEC     Duration in seconds (default: 60)"
    echo "  -p, --pattern PATTERN  Traffic pattern: uniform, burst, random (default: uniform)"
    echo "  -b, --bandwidth BW     Bandwidth per flow (default: 10M)"
    echo "  -h, --hosts LIST       Comma-separated host list (default: all)"
    echo "  --help                 Show this help"
}

while [[ $# -gt 0 ]]; do
    case $1 in
        -d|--duration)
            DURATION="$2"
            shift 2
            ;;
        -p|--pattern)
            PATTERN="$2"
            shift 2
            ;;
        -b|--bandwidth)
            BANDWIDTH="$2"
            shift 2
            ;;
        -h|--hosts)
            HOSTS="$2"
            shift 2
            ;;
        --help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            usage
            exit 1
            ;;
    esac
done

echo "=== HYDRA-LB Traffic Generation ==="
echo "Duration: ${DURATION}s"
echo "Pattern: $PATTERN"
echo "Bandwidth: $BANDWIDTH"

# Check if running inside Mininet container
if ! command -v mn &> /dev/null; then
    echo "This script should be run inside the Mininet container"
    echo "Use: docker exec -it hydra-mininet bash"
    exit 1
fi

generate_uniform_traffic() {
    echo "Generating uniform traffic pattern..."
    # Start iperf server on h1
    mx h1 iperf3 -s -D
    
    # Generate traffic from other hosts
    for i in 2 3 4; do
        mx h$i iperf3 -c 10.0.0.1 -t $DURATION -b $BANDWIDTH &
    done
    
    wait
}

generate_burst_traffic() {
    echo "Generating burst traffic pattern..."
    # Start iperf server
    mx h1 iperf3 -s -D
    
    # Burst pattern: high traffic for 5s, then low for 5s
    end_time=$((SECONDS + DURATION))
    while [ $SECONDS -lt $end_time ]; do
        # High traffic burst
        for i in 2 3 4; do
            mx h$i iperf3 -c 10.0.0.1 -t 5 -b 100M &
        done
        sleep 5
        
        # Low traffic period
        mx h2 iperf3 -c 10.0.0.1 -t 5 -b 1M &
        sleep 5
    done
}

generate_random_traffic() {
    echo "Generating random traffic pattern..."
    # Start iperf server
    mx h1 iperf3 -s -D
    
    end_time=$((SECONDS + DURATION))
    while [ $SECONDS -lt $end_time ]; do
        # Random host, random duration, random bandwidth
        host=$((RANDOM % 3 + 2))
        dur=$((RANDOM % 5 + 1))
        bw=$((RANDOM % 50 + 1))M
        
        mx h$host iperf3 -c 10.0.0.1 -t $dur -b $bw &
        sleep $dur
    done
}

case $PATTERN in
    uniform)
        generate_uniform_traffic
        ;;
    burst)
        generate_burst_traffic
        ;;
    random)
        generate_random_traffic
        ;;
    *)
        echo "Unknown pattern: $PATTERN"
        exit 1
        ;;
esac

echo "Traffic generation complete."
