"""
HYDRA-LB: Proactive Load Optimizer

Uses LSTM predictions to make proactive load balancing decisions.
This is the core research contribution — transitioning from reactive
to predictive load management.

Algorithm:
    1. Collect current load + predictions from all peer controllers
    2. Compute predicted load variance across the cluster
    3. If predicted variance > threshold → compute migration plan
    4. Execute migrations by reassigning switches between controllers
"""

import os
import time
import logging
import threading
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from collections import deque

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

logger = logging.getLogger('hydra-lb.optimizer')


@dataclass
class ControllerState:
    """Snapshot of a controller's current and predicted load."""
    controller_id: int
    current_load: float = 0.0
    predicted_load: List[float] = field(default_factory=lambda: [0.0] * 5)
    switch_count: int = 0
    packet_rate: float = 0.0
    byte_rate: float = 0.0
    healthy: bool = True
    last_update: float = 0.0


@dataclass
class MigrationDecision:
    """A decision to migrate a switch from one controller to another."""
    switch_dpid: int
    from_controller: int
    to_controller: int
    reason: str
    predicted_improvement: float  # Expected variance reduction
    timestamp: float = 0.0


class ProactiveOptimizer:
    """
    Variance-aware proactive load optimizer.
    
    Uses LSTM predictions to forecast future load imbalance and
    triggers switch migrations BEFORE congestion occurs.
    
    Key design decisions:
    - Uses predicted load at t+3 (15s ahead) for decisions — enough
      lead time to execute migration before congestion hits
    - Migration threshold is adaptive based on cluster size
    - Cooldown period prevents oscillation (ping-pong migrations)
    """
    
    def __init__(
        self,
        controller_id: int,
        peer_addresses: List[str] = None,
        variance_threshold: float = 30.0,
        migration_cooldown: int = 30,
        prediction_horizon: int = 5,  # Use t+5 prediction (5s ahead at 1s intervals)
        migration_cost_weight: float = 0.3,
    ):
        self.controller_id = controller_id
        self.peer_addresses = peer_addresses or []
        self.variance_threshold = variance_threshold
        self.migration_cooldown = migration_cooldown
        self.prediction_horizon = prediction_horizon
        self.migration_cost_weight = migration_cost_weight
        
        # State tracking
        self.cluster_state: Dict[int, ControllerState] = {}
        self.migration_history: deque = deque(maxlen=100)
        self.last_migration_time: float = 0.0
        self.optimization_count: int = 0
        self.migrations_triggered: int = 0
        
        # Metrics for Prometheus
        self.current_variance: float = 0.0
        self.predicted_variance: float = 0.0
        self.last_decision: str = "none"
        self.cluster_balanced: bool = True
        
        # Initialize own state
        self.cluster_state[controller_id] = ControllerState(
            controller_id=controller_id
        )
        
        logger.info(
            f"ProactiveOptimizer initialized: controller={controller_id}, "
            f"threshold={variance_threshold}, cooldown={migration_cooldown}s, "
            f"horizon=t+{prediction_horizon}, peers={len(self.peer_addresses)}"
        )
    
    def update_local_state(
        self,
        load_score: float,
        predicted_load: List[float],
        switch_count: int,
        packet_rate: float,
        byte_rate: float,
        switch_dpids: List[int] = None,
    ):
        """Update state for the local controller."""
        state = self.cluster_state[self.controller_id]
        state.current_load = load_score
        state.predicted_load = predicted_load
        state.switch_count = switch_count
        state.packet_rate = packet_rate
        state.byte_rate = byte_rate
        state.healthy = True
        state.last_update = time.time()
    
    def fetch_peer_states(self):
        """
        Fetch load state from peer controllers via their metrics endpoints.
        
        Each controller exposes /metrics on port 9100 with:
        - hydra_load_score, hydra_packet_rate, hydra_switch_count
        - hydra_predicted_load_t1 through t5
        """
        if not REQUESTS_AVAILABLE:
            return
            
        for addr in self.peer_addresses:
            try:
                resp = requests.get(f"http://{addr}/metrics", timeout=2)
                if resp.status_code == 200:
                    self._parse_peer_metrics(resp.text, addr)
            except Exception as e:
                logger.debug(f"Could not reach peer {addr}: {e}")
    
    def _parse_peer_metrics(self, metrics_text: str, addr: str):
        """Parse Prometheus-format metrics from a peer controller."""
        peer_id = None
        load_score = 0.0
        packet_rate = 0.0
        switch_count = 0
        byte_rate = 0.0
        predicted = [0.0] * 5
        
        for line in metrics_text.split('\n'):
            if line.startswith('#') or not line.strip():
                continue
            try:
                # Parse: metric_name{labels} value
                parts = line.split('}')
                if len(parts) < 2:
                    continue
                metric_part = parts[0]
                value = float(parts[1].strip())
                
                if 'controller_id="' in metric_part:
                    cid = metric_part.split('controller_id="')[1].split('"')[0]
                    peer_id = int(cid)
                
                if 'hydra_load_score' in metric_part:
                    load_score = value
                elif 'hydra_packet_rate' in metric_part:
                    packet_rate = value
                elif 'hydra_switch_count' in metric_part:
                    switch_count = int(value)
                elif 'hydra_byte_rate' in metric_part:
                    byte_rate = value
                elif 'hydra_predicted_load_t' in metric_part:
                    for i in range(5):
                        if f'hydra_predicted_load_t{i+1}' in metric_part:
                            predicted[i] = value
                            break
            except (ValueError, IndexError):
                continue
        
        if peer_id is not None and peer_id != self.controller_id:
            self.cluster_state[peer_id] = ControllerState(
                controller_id=peer_id,
                current_load=load_score,
                predicted_load=predicted,
                switch_count=switch_count,
                packet_rate=packet_rate,
                byte_rate=byte_rate,
                healthy=True,
                last_update=time.time(),
            )
    
    def compute_variance(self, loads: List[float]) -> float:
        """Compute load variance across controllers."""
        if len(loads) < 2:
            return 0.0
        mean = sum(loads) / len(loads)
        return sum((l - mean) ** 2 for l in loads) / len(loads)
    
    def compute_imbalance_ratio(self, loads: List[float]) -> float:
        """Compute max/min load ratio (1.0 = perfect balance)."""
        if not loads or min(loads) <= 0:
            return 1.0
        return max(loads) / max(min(loads), 0.01)
    
    def optimize(self) -> Optional[MigrationDecision]:
        """
        Core optimization loop. Called periodically.
        
        Returns:
            MigrationDecision if action needed, None otherwise.
        """
        self.optimization_count += 1
        
        # Fetch latest peer states
        self.fetch_peer_states()
        
        # Need at least 2 controllers for optimization
        healthy_states = {
            cid: s for cid, s in self.cluster_state.items()
            if s.healthy and (time.time() - s.last_update) < 30
        }
        
        if len(healthy_states) < 2:
            self.last_decision = "insufficient_peers"
            return None
        
        # Cooldown check
        if time.time() - self.last_migration_time < self.migration_cooldown:
            self.last_decision = "cooldown"
            return None
        
        # Compute CURRENT variance
        current_loads = [s.current_load for s in healthy_states.values()]
        self.current_variance = self.compute_variance(current_loads)
        
        # Compute PREDICTED variance (using horizon step)
        predicted_loads = []
        if self.prediction_horizon <= 0:
            # Reactive strategy: forecast equals current
            for s in healthy_states.values():
                predicted_loads.append(s.current_load)
        else:
            h = min(self.prediction_horizon - 1, 4)  # 0-indexed
            for s in healthy_states.values():
                if s.predicted_load and len(s.predicted_load) > h and s.predicted_load[h] > 0:
                    predicted_loads.append(s.predicted_load[h])
                else:
                    predicted_loads.append(s.current_load)
        
        self.predicted_variance = self.compute_variance(predicted_loads)
        
        # Decision: is predicted variance going to exceed threshold?
        if self.predicted_variance <= self.variance_threshold:
            self.cluster_balanced = True
            self.last_decision = "balanced"
            return None
        
        # Find the overloaded and underloaded controllers
        max_load_cid = max(healthy_states, key=lambda c: predicted_loads[list(healthy_states.keys()).index(c)])
        min_load_cid = min(healthy_states, key=lambda c: predicted_loads[list(healthy_states.keys()).index(c)])
        
        max_state = healthy_states[max_load_cid]
        min_state = healthy_states[min_load_cid]
        
        # Only migrate if the overloaded controller has switches to give
        if max_state.switch_count <= 1:
            self.last_decision = "no_switches_to_migrate"
            return None
        
        # Compute expected improvement
        load_diff = predicted_loads[list(healthy_states.keys()).index(max_load_cid)] - \
                    predicted_loads[list(healthy_states.keys()).index(min_load_cid)]
        
        # Migration cost: don't migrate if improvement is marginal
        migration_cost = self.migration_cost_weight * load_diff
        expected_improvement = load_diff - migration_cost
        
        if expected_improvement <= 5.0:  # Minimum improvement threshold
            self.last_decision = "marginal_improvement"
            return None
        
        # Create migration decision
        self.cluster_balanced = False
        self.last_decision = "migrate"
        
        decision = MigrationDecision(
            switch_dpid=-1,  # Will be filled by the controller
            from_controller=max_load_cid,
            to_controller=min_load_cid,
            reason=f"predicted_variance={self.predicted_variance:.1f} > threshold={self.variance_threshold}",
            predicted_improvement=expected_improvement,
            timestamp=time.time(),
        )
        
        self.migrations_triggered += 1
        self.last_migration_time = time.time()
        self.migration_history.append(decision)
        
        logger.info(
            f"OPTIMIZER: Migration triggered! C{max_load_cid}→C{min_load_cid} "
            f"(predicted_var={self.predicted_variance:.1f}, "
            f"improvement={expected_improvement:.1f})"
        )
        
        return decision
    
    def get_metrics(self) -> Dict:
        """Return optimizer metrics for Prometheus export."""
        return {
            'current_variance': self.current_variance,
            'predicted_variance': self.predicted_variance,
            'optimization_count': self.optimization_count,
            'migrations_triggered': self.migrations_triggered,
            'cluster_balanced': 1 if self.cluster_balanced else 0,
            'last_decision': self.last_decision,
            'peer_count': len([s for s in self.cluster_state.values() 
                             if s.healthy and s.controller_id != self.controller_id]),
        }
    
    def get_prometheus_metrics(self) -> str:
        """Generate Prometheus-format metrics string."""
        m = self.get_metrics()
        cid = self.controller_id
        
        return f"""
# HELP hydra_load_variance_current Current load variance across cluster
# TYPE hydra_load_variance_current gauge
hydra_load_variance_current{{controller_id="{cid}"}} {m['current_variance']:.2f}

# HELP hydra_load_variance_predicted Predicted load variance (t+{self.prediction_horizon})
# TYPE hydra_load_variance_predicted gauge
hydra_load_variance_predicted{{controller_id="{cid}"}} {m['predicted_variance']:.2f}

# HELP hydra_optimizer_runs_total Total optimization cycles executed
# TYPE hydra_optimizer_runs_total counter
hydra_optimizer_runs_total{{controller_id="{cid}"}} {m['optimization_count']}

# HELP hydra_migrations_triggered_total Total migrations triggered
# TYPE hydra_migrations_triggered_total counter
hydra_migrations_triggered_total{{controller_id="{cid}"}} {m['migrations_triggered']}

# HELP hydra_cluster_balanced Whether the cluster is currently balanced
# TYPE hydra_cluster_balanced gauge
hydra_cluster_balanced{{controller_id="{cid}"}} {m['cluster_balanced']}

# HELP hydra_optimizer_peers Number of reachable peer controllers
# TYPE hydra_optimizer_peers gauge
hydra_optimizer_peers{{controller_id="{cid}"}} {m['peer_count']}
"""
