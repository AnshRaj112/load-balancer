"""
HYDRA-LB: Load Balancer Manager

Abstract base class and manager for load balancing strategies.
Handles switch-controller assignment and migration coordination.
"""

import logging
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger('hydra-lb.load_balancer')


@dataclass
class Server:
    """Represents a backend server for load balancing."""
    ip: str
    port: int = 80
    weight: float = 1.0
    active_connections: int = 0
    total_requests: int = 0
    healthy: bool = True
    
    def __hash__(self):
        return hash((self.ip, self.port))


@dataclass
class LoadBalancerStats:
    """Statistics for a load balancer instance."""
    total_requests: int = 0
    total_decisions: int = 0
    servers_count: int = 0
    healthy_servers: int = 0


class BaseLoadBalancer(ABC):
    """
    Abstract base class for load balancing algorithms.
    
    All load balancer implementations must inherit from this class
    and implement the select_server method.
    """
    
    def __init__(self, servers: List[str], name: str = "base"):
        """
        Initialize the load balancer.
        
        Args:
            servers: List of backend server IPs
            name: Name identifier for this balancer
        """
        self.name = name
        self.servers = [Server(ip=ip) for ip in servers]
        self.stats = LoadBalancerStats(servers_count=len(servers))
        
        logger.info(f"Initialized {name} load balancer with {len(servers)} servers")
    
    @abstractmethod
    def select_server(self, src_ip: str = None, dst_port: int = None, 
                      **kwargs) -> Optional[str]:
        """
        Select a backend server for the incoming request.
        
        Args:
            src_ip: Source IP of the request (for session affinity)
            dst_port: Destination port of the request
            **kwargs: Additional parameters for specific algorithms
            
        Returns:
            IP address of the selected server, or None if no server available
        """
        pass
    
    def get_healthy_servers(self) -> List[Server]:
        """Get list of healthy servers."""
        return [s for s in self.servers if s.healthy]
    
    def mark_server_unhealthy(self, ip: str):
        """Mark a server as unhealthy."""
        for server in self.servers:
            if server.ip == ip:
                server.healthy = False
                logger.warning(f"Server {ip} marked unhealthy")
                break
    
    def mark_server_healthy(self, ip: str):
        """Mark a server as healthy."""
        for server in self.servers:
            if server.ip == ip:
                server.healthy = True
                logger.info(f"Server {ip} marked healthy")
                break
    
    def add_server(self, ip: str, port: int = 80, weight: float = 1.0):
        """Add a new server to the pool."""
        server = Server(ip=ip, port=port, weight=weight)
        self.servers.append(server)
        self.stats.servers_count = len(self.servers)
        logger.info(f"Added server {ip}:{port} to {self.name}")
    
    def remove_server(self, ip: str):
        """Remove a server from the pool."""
        self.servers = [s for s in self.servers if s.ip != ip]
        self.stats.servers_count = len(self.servers)
        logger.info(f"Removed server {ip} from {self.name}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get current load balancer statistics."""
        healthy = len(self.get_healthy_servers())
        return {
            'name': self.name,
            'total_requests': self.stats.total_requests,
            'total_decisions': self.stats.total_decisions,
            'servers_count': self.stats.servers_count,
            'healthy_servers': healthy,
            'servers': [
                {
                    'ip': s.ip,
                    'port': s.port,
                    'weight': s.weight,
                    'active_connections': s.active_connections,
                    'total_requests': s.total_requests,
                    'healthy': s.healthy
                }
                for s in self.servers
            ]
        }
    
    def record_request(self, server_ip: str):
        """Record a request sent to a server."""
        self.stats.total_requests += 1
        self.stats.total_decisions += 1
        
        for server in self.servers:
            if server.ip == server_ip:
                server.total_requests += 1
                server.active_connections += 1
                break
    
    def record_response(self, server_ip: str):
        """Record a response from a server (connection completed)."""
        for server in self.servers:
            if server.ip == server_ip:
                server.active_connections = max(0, server.active_connections - 1)
                break


class LoadBalancerManager:
    """
    Manages multiple load balancer instances for different VIPs.
    
    Coordinates load balancing decisions and tracks overall statistics.
    """
    
    def __init__(self):
        self.balancers: Dict[str, BaseLoadBalancer] = {}
        self.default_strategy = 'round_robin'
        
        logger.info("Load Balancer Manager initialized")
    
    def register_vip(self, vip: str, servers: List[str], 
                      strategy: str = None) -> BaseLoadBalancer:
        """
        Register a virtual IP with its backend servers.
        
        Args:
            vip: Virtual IP address
            servers: List of backend server IPs
            strategy: Load balancing strategy (round_robin, least_load, etc.)
            
        Returns:
            The created load balancer instance
        """
        from controller.baselines.round_robin import RoundRobinBalancer
        from controller.baselines.least_load import LeastLoadBalancer
        
        strategy = strategy or self.default_strategy
        
        if strategy == 'round_robin':
            balancer = RoundRobinBalancer(servers)
        elif strategy == 'least_load':
            balancer = LeastLoadBalancer(servers)
        else:
            logger.warning(f"Unknown strategy {strategy}, using round_robin")
            balancer = RoundRobinBalancer(servers)
        
        self.balancers[vip] = balancer
        logger.info(f"Registered VIP {vip} with {strategy} strategy")
        
        return balancer
    
    def get_balancer(self, vip: str) -> Optional[BaseLoadBalancer]:
        """Get the load balancer for a VIP."""
        return self.balancers.get(vip)
    
    def select_server(self, vip: str, **kwargs) -> Optional[str]:
        """
        Select a server for the given VIP.
        
        Args:
            vip: Virtual IP address
            **kwargs: Additional parameters for the load balancer
            
        Returns:
            Selected server IP or None
        """
        balancer = self.balancers.get(vip)
        if balancer:
            return balancer.select_server(**kwargs)
        return None
    
    def get_all_stats(self) -> Dict[str, Any]:
        """Get statistics for all load balancers."""
        return {
            vip: balancer.get_stats()
            for vip, balancer in self.balancers.items()
        }
