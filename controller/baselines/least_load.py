"""
HYDRA-LB: Least Load (Least Connections) Load Balancer

Routes requests to the server with the fewest active connections.
Used as a baseline for comparison with HYDRA-LB's advanced algorithms.
"""

import logging
from typing import Optional, List
import threading

from controller.load_balancer import BaseLoadBalancer

logger = logging.getLogger('hydra-lb.least_load')


class LeastLoadBalancer(BaseLoadBalancer):
    """
    Least Connections Load Balancer
    
    Routes requests to the server with the least active connections.
    Better than round robin when requests have varying processing times.
    
    Complexity: O(n) per selection where n = number of servers
    
    Pros:
    - Adapts to varying request durations
    - Prevents overloading slow servers
    - Simple to implement and understand
    
    Cons:
    - Requires connection tracking
    - All servers treated equally (ignores capacity differences)
    - Slight overhead for connection counting
    """
    
    def __init__(self, servers: List[str]):
        super().__init__(servers, name="least_connections")
        self._lock = threading.Lock()
        
        logger.info(f"Least Connections balancer initialized with {len(servers)} servers")
    
    def select_server(self, src_ip: str = None, dst_port: int = None,
                      **kwargs) -> Optional[str]:
        """
        Select the server with the fewest active connections.
        
        Args:
            src_ip: Source IP (unused)
            dst_port: Destination port (unused)
            
        Returns:
            IP of the selected server, or None if no healthy servers
        """
        healthy_servers = self.get_healthy_servers()
        
        if not healthy_servers:
            logger.warning("No healthy servers available")
            return None
        
        with self._lock:
            # Find server with minimum connections
            selected = min(healthy_servers, 
                          key=lambda s: s.active_connections)
        
        self.record_request(selected.ip)
        
        logger.debug(f"Least Connections selected: {selected.ip} "
                    f"(connections={selected.active_connections})")
        return selected.ip
    
    def get_connection_counts(self) -> dict:
        """Get current connection counts for all servers."""
        return {s.ip: s.active_connections for s in self.servers}


class WeightedLeastConnectionsBalancer(BaseLoadBalancer):
    """
    Weighted Least Connections Load Balancer
    
    Selects server based on: connections / weight
    Servers with higher weights can handle more connections proportionally.
    
    Example: 
    - Server A: weight=2, connections=4 → score = 4/2 = 2
    - Server B: weight=1, connections=3 → score = 3/1 = 3
    - Selected: Server A (lower score)
    """
    
    def __init__(self, servers: List[str], weights: List[float] = None):
        super().__init__(servers, name="weighted_least_connections")
        
        # Set weights (default to 1.0)
        if weights:
            for i, weight in enumerate(weights):
                if i < len(self.servers):
                    self.servers[i].weight = max(0.1, weight)  # Avoid division by zero
        
        self._lock = threading.Lock()
        
        logger.info(f"Weighted Least Connections balancer initialized")
    
    def select_server(self, src_ip: str = None, dst_port: int = None,
                      **kwargs) -> Optional[str]:
        """
        Select server with lowest connections-to-weight ratio.
        """
        healthy_servers = self.get_healthy_servers()
        
        if not healthy_servers:
            logger.warning("No healthy servers available")
            return None
        
        with self._lock:
            # Calculate score: connections / weight (lower is better)
            selected = min(healthy_servers,
                          key=lambda s: s.active_connections / s.weight)
        
        self.record_request(selected.ip)
        
        logger.debug(f"Weighted Least Connections selected: {selected.ip} "
                    f"(connections={selected.active_connections}, weight={selected.weight})")
        return selected.ip


class LeastResponseTimeBalancer(BaseLoadBalancer):
    """
    Least Response Time Load Balancer
    
    Routes to the server with the lowest average response time.
    Requires response time tracking from the controller.
    
    Note: This is a placeholder for when response time metrics are available.
    """
    
    def __init__(self, servers: List[str]):
        super().__init__(servers, name="least_response_time")
        self._lock = threading.Lock()
        
        # Response time tracking: {ip: [recent_response_times]}
        self._response_times = {s.ip: [] for s in self.servers}
        self._max_samples = 100  # Keep last 100 response times
        
        logger.info(f"Least Response Time balancer initialized")
    
    def record_response_time(self, server_ip: str, response_time_ms: float):
        """Record a response time measurement for a server."""
        with self._lock:
            if server_ip in self._response_times:
                times = self._response_times[server_ip]
                times.append(response_time_ms)
                # Keep only recent samples
                if len(times) > self._max_samples:
                    self._response_times[server_ip] = times[-self._max_samples:]
    
    def _get_avg_response_time(self, server_ip: str) -> float:
        """Get average response time for a server."""
        times = self._response_times.get(server_ip, [])
        if not times:
            return 0.0  # No data, assume fast
        return sum(times) / len(times)
    
    def select_server(self, src_ip: str = None, dst_port: int = None,
                      **kwargs) -> Optional[str]:
        """
        Select the server with the lowest average response time.
        """
        healthy_servers = self.get_healthy_servers()
        
        if not healthy_servers:
            logger.warning("No healthy servers available")
            return None
        
        with self._lock:
            # Calculate average response times
            server_times = {
                s.ip: self._get_avg_response_time(s.ip)
                for s in healthy_servers
            }
            
            # Select server with minimum average response time
            # Tie-break: prefer servers with fewer connections
            selected = min(healthy_servers,
                          key=lambda s: (server_times[s.ip], s.active_connections))
        
        self.record_request(selected.ip)
        
        logger.debug(f"Least Response Time selected: {selected.ip} "
                    f"(avg_time={server_times[selected.ip]:.2f}ms)")
        return selected.ip
    
    def get_response_time_stats(self) -> dict:
        """Get response time statistics for all servers."""
        with self._lock:
            return {
                ip: {
                    'avg': self._get_avg_response_time(ip),
                    'samples': len(times),
                    'min': min(times) if times else 0,
                    'max': max(times) if times else 0
                }
                for ip, times in self._response_times.items()
            }
