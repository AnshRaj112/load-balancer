# HYDRA-LB Live Demonstration Guide

This document is a step-by-step walkthrough detailing how to conduct a live presentation of the **HYDRA-LB** intelligent load balancing framework.

## Preparation
Ensure Docker Desktop or the Docker daemon is running on your machine.
Ensure Port 3000 is open and unoccupied on your localhost for Grafana.

---

## The Demonstration

### Step 1: Bootstrapping the Cluster
In your terminal, navigate to the `load-balancer/` directory and run the fully automated demonstration script:

```bash
./run_demo.sh
```

**Talking Points:**
* Explain that this script automatically cleans the environment.
* Then, it boots 3 Ryu SDN controllers in parallel.
* Next, it generates a complex, 20-switch, k=4 Fat-Tree Mininet network.
* Finally, it waits for the controllers to connect to the switches and loads the PyTorch LSTM models into memory.

### Step 2: Displaying the Dashboard
The script will prompt you:
> The cluster is now online! Open your browser to the Live Dashboard: http://localhost:3000/d/hydra-lb-main/hydra-lb-controller-dashboard

Open this link. Log in with:
* **Username**: `admin`
* **Password**: `hydra`

**Talking Points:**
* Point out the **Controller Load** panels at the very top, which should initially show near-idle (1%-5%) status across the board.
* Show the **Load Prediction** graph and explain that the $>99\%$ accurate LSTM models are live-predicting traffic spikes $t+3$ timesteps (15 seconds) into the future.

### Step 3: Triggering the Burst Traffic
While you are talking, the script has silently initiated the `burst` traffic simulation payload in the background.

Within 10–20 seconds, your Grafana dashboard will react fiercely:
* You will see dramatic spikes in the **Packet Rate** charting.
* You will see Controller 1's **Load Score** begin to climb.

**Talking Points:**
* Explain to the audience that if this was ordinary static load balancing, Controller 1 would eventually crash.
* However, direct their attention back to the terminal where `./run_demo.sh` is running.

### Step 4: Live Physical Migration Logging
Back in the terminal, the `run_demo.sh` script will automatically begin tailing the immediate Docker logs of the three controllers. 

Wait for the following lines to appear:

```text
hydra-controller-2  | OPTIMIZER: Migration triggered! C1→C2 (predicted_var=290.7, improvement=26.6)
hydra-controller-2  | PROACTIVE LB: Migration recommended: C1→C2 reason=predicted_variance=290.7 > threshold=30.0
hydra-controller-1  | PHYSICAL MIGRATION: Offering switch 1 to C2 via http://172.20.0.11:9100/migrate
hydra-controller-2  | PHYSICAL MIGRATION: Claimed MASTER for switch 1 transferred from Controller 1
hydra-controller-1  | MIGRATION SUCCESS: Demoted to SLAVE for Switch 1
```

**Talking Points:**
* Trace through the logs line-by-line with the audience.
* Point out that the optimizer detected a massive `predicted_variance` anomaly ahead of time.
* Highlight the physical execution sequence: Controller 1 offered a struggling datapath switch to Controller 2 via a fast internal REST RPC proxy.
* Controller 2 accepted the load and automatically issued an `OFPRoleRequest` downward to the OVS layer, stripping Controller 1 to `SLAVE` and claiming `MASTER` ownership over the traffic processing physically.

### Step 5: Verification
Flick seamlessly back to the Grafana dashboard.
* Direct the audience to look at the **Controller Load** readouts again.
* They will visually witness the load percentage evenly distributing away from the spiked Controller 1, dropping across Controller 2 and Controller 3 evenly in order to preserve aggregate health dynamically.

### Step 6: Teardown
When the presentation is finished, simply hit `Ctrl+C` in the CLI to kill the log streamer.
To wipe the demo safely, run:
```bash
docker compose down
```
