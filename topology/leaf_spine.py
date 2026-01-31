"""
HYDRA-LB: Leaf-Spine Topology Generator

Generates a Leaf-Spine data center topology for Mininet.
Common topology for modern data centers with predictable latency.
"""

import logging
from typing import List, Tuple, Optional
import os

logger = logging.getLogger('hydra-lb.topology.leaf_spine')


class LeafSpineTopology:
    """
    Leaf-Spine Topology Generator
    
    A Leaf-Spine topology consists of:
    - Spine layer: fully connected to all leaf switches
    - Leaf layer: connected to hosts and all spine switches
    
    Benefits:
    - Predictable latency (any host to any host is 3 hops)
    - High bandwidth and redundancy
    - Easy to scale horizontally
    """
    
    def __init__(self, num_leaves: int = 4, num_spines: int = 2,
                 hosts_per_leaf: int = 4):
        """
        Initialize Leaf-Spine topology.
        
        Args:
            num_leaves: Number of leaf switches
            num_spines: Number of spine switches
            hosts_per_leaf: Hosts connected to each leaf switch
        """
        self.num_leaves = num_leaves
        self.num_spines = num_spines
        self.hosts_per_leaf = hosts_per_leaf
        
        self.total_switches = num_leaves + num_spines
        self.total_hosts = num_leaves * hosts_per_leaf
        self.total_links = (num_leaves * num_spines) + (num_leaves * hosts_per_leaf)
        
        logger.info(f"Leaf-Spine: {num_leaves} leaves, {num_spines} spines, "
                   f"{self.total_hosts} hosts")
    
    def get_topology_info(self) -> dict:
        """Get topology information."""
        return {
            'type': 'leaf_spine',
            'num_leaves': self.num_leaves,
            'num_spines': self.num_spines,
            'hosts_per_leaf': self.hosts_per_leaf,
            'total_switches': self.total_switches,
            'total_hosts': self.total_hosts,
            'total_links': self.total_links
        }
    
    def generate_names(self) -> Tuple[List[str], List[str], List[Tuple[str, str]]]:
        """
        Generate switch names, host names, and links.
        
        Returns:
            Tuple of (switches, hosts, links)
        """
        switches = []
        hosts = []
        links = []
        
        # Generate spine switches: spine1, spine2, ...
        for i in range(self.num_spines):
            switches.append(f"spine{i+1}")
        
        # Generate leaf switches and hosts
        for leaf_idx in range(self.num_leaves):
            leaf_name = f"leaf{leaf_idx+1}"
            switches.append(leaf_name)
            
            # Connect leaf to all spines
            for spine_idx in range(self.num_spines):
                spine_name = f"spine{spine_idx+1}"
                links.append((leaf_name, spine_name))
            
            # Add hosts to this leaf
            for h in range(self.hosts_per_leaf):
                host_id = leaf_idx * self.hosts_per_leaf + h + 1
                host_name = f"h{host_id}"
                hosts.append(host_name)
                links.append((leaf_name, host_name))
        
        return switches, hosts, links
    
    def generate_mininet_script(self, controllers: List[str] = None,
                                  output_file: str = None) -> str:
        """
        Generate a Mininet Python script for this topology.
        
        Args:
            controllers: List of controller addresses (ip:port)
            output_file: Optional file path to write the script
            
        Returns:
            The generated Python script as a string
        """
        if controllers is None:
            controllers = ['172.20.0.10:6653']
        
        switches, hosts, links = self.generate_names()
        
        # Generate controller connection code
        controller_code = []
        for i, ctrl in enumerate(controllers):
            ip, port = ctrl.split(':')
            controller_code.append(
                f"    c{i} = net.addController('c{i}', controller=RemoteController, "
                f"ip='{ip}', port={port})"
            )
        
        # Generate switch creation code
        switch_code = []
        for sw in switches:
            switch_code.append(f"    {sw} = net.addSwitch('{sw}', cls=OVSSwitch, protocols='OpenFlow13')")
        
        # Generate host creation code with IPs
        host_code = []
        for i, host in enumerate(hosts):
            ip = f"10.0.0.{i+1}"
            host_code.append(f"    {host} = net.addHost('{host}', ip='{ip}/24')")
        
        # Generate link creation code
        link_code = []
        for n1, n2 in links:
            link_code.append(f"    net.addLink({n1}, {n2})")
        
        script = f'''#!/usr/bin/env python3
"""
HYDRA-LB: Leaf-Spine Topology
Auto-generated Mininet topology script

Topology:
- {self.num_spines} spine switches
- {self.num_leaves} leaf switches
- {self.total_hosts} hosts ({self.hosts_per_leaf} per leaf)
"""

from mininet.net import Mininet
from mininet.node import Controller, RemoteController, OVSSwitch
from mininet.cli import CLI
from mininet.log import setLogLevel, info
from mininet.link import TCLink

def create_topology():
    """Create and return the Leaf-Spine topology."""
    
    net = Mininet(controller=None, switch=OVSSwitch, link=TCLink, autoSetMacs=True)
    
    info('*** Adding controllers\\n')
{chr(10).join(controller_code)}
    
    info('*** Adding switches\\n')
{chr(10).join(switch_code)}
    
    info('*** Adding hosts\\n')
{chr(10).join(host_code)}
    
    info('*** Creating links\\n')
{chr(10).join(link_code)}
    
    return net

def run():
    """Run the topology."""
    setLogLevel('info')
    
    net = create_topology()
    
    info('*** Starting network\\n')
    net.start()
    
    info('*** Testing connectivity\\n')
    net.pingAll()
    
    info('*** Running CLI\\n')
    CLI(net)
    
    info('*** Stopping network\\n')
    net.stop()

if __name__ == '__main__':
    run()
'''
        
        if output_file:
            with open(output_file, 'w') as f:
                f.write(script)
            os.chmod(output_file, 0o755)
            logger.info(f"Generated Mininet script: {output_file}")
        
        return script
    
    def assign_switches_to_controllers(self, num_controllers: int) -> dict:
        """
        Assign switches to controllers for multi-controller experiments.
        
        Uses a simple round-robin assignment. Returns a mapping of
        switch_name -> controller_id.
        
        Args:
            num_controllers: Number of controllers
            
        Returns:
            Dict mapping switch names to controller IDs (1-indexed)
        """
        switches, _, _ = self.generate_names()
        assignment = {}
        
        for i, switch in enumerate(switches):
            controller_id = (i % num_controllers) + 1
            assignment[switch] = controller_id
        
        return assignment


def create_leaf_spine(num_leaves: int = 4, num_spines: int = 2,
                       hosts_per_leaf: int = 4,
                       controllers: List[str] = None,
                       output_file: str = None) -> LeafSpineTopology:
    """
    Convenience function to create a Leaf-Spine topology.
    
    Args:
        num_leaves: Number of leaf switches
        num_spines: Number of spine switches
        hosts_per_leaf: Hosts per leaf switch
        controllers: List of controller addresses
        output_file: Optional file to write Mininet script
        
    Returns:
        LeafSpineTopology instance
    """
    topo = LeafSpineTopology(
        num_leaves=num_leaves,
        num_spines=num_spines,
        hosts_per_leaf=hosts_per_leaf
    )
    
    if output_file:
        topo.generate_mininet_script(controllers=controllers, output_file=output_file)
    
    return topo


if __name__ == '__main__':
    # Example usage
    import sys
    
    leaves = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    spines = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    hosts = int(sys.argv[3]) if len(sys.argv) > 3 else 4
    
    topo = LeafSpineTopology(num_leaves=leaves, num_spines=spines, hosts_per_leaf=hosts)
    print(f"Leaf-Spine topology:")
    print(f"  Spine switches: {topo.num_spines}")
    print(f"  Leaf switches: {topo.num_leaves}")
    print(f"  Hosts per leaf: {topo.hosts_per_leaf}")
    print(f"  Total switches: {topo.total_switches}")
    print(f"  Total hosts: {topo.total_hosts}")
    print(f"  Total links: {topo.total_links}")
    
    # Generate script
    controllers = os.environ.get('CONTROLLERS', '172.20.0.10:6653').split(',')
    topo.generate_mininet_script(controllers=controllers,
                                  output_file=f'/app/topology/leaf_spine_{leaves}x{spines}.py')
