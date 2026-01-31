"""
HYDRA-LB: Topology Tests

Unit tests for topology generators.
"""

import pytest
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from topology.fat_tree import FatTreeTopology, create_fat_tree
from topology.leaf_spine import LeafSpineTopology, create_leaf_spine


class TestFatTreeTopology:
    """Tests for Fat-Tree topology generator."""
    
    def test_fat_tree_k4_counts(self):
        """Test Fat-Tree k=4 produces correct node counts."""
        topo = FatTreeTopology(k=4)
        
        assert topo.total_core == 4, "k=4 should have 4 core switches"
        assert topo.total_agg == 8, "k=4 should have 8 aggregation switches"
        assert topo.total_edge == 8, "k=4 should have 8 edge switches"
        assert topo.total_switches == 20, "k=4 should have 20 total switches"
        assert topo.total_hosts == 16, "k=4 should have 16 hosts"
    
    def test_fat_tree_k6_counts(self):
        """Test Fat-Tree k=6 produces correct node counts."""
        topo = FatTreeTopology(k=6)
        
        assert topo.total_core == 9
        assert topo.total_agg == 18
        assert topo.total_edge == 18
        assert topo.total_switches == 45
        assert topo.total_hosts == 54
    
    def test_fat_tree_odd_k_raises(self):
        """Test that odd k values raise an error."""
        with pytest.raises(ValueError):
            FatTreeTopology(k=3)
        
        with pytest.raises(ValueError):
            FatTreeTopology(k=5)
    
    def test_fat_tree_generate_names(self):
        """Test that generate_names produces correct structure."""
        topo = FatTreeTopology(k=4)
        switches, hosts, links = topo.generate_names()
        
        assert len(switches) == 20
        assert len(hosts) == 16
        
        # Check switch naming
        assert 'c1' in switches  # Core switches
        assert 'a1_1' in switches  # Aggregation switches
        assert 'e1_1' in switches  # Edge switches
        
        # Check host naming
        assert 'h1' in hosts
        assert 'h16' in hosts
        
        # Check links exist
        assert len(links) > 0
        
        # Verify core-to-agg links (should have k * num_core = 4 * 4 = 16)
        core_agg_links = [(n1, n2) for n1, n2 in links 
                          if n1.startswith('c') and n2.startswith('a')]
        assert len(core_agg_links) == 16
    
    def test_fat_tree_mininet_script(self):
        """Test Mininet script generation."""
        topo = FatTreeTopology(k=4)
        script = topo.generate_mininet_script(controllers=['172.20.0.10:6653'])
        
        assert 'from mininet.net import Mininet' in script
        assert 'RemoteController' in script
        assert "ip='172.20.0.10'" in script
        assert 'def create_topology' in script
        assert 'def run' in script
    
    def test_fat_tree_topology_info(self):
        """Test topology info output."""
        topo = FatTreeTopology(k=4)
        info = topo.get_topology_info()
        
        assert info['type'] == 'fat_tree'
        assert info['k'] == 4
        assert info['core_switches'] == 4
        assert info['total_hosts'] == 16


class TestLeafSpineTopology:
    """Tests for Leaf-Spine topology generator."""
    
    def test_leaf_spine_default_counts(self):
        """Test default Leaf-Spine counts."""
        topo = LeafSpineTopology()  # 4 leaves, 2 spines, 4 hosts/leaf
        
        assert topo.num_leaves == 4
        assert topo.num_spines == 2
        assert topo.hosts_per_leaf == 4
        assert topo.total_switches == 6
        assert topo.total_hosts == 16
    
    def test_leaf_spine_custom_counts(self):
        """Test custom Leaf-Spine configuration."""
        topo = LeafSpineTopology(num_leaves=8, num_spines=4, hosts_per_leaf=8)
        
        assert topo.total_switches == 12
        assert topo.total_hosts == 64
    
    def test_leaf_spine_generate_names(self):
        """Test name generation."""
        topo = LeafSpineTopology(num_leaves=2, num_spines=2, hosts_per_leaf=2)
        switches, hosts, links = topo.generate_names()
        
        assert len(switches) == 4  # 2 spines + 2 leaves
        assert len(hosts) == 4  # 2 leaves * 2 hosts
        
        # Check naming
        assert 'spine1' in switches
        assert 'spine2' in switches
        assert 'leaf1' in switches
        assert 'leaf2' in switches
        
        # Each leaf should connect to all spines
        leaf_spine_links = [(n1, n2) for n1, n2 in links 
                            if 'leaf' in n1 and 'spine' in n2]
        assert len(leaf_spine_links) == 4  # 2 leaves * 2 spines
    
    def test_leaf_spine_controller_assignment(self):
        """Test switch-to-controller assignment."""
        topo = LeafSpineTopology(num_leaves=4, num_spines=2)
        assignment = topo.assign_switches_to_controllers(num_controllers=2)
        
        # Should have 6 switches assigned
        assert len(assignment) == 6
        
        # Each controller should get some switches
        controller_1_switches = [s for s, c in assignment.items() if c == 1]
        controller_2_switches = [s for s, c in assignment.items() if c == 2]
        
        assert len(controller_1_switches) == 3
        assert len(controller_2_switches) == 3
    
    def test_leaf_spine_mininet_script(self):
        """Test Mininet script generation."""
        topo = LeafSpineTopology()
        script = topo.generate_mininet_script(
            controllers=['172.20.0.10:6653', '172.20.0.11:6653']
        )
        
        assert 'from mininet.net import Mininet' in script
        assert "ip='172.20.0.10'" in script
        assert "ip='172.20.0.11'" in script
    
    def test_leaf_spine_topology_info(self):
        """Test topology info output."""
        topo = LeafSpineTopology(num_leaves=4, num_spines=2, hosts_per_leaf=4)
        info = topo.get_topology_info()
        
        assert info['type'] == 'leaf_spine'
        assert info['num_leaves'] == 4
        assert info['num_spines'] == 2
        assert info['total_hosts'] == 16


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
