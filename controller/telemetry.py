"""
HYDRA-LB: Telemetry Collection Module

Collects, aggregates, and exports metrics from SDN switches and controllers.
Supports CSV export and optional Prometheus metrics.
"""

import os
import time
import threading
import logging
from collections import defaultdict
from datetime import datetime
from pathlib import Path

logger = logging.getLogger('hydra-lb.telemetry')


class TelemetryCollector:
    """
    Collects and aggregates telemetry data from switches.
    
    Metrics collected:
    - packet_in_rate: Packet-in messages per second
    - flow_count: Active flows per switch
    - byte_count: Total bytes processed
    - lb_decisions: Load balancer decisions made
    """
    
    def __init__(self, controller_id: int = 1, output_dir: str = '/app/data/metrics'):
        self.controller_id = controller_id
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Switch registration
        self.switches = set()
        
        # Metrics storage with thread-safe access
        self._lock = threading.Lock()
        
        # Per-switch metrics: {dpid: {metric_name: [(timestamp, value), ...]}}
        self.switch_metrics = defaultdict(lambda: defaultdict(list))
        
        # Aggregated controller metrics
        self.controller_metrics = defaultdict(list)
        
        # Packet-in counters for rate calculation
        self._packet_in_counts = defaultdict(int)
        self._last_packet_in_time = defaultdict(float)
        
        # Load balancer decision tracking
        self.lb_decisions = []
        
        # Initialize CSV files
        self._init_csv_files()
        
        logger.info(f"Telemetry collector initialized for controller {controller_id}")
    
    def _init_csv_files(self):
        """Initialize CSV output files with headers."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Switch metrics file
        self.switch_metrics_file = self.output_dir / f'switch_metrics_c{self.controller_id}_{timestamp}.csv'
        with open(self.switch_metrics_file, 'w') as f:
            f.write('timestamp,controller_id,switch_dpid,packet_in_rate,flow_count,byte_count,rx_bytes,tx_bytes\n')
        
        # Controller metrics file
        self.controller_metrics_file = self.output_dir / f'controller_metrics_c{self.controller_id}_{timestamp}.csv'
        with open(self.controller_metrics_file, 'w') as f:
            f.write('timestamp,controller_id,switch_count,total_packet_ins,total_flows,total_bytes\n')
        
        # Load balancer decisions file
        self.lb_decisions_file = self.output_dir / f'lb_decisions_c{self.controller_id}_{timestamp}.csv'
        with open(self.lb_decisions_file, 'w') as f:
            f.write('timestamp,controller_id,switch_dpid,vip,selected_server\n')
        
        logger.info(f"CSV files initialized: {self.switch_metrics_file}")
    
    def register_switch(self, dpid: int):
        """Register a new switch for telemetry collection."""
        with self._lock:
            self.switches.add(dpid)
            self._packet_in_counts[dpid] = 0
            self._last_packet_in_time[dpid] = time.time()
            logger.info(f"Switch {dpid} registered for telemetry")
    
    def unregister_switch(self, dpid: int):
        """Unregister a switch from telemetry collection."""
        with self._lock:
            self.switches.discard(dpid)
            if dpid in self._packet_in_counts:
                del self._packet_in_counts[dpid]
            logger.info(f"Switch {dpid} unregistered from telemetry")
    
    def record_packet_in(self, dpid: int):
        """Record a packet-in event for a switch."""
        with self._lock:
            self._packet_in_counts[dpid] += 1
    
    def record_port_stats(self, dpid: int, stats: dict):
        """Record port statistics for a switch."""
        timestamp = time.time()
        with self._lock:
            self.switch_metrics[dpid]['rx_bytes'].append((timestamp, stats.get('rx_bytes', 0)))
            self.switch_metrics[dpid]['tx_bytes'].append((timestamp, stats.get('tx_bytes', 0)))
    
    def record_flow_stats(self, dpid: int, stats: dict):
        """Record flow statistics for a switch."""
        timestamp = time.time()
        with self._lock:
            self.switch_metrics[dpid]['flow_count'].append((timestamp, stats.get('flow_count', 0)))
            self.switch_metrics[dpid]['byte_count'].append((timestamp, stats.get('byte_count', 0)))
    
    def record_lb_decision(self, dpid: int, vip: str, selected_server: str):
        """Record a load balancer decision."""
        timestamp = time.time()
        with self._lock:
            self.lb_decisions.append({
                'timestamp': timestamp,
                'dpid': dpid,
                'vip': vip,
                'selected_server': selected_server
            })
    
    def _calculate_packet_in_rate(self, dpid: int) -> float:
        """Calculate packet-in rate for a switch."""
        current_time = time.time()
        with self._lock:
            count = self._packet_in_counts.get(dpid, 0)
            last_time = self._last_packet_in_time.get(dpid, current_time)
            
            elapsed = current_time - last_time
            if elapsed > 0:
                rate = count / elapsed
            else:
                rate = 0.0
            
            # Reset counters
            self._packet_in_counts[dpid] = 0
            self._last_packet_in_time[dpid] = current_time
            
            return rate
    
    def get_switch_metrics(self, dpid: int) -> dict:
        """Get current metrics for a specific switch."""
        with self._lock:
            metrics = self.switch_metrics.get(dpid, {})
            
            # Get latest values
            result = {
                'dpid': dpid,
                'packet_in_rate': self._calculate_packet_in_rate(dpid),
                'flow_count': metrics.get('flow_count', [(0, 0)])[-1][1] if metrics.get('flow_count') else 0,
                'byte_count': metrics.get('byte_count', [(0, 0)])[-1][1] if metrics.get('byte_count') else 0,
                'rx_bytes': metrics.get('rx_bytes', [(0, 0)])[-1][1] if metrics.get('rx_bytes') else 0,
                'tx_bytes': metrics.get('tx_bytes', [(0, 0)])[-1][1] if metrics.get('tx_bytes') else 0,
            }
            
            return result
    
    def get_all_switch_metrics(self) -> list:
        """Get metrics for all registered switches."""
        return [self.get_switch_metrics(dpid) for dpid in self.switches]
    
    def get_controller_load(self) -> float:
        """
        Calculate the total load on this controller.
        
        Load is defined as the sum of packet-in rates from all switches.
        """
        total_load = 0.0
        for dpid in self.switches:
            metrics = self.get_switch_metrics(dpid)
            total_load += metrics.get('packet_in_rate', 0)
        return total_load
    
    def get_load_variance(self) -> dict:
        """
        Calculate load statistics across switches.
        
        Returns variance, mean, and per-switch loads.
        """
        loads = []
        switch_loads = {}
        
        for dpid in self.switches:
            metrics = self.get_switch_metrics(dpid)
            load = metrics.get('packet_in_rate', 0)
            loads.append(load)
            switch_loads[dpid] = load
        
        if not loads:
            return {'variance': 0, 'mean': 0, 'switch_loads': {}}
        
        mean_load = sum(loads) / len(loads)
        variance = sum((l - mean_load) ** 2 for l in loads) / len(loads)
        
        return {
            'variance': variance,
            'mean': mean_load,
            'switch_loads': switch_loads,
            'switch_count': len(loads)
        }
    
    def export_metrics(self):
        """Export current metrics to CSV files."""
        timestamp = datetime.now().isoformat()
        
        # Export switch metrics
        with self._lock:
            switch_data = []
            for dpid in self.switches:
                metrics = self.get_switch_metrics(dpid)
                switch_data.append(metrics)
        
        with open(self.switch_metrics_file, 'a') as f:
            for metrics in switch_data:
                f.write(f"{timestamp},{self.controller_id},{metrics['dpid']},"
                       f"{metrics['packet_in_rate']:.4f},{metrics['flow_count']},"
                       f"{metrics['byte_count']},{metrics['rx_bytes']},{metrics['tx_bytes']}\n")
        
        # Export controller aggregate metrics
        total_packet_ins = sum(m.get('packet_in_rate', 0) for m in switch_data)
        total_flows = sum(m.get('flow_count', 0) for m in switch_data)
        total_bytes = sum(m.get('byte_count', 0) for m in switch_data)
        
        with open(self.controller_metrics_file, 'a') as f:
            f.write(f"{timestamp},{self.controller_id},{len(self.switches)},"
                   f"{total_packet_ins:.4f},{total_flows},{total_bytes}\n")
        
        # Export pending LB decisions
        with self._lock:
            decisions_to_export = self.lb_decisions.copy()
            self.lb_decisions.clear()
        
        if decisions_to_export:
            with open(self.lb_decisions_file, 'a') as f:
                for decision in decisions_to_export:
                    f.write(f"{datetime.fromtimestamp(decision['timestamp']).isoformat()},"
                           f"{self.controller_id},{decision['dpid']},"
                           f"{decision['vip']},{decision['selected_server']}\n")
        
        logger.debug(f"Exported metrics for {len(switch_data)} switches")
    
    def get_metrics_summary(self) -> dict:
        """Get a summary of all collected metrics."""
        load_stats = self.get_load_variance()
        
        return {
            'controller_id': self.controller_id,
            'switch_count': len(self.switches),
            'total_load': self.get_controller_load(),
            'load_variance': load_stats['variance'],
            'load_mean': load_stats['mean'],
            'switches': list(self.switches)
        }


class PrometheusExporter:
    """
    Optional Prometheus metrics exporter.
    
    Exposes metrics at /metrics endpoint for Prometheus scraping.
    """
    
    def __init__(self, port: int = 9100):
        self.port = port
        self._metrics_registered = False
        
        try:
            from prometheus_client import start_http_server, Gauge, Counter
            
            # Define Prometheus metrics
            self.packet_in_rate = Gauge('hydra_packet_in_rate', 
                                         'Packet-in rate per switch',
                                         ['controller_id', 'switch_dpid'])
            self.flow_count = Gauge('hydra_flow_count',
                                     'Flow count per switch',
                                     ['controller_id', 'switch_dpid'])
            self.controller_load = Gauge('hydra_controller_load',
                                          'Total controller load',
                                          ['controller_id'])
            self.load_variance = Gauge('hydra_load_variance',
                                        'Load variance across switches',
                                        ['controller_id'])
            
            # Start HTTP server
            start_http_server(port)
            self._metrics_registered = True
            logger.info(f"Prometheus exporter started on port {port}")
            
        except ImportError:
            logger.warning("prometheus_client not installed, Prometheus export disabled")
    
    def update_metrics(self, telemetry: TelemetryCollector):
        """Update Prometheus metrics from telemetry collector."""
        if not self._metrics_registered:
            return
        
        controller_id = str(telemetry.controller_id)
        
        # Update per-switch metrics
        for metrics in telemetry.get_all_switch_metrics():
            dpid = str(metrics['dpid'])
            self.packet_in_rate.labels(controller_id, dpid).set(metrics['packet_in_rate'])
            self.flow_count.labels(controller_id, dpid).set(metrics['flow_count'])
        
        # Update controller-level metrics
        self.controller_load.labels(controller_id).set(telemetry.get_controller_load())
        self.load_variance.labels(controller_id).set(telemetry.get_load_variance()['variance'])
