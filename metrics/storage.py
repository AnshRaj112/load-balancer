"""
HYDRA-LB: Metrics Storage

Persistent storage for metrics data.
Supports CSV and SQLite backends.
"""

import os
import time
import logging
import threading
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
from contextlib import contextmanager

logger = logging.getLogger('hydra-lb.metrics.storage')


class CSVStorage:
    """
    CSV-based metrics storage.
    
    Simple and portable storage format for experiment data.
    """
    
    def __init__(self, output_dir: str = '/app/data/metrics',
                 prefix: str = 'hydra'):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.prefix = prefix
        
        self._files = {}
        self._lock = threading.Lock()
        
        logger.info(f"CSV storage initialized at {output_dir}")
    
    def _get_file(self, table_name: str, headers: List[str]):
        """Get or create a CSV file for a table."""
        if table_name not in self._files:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{self.prefix}_{table_name}_{timestamp}.csv"
            filepath = self.output_dir / filename
            
            # Create file with headers
            with open(filepath, 'w') as f:
                f.write(','.join(headers) + '\n')
            
            self._files[table_name] = {
                'path': filepath,
                'headers': headers
            }
            
            logger.info(f"Created CSV file: {filepath}")
        
        return self._files[table_name]
    
    def write_row(self, table_name: str, data: Dict[str, Any], 
                  headers: List[str] = None):
        """Write a row to a CSV table."""
        with self._lock:
            if headers is None:
                headers = list(data.keys())
            
            file_info = self._get_file(table_name, headers)
            
            # Build row in correct order
            row = [str(data.get(h, '')) for h in file_info['headers']]
            
            with open(file_info['path'], 'a') as f:
                f.write(','.join(row) + '\n')
    
    def write_switch_metrics(self, controller_id: int, dpid: int,
                              packet_rate: float, flow_count: int,
                              byte_count: int):
        """Write switch metrics row."""
        self.write_row('switch_metrics', {
            'timestamp': datetime.now().isoformat(),
            'controller_id': controller_id,
            'dpid': dpid,
            'packet_rate': f"{packet_rate:.4f}",
            'flow_count': flow_count,
            'byte_count': byte_count
        }, headers=['timestamp', 'controller_id', 'dpid', 'packet_rate', 
                   'flow_count', 'byte_count'])
    
    def write_controller_metrics(self, controller_id: int, switch_count: int,
                                  total_load: float, variance: float):
        """Write controller metrics row."""
        self.write_row('controller_metrics', {
            'timestamp': datetime.now().isoformat(),
            'controller_id': controller_id,
            'switch_count': switch_count,
            'total_load': f"{total_load:.4f}",
            'variance': f"{variance:.6f}"
        }, headers=['timestamp', 'controller_id', 'switch_count', 
                   'total_load', 'variance'])
    
    def write_lb_decision(self, controller_id: int, vip: str,
                           selected_server: str, response_time_ms: float = None):
        """Write load balancer decision row."""
        self.write_row('lb_decisions', {
            'timestamp': datetime.now().isoformat(),
            'controller_id': controller_id,
            'vip': vip,
            'selected_server': selected_server,
            'response_time_ms': f"{response_time_ms:.2f}" if response_time_ms else ''
        }, headers=['timestamp', 'controller_id', 'vip', 
                   'selected_server', 'response_time_ms'])
    
    def write_migration(self, switch_dpid: int, from_controller: int,
                        to_controller: int, cost_ms: float, reason: str):
        """Write migration event row."""
        self.write_row('migrations', {
            'timestamp': datetime.now().isoformat(),
            'switch_dpid': switch_dpid,
            'from_controller': from_controller,
            'to_controller': to_controller,
            'cost_ms': f"{cost_ms:.2f}",
            'reason': reason
        }, headers=['timestamp', 'switch_dpid', 'from_controller',
                   'to_controller', 'cost_ms', 'reason'])
    
    def get_files(self) -> Dict[str, str]:
        """Get all output file paths."""
        return {name: str(info['path']) for name, info in self._files.items()}


class SQLiteStorage:
    """
    SQLite-based metrics storage.
    
    More efficient for querying large datasets.
    """
    
    def __init__(self, db_path: str = '/app/data/metrics/hydra.db'):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        self._local = threading.local()
        self._init_tables()
        
        logger.info(f"SQLite storage initialized at {db_path}")
    
    @contextmanager
    def _get_connection(self):
        """Get a thread-local database connection."""
        if not hasattr(self._local, 'conn'):
            self._local.conn = sqlite3.connect(str(self.db_path))
            self._local.conn.row_factory = sqlite3.Row
        
        try:
            yield self._local.conn
        finally:
            self._local.conn.commit()
    
    def _init_tables(self):
        """Initialize database tables."""
        with self._get_connection() as conn:
            conn.executescript('''
                CREATE TABLE IF NOT EXISTS switch_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    controller_id INTEGER NOT NULL,
                    dpid INTEGER NOT NULL,
                    packet_rate REAL,
                    flow_count INTEGER,
                    byte_count INTEGER
                );
                
                CREATE TABLE IF NOT EXISTS controller_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    controller_id INTEGER NOT NULL,
                    switch_count INTEGER,
                    total_load REAL,
                    variance REAL
                );
                
                CREATE TABLE IF NOT EXISTS lb_decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    controller_id INTEGER NOT NULL,
                    vip TEXT NOT NULL,
                    selected_server TEXT NOT NULL,
                    response_time_ms REAL
                );
                
                CREATE TABLE IF NOT EXISTS migrations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    switch_dpid INTEGER NOT NULL,
                    from_controller INTEGER NOT NULL,
                    to_controller INTEGER NOT NULL,
                    cost_ms REAL,
                    reason TEXT
                );
                
                CREATE INDEX IF NOT EXISTS idx_switch_metrics_time 
                    ON switch_metrics(timestamp);
                CREATE INDEX IF NOT EXISTS idx_controller_metrics_time 
                    ON controller_metrics(timestamp);
                CREATE INDEX IF NOT EXISTS idx_lb_decisions_time 
                    ON lb_decisions(timestamp);
            ''')
    
    def write_switch_metrics(self, controller_id: int, dpid: int,
                              packet_rate: float, flow_count: int,
                              byte_count: int):
        """Write switch metrics."""
        with self._get_connection() as conn:
            conn.execute('''
                INSERT INTO switch_metrics 
                (timestamp, controller_id, dpid, packet_rate, flow_count, byte_count)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (datetime.now().isoformat(), controller_id, dpid,
                  packet_rate, flow_count, byte_count))
    
    def write_controller_metrics(self, controller_id: int, switch_count: int,
                                  total_load: float, variance: float):
        """Write controller metrics."""
        with self._get_connection() as conn:
            conn.execute('''
                INSERT INTO controller_metrics
                (timestamp, controller_id, switch_count, total_load, variance)
                VALUES (?, ?, ?, ?, ?)
            ''', (datetime.now().isoformat(), controller_id, switch_count,
                  total_load, variance))
    
    def write_lb_decision(self, controller_id: int, vip: str,
                           selected_server: str, response_time_ms: float = None):
        """Write load balancer decision."""
        with self._get_connection() as conn:
            conn.execute('''
                INSERT INTO lb_decisions
                (timestamp, controller_id, vip, selected_server, response_time_ms)
                VALUES (?, ?, ?, ?, ?)
            ''', (datetime.now().isoformat(), controller_id, vip,
                  selected_server, response_time_ms))
    
    def write_migration(self, switch_dpid: int, from_controller: int,
                        to_controller: int, cost_ms: float, reason: str):
        """Write migration event."""
        with self._get_connection() as conn:
            conn.execute('''
                INSERT INTO migrations
                (timestamp, switch_dpid, from_controller, to_controller, cost_ms, reason)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (datetime.now().isoformat(), switch_dpid, from_controller,
                  to_controller, cost_ms, reason))
    
    def query_variance_timeseries(self, start_time: str = None,
                                   end_time: str = None) -> List[Dict]:
        """Query variance time series."""
        with self._get_connection() as conn:
            query = 'SELECT timestamp, variance FROM controller_metrics'
            params = []
            
            if start_time:
                query += ' WHERE timestamp >= ?'
                params.append(start_time)
                if end_time:
                    query += ' AND timestamp <= ?'
                    params.append(end_time)
            elif end_time:
                query += ' WHERE timestamp <= ?'
                params.append(end_time)
            
            query += ' ORDER BY timestamp'
            
            cursor = conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
    
    def query_average_response_time(self) -> float:
        """Query average response time."""
        with self._get_connection() as conn:
            cursor = conn.execute('''
                SELECT AVG(response_time_ms) as avg_rt
                FROM lb_decisions
                WHERE response_time_ms IS NOT NULL
            ''')
            row = cursor.fetchone()
            return row['avg_rt'] if row and row['avg_rt'] else 0.0
    
    def query_migration_count(self) -> int:
        """Query total migration count."""
        with self._get_connection() as conn:
            cursor = conn.execute('SELECT COUNT(*) as count FROM migrations')
            row = cursor.fetchone()
            return row['count'] if row else 0
