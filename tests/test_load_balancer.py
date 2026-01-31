"""
HYDRA-LB: Load Balancer Tests

Unit tests for load balancing algorithms.
"""

import pytest
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from controller.baselines.round_robin import RoundRobinBalancer, WeightedRoundRobinBalancer
from controller.baselines.least_load import (
    LeastLoadBalancer, 
    WeightedLeastConnectionsBalancer,
    LeastResponseTimeBalancer
)
from controller.load_balancer import LoadBalancerManager


class TestRoundRobinBalancer:
    """Tests for Round Robin load balancer."""
    
    def test_round_robin_basic(self):
        """Test basic round robin selection."""
        servers = ['10.0.0.1', '10.0.0.2', '10.0.0.3']
        lb = RoundRobinBalancer(servers)
        
        # Should cycle through servers
        assert lb.select_server() == '10.0.0.1'
        assert lb.select_server() == '10.0.0.2'
        assert lb.select_server() == '10.0.0.3'
        assert lb.select_server() == '10.0.0.1'  # Back to first
    
    def test_round_robin_single_server(self):
        """Test with single server."""
        lb = RoundRobinBalancer(['10.0.0.1'])
        
        for _ in range(5):
            assert lb.select_server() == '10.0.0.1'
    
    def test_round_robin_no_healthy_servers(self):
        """Test when no servers are healthy."""
        servers = ['10.0.0.1', '10.0.0.2']
        lb = RoundRobinBalancer(servers)
        
        lb.mark_server_unhealthy('10.0.0.1')
        lb.mark_server_unhealthy('10.0.0.2')
        
        assert lb.select_server() is None
    
    def test_round_robin_with_unhealthy(self):
        """Test that unhealthy servers are skipped."""
        servers = ['10.0.0.1', '10.0.0.2', '10.0.0.3']
        lb = RoundRobinBalancer(servers)
        
        lb.mark_server_unhealthy('10.0.0.2')
        
        # Should only return healthy servers
        results = [lb.select_server() for _ in range(6)]
        assert '10.0.0.2' not in results
        assert results.count('10.0.0.1') == 3
        assert results.count('10.0.0.3') == 3
    
    def test_round_robin_reset(self):
        """Test reset functionality."""
        lb = RoundRobinBalancer(['10.0.0.1', '10.0.0.2', '10.0.0.3'])
        
        lb.select_server()  # Get first
        lb.select_server()  # Get second
        lb.reset()
        
        assert lb.select_server() == '10.0.0.1'  # Back to first
    
    def test_round_robin_stats(self):
        """Test statistics tracking."""
        lb = RoundRobinBalancer(['10.0.0.1', '10.0.0.2'])
        
        for _ in range(10):
            lb.select_server()
        
        stats = lb.get_stats()
        assert stats['total_decisions'] == 10
        assert stats['servers_count'] == 2


class TestWeightedRoundRobinBalancer:
    """Tests for Weighted Round Robin load balancer."""
    
    def test_weighted_rr_distribution(self):
        """Test that weights affect distribution."""
        servers = ['10.0.0.1', '10.0.0.2']
        weights = [3.0, 1.0]  # 3:1 ratio
        
        lb = WeightedRoundRobinBalancer(servers, weights)
        
        # Count selections over many iterations
        counts = {'10.0.0.1': 0, '10.0.0.2': 0}
        for _ in range(100):
            server = lb.select_server()
            counts[server] += 1
        
        # Should be approximately 3:1 ratio
        ratio = counts['10.0.0.1'] / counts['10.0.0.2']
        assert 2.5 <= ratio <= 3.5  # Allow some variance


class TestLeastLoadBalancer:
    """Tests for Least Connections load balancer."""
    
    def test_least_load_basic(self):
        """Test basic least connections selection."""
        lb = LeastLoadBalancer(['10.0.0.1', '10.0.0.2', '10.0.0.3'])
        
        # First request should go to first server (all have 0 connections)
        first = lb.select_server()
        assert first in ['10.0.0.1', '10.0.0.2', '10.0.0.3']
        
        # After selecting, that server has 1 connection
        # Next request should go to a different server
        second = lb.select_server()
        # Both servers now have 1 connection each if different,
        # or first has 2 if same (depends on tie-breaking)
    
    def test_least_load_prefers_less_loaded(self):
        """Test that less loaded servers are preferred."""
        lb = LeastLoadBalancer(['10.0.0.1', '10.0.0.2'])
        
        # Simulate 10 connections to server 1
        for _ in range(10):
            lb.servers[0].active_connections += 1
        
        # Next request should go to server 2 (0 connections)
        assert lb.select_server() == '10.0.0.2'
    
    def test_least_load_connection_counts(self):
        """Test connection count tracking."""
        lb = LeastLoadBalancer(['10.0.0.1', '10.0.0.2'])
        
        # Simulate requests - first server gets selected
        first_server = lb.select_server()
        
        # After selecting, that server has 1 active connection
        counts = lb.get_connection_counts()
        assert counts[first_server] == 1
        
        # Record response (connection complete) 
        lb.record_response(first_server)
        
        # Now it should have 0 connections
        counts = lb.get_connection_counts()
        assert counts[first_server] == 0


class TestLeastResponseTimeBalancer:
    """Tests for Least Response Time load balancer."""
    
    def test_response_time_tracking(self):
        """Test response time recording."""
        lb = LeastResponseTimeBalancer(['10.0.0.1', '10.0.0.2'])
        
        # Record response times
        lb.record_response_time('10.0.0.1', 50.0)
        lb.record_response_time('10.0.0.1', 60.0)
        lb.record_response_time('10.0.0.2', 100.0)
        
        stats = lb.get_response_time_stats()
        
        assert stats['10.0.0.1']['avg'] == 55.0
        assert stats['10.0.0.2']['avg'] == 100.0
    
    def test_response_time_selection(self):
        """Test that faster servers are preferred."""
        lb = LeastResponseTimeBalancer(['10.0.0.1', '10.0.0.2'])
        
        # Server 1 is fast
        for _ in range(10):
            lb.record_response_time('10.0.0.1', 10.0)
        
        # Server 2 is slow
        for _ in range(10):
            lb.record_response_time('10.0.0.2', 100.0)
        
        # Should prefer server 1
        selections = [lb.select_server() for _ in range(10)]
        assert selections.count('10.0.0.1') > selections.count('10.0.0.2')


class TestLoadBalancerManager:
    """Tests for Load Balancer Manager."""
    
    def test_register_vip(self):
        """Test VIP registration."""
        manager = LoadBalancerManager()
        
        manager.register_vip('10.0.0.100', ['10.0.0.1', '10.0.0.2'], 
                             strategy='round_robin')
        
        balancer = manager.get_balancer('10.0.0.100')
        assert balancer is not None
        assert balancer.name == 'round_robin'
    
    def test_select_server_through_manager(self):
        """Test server selection through manager."""
        manager = LoadBalancerManager()
        manager.register_vip('10.0.0.100', ['10.0.0.1', '10.0.0.2'])
        
        server = manager.select_server('10.0.0.100')
        assert server in ['10.0.0.1', '10.0.0.2']
    
    def test_unknown_vip(self):
        """Test behavior with unknown VIP."""
        manager = LoadBalancerManager()
        
        assert manager.get_balancer('10.0.0.999') is None
        assert manager.select_server('10.0.0.999') is None
    
    def test_different_strategies(self):
        """Test different strategies for different VIPs."""
        manager = LoadBalancerManager()
        
        manager.register_vip('10.0.0.100', ['10.0.0.1', '10.0.0.2'], 
                             strategy='round_robin')
        manager.register_vip('10.0.0.200', ['10.0.0.3', '10.0.0.4'], 
                             strategy='least_load')
        
        assert manager.get_balancer('10.0.0.100').name == 'round_robin'
        assert manager.get_balancer('10.0.0.200').name == 'least_connections'
    
    def test_get_all_stats(self):
        """Test aggregated statistics."""
        manager = LoadBalancerManager()
        manager.register_vip('10.0.0.100', ['10.0.0.1', '10.0.0.2'])
        manager.register_vip('10.0.0.200', ['10.0.0.3', '10.0.0.4'])
        
        # Make some requests
        for _ in range(5):
            manager.select_server('10.0.0.100')
            manager.select_server('10.0.0.200')
        
        stats = manager.get_all_stats()
        assert '10.0.0.100' in stats
        assert '10.0.0.200' in stats


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
