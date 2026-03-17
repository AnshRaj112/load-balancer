#!/usr/bin/env python3
"""
HYDRA-LB: Fat-Tree k=4 Topology
Auto-generated Mininet topology script

Topology:
- 4 core switches
- 8 aggregation switches
- 8 edge switches
- 16 hosts
"""

from mininet.net import Mininet
from mininet.node import Controller, RemoteController, OVSSwitch
from mininet.cli import CLI
from mininet.log import setLogLevel, info
from mininet.link import TCLink

def create_topology():
    """Create and return the Fat-Tree topology."""
    
    net = Mininet(controller=None, switch=OVSSwitch, link=TCLink, autoSetMacs=True)
    
    info('*** Adding controllers\n')
    c0 = net.addController('c0', controller=RemoteController, ip='172.20.0.10', port=6653)
    c1 = net.addController('c1', controller=RemoteController, ip='172.20.0.11', port=6653)
    c2 = net.addController('c2', controller=RemoteController, ip='172.20.0.12', port=6653)
    
    info('*** Adding switches\n')
    c1 = net.addSwitch('c1', cls=OVSSwitch, protocols='OpenFlow13')
    c2 = net.addSwitch('c2', cls=OVSSwitch, protocols='OpenFlow13')
    c3 = net.addSwitch('c3', cls=OVSSwitch, protocols='OpenFlow13')
    c4 = net.addSwitch('c4', cls=OVSSwitch, protocols='OpenFlow13')
    a1_1 = net.addSwitch('a1_1', cls=OVSSwitch, protocols='OpenFlow13')
    a1_2 = net.addSwitch('a1_2', cls=OVSSwitch, protocols='OpenFlow13')
    e1_1 = net.addSwitch('e1_1', cls=OVSSwitch, protocols='OpenFlow13')
    e1_2 = net.addSwitch('e1_2', cls=OVSSwitch, protocols='OpenFlow13')
    a2_1 = net.addSwitch('a2_1', cls=OVSSwitch, protocols='OpenFlow13')
    a2_2 = net.addSwitch('a2_2', cls=OVSSwitch, protocols='OpenFlow13')
    e2_1 = net.addSwitch('e2_1', cls=OVSSwitch, protocols='OpenFlow13')
    e2_2 = net.addSwitch('e2_2', cls=OVSSwitch, protocols='OpenFlow13')
    a3_1 = net.addSwitch('a3_1', cls=OVSSwitch, protocols='OpenFlow13')
    a3_2 = net.addSwitch('a3_2', cls=OVSSwitch, protocols='OpenFlow13')
    e3_1 = net.addSwitch('e3_1', cls=OVSSwitch, protocols='OpenFlow13')
    e3_2 = net.addSwitch('e3_2', cls=OVSSwitch, protocols='OpenFlow13')
    a4_1 = net.addSwitch('a4_1', cls=OVSSwitch, protocols='OpenFlow13')
    a4_2 = net.addSwitch('a4_2', cls=OVSSwitch, protocols='OpenFlow13')
    e4_1 = net.addSwitch('e4_1', cls=OVSSwitch, protocols='OpenFlow13')
    e4_2 = net.addSwitch('e4_2', cls=OVSSwitch, protocols='OpenFlow13')
    
    info('*** Adding hosts\n')
    h1 = net.addHost('h1', ip='10.0.0.1/24')
    h2 = net.addHost('h2', ip='10.0.0.2/24')
    h3 = net.addHost('h3', ip='10.0.0.3/24')
    h4 = net.addHost('h4', ip='10.0.0.4/24')
    h5 = net.addHost('h5', ip='10.0.0.5/24')
    h6 = net.addHost('h6', ip='10.0.0.6/24')
    h7 = net.addHost('h7', ip='10.0.0.7/24')
    h8 = net.addHost('h8', ip='10.0.0.8/24')
    h9 = net.addHost('h9', ip='10.0.0.9/24')
    h10 = net.addHost('h10', ip='10.0.0.10/24')
    h11 = net.addHost('h11', ip='10.0.0.11/24')
    h12 = net.addHost('h12', ip='10.0.0.12/24')
    h13 = net.addHost('h13', ip='10.0.0.13/24')
    h14 = net.addHost('h14', ip='10.0.0.14/24')
    h15 = net.addHost('h15', ip='10.0.0.15/24')
    h16 = net.addHost('h16', ip='10.0.0.16/24')
    
    info('*** Creating links\n')
    net.addLink(c1, a1_1)
    net.addLink(c1, a2_1)
    net.addLink(c1, a3_1)
    net.addLink(c1, a4_1)
    net.addLink(c2, a1_2)
    net.addLink(c2, a2_2)
    net.addLink(c2, a3_2)
    net.addLink(c2, a4_2)
    net.addLink(c3, a1_1)
    net.addLink(c3, a2_1)
    net.addLink(c3, a3_1)
    net.addLink(c3, a4_1)
    net.addLink(c4, a1_2)
    net.addLink(c4, a2_2)
    net.addLink(c4, a3_2)
    net.addLink(c4, a4_2)
    net.addLink(a1_1, e1_1)
    net.addLink(a1_1, e1_2)
    net.addLink(a1_2, e1_1)
    net.addLink(a1_2, e1_2)
    net.addLink(a2_1, e2_1)
    net.addLink(a2_1, e2_2)
    net.addLink(a2_2, e2_1)
    net.addLink(a2_2, e2_2)
    net.addLink(a3_1, e3_1)
    net.addLink(a3_1, e3_2)
    net.addLink(a3_2, e3_1)
    net.addLink(a3_2, e3_2)
    net.addLink(a4_1, e4_1)
    net.addLink(a4_1, e4_2)
    net.addLink(a4_2, e4_1)
    net.addLink(a4_2, e4_2)
    net.addLink(e1_1, h1)
    net.addLink(e1_1, h2)
    net.addLink(e1_2, h3)
    net.addLink(e1_2, h4)
    net.addLink(e2_1, h5)
    net.addLink(e2_1, h6)
    net.addLink(e2_2, h7)
    net.addLink(e2_2, h8)
    net.addLink(e3_1, h9)
    net.addLink(e3_1, h10)
    net.addLink(e3_2, h11)
    net.addLink(e3_2, h12)
    net.addLink(e4_1, h13)
    net.addLink(e4_1, h14)
    net.addLink(e4_2, h15)
    net.addLink(e4_2, h16)
    
    return net

def run():
    """Run the topology."""
    setLogLevel('info')
    
    net = create_topology()
    
    info('*** Starting network\n')
    net.start()
    
    info('*** Testing connectivity\n')
    net.pingAll()
    
    info('*** Running CLI\n')
    CLI(net)
    
    info('*** Stopping network\n')
    net.stop()

if __name__ == '__main__':
    run()
