# HYDRA-LB: Topology + Mininet Documentation

---

## 1. Overview

HYDRA-LB supports two data center network topologies for Mininet emulation:

| Topology | File | Use Case |
|---|---|---|
| **Fat-Tree** | `topology/fat_tree.py` | Default for all experiments |
| **Leaf-Spine** | `topology/leaf_spine.py` | Alternative two-tier |
| **Fat-Tree k=4** | `topology/fat_tree_k4.py` | Pre-generated Mininet script |

Both generators produce:
1. Switch and host names
2. Link topology (which nodes connect to which)
3. Complete Mininet Python scripts with Remote Controller configuration

---

## 2. Fat-Tree Topology

### 2.1 What is a Fat-Tree?

A Fat-Tree is a hierarchical network topology used in data centers. It was proposed by Al-Fares et al. (2008) and is based on a Clos network design. It has three tiers:

```
                  ┌───┐  ┌───┐
                  │ C1│  │ C2│  ← Core switches
                  └─┬─┘  └─┬─┘
                    │      │
         ┌──────┬──┼──┬───┘
         │      │  │  │
       ┌─┴─┐ ┌─┴─┐ ┌─┴─┐ ┌─┴─┐
       │A1 │ │A2 │ │A3 │ │A4 │  ← Aggregation switches
       └─┬─┘ └─┬─┘ └─┬─┘ └─┬─┘
         │      │     │      │
       ┌─┴─┐ ┌─┴─┐ ┌─┴─┐ ┌─┴─┐
       │E1 │ │E2 │ │E3 │ │E4 │  ← Edge (ToR) switches
       └─┬─┘ └─┬─┘ └─┬─┘ └─┬─┘
        /|\    /|\   /|\    /|\
       H H H  H H H H H H  H H H  ← Hosts
```

### 2.2 Parameterization

The **k parameter** controls the size of the Fat-Tree:

| k | Core | Aggregation | Edge | Total Switches | Hosts | Pods |
|---|---|---|---|---|---|---|
| **4** | 4 | 8 | 8 | **20** | 16 | 4 |
| 6 | 9 | 18 | 18 | 45 | 54 | 6 |
| 8 | 16 | 32 | 32 | 80 | 128 | 8 |

Formulas:
- Core switches: `(k/2)²`
- Aggregation switches: `k × (k/2)` = `k²/2`
- Edge switches: `k × (k/2)` = `k²/2`
- Total switches: `(k/2)² + k²`
- Hosts per edge switch: `k/2`
- Total hosts: `k³/4`
- **k must be even** (enforced by validation)

### 2.3 `FatTreeTopology` Class

```python
class FatTreeTopology:
    def __init__(self, k=4):
        if k % 2 != 0:
            raise ValueError(f"k must be even, got {k}")
        self.k = k
        self.num_pods = k
        self.total_core = (k // 2) ** 2
        self.total_agg = k * (k // 2)
        self.total_edge = k * (k // 2)
        self.total_switches = self.total_core + self.total_agg + self.total_edge
        self.total_hosts = k * k * k // 4
```

### 2.4 Name Generation (`generate_names()`)

Returns three lists: `(switches, hosts, links)`

**Naming convention**:
- Core: `c1`, `c2`, `c3`, `c4`
- Aggregation: `a{pod}_{index}` → `a1_1`, `a1_2`, `a2_1`, ...
- Edge: `e{pod}_{index}` → `e1_1`, `e1_2`, `e2_1`, ...
- Hosts: `h1`, `h2`, ..., `h16`

**Links** (for k=4):
```
Core-to-Aggregation: 16 links (each core connects to one agg per pod)
Aggregation-to-Edge: 8 links (each agg connects to all edges in its pod)
Edge-to-Host: 16 links (each edge connects to k/2 hosts)
Total: 40 links
```

### 2.5 Mininet Script Generation

```python
def generate_mininet_script(self, controllers=None, output_file=None):
```

Generates a complete Python script that:
1. Creates a `Mininet()` instance
2. Adds `RemoteController` connections to the specified controller IPs
3. Adds all switches (OVS, OpenFlow 1.3)
4. Adds all hosts
5. Adds all links
6. Provides `create_topology()` and `run()` functions

**Example controller config**:
```python
controllers=['172.20.0.10:6653', '172.20.0.11:6653', '172.20.0.12:6653']
```

Generates:
```python
c1 = net.addController('c1', controller=RemoteController, ip='172.20.0.10', port=6653)
c2 = net.addController('c2', controller=RemoteController, ip='172.20.0.11', port=6653)
c3 = net.addController('c3', controller=RemoteController, ip='172.20.0.12', port=6653)
```

---

## 3. Pre-Generated Fat-Tree k=4 (`topology/fat_tree_k4.py`)

This is a **ready-to-run** Mininet script (295 lines), used by the Docker container. It creates:

- **4 core switches**: `s_core_1` through `s_core_4`
- **8 aggregation switches**: `s_agg_1_1` through `s_agg_4_2`
- **8 edge switches**: `s_edge_1_1` through `s_edge_4_2`
- **16 hosts**: `h_1_1_1` through `h_4_2_2`
- **3 remote controllers**: `172.20.0.10:6653`, `172.20.0.11:6653`, `172.20.0.12:6653`

Key functions:

| Function | Purpose |
|---|---|
| `create_topology()` | Creates and returns the Mininet network (does not start it) |
| `run()` | Starts network, runs `pingAll`, opens CLI, stops network |

### Switch Configuration

All switches use:
- Protocol: OpenFlow 1.3 (`OVS, protocols='OpenFlow13'`)
- Fail mode: secure
- Connect to all 3 controllers simultaneously

### Host Configuration

Each host gets an IP from `10.0.0.0/24`:
```python
h_1_1_1 = net.addHost('h_1_1_1', ip='10.0.0.1/24')
h_1_1_2 = net.addHost('h_1_1_2', ip='10.0.0.2/24')
# ... through ...
h_4_2_2 = net.addHost('h_4_2_2', ip='10.0.0.16/24')
```

---

## 4. Leaf-Spine Topology

### 4.1 What is Leaf-Spine?

A two-tier topology widely used in modern data centers:

```
       ┌─────────┐  ┌─────────┐
       │ Spine 1  │  │ Spine 2  │     ← Spine layer (aggregation)
       └────┬┬────┘  └────┬┬────┘
            ││             ││
       ┌────┘└──┐    ┌────┘└──┐
       │        │    │        │
   ┌───┴───┐ ┌──┴──┐┌──┴──┐ ┌───┴───┐
   │ Leaf 1│ │Leaf 2││Leaf 3│ │ Leaf 4│   ← Leaf layer (ToR)
   └───┬───┘ └──┬──┘└──┬──┘ └───┬───┘
      /|\       /|\    /|\      /|\
     H H H    H H H  H H H   H H H      ← Hosts
```

**Key property**: Every leaf connects to every spine. This provides predictable latency (always exactly 2 hops between any two hosts on different leaves).

### 4.2 Parameterization

| Parameter | Default | Description |
|---|---|---|
| `num_leaves` | 4 | Number of leaf (ToR) switches |
| `num_spines` | 2 | Number of spine switches |
| `hosts_per_leaf` | 4 | Hosts attached to each leaf |

Derived values:
- Total switches: `num_leaves + num_spines`
- Total hosts: `num_leaves × hosts_per_leaf`
- Total links: `(num_leaves × num_spines) + (num_leaves × hosts_per_leaf)`

### 4.3 Controller Assignment

```python
def assign_switches_to_controllers(self, num_controllers):
    assignment = {}
    all_switches = list(self.spine_switches) + list(self.leaf_switches)
    for i, switch in enumerate(all_switches):
        assignment[switch] = (i % num_controllers) + 1
    return assignment
```

Round-robin assignment ensures balanced distribution. With 6 switches and 2 controllers:
- Controller 1: spine1, leaf1, leaf3
- Controller 2: spine2, leaf2, leaf4

---

## 5. Mininet Integration

### 5.1 How Switches Connect to Controllers

Each OVS switch in Mininet is configured with **multiple** controller connections:

```python
switch = net.addSwitch('s1', cls=OVSSwitch, protocols='OpenFlow13')
# All 3 controllers are added to the net
# OVS connects to all controllers simultaneously
```

**OpenFlow Multi-Controller**: OVS maintains connections to all controllers. Only the MASTER controller receives PacketIn messages and can install flows. SLAVE controllers can only read state (port/flow stats).

### 5.2 How the Docker Network Works

```
Docker network: hydra-net (172.20.0.0/24)
┌──────────────────────────────────────┐
│ ryu-controller-1: 172.20.0.10:6653   │ ← OpenFlow
│ ryu-controller-2: 172.20.0.11:6653   │ ← OpenFlow
│ ryu-controller-3: 172.20.0.12:6653   │ ← OpenFlow
│                                      │
│ hydra-mininet: 172.20.0.20           │
│   └─ Mininet process                 │
│      └─ OVS switches                │
│         └─ Connect to all 3 IPs     │
└──────────────────────────────────────┘
```

### 5.3 Parameters and Their Impact

| Change | Impact | Risk |
|---|---|---|
| **Increase k** (e.g., k=8) | More switches (80) and hosts (128) → higher load on controllers | Memory usage, slower convergence |
| **Increase hosts_per_leaf** | More source MAC addresses → larger MAC tables | Higher PacketIn rate during learning phase |
| **More controllers** | Better load distribution capacity | More inter-controller communication |
| **Single controller** | No load balancing possible | Baseline for comparison only |
| **Custom link delays** | Affects latency metrics | May trigger false migration decisions |

### 5.4 Constraints

1. **k must be even**: Fat-Tree math requires even k (enforced by `ValueError`)
2. **IP addressing**: Hosts use `10.0.0.0/24` → maximum 254 hosts. For k≥8, use a larger subnet
3. **OVS memory**: Each flow rule consumes OVS memory. Large topologies may exhaust container resources
4. **Controller CPU**: More switches = more PacketIn events = higher CPU. The monitoring thread's 1-second interval may be too fast for large topologies
5. **Link bandwidth**: Not explicitly configured (Mininet default: 10Mbps for software links). Experiments use iperf to control actual traffic volume

---

## 6. Generated Script Structure

Both generators produce scripts with the same structure:

```python
#!/usr/bin/env python3
from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.cli import CLI
from mininet.log import setLogLevel, info

def create_topology():
    """Create and return the Mininet network."""
    net = Mininet(controller=RemoteController, switch=OVSSwitch)

    # Add controllers
    c1 = net.addController('c1', controller=RemoteController,
                           ip='172.20.0.10', port=6653)
    # ...

    # Add switches
    s1 = net.addSwitch('s1', cls=OVSSwitch, protocols='OpenFlow13')
    # ...

    # Add hosts
    h1 = net.addHost('h1', ip='10.0.0.1/24')
    # ...

    # Add links
    net.addLink(s1, s2)
    # ...

    return net

def run():
    """Start the network, test, and clean up."""
    setLogLevel('info')
    net = create_topology()
    net.start()
    info('*** Running connectivity test\n')
    net.pingAll()
    info('*** Starting CLI\n')
    CLI(net)
    net.stop()

if __name__ == '__main__':
    run()
```
