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
        
        # Start servers and threads
        MetricsHandler.controller = self
        self._start_metrics_server()
        self._start_monitoring_thread()
        
        logger.info(f"HYDRA Controller {self.controller_id} initialized with comprehensive monitoring")

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
                time.sleep(5)
                self._calculate_rates()
                self._calculate_load_score()
                self._update_predictions()
        
        thread = threading.Thread(target=update_loop, daemon=True)
        thread.start()

    def _calculate_rates(self):
        """Calculate rate metrics."""
        now = time.time()
        elapsed = now - self.last_stats_time
        if elapsed > 0:
            self.packet_rate = (self.packet_in_count - self.last_packet_in_count) / elapsed
            self.byte_rate = (self.bytes_total - self.last_bytes_total) / elapsed
            
        self.last_packet_in_count = self.packet_in_count
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
        packet_score = min(100, self.packet_rate * 2)  # 50 pps = 100
        flow_score = min(100, self.flow_count * 2)     # 50 flows = 100
        switch_score = min(100, self.switch_count * 20) # 5 switches = 100
        
        self.load_score = (packet_score * 0.5 + flow_score * 0.3 + switch_score * 0.2)

    def _update_predictions(self):
        """Update load predictions if predictor is available."""
        if self.predictor is None:
            return
            
        # Add current observation
        self.predictor.add_observation(
            packet_rate=self.packet_rate,
            flow_count=float(self.flow_count),
            byte_rate=self.byte_rate,
            switch_count=float(self.switch_count)
        )
        
        # Get predictions
        predictions = self.predictor.get_all_predictions()
        if predictions:
            self.predicted_load = [
                predictions.get('t+1', -1),
                predictions.get('t+2', -1),
                predictions.get('t+3', -1),
                predictions.get('t+4', -1),
                predictions.get('t+5', -1),
            ]

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
        
        return metrics

    @set_ev_cls(ofp_event.EventOFPStateChange, [MAIN_DISPATCHER, DEAD_DISPATCHER])
    def state_change_handler(self, ev):
        """Track switch connect/disconnect events."""
        datapath = ev.datapath
        if ev.state == MAIN_DISPATCHER:
            if datapath.id not in self.datapaths:
                logger.info(f"Switch {datapath.id} connected to Controller {self.controller_id}")
                self.datapaths[datapath.id] = datapath
                self.switch_count = len(self.datapaths)
        elif ev.state == DEAD_DISPATCHER:
            if datapath.id in self.datapaths:
                logger.info(f"Switch {datapath.id} disconnected from Controller {self.controller_id}")
                del self.datapaths[datapath.id]
                self.switch_count = len(self.datapaths)

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        """Install table-miss flow entry when switch connects."""
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        dpid = datapath.id

        logger.info(f"Switch {dpid} features received on Controller {self.controller_id}")

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

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        """Handle packet-in events - learn MAC and forward."""
        start_time = time.time()
        self.packet_in_count += 1
        
        msg = ev.msg
        datapath = msg.datapath
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
