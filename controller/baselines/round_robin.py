"""
HYDRA-LB: Round Robin Load Balancer

Simple round-robin load balancing - cycles through servers sequentially.
Used as a baseline for comparison with HYDRA-LB's advanced algorithms.
"""

import logging
from typing import Optional, List
import threading

from controller.load_balancer import BaseLoadBalancer

logger = logging.getLogger('hydra-lb.round_robin')


class RoundRobinBalancer(BaseLoadBalancer):
    """
    Round Robin Load Balancer
    
    Distributes requests evenly across all healthy servers in a circular fashion.
    Each request goes to the next server in the rotation.
    
    Complexity: O(1) per selection (amortized)
    
    Pros:
    - Simple and predictable
    - Even distribution over time
    - No state beyond current index
    
    Cons:
    - Ignores server load/capacity
    - No session affinity
    - Doesn't adapt to varying response times
    """
    
    def __init__(self, servers: List[str]):
        super().__init__(servers, name="round_robin")
        self._current_index = 0
        self._lock = threading.Lock()
        
        logger.info(f"Round Robin balancer initialized with {len(servers)} servers")
    
    def select_server(self, src_ip: str = None, dst_port: int = None,
                      **kwargs) -> Optional[str]:
        """
        Select the next server in the rotation.
        
        Args:
            src_ip: Source IP (unused in round robin)
            dst_port: Destination port (unused in round robin)
            
        Returns:
            IP of the selected server, or None if no healthy servers
        """
        healthy_servers = self.get_healthy_servers()
        
        if not healthy_servers:
            logger.warning("No healthy servers available")
            return None
        
        with self._lock:
            # Ensure index is within bounds after server changes
            self._current_index = self._current_index % len(healthy_servers)
            
            # Get the current server
            selected = healthy_servers[self._current_index]
            
            # Move to next server
            self._current_index = (self._current_index + 1) % len(healthy_servers)
        
        # Record the request
        self.record_request(selected.ip)
        
        logger.debug(f"Round Robin selected server: {selected.ip}")
        return selected.ip
    
    def reset(self):
        """Reset the rotation to the first server."""
        with self._lock:
            self._current_index = 0
        logger.debug("Round Robin rotation reset")


class WeightedRoundRobinBalancer(BaseLoadBalancer):
    """
    Weighted Round Robin Load Balancer
    
    Like round robin, but servers with higher weights get more requests.
    Weight determines how many requests a server receives per rotation cycle.
    
    Example: Server A (weight=3), Server B (weight=1)
    Sequence: A, A, A, B, A, A, A, B, ...
    """
    
    def __init__(self, servers: List[str], weights: List[float] = None):
        super().__init__(servers, name="weighted_round_robin")
        
        # Set weights (default to 1.0 for all)
        if weights:
            for i, weight in enumerate(weights):
                if i < len(self.servers):
                    self.servers[i].weight = weight
        
        self._lock = threading.Lock()
        self._current_weights = {s.ip: 0.0 for s in self.servers}
        
        logger.info(f"Weighted Round Robin balancer initialized")
    
    def select_server(self, src_ip: str = None, dst_port: int = None,
                      **kwargs) -> Optional[str]:
        """
        Select server based on weighted round robin.
        
        Uses the "smooth weighted round robin" algorithm for better distribution.
        """
        healthy_servers = self.get_healthy_servers()
        
        if not healthy_servers:
            logger.warning("No healthy servers available")
            return None
        
        with self._lock:
            # Calculate total weight
            total_weight = sum(s.weight for s in healthy_servers)
            
            # Add weight to current_weight for each server
            for server in healthy_servers:
                self._current_weights[server.ip] = \
                    self._current_weights.get(server.ip, 0) + server.weight
            
            # Select server with highest current weight
            selected = max(healthy_servers, 
                          key=lambda s: self._current_weights.get(s.ip, 0))
            
            # Reduce selected server's current weight
            self._current_weights[selected.ip] -= total_weight
        
        self.record_request(selected.ip)
        
        logger.debug(f"Weighted Round Robin selected: {selected.ip} (weight={selected.weight})")
        return selected.ip
