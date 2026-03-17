#!/usr/bin/env python3
"""
HYDRA-LB Benchmark: Traffic Workload Definitions

Defines reproducible traffic patterns for evaluation experiments.
Each workload runs inside Mininet and generates specific traffic
patterns to stress-test different aspects of the load balancer.

Workload Types:
    steady     - Uniform traffic from all hosts (baseline)
    burst      - Alternating high/low bursts
    flash_crowd - Sudden spike to one controller segment
    skewed     - 70% traffic to one segment, 30% distributed
"""

import time
import random
import subprocess
import sys

# Default config
DEFAULT_DURATION = 60  # seconds
DEFAULT_BANDWIDTH = "5M"


class Workload:
    """Base class for traffic workloads."""
    
    def __init__(self, duration=DEFAULT_DURATION, seed=42):
        self.duration = duration
        self.seed = seed
        random.seed(seed)
        self.description = "base workload"
    
    def generate(self, net):
        """Generate traffic on the Mininet network. Override in subclasses."""
        raise NotImplementedError
    
    def _iperf_bg(self, net, src_name, dst_name, bw="5M", duration=10, port=5001):
        """Run iperf in background between two hosts."""
        src = net.get(src_name)
        dst = net.get(dst_name)
        
        # Start server
        dst.cmd(f'iperf -s -p {port} &')
        time.sleep(0.5)
        
        # Start client
        src.cmd(f'iperf -c {dst.IP()} -p {port} -b {bw} -t {duration} &')
        return port
    
    def _ping_flood(self, net, src_name, dst_name, count=100):
        """Ping flood between two hosts."""
        src = net.get(src_name)
        dst = net.get(dst_name)
        src.cmd(f'ping -c {count} -i 0.01 {dst.IP()} &')


class SteadyWorkload(Workload):
    """Uniform traffic from all hosts — baseline workload."""
    
    def __init__(self, duration=DEFAULT_DURATION, bandwidth="5M", **kwargs):
        super().__init__(duration, **kwargs)
        self.bandwidth = bandwidth
        self.description = f"steady: uniform {bandwidth} from all hosts for {duration}s"
    
    def generate(self, net):
        hosts = net.hosts
        n = len(hosts)
        port = 5001
        
        print(f"  [steady] Starting uniform traffic: {n} hosts, {self.bandwidth}, {self.duration}s")
        
        # Each host sends to a random peer
        for i in range(n):
            dst_idx = (i + 1) % n
            self._iperf_bg(
                net, hosts[i].name, hosts[dst_idx].name,
                bw=self.bandwidth, duration=self.duration, port=port + i
            )
        
        time.sleep(self.duration)
        print("  [steady] Workload complete")


class BurstWorkload(Workload):
    """Alternating high/low bursts — tests reactive response."""
    
    def __init__(self, duration=DEFAULT_DURATION, high_bw="20M", low_bw="1M",
                 burst_interval=10, **kwargs):
        super().__init__(duration, **kwargs)
        self.high_bw = high_bw
        self.low_bw = low_bw
        self.burst_interval = burst_interval
        self.description = (
            f"burst: alternating {high_bw}/{low_bw} "
            f"every {burst_interval}s for {duration}s"
        )
    
    def generate(self, net):
        hosts = net.hosts
        elapsed = 0
        burst_high = True
        port = 5001
        
        print(f"  [burst] Starting burst workload: {self.duration}s")
        
        while elapsed < self.duration:
            bw = self.high_bw if burst_high else self.low_bw
            phase_dur = min(self.burst_interval, self.duration - elapsed)
            
            phase = "HIGH" if burst_high else "LOW"
            print(f"  [burst] Phase: {phase} ({bw}) for {phase_dur}s")
            
            # Kill previous iperf instances
            for h in hosts:
                h.cmd('killall iperf 2>/dev/null')
            time.sleep(0.5)
            
            # Start new traffic
            for i in range(len(hosts)):
                dst_idx = (i + 1) % len(hosts)
                self._iperf_bg(
                    net, hosts[i].name, hosts[dst_idx].name,
                    bw=bw, duration=phase_dur, port=port + i
                )
            
            time.sleep(phase_dur)
            elapsed += phase_dur
            burst_high = not burst_high
        
        print("  [burst] Workload complete")


class FlashCrowdWorkload(Workload):
    """Sudden spike to one controller segment — tests proactive response."""
    
    def __init__(self, duration=DEFAULT_DURATION, spike_bw="30M",
                 normal_bw="2M", spike_start=20, spike_duration=20, **kwargs):
        super().__init__(duration, **kwargs)
        self.spike_bw = spike_bw
        self.normal_bw = normal_bw
        self.spike_start = spike_start
        self.spike_duration = spike_duration
        self.description = (
            f"flash_crowd: spike at t={spike_start}s to {spike_bw} "
            f"for {spike_duration}s"
        )
    
    def generate(self, net):
        hosts = net.hosts
        n = len(hosts)
        port = 5001
        
        print(f"  [flash_crowd] Starting: normal={self.normal_bw}, "
              f"spike at t={self.spike_start}s")
        
        # Phase 1: Normal traffic
        for i in range(n):
            dst_idx = (i + 1) % n
            self._iperf_bg(
                net, hosts[i].name, hosts[dst_idx].name,
                bw=self.normal_bw, duration=self.duration, port=port + i
            )
        
        # Wait for spike
        time.sleep(self.spike_start)
        
        # Phase 2: Flash crowd — concentrate traffic on first segment
        target_hosts = hosts[:max(1, n // 3)]  # First 1/3 of hosts
        print(f"  [flash_crowd] SPIKE: {len(target_hosts)} hosts "
              f"sending {self.spike_bw}")
        
        for i, h in enumerate(target_hosts):
            dst = hosts[(n // 2 + i) % n]
            self._iperf_bg(
                net, h.name, dst.name,
                bw=self.spike_bw, duration=self.spike_duration, port=6000 + i
            )
        
        # Wait for remaining duration
        remaining = self.duration - self.spike_start
        time.sleep(remaining)
        print("  [flash_crowd] Workload complete")


class SkewedWorkload(Workload):
    """70% traffic to one segment — tests sustained imbalance."""
    
    def __init__(self, duration=DEFAULT_DURATION, heavy_bw="15M",
                 light_bw="3M", **kwargs):
        super().__init__(duration, **kwargs)
        self.heavy_bw = heavy_bw
        self.light_bw = light_bw
        self.description = (
            f"skewed: 70% traffic ({heavy_bw}) to segment 1, "
            f"30% ({light_bw}) to rest"
        )
    
    def generate(self, net):
        hosts = net.hosts
        n = len(hosts)
        port = 5001
        
        # Split hosts: first 1/3 gets heavy traffic, rest gets light
        heavy_count = max(1, n // 3)
        
        print(f"  [skewed] Starting: {heavy_count} hosts at {self.heavy_bw}, "
              f"{n - heavy_count} at {self.light_bw}")
        
        for i in range(n):
            dst_idx = (i + 1) % n
            bw = self.heavy_bw if i < heavy_count else self.light_bw
            self._iperf_bg(
                net, hosts[i].name, hosts[dst_idx].name,
                bw=bw, duration=self.duration, port=port + i
            )
        
        time.sleep(self.duration)
        print("  [skewed] Workload complete")


# Registry
WORKLOADS = {
    'steady': SteadyWorkload,
    'burst': BurstWorkload,
    'flash_crowd': FlashCrowdWorkload,
    'skewed': SkewedWorkload,
}


def get_workload(name, **kwargs):
    """Factory function to create a workload by name."""
    if name not in WORKLOADS:
        raise ValueError(f"Unknown workload: {name}. Available: {list(WORKLOADS.keys())}")
    return WORKLOADS[name](**kwargs)
