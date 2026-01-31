"""
HYDRA-LB: Telemetry Tests

Unit tests for telemetry collection and metrics.
"""

import pytest
import sys
import os
import time
import tempfile

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from controller.telemetry import TelemetryCollector
from metrics.collector import MetricsCollector, ExperimentMetrics
from metrics.storage import CSVStorage


class TestTelemetryCollector:
    """Tests for TelemetryCollector."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.telemetry = TelemetryCollector(
            controller_id=1, 
            output_dir=self.temp_dir
        )
    
    def test_register_switch(self):
        """Test switch registration."""
        self.telemetry.register_switch(1)
        self.telemetry.register_switch(2)
        
        assert 1 in self.telemetry.switches
        assert 2 in self.telemetry.switches
        assert len(self.telemetry.switches) == 2
    
    def test_unregister_switch(self):
        """Test switch unregistration."""
        self.telemetry.register_switch(1)
        self.telemetry.unregister_switch(1)
        
        assert 1 not in self.telemetry.switches
    
    def test_record_packet_in(self):
        """Test packet-in recording."""
        self.telemetry.register_switch(1)
        
        for _ in range(100):
            self.telemetry.record_packet_in(1)
        
        # The count should be recorded
        assert self.telemetry._packet_in_counts[1] == 100
    
    def test_packet_in_rate_calculation(self):
        """Test packet-in rate calculation."""
        self.telemetry.register_switch(1)
        
        # Record 100 packets
        for _ in range(100):
            self.telemetry.record_packet_in(1)
        
        # Wait a bit and calculate rate
        time.sleep(0.1)
        rate = self.telemetry._calculate_packet_in_rate(1)
        
        # Rate should be approximately 100 / 0.1 = 1000 pps
        # But timing isn't exact, so just check it's positive
        assert rate > 0
        
        # Counter should be reset
        assert self.telemetry._packet_in_counts[1] == 0
    
    def test_record_flow_stats(self):
        """Test flow stats recording."""
        self.telemetry.register_switch(1)
        
        self.telemetry.record_flow_stats(1, {
            'flow_count': 50,
            'byte_count': 1000000
        })
        
        metrics = self.telemetry.get_switch_metrics(1)
        assert metrics['flow_count'] == 50
        assert metrics['byte_count'] == 1000000
    
    def test_get_controller_load(self):
        """Test controller load calculation."""
        self.telemetry.register_switch(1)
        self.telemetry.register_switch(2)
        
        # Record packets for each switch
        for _ in range(50):
            self.telemetry.record_packet_in(1)
        for _ in range(100):
            self.telemetry.record_packet_in(2)
        
        load = self.telemetry.get_controller_load()
        
        # Load should be positive (sum of packet-in rates)
        assert load >= 0
    
    def test_get_load_variance(self):
        """Test load variance calculation."""
        self.telemetry.register_switch(1)
        self.telemetry.register_switch(2)
        
        # Create imbalanced load
        for _ in range(100):
            self.telemetry.record_packet_in(1)
        for _ in range(10):
            self.telemetry.record_packet_in(2)
        
        stats = self.telemetry.get_load_variance()
        
        assert 'variance' in stats
        assert 'mean' in stats
        assert 'switch_loads' in stats
        assert stats['switch_count'] == 2
    
    def test_export_metrics(self):
        """Test metrics export to CSV."""
        self.telemetry.register_switch(1)
        self.telemetry.record_packet_in(1)
        self.telemetry.record_flow_stats(1, {'flow_count': 10, 'byte_count': 1000})
        
        self.telemetry.export_metrics()
        
        # Check that files were created
        files = list(os.listdir(self.temp_dir))
        assert len(files) >= 2  # At least switch and controller metrics


class TestMetricsCollector:
    """Tests for MetricsCollector."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.collector = MetricsCollector(
            output_dir=self.temp_dir,
            experiment_id='test_exp'
        )
    
    def test_record_controller_load(self):
        """Test controller load recording."""
        self.collector.record_controller_load(1, 100.0)
        self.collector.record_controller_load(1, 150.0)
        self.collector.record_controller_load(2, 50.0)
        
        loads = self.collector.metrics.controller_loads
        assert len(loads[1]) == 2
        assert len(loads[2]) == 1
    
    def test_record_load_variance(self):
        """Test variance recording."""
        self.collector.record_load_variance(10.5)
        self.collector.record_load_variance(15.2)
        
        variances = self.collector.metrics.controller_variances
        assert len(variances) == 2
        assert variances[0] == 10.5
    
    def test_record_lb_decision(self):
        """Test LB decision recording."""
        self.collector.record_lb_decision('10.0.0.100', '10.0.0.1', 5.5)
        self.collector.record_lb_decision('10.0.0.100', '10.0.0.2', 3.2)
        
        decisions = self.collector.metrics.lb_decisions
        assert len(decisions) == 2
        
        response_times = self.collector.metrics.response_times
        assert len(response_times) == 2
    
    def test_get_summary_stats(self):
        """Test summary statistics."""
        # Add some data
        for i in range(10):
            self.collector.record_load_variance(i * 1.0)
            self.collector.record_throughput(100.0 + i)
        
        summary = self.collector.get_summary_stats()
        
        assert summary['experiment_id'] == 'test_exp'
        assert 'variance_stats' in summary
        assert 'throughput_stats' in summary
        assert summary['variance_stats']['samples'] == 10
    
    def test_export_json(self):
        """Test JSON export."""
        self.collector.record_load_variance(10.0)
        self.collector.record_controller_load(1, 100.0)
        
        filepath = self.collector.export_json()
        
        assert os.path.exists(filepath)
        assert filepath.endswith('.json')


class TestCSVStorage:
    """Tests for CSV storage backend."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.storage = CSVStorage(
            output_dir=self.temp_dir,
            prefix='test'
        )
    
    def test_write_switch_metrics(self):
        """Test writing switch metrics."""
        self.storage.write_switch_metrics(
            controller_id=1,
            dpid=1,
            packet_rate=100.5,
            flow_count=50,
            byte_count=1000000
        )
        
        files = self.storage.get_files()
        assert 'switch_metrics' in files
        assert os.path.exists(files['switch_metrics'])
    
    def test_write_controller_metrics(self):
        """Test writing controller metrics."""
        self.storage.write_controller_metrics(
            controller_id=1,
            switch_count=5,
            total_load=500.0,
            variance=25.5
        )
        
        files = self.storage.get_files()
        assert 'controller_metrics' in files
    
    def test_write_lb_decision(self):
        """Test writing LB decisions."""
        self.storage.write_lb_decision(
            controller_id=1,
            vip='10.0.0.100',
            selected_server='10.0.0.1',
            response_time_ms=5.5
        )
        
        files = self.storage.get_files()
        assert 'lb_decisions' in files
    
    def test_write_migration(self):
        """Test writing migration events."""
        self.storage.write_migration(
            switch_dpid=1,
            from_controller=1,
            to_controller=2,
            cost_ms=50.0,
            reason='overload'
        )
        
        files = self.storage.get_files()
        assert 'migrations' in files


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
