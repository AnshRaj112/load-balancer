"""
HYDRA-LB: Metrics Collector

Central metrics collection and aggregation for experiments.
Consolidates data from multiple controllers for analysis.
"""

import os
import time
import json
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict, field

logger = logging.getLogger('hydra-lb.metrics.collector')


@dataclass
class ExperimentMetrics:
    """Container for experiment-level metrics."""
    experiment_id: str
    start_time: float
    end_time: float = 0
    
    # Controller metrics
    controller_loads: Dict[int, List[float]] = field(default_factory=dict)
    controller_variances: List[float] = field(default_factory=list)
    
    # Switch metrics
    switch_packet_rates: Dict[int, List[float]] = field(default_factory=dict)
    switch_flow_counts: Dict[int, List[int]] = field(default_factory=dict)
    
    # Load balancer metrics
    lb_decisions: List[Dict] = field(default_factory=list)
    response_times: List[float] = field(default_factory=list)
    throughput_samples: List[float] = field(default_factory=list)
    
    # Migration metrics (for Phase 3)
    migrations: List[Dict] = field(default_factory=list)
    migration_costs: List[float] = field(default_factory=list)


class MetricsCollector:
    """
    Centralized metrics collection for HYDRA-LB experiments.
    
    Aggregates metrics from multiple sources:
    - Per-controller telemetry
    - Per-switch statistics
    - Load balancer decisions
    - Migration events
    """
    
    def __init__(self, output_dir: str = '/app/data/metrics',
                 experiment_id: str = None):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate experiment ID if not provided
        if experiment_id is None:
            experiment_id = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        self.experiment_id = experiment_id
        self.metrics = ExperimentMetrics(
            experiment_id=experiment_id,
            start_time=time.time()
        )
        
        self._lock = threading.Lock()
        
        # Time series storage
        self._timestamps: List[float] = []
        
        logger.info(f"Metrics collector initialized for experiment: {experiment_id}")
    
    def record_controller_load(self, controller_id: int, load: float):
        """Record load measurement for a controller."""
        with self._lock:
            if controller_id not in self.metrics.controller_loads:
                self.metrics.controller_loads[controller_id] = []
            self.metrics.controller_loads[controller_id].append(load)
    
    def record_load_variance(self, variance: float):
        """Record system-wide load variance."""
        with self._lock:
            self.metrics.controller_variances.append(variance)
            self._timestamps.append(time.time())
    
    def record_switch_metrics(self, switch_dpid: int, packet_rate: float, 
                               flow_count: int):
        """Record per-switch metrics."""
        with self._lock:
            if switch_dpid not in self.metrics.switch_packet_rates:
                self.metrics.switch_packet_rates[switch_dpid] = []
                self.metrics.switch_flow_counts[switch_dpid] = []
            
            self.metrics.switch_packet_rates[switch_dpid].append(packet_rate)
            self.metrics.switch_flow_counts[switch_dpid].append(flow_count)
    
    def record_lb_decision(self, vip: str, selected_server: str, 
                            response_time_ms: float = None):
        """Record a load balancer decision."""
        with self._lock:
            self.metrics.lb_decisions.append({
                'timestamp': time.time(),
                'vip': vip,
                'server': selected_server,
                'response_time_ms': response_time_ms
            })
            
            if response_time_ms is not None:
                self.metrics.response_times.append(response_time_ms)
    
    def record_throughput(self, throughput: float):
        """Record throughput measurement (requests/sec or bytes/sec)."""
        with self._lock:
            self.metrics.throughput_samples.append(throughput)
    
    def record_migration(self, switch_dpid: int, from_controller: int,
                         to_controller: int, cost: float, reason: str = ''):
        """Record a switch migration event."""
        with self._lock:
            self.metrics.migrations.append({
                'timestamp': time.time(),
                'switch': switch_dpid,
                'from': from_controller,
                'to': to_controller,
                'cost': cost,
                'reason': reason
            })
            self.metrics.migration_costs.append(cost)
    
    def get_summary_stats(self) -> Dict[str, Any]:
        """Get summary statistics for the experiment."""
        with self._lock:
            variances = self.metrics.controller_variances
            response_times = self.metrics.response_times
            throughputs = self.metrics.throughput_samples
            
            return {
                'experiment_id': self.experiment_id,
                'duration_seconds': time.time() - self.metrics.start_time,
                'num_controllers': len(self.metrics.controller_loads),
                'num_switches': len(self.metrics.switch_packet_rates),
                'variance_stats': {
                    'mean': sum(variances) / len(variances) if variances else 0,
                    'min': min(variances) if variances else 0,
                    'max': max(variances) if variances else 0,
                    'samples': len(variances)
                },
                'response_time_stats': {
                    'mean': sum(response_times) / len(response_times) if response_times else 0,
                    'min': min(response_times) if response_times else 0,
                    'max': max(response_times) if response_times else 0,
                    'p95': self._percentile(response_times, 95),
                    'p99': self._percentile(response_times, 99),
                    'samples': len(response_times)
                },
                'throughput_stats': {
                    'mean': sum(throughputs) / len(throughputs) if throughputs else 0,
                    'max': max(throughputs) if throughputs else 0,
                    'samples': len(throughputs)
                },
                'lb_decisions': len(self.metrics.lb_decisions),
                'migrations': len(self.metrics.migrations),
                'total_migration_cost': sum(self.metrics.migration_costs)
            }
    
    def _percentile(self, data: List[float], percentile: int) -> float:
        """Calculate percentile of data."""
        if not data:
            return 0
        sorted_data = sorted(data)
        index = int(len(sorted_data) * percentile / 100)
        return sorted_data[min(index, len(sorted_data) - 1)]
    
    def export_json(self, filename: str = None) -> str:
        """Export all metrics to JSON file."""
        if filename is None:
            filename = f'experiment_{self.experiment_id}.json'
        
        filepath = self.output_dir / filename
        
        with self._lock:
            self.metrics.end_time = time.time()
            data = {
                'metrics': asdict(self.metrics),
                'summary': self.get_summary_stats(),
                'timestamps': self._timestamps
            }
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
        
        logger.info(f"Exported metrics to {filepath}")
        return str(filepath)
    
    def export_csv_summary(self, filename: str = None) -> str:
        """Export summary metrics to CSV."""
        if filename is None:
            filename = f'summary_{self.experiment_id}.csv'
        
        filepath = self.output_dir / filename
        
        with self._lock:
            summary = self.get_summary_stats()
        
        # Flatten the summary for CSV
        headers = []
        values = []
        
        for key, value in summary.items():
            if isinstance(value, dict):
                for sub_key, sub_value in value.items():
                    headers.append(f"{key}_{sub_key}")
                    values.append(str(sub_value))
            else:
                headers.append(key)
                values.append(str(value))
        
        with open(filepath, 'w') as f:
            f.write(','.join(headers) + '\n')
            f.write(','.join(values) + '\n')
        
        logger.info(f"Exported CSV summary to {filepath}")
        return str(filepath)
    
    def export_timeseries_csv(self, metric_name: str = 'variance',
                               filename: str = None) -> str:
        """Export time series data to CSV."""
        if filename is None:
            filename = f'timeseries_{metric_name}_{self.experiment_id}.csv'
        
        filepath = self.output_dir / filename
        
        with self._lock:
            if metric_name == 'variance':
                data = list(zip(self._timestamps, self.metrics.controller_variances))
                headers = 'timestamp,variance'
            elif metric_name == 'response_time':
                # Use lb_decisions for timestamps
                data = [(d['timestamp'], d.get('response_time_ms', 0)) 
                        for d in self.metrics.lb_decisions 
                        if d.get('response_time_ms')]
                headers = 'timestamp,response_time_ms'
            else:
                logger.warning(f"Unknown metric: {metric_name}")
                return ''
        
        with open(filepath, 'w') as f:
            f.write(headers + '\n')
            for ts, value in data:
                f.write(f"{datetime.fromtimestamp(ts).isoformat()},{value}\n")
        
        logger.info(f"Exported time series to {filepath}")
        return str(filepath)


class MultiControllerAggregator:
    """
    Aggregates metrics from multiple distributed controllers.
    
    Used for experiments with multiple Ryu controller instances.
    """
    
    def __init__(self, output_dir: str = '/app/data/metrics'):
        self.output_dir = Path(output_dir)
        self.controller_data: Dict[int, Dict] = {}
        self._lock = threading.Lock()
    
    def update_controller_metrics(self, controller_id: int, metrics: Dict):
        """Update metrics for a specific controller."""
        with self._lock:
            self.controller_data[controller_id] = {
                'timestamp': time.time(),
                **metrics
            }
    
    def get_system_load_variance(self) -> float:
        """Calculate load variance across all controllers."""
        with self._lock:
            loads = [data.get('total_load', 0) 
                     for data in self.controller_data.values()]
        
        if not loads:
            return 0.0
        
        mean_load = sum(loads) / len(loads)
        variance = sum((l - mean_load) ** 2 for l in loads) / len(loads)
        return variance
    
    def get_aggregated_metrics(self) -> Dict:
        """Get aggregated metrics from all controllers."""
        with self._lock:
            return {
                'num_controllers': len(self.controller_data),
                'controllers': dict(self.controller_data),
                'system_variance': self.get_system_load_variance(),
                'total_switches': sum(
                    data.get('switch_count', 0) 
                    for data in self.controller_data.values()
                ),
                'timestamp': time.time()
            }
