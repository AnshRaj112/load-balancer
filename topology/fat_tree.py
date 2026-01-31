"""
HYDRA-LB: Fat-Tree Topology Generator

Generates a Fat-Tree (k-ary) data center topology for Mininet.
Standard topology for SDN load balancing experiments.
"""

import logging
from typing import List, Tuple, Optional
import os

logger = logging.getLogger('hydra-lb.topology.fat_tree')


class FatTreeTopology:
    """
    Fat-Tree (k-ary) Topology Generator
    
    A k-ary fat tree consists of:
    - (k/2)^2 core switches
    - k pods, each with:
      - k/2 aggregation switches
      - k/2 edge switches
      - (k/2)^2 hosts per pod
    
    Total: k^3/4 hosts, 5k^2/4 switches
    
    For k=4:
    - 4 core switches
    - 8 aggregation switches (4 pods × 2)
    - 8 edge switches (4 pods × 2)
    - 16 hosts (4 pods × 4)
    - Total: 20 switches, 16 hosts
    """
    
    def __init__(self, k: int = 4):
        """
        Initialize Fat-Tree topology.
        
        Args:
            k: Fat-tree parameter (must be even). Default is 4.
        """
        if k % 2 != 0:
            raise ValueError("k must be even for Fat-Tree topology")
        
        self.k = k
        self.num_pods = k
        self.num_core = (k // 2) ** 2
        self.num_agg_per_pod = k // 2
        self.num_edge_per_pod = k // 2
        self.num_hosts_per_edge = k // 2
        
        # Calculated totals
        self.total_core = self.num_core
        self.total_agg = self.num_pods * self.num_agg_per_pod
        self.total_edge = self.num_pods * self.num_edge_per_pod
        self.total_switches = self.total_core + self.total_agg + self.total_edge
        self.total_hosts = self.num_pods * self.num_edge_per_pod * self.num_hosts_per_edge
        
        logger.info(f"Fat-Tree k={k}: {self.total_switches} switches, {self.total_hosts} hosts")
    
    def get_topology_info(self) -> dict:
        """Get topology information."""
        return {
            'type': 'fat_tree',
            'k': self.k,
            'num_pods': self.num_pods,
            'core_switches': self.total_core,
            'aggregation_switches': self.total_agg,
            'edge_switches': self.total_edge,
            'total_switches': self.total_switches,
            'total_hosts': self.total_hosts
        }
    
    def generate_names(self) -> Tuple[List[str], List[str], List[Tuple[str, str]]]:
        """
        Generate switch names, host names, and links.
        
        Returns:
            Tuple of (switches, hosts, links)
            - switches: List of switch names
            - hosts: List of host names  
            - links: List of (node1, node2) tuples
        """
        switches = []
        hosts = []
        links = []
        
        k = self.k
        
        # Generate core switches: c_<i>
        for i in range(self.num_core):
            switches.append(f"c{i+1}")
        
        # Generate aggregation and edge switches per pod
        for pod in range(self.num_pods):
            # Aggregation switches: a_<pod>_<i>
            for i in range(self.num_agg_per_pod):
                switches.append(f"a{pod+1}_{i+1}")
            
            # Edge switches: e_<pod>_<i>
            for i in range(self.num_edge_per_pod):
                switches.append(f"e{pod+1}_{i+1}")
                
                # Hosts connected to this edge switch
                for h in range(self.num_hosts_per_edge):
                    host_id = pod * self.num_edge_per_pod * self.num_hosts_per_edge + \
                              i * self.num_hosts_per_edge + h + 1
                    hosts.append(f"h{host_id}")
        
        # Generate links
        
        # Core to Aggregation links
        # Each core switch connects to one agg switch in each pod
        for core_idx in range(self.num_core):
            # Determine which agg switch in each pod this core connects to
            agg_offset = core_idx % self.num_agg_per_pod
            core_name = f"c{core_idx+1}"
            
            for pod in range(self.num_pods):
                agg_name = f"a{pod+1}_{agg_offset+1}"
                links.append((core_name, agg_name))
        
        # Aggregation to Edge links (within each pod)
        for pod in range(self.num_pods):
            for agg_idx in range(self.num_agg_per_pod):
                agg_name = f"a{pod+1}_{agg_idx+1}"
                
                for edge_idx in range(self.num_edge_per_pod):
                    edge_name = f"e{pod+1}_{edge_idx+1}"
                    links.append((agg_name, edge_name))
        
        # Edge to Host links
        for pod in range(self.num_pods):
            for edge_idx in range(self.num_edge_per_pod):
                edge_name = f"e{pod+1}_{edge_idx+1}"
                
                for h in range(self.num_hosts_per_edge):
                    host_id = pod * self.num_edge_per_pod * self.num_hosts_per_edge + \
                              edge_idx * self.num_hosts_per_edge + h + 1
                    host_name = f"h{host_id}"
                    links.append((edge_name, host_name))
        
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
HYDRA-LB: Fat-Tree k={self.k} Topology
Auto-generated Mininet topology script

Topology:
- {self.total_core} core switches
- {self.total_agg} aggregation switches
- {self.total_edge} edge switches
- {self.total_hosts} hosts
"""

from mininet.net import Mininet
from mininet.node import Controller, RemoteController, OVSSwitch
from mininet.cli import CLI
from mininet.log import setLogLevel, info
from mininet.link import TCLink

def create_topology():
    """Create and return the Fat-Tree topology."""
    
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


def create_fat_tree(k: int = 4, controllers: List[str] = None,
                     output_file: str = None) -> FatTreeTopology:
    """
    Convenience function to create a Fat-Tree topology.
    
    Args:
        k: Fat-tree parameter (must be even)
        controllers: List of controller addresses
        output_file: Optional file to write Mininet script
        
    Returns:
        FatTreeTopology instance
    """
    topo = FatTreeTopology(k=k)
    
    if output_file:
        topo.generate_mininet_script(controllers=controllers, output_file=output_file)
    
    return topo


if __name__ == '__main__':
    # Example usage
    import sys
    
    k = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    
    topo = FatTreeTopology(k=k)
    print(f"Fat-Tree k={k} topology:")
    print(f"  Core switches: {topo.total_core}")
    print(f"  Aggregation switches: {topo.total_agg}")
    print(f"  Edge switches: {topo.total_edge}")
    print(f"  Total switches: {topo.total_switches}")
    print(f"  Total hosts: {topo.total_hosts}")
    
    # Generate script
    controllers = os.environ.get('CONTROLLERS', '172.20.0.10:6653').split(',')
    topo.generate_mininet_script(controllers=controllers, 
                                  output_file=f'/app/topology/fat_tree_k{k}.py')
