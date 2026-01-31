#!/usr/bin/env python3
"""
Data Collector for Load Prediction Training

Collects telemetry data from running controllers and saves
to CSV for model training.

Usage:
    # Collect 10 minutes of data
    python prediction/data_collector.py --duration 600 --output data/training/
    
    # Collect from specific controller
    python prediction/data_collector.py --controller http://localhost:9100 --duration 300
"""

import argparse
import time
import csv
from datetime import datetime
from pathlib import Path
import requests


# Default controller metrics endpoints
CONTROLLER_ENDPOINTS = [
    "http://localhost:9100/metrics",  # Controller 1
    "http://localhost:9101/metrics",  # Controller 2
    "http://localhost:9102/metrics",  # Controller 3
]


def parse_prometheus_metrics(text: str) -> dict:
    """Parse Prometheus text format into dict."""
    metrics = {}
    
    for line in text.strip().split('\n'):
        if line.startswith('#') or not line:
            continue
        
        # Parse metric line
        try:
            if '{' in line:
                # Has labels: metric_name{labels} value
                name_part, value = line.rsplit(' ', 1)
                name = name_part.split('{')[0]
                labels = name_part.split('{')[1].rstrip('}')
            else:
                # No labels: metric_name value
                name, value = line.split()
                labels = ''
            
            key = f"{name}_{labels}" if labels else name
            metrics[key] = float(value)
        except (ValueError, IndexError):
            continue
    
    return metrics


def collect_from_controller(endpoint: str) -> dict:
    """Collect metrics from a single controller."""
    try:
        response = requests.get(endpoint, timeout=5)
        response.raise_for_status()
        return parse_prometheus_metrics(response.text)
    except requests.RequestException as e:
        print(f"Warning: Failed to collect from {endpoint}: {e}")
        return {}


def extract_features(metrics: dict) -> dict:
    """Extract relevant features for prediction."""
    features = {
        'timestamp': datetime.now().isoformat(),
        'packet_rate': 0.0,
        'flow_count': 0.0,
        'byte_rate': 0.0,
        'switch_count': 0.0
    }
    
    # Look for specific metrics
    for key, value in metrics.items():
        if 'packet_in' in key.lower() and 'total' in key.lower():
            features['packet_rate'] = value
        elif 'flow_count' in key.lower():
            features['flow_count'] = value
        elif 'bytes' in key.lower() and 'total' in key.lower():
            features['byte_rate'] = value
        elif 'switch_count' in key.lower():
            features['switch_count'] = value
    
    return features


def collect_data(
    output_dir: str,
    duration: int = 600,
    interval: int = 5,
    endpoints: list = None
):
    """
    Collect telemetry data for specified duration.
    
    Args:
        output_dir: Directory to save CSV files
        duration: Collection duration in seconds
        interval: Collection interval in seconds
        endpoints: List of controller endpoints to collect from
    """
    if endpoints is None:
        endpoints = CONTROLLER_ENDPOINTS
    
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_file = output_path / f'telemetry_{timestamp}.csv'
    
    print(f"Collecting data for {duration}s at {interval}s intervals...")
    print(f"Endpoints: {endpoints}")
    print(f"Output: {output_file}")
    
    # Initialize CSV
    fieldnames = ['timestamp', 'controller_id', 'packet_rate', 'flow_count', 'byte_rate', 'switch_count']
    
    with open(output_file, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        
        start_time = time.time()
        samples_collected = 0
        
        while time.time() - start_time < duration:
            for i, endpoint in enumerate(endpoints):
                metrics = collect_from_controller(endpoint)
                
                if metrics:
                    features = extract_features(metrics)
                    features['controller_id'] = i + 1
                    writer.writerow(features)
                    samples_collected += 1
            
            # Flush periodically
            if samples_collected % 10 == 0:
                f.flush()
            
            elapsed = time.time() - start_time
            remaining = duration - elapsed
            print(f"\rProgress: {elapsed:.0f}/{duration}s ({samples_collected} samples)", end='')
            
            time.sleep(interval)
    
    print(f"\n\nCollection complete!")
    print(f"Saved {samples_collected} samples to {output_file}")
    
    return output_file


def main():
    parser = argparse.ArgumentParser(description='Collect telemetry data for training')
    parser.add_argument('--output', type=str, default='data/training',
                        help='Output directory')
    parser.add_argument('--duration', type=int, default=600,
                        help='Collection duration in seconds')
    parser.add_argument('--interval', type=int, default=5,
                        help='Collection interval in seconds')
    parser.add_argument('--controller', type=str, default=None,
                        help='Single controller endpoint to collect from')
    
    args = parser.parse_args()
    
    endpoints = [args.controller] if args.controller else None
    
    collect_data(
        output_dir=args.output,
        duration=args.duration,
        interval=args.interval,
        endpoints=endpoints
    )


if __name__ == '__main__':
    main()
