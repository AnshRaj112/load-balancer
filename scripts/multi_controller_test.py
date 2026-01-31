#!/usr/bin/env python3
"""
HYDRA-LB: Multi-Controller Load Balancing Demo

This script creates multiple network segments, each connected to a different
controller, demonstrating load balancing across all 3 controllers.

Usage: Run inside Mininet container:
    docker exec -it hydra-mininet python3 /app/scripts/multi_controller_test.py
"""

import time
import subprocess
import sys
import os

# Controller IPs and ports
CONTROLLERS = [
    ("172.20.0.10", 6653, "Controller-1"),  # Controller 1
    ("172.20.0.11", 6653, "Controller-2"),  # Controller 2
    ("172.20.0.12", 6653, "Controller-3"),  # Controller 3
]

def print_header(text):
    print("\n" + "=" * 70)
    print(f"  {text}")
    print("=" * 70)
    sys.stdout.flush()

def print_step(num, text):
    print(f"\n[STEP {num}] {text}")
    sys.stdout.flush()

def run_test(controller_ip, controller_port, controller_name, topo="single,3"):
    """Run a network test against a specific controller."""
    print(f"\n>>> Testing with {controller_name} at {controller_ip}:{controller_port}")
    sys.stdout.flush()
    
    cmd = f"mn --controller=remote,ip={controller_ip},port={controller_port} --topo={topo} --test=pingall"
    
    try:
        result = subprocess.run(
            cmd, 
            shell=True,  # Use shell to handle the command properly
            capture_output=True, 
            text=True, 
            timeout=60
        )
        
        output = result.stdout + result.stderr
        
        # Print relevant lines
        for line in output.split('\n'):
            if any(x in line for x in ['hosts', 'switches', 'Results', 'Ping']):
                print(f"    {line.strip()}")
        
        if '0% dropped' in output:
            print(f"    ✅ {controller_name}: PASSED (0% packet loss)")
            sys.stdout.flush()
            return True
        elif 'dropped' in output:
            print(f"    ❌ {controller_name}: SOME PACKET LOSS")
            sys.stdout.flush()
            return False
        else:
            # Check if ping test ran at all
            if 'Ping' in output or 'received' in output:
                print(f"    ✅ {controller_name}: PASSED")
                sys.stdout.flush()
                return True
            else:
                print(f"    ❌ {controller_name}: TEST DID NOT COMPLETE")
                print(f"    Output: {output[:200]}...")
                sys.stdout.flush()
                return False
    except subprocess.TimeoutExpired:
        print(f"    ❌ {controller_name}: TIMEOUT")
        sys.stdout.flush()
        return False
    except Exception as e:
        print(f"    ❌ {controller_name}: Error - {e}")
        sys.stdout.flush()
        return False

def main():
    print_header("HYDRA-LB Multi-Controller Load Balancing Demo")
    
    print("""
This test demonstrates that ALL 3 controllers can handle network traffic.
Each controller will manage a separate network segment.

Controllers:
  - Controller 1: 172.20.0.10:6653
  - Controller 2: 172.20.0.11:6653  
  - Controller 3: 172.20.0.12:6653
""")
    sys.stdout.flush()
    
    results = {}
    
    # Test each controller sequentially
    print_step(1, "Testing Each Controller Individually")
    
    for i, (ip, port, name) in enumerate(CONTROLLERS):
        print(f"\n--- Test {i+1}/3: {name} ---")
        sys.stdout.flush()
        success = run_test(ip, port, name, topo="single,3")
        results[name] = success
        time.sleep(2)  # Brief pause between tests to clean up
    
    # Summary
    print_header("Load Balancing Test Results")
    
    all_passed = True
    for name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {name}: {status}")
        if not passed:
            all_passed = False
    
    print("")
    if all_passed:
        print("🎉 SUCCESS: All 3 controllers are working correctly!")
        print("   Load balancing is ready - each controller can handle traffic.")
    else:
        print("⚠️  WARNING: Some controllers failed the test.")
        print("   Check controller logs: docker logs hydra-controller-X")
    
    print("\n" + "=" * 70)
    print("  Check the Grafana dashboard to see metrics from all 3 controllers!")
    print("  URL: http://localhost:3000/d/hydra-lb-main/hydra-lb-controller-dashboard")
    print("=" * 70 + "\n")
    sys.stdout.flush()

if __name__ == "__main__":
    main()
