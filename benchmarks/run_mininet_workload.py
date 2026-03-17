#!/usr/bin/env python3
"""
Executes a specific workload against the Fat-Tree topology in Mininet.
Designed to be called from `run_experiment.py` via Docker exec.
"""
import sys
import os
import argparse
import time

# Ensure we can import from /app
sys.path.insert(0, '/app')

from mininet.log import setLogLevel, info
from benchmarks.workloads import get_workload

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--workload', required=True)
    parser.add_argument('--duration', type=int, default=60)
    args = parser.parse_args()

    setLogLevel('info')
    
    # Generate topology script if it doesn't exist
    topo_script = '/app/topology/fat_tree_k4.py'
    if not os.path.exists(topo_script):
        info('*** Generating Fat-Tree script...\n')
        os.system('python3 /app/topology/fat_tree.py 4')
    
    # Import the generated topology
    import topology.fat_tree_k4 as topo
    
    info('*** Creating Fat-Tree Topology\n')
    net = topo.create_topology()
    net.start()
    
    info('*** Waiting for switches to connect to controllers (10s)\n')
    time.sleep(10)
    
    info(f'*** Running Workload: {args.workload}\n')
    workload = get_workload(args.workload, duration=args.duration)
    workload.generate(net)
    
    info('*** Workload Complete. Stopping Network...\n')
    net.stop()

if __name__ == '__main__':
    main()
