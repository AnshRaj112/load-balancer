"""
HYDRA-LB: Main Ryu Controller Application with Comprehensive Monitoring

Features:
- L2 Learning Switch functionality
- Prometheus metrics endpoint for monitoring
- Flow statistics collection
- Switch connection tracking
- LSTM-based load prediction (Phase 2)
- Comprehensive performance metrics
"""

import os
import logging
import time
import threading
import resource
from collections import defaultdict
from http.server import HTTPServer, BaseHTTPRequestHandler

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, DEAD_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, ether_types

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('hydra-lb')

# Try to import predictor (optional - won't fail if not available)
try:
    from predictor import LoadPredictorInference
    PREDICTOR_AVAILABLE = True
except ImportError:
    PREDICTOR_AVAILABLE = False
    logger.info("Predictor module not available - running without predictions")

# Try to import optimizer
try:
    from optimizer import ProactiveOptimizer
    OPTIMIZER_AVAILABLE = True
except ImportError:
    OPTIMIZER_AVAILABLE = False
    logger.info("Optimizer module not available - running without proactive LB")


class MetricsHandler(BaseHTTPRequestHandler):
    """HTTP handler for Prometheus metrics endpoint."""
    
    controller = None
    
    def log_message(self, format, *args):
        pass  # Suppress HTTP logs
    
    def do_GET(self):
        if self.path == '/metrics':
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            metrics = self.controller.get_metrics() if self.controller else ""
            self.wfile.write(metrics.encode())
        elif self.path == '/health':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"status":"healthy"}')
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        """Handle incoming migration requests from other controllers."""
        if self.path == '/migrate':
            try:
                content_length = int(self.headers.get('Content-Length', 0))
                post_data = self.rfile.read(content_length)
                import json
                data = json.loads(post_data.decode('utf-8'))
                
                dpid = data.get('dpid')
                from_cid = data.get('from_controller')
                
                if dpid is None:
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(b"Missing dpid")
                    return
                    
                if self.controller:
                    datapath = self.controller.datapaths.get(dpid)
                    if datapath:
                        self.controller.set_role(datapath, is_master=True)
                        logger.info(f"PHYSICAL MIGRATION: Claimed MASTER for switch {dpid} transferred from Controller {from_cid}")
                        
                        self.send_response(200)
                        self.end_headers()
                        self.wfile.write(b"OK")
                    else:
                        self.send_response(404)
                        self.end_headers()
                        self.wfile.write(b"Datapath not found")
                else:
                    self.send_response(500)
                    self.end_headers()
                    self.wfile.write(b"Controller not linked")
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(str(e).encode())
        else:
            self.send_response(404)
            self.end_headers()


class HydraController(app_manager.RyuApp):
    """
    HYDRA-LB Main Controller Application with Monitoring and Prediction
    """
    
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(HydraController, self).__init__(*args, **kwargs)
        self.mac_to_port = {}
        self.controller_id = int(os.environ.get('CONTROLLER_ID', 1))
        self.datapaths = {}
        self.master_switches = set()

        # Core metrics
        self.packet_in_count = 0
        self.packet_out_count = 0
        self.flow_count = 0
        self.switch_count = 0
        self.bytes_total = 0
        self.start_time = time.time()
        
        # Rate metrics
        self.last_packet_in_count = 0
        self.last_bytes_total = 0
        self.last_stats_time = time.time()
        self.packet_rate = 0.0
        self.byte_rate = 0.0
        
        # Latency tracking
        self.request_latencies = []
        self.avg_latency_ms = 0.0
        self.max_latency_ms = 0.0
        
        # Load score (0-100)
        self.load_score = 0.0
        
        # Prediction
        self.predictor = None
        self.predicted_load = [-1.0] * 5
        self._init_predictor()
        
        # Proactive Optimizer
        self.optimizer = None
        self._init_optimizer()
        
        # Start servers and threads
        MetricsHandler.controller = self
        self._start_metrics_server()
        self._start_monitoring_thread()
        
        logger.info(f"HYDRA Controller {self.controller_id} initialized with monitoring + optimizer")

    def _init_predictor(self):
        """Initialize the load predictor if model is available."""
        if not PREDICTOR_AVAILABLE:
            logger.info("Predictor module not loaded")
            return
            
        model_path = os.environ.get('MODEL_PATH', '/app/models/lstm_predictor.pt')
        
        if os.path.exists(model_path):
            try:
                self.predictor = LoadPredictorInference(model_path)
                logger.info(f"Loaded prediction model from {model_path}")
            except Exception as e:
                logger.warning(f"Failed to load prediction model: {e}")
        else:
            logger.info(f"No prediction model found at {model_path}")

    def _init_optimizer(self):
        """Initialize the proactive load optimizer."""
        lb_strategy = os.environ.get('LB_STRATEGY', 'hydra_proactive')
        logger.info(f"Initializing LB strategy: {lb_strategy}")
        
        if not OPTIMIZER_AVAILABLE or lb_strategy == 'round_robin':
            logger.info("Optimizer disabled (round_robin strategy or module unavailable)")
            return
            
        horizon = 3 if lb_strategy == 'hydra_proactive' else 0
        
        # Build peer addresses from environment
        peer_addrs = []
        for i in range(1, 4):  # Controllers 1-3
            if i != self.controller_id:
                peer_addrs.append(f"172.20.0.{9+i}:9100")
        
        self.optimizer = ProactiveOptimizer(
            controller_id=self.controller_id,
            peer_addresses=peer_addrs,
            variance_threshold=float(os.environ.get('VARIANCE_THRESHOLD', '30.0')),
            migration_cooldown=int(os.environ.get('MIGRATION_COOLDOWN', '30')),
            prediction_horizon=horizon
        )
        logger.info(f"Proactive optimizer initialized with {len(peer_addrs)} peers")

    def _start_metrics_server(self):
        """Start HTTP server for Prometheus metrics on port 9100."""
        def run_server():
            server = HTTPServer(('0.0.0.0', 9100), MetricsHandler)
            logger.info("Metrics server started on port 9100")
            server.serve_forever()
        
        thread = threading.Thread(target=run_server, daemon=True)
        thread.start()

    def _start_monitoring_thread(self):
        """Start thread that updates metrics periodically."""
        def update_loop():
            while True:
                time.sleep(1)
                self._request_stats()
                self._calculate_rates()
                self._calculate_load_score()
                self._update_predictions()
                self._run_optimizer()
        
        thread = threading.Thread(target=update_loop, daemon=True)
        thread.start()

    def _request_stats(self):
        """Send stats request to all connected datapaths."""
        for datapath in list(self.datapaths.values()):
            ofp = datapath.ofproto
            parser = datapath.ofproto_parser
            
            # Request port stats for byte/packet count
            req = parser.OFPPortStatsRequest(datapath, 0, ofp.OFPP_ANY)
            datapath.send_msg(req)
            
            # Request flow stats for flow count
            req = parser.OFPFlowStatsRequest(datapath)
            datapath.send_msg(req)

    def _calculate_rates(self):
        """Calculate rate metrics."""
        now = time.time()
        elapsed = now - self.last_stats_time
        if elapsed > 0:
            if not hasattr(self, 'data_packets_total'):
                self.data_packets_total = 0
            if not hasattr(self, 'last_data_packets_total'):
                self.last_data_packets_total = 0
                
            self.packet_rate = max(0.0, (self.data_packets_total - self.last_data_packets_total) / elapsed)
            self.byte_rate = max(0.0, (self.bytes_total - self.last_bytes_total) / elapsed)
            
        self.last_data_packets_total = getattr(self, 'data_packets_total', 0)
        self.last_bytes_total = self.bytes_total
        self.last_stats_time = now
        
        # Calculate latency stats
        if self.request_latencies:
            self.avg_latency_ms = sum(self.request_latencies) / len(self.request_latencies)
            self.max_latency_ms = max(self.request_latencies)
            self.request_latencies = []  # Reset for next interval

    def _calculate_load_score(self):
        """Calculate a normalized load score (0-100)."""
        # Weighted combination of metrics
        # Mininet uses up to 3000 pps, so scale packet rate down by 30 to make it comparable to 100
        packet_score = min(100, self.packet_rate / 30.0)  
        flow_score = min(100, self.flow_count * 10.0)     
        switch_score = min(100, self.switch_count * 20.0) 
        
        self.load_score = (packet_score * 0.5 + flow_score * 0.3 + switch_score * 0.2)

    def _update_predictions(self):
        """Update load predictions if predictor is available."""
        if self.predictor is None:
            return
            
        # Scale inputs down by 30 to match the synthetic data distributions
        # The LSTM was trained on synthetic data where packet_rate was ~50-100
        # By scaling down both packet_rate and byte_rate by 30, we align live
        # high-throughput traffic with the training normalizations.
        scaled_packet_rate = self.packet_rate / 30.0
        scaled_byte_rate = self.byte_rate / 30.0
        
        self.predictor.add_observation(
            packet_rate=scaled_packet_rate,
            flow_count=float(self.flow_count),
            byte_rate=scaled_byte_rate,
            switch_count=float(self.switch_count)
        )
        
        # Get predictions (the model directly outputs the predicted scaled packet rate)
        predictions = self.predictor.get_all_predictions()
        if predictions:
            predicted_scores = []
            for t in range(1, 6):
                pred_scaled_pr = predictions.get(f't+{t}', -1)
                if pred_scaled_pr == -1:
                    predicted_scores.append(-1.0)
                else:
                    # Convert the predicted scaled packet rate directly to a load score
                    p_score = min(100, max(0, pred_scaled_pr))
                    f_score = min(100, self.flow_count * 10.0)
                    s_score = min(100, self.switch_count * 20.0)
                    predicted_load_score = (p_score * 0.5 + f_score * 0.3 + s_score * 0.2)
                    predicted_scores.append(predicted_load_score)
                    
            self.predicted_load = predicted_scores

    def _run_optimizer(self):
        """Run proactive optimization cycle."""
        if self.optimizer is None:
            return
        
        # Update optimizer with local state
        self.optimizer.update_local_state(
            load_score=self.load_score,
            predicted_load=self.predicted_load,
            switch_count=self.switch_count,
            packet_rate=self.packet_rate,
            byte_rate=self.byte_rate,
            switch_dpids=list(self.master_switches),
        )
        
        # Run optimization
        decision = self.optimizer.optimize()
        
        if decision is not None:
            logger.info(
                f"PROACTIVE LB: Migration recommended: "
                f"C{decision.from_controller}→C{decision.to_controller} "
                f"reason={decision.reason}"
            )
            # Execute the physical migration using OpenFlow roles and REST RPC
            self._execute_migration(decision)
            self._record_migration_event(decision)
    
    def _execute_migration(self, decision):
        """Physically execute the migration using OpenFlow Role Requests and a REST API exchange."""
        if decision.from_controller == self.controller_id:
            # We are the overloaded controller. We initiate the migration.
            if not getattr(self, 'master_switches', set()):
                return
            
            # Select an arbitrary master switch to migrate to shed load
            dpid_to_migrate = list(self.master_switches)[0]
            decision.switch_dpid = dpid_to_migrate
            
            # Send HTTP POST to the target peer controller (it runs metrics on 9100)
            target_ip = f"172.20.0.1{decision.to_controller - 1}:9100"
            url = f"http://{target_ip}/migrate"
            data = {
                "dpid": dpid_to_migrate,
                "from_controller": self.controller_id
            }
            
            try:
                import requests
                logger.info(f"PHYSICAL MIGRATION: Offering switch {dpid_to_migrate} to C{decision.to_controller} via {url}")
                resp = requests.post(url, json=data, timeout=2)
                if resp.status_code == 200:
                    # Switch successfully claimed by peer. Mark local state as SLAVE.
                    datapath = self.datapaths.get(dpid_to_migrate)
                    if datapath:
                        self.set_role(datapath, is_master=False)
                        logger.info(f"MIGRATION SUCCESS: Demoted to SLAVE for Switch {dpid_to_migrate}")
                else:
                    logger.warning(f"MIGRATION FAILED: Target rejected with status {resp.status_code}")
            except Exception as e:
                logger.error(f"Migration RPC to {target_ip} failed: {e}")
    
    def _record_migration_event(self, decision):
        """Record a migration event for analysis."""
        import csv
        from datetime import datetime
        
        log_path = '/app/data/metrics/migration_log.csv'
        try:
            file_exists = os.path.exists(log_path)
            with open(log_path, 'a') as f:
                writer = csv.writer(f)
                if not file_exists:
                    writer.writerow([
                        'timestamp', 'from_controller', 'to_controller',
                        'reason', 'predicted_improvement', 'current_variance',
                        'predicted_variance'
                    ])
                writer.writerow([
                    datetime.now().isoformat(),
                    decision.from_controller,
                    decision.to_controller,
                    decision.reason,
                    f"{decision.predicted_improvement:.2f}",
                    f"{self.optimizer.current_variance:.2f}",
                    f"{self.optimizer.predicted_variance:.2f}",
                ])
        except Exception as e:
            logger.debug(f"Could not write migration log: {e}")

    def get_metrics(self):
        """Generate Prometheus-format metrics."""
        uptime = time.time() - self.start_time
        
        # Get CPU and memory usage
        try:
            rusage = resource.getrusage(resource.RUSAGE_SELF)
            cpu_time = rusage.ru_utime + rusage.ru_stime
            memory_mb = rusage.ru_maxrss / 1024  # Convert to MB
        except:
            cpu_time = 0
            memory_mb = 0
        
        metrics = f"""# HELP hydra_controller_info Controller information
# TYPE hydra_controller_info gauge
hydra_controller_info{{controller_id="{self.controller_id}"}} 1

# HELP hydra_uptime_seconds Controller uptime in seconds
# TYPE hydra_uptime_seconds counter
hydra_uptime_seconds{{controller_id="{self.controller_id}"}} {uptime:.2f}

# HELP hydra_packet_in_total Total packet-in events received
# TYPE hydra_packet_in_total counter
hydra_packet_in_total{{controller_id="{self.controller_id}"}} {self.packet_in_count}

# HELP hydra_packet_out_total Total packet-out messages sent
# TYPE hydra_packet_out_total counter
hydra_packet_out_total{{controller_id="{self.controller_id}"}} {self.packet_out_count}

# HELP hydra_packet_rate Packets per second (current rate)
# TYPE hydra_packet_rate gauge
hydra_packet_rate{{controller_id="{self.controller_id}"}} {self.packet_rate:.2f}

# HELP hydra_byte_rate Bytes per second (current rate)
# TYPE hydra_byte_rate gauge
hydra_byte_rate{{controller_id="{self.controller_id}"}} {self.byte_rate:.2f}

# HELP hydra_flow_count Number of flows installed
# TYPE hydra_flow_count gauge
hydra_flow_count{{controller_id="{self.controller_id}"}} {self.flow_count}

# HELP hydra_switch_count Number of connected switches
# TYPE hydra_switch_count gauge
hydra_switch_count{{controller_id="{self.controller_id}"}} {self.switch_count}

# HELP hydra_bytes_total Total bytes processed
# TYPE hydra_bytes_total counter
hydra_bytes_total{{controller_id="{self.controller_id}"}} {self.bytes_total}

# HELP hydra_mac_table_size Number of learned MAC addresses
# TYPE hydra_mac_table_size gauge
hydra_mac_table_size{{controller_id="{self.controller_id}"}} {sum(len(v) for v in self.mac_to_port.values())}

# HELP hydra_load_score Current load score (0-100)
# TYPE hydra_load_score gauge
hydra_load_score{{controller_id="{self.controller_id}"}} {self.load_score:.2f}

# HELP hydra_cpu_seconds_total Total CPU time used
# TYPE hydra_cpu_seconds_total counter
hydra_cpu_seconds_total{{controller_id="{self.controller_id}"}} {cpu_time:.2f}

# HELP hydra_memory_mb Current memory usage in MB
# TYPE hydra_memory_mb gauge
hydra_memory_mb{{controller_id="{self.controller_id}"}} {memory_mb:.2f}

# HELP hydra_latency_avg_ms Average request latency
# TYPE hydra_latency_avg_ms gauge
hydra_latency_avg_ms{{controller_id="{self.controller_id}"}} {self.avg_latency_ms:.2f}

# HELP hydra_latency_max_ms Maximum request latency
# TYPE hydra_latency_max_ms gauge
hydra_latency_max_ms{{controller_id="{self.controller_id}"}} {self.max_latency_ms:.2f}
"""
        
        # Add prediction metrics if available
        if self.predictor is not None and self.predictor.model_loaded:
            for i, pred in enumerate(self.predicted_load):
                if pred >= 0:
                    metrics += f"""
# HELP hydra_predicted_load_t{i+1} Predicted load at t+{i+1}
# TYPE hydra_predicted_load_t{i+1} gauge
hydra_predicted_load_t{i+1}{{controller_id="{self.controller_id}"}} {pred:.2f}
"""
        
        # Add optimizer metrics if available
        if self.optimizer is not None:
            metrics += self.optimizer.get_prometheus_metrics()
        
        return metrics

    @set_ev_cls(ofp_event.EventOFPStateChange, [MAIN_DISPATCHER, DEAD_DISPATCHER])
    def state_change_handler(self, ev):
        """Track switch connect/disconnect events and assign roles."""
        datapath = ev.datapath
        if ev.state == DEAD_DISPATCHER:
            if datapath.id and datapath.id in self.datapaths:
                del self.datapaths[datapath.id]
            if datapath.id and datapath.id in self.master_switches:
                self.master_switches.remove(datapath.id)
                self.switch_count = len(self.master_switches)
                logger.info(f"Switch {datapath.id} DISCONNECTED from Controller {self.controller_id}")

    def set_role(self, datapath, is_master):
        """Send an OpenFlow Role Request to explicitly claim MASTER or SLAVE."""
        ofp = datapath.ofproto
        parser = datapath.ofproto_parser
        role = ofp.OFPCR_ROLE_MASTER if is_master else ofp.OFPCR_ROLE_SLAVE
        # Ensure generation ID is a valid 64-bit unsigned integer
        gen_id = int(time.time() * 1000000) & 0xffffffffffffffff
        
        req = parser.OFPRoleRequest(datapath, role, gen_id)
        datapath.send_msg(req)
        
        if is_master:
            self.master_switches.add(datapath.id)
            logger.info(f"Switch {datapath.id} -> ASSIGNED to Controller {self.controller_id} (MASTER)")
        else:
            self.master_switches.discard(datapath.id)
            logger.info(f"Switch {datapath.id} -> IGNORED by Controller {self.controller_id} (SLAVE)")
            
        self.switch_count = len(self.master_switches)

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        """Register switch and install table-miss flow entry when switch connects."""
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        dpid = datapath.id

        if dpid not in self.datapaths:
            self.datapaths[dpid] = datapath
            
            # Assign initial role based on simple modulo distribution
            # Since there are 3 controllers, distribute switches equally
            is_master = (dpid % 3) == (self.controller_id % 3)
            self.set_role(datapath, is_master)

        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                          ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, 0, match, actions)

    def add_flow(self, datapath, priority, match, actions, buffer_id=None):
        """Add a flow entry to the switch."""
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS,
                                             actions)]
        if buffer_id:
            mod = parser.OFPFlowMod(datapath=datapath, buffer_id=buffer_id,
                                    priority=priority, match=match,
                                    instructions=inst)
        else:
            mod = parser.OFPFlowMod(datapath=datapath, priority=priority,
                                    match=match, instructions=inst)
        datapath.send_msg(mod)
        self.flow_count += 1

    @set_ev_cls(ofp_event.EventOFPPortStatsReply, MAIN_DISPATCHER)
    def _port_stats_reply_handler(self, ev):
        """Handle port stats replies."""
        dpid = ev.msg.datapath.id
        if dpid not in self.master_switches:
            return
            
        body = ev.msg.body
        
        if not hasattr(self, 'port_stats'):
            self.port_stats = {}
            
        total_bytes = 0
        total_packets = 0
        for stat in body:
            # Sum rx_bytes and rx_packets across all ports to represent incoming traffic to the switch
            total_bytes += stat.rx_bytes
            total_packets += stat.rx_packets
            
        self.port_stats[dpid] = (total_bytes, total_packets)
        
        # Update total controller byte and packet counts
        self.bytes_total = sum(b for b, p in self.port_stats.values())
        self.data_packets_total = sum(p for b, p in self.port_stats.values())

    @set_ev_cls(ofp_event.EventOFPFlowStatsReply, MAIN_DISPATCHER)
    def _flow_stats_reply_handler(self, ev):
        """Handle flow stats replies."""
        dpid = ev.msg.datapath.id
        if dpid not in self.master_switches:
            return
            
        body = ev.msg.body
        
        if not hasattr(self, 'switch_flow_counts'):
            self.switch_flow_counts = {}
            
        self.switch_flow_counts[dpid] = len(body)
        self.flow_count = sum(self.switch_flow_counts.values())

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        """Handle packet-in events - learn MAC and forward."""
        msg = ev.msg
        datapath = msg.datapath
        
        # OVS natively shouldn't send PacketIn to SLAVE controllers, but as a safeguard we strictly enforce it
        if datapath.id not in self.master_switches:
            return
            
        start_time = time.time()
        self.packet_in_count += 1
        
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match['in_port']

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocols(ethernet.ethernet)[0]

        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return

        dst = eth.dst
        src = eth.src
        dpid = datapath.id

        self.mac_to_port.setdefault(dpid, {})
        self.mac_to_port[dpid][src] = in_port
        self.bytes_total += len(msg.data) if msg.data else 0

        if dst in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][dst]
        else:
            out_port = ofproto.OFPP_FLOOD

        actions = [parser.OFPActionOutput(out_port)]

        if out_port != ofproto.OFPP_FLOOD:
            match = parser.OFPMatch(in_port=in_port, eth_dst=dst, eth_src=src)
            if msg.buffer_id != ofproto.OFP_NO_BUFFER:
                self.add_flow(datapath, 1, match, actions, msg.buffer_id)
                # Track latency
                latency_ms = (time.time() - start_time) * 1000
                self.request_latencies.append(latency_ms)
                return
            else:
                self.add_flow(datapath, 1, match, actions)

        data = None
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data

        out = parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id,
                                  in_port=in_port, actions=actions, data=data)
        datapath.send_msg(out)
        self.packet_out_count += 1
        
        # Track latency
        latency_ms = (time.time() - start_time) * 1000
        self.request_latencies.append(latency_ms)
