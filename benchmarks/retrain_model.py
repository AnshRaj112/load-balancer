#!/usr/bin/env python3
"""
HYDRA-LB: Convenience script to collect data + retrain model.

Usage:
    # Collect 5 min of data during traffic, then retrain
    python benchmarks/retrain_model.py --collect-duration 300

    # Retrain on existing data
    python benchmarks/retrain_model.py --data data/training/telemetry_*.csv --epochs 100
"""

import argparse
import glob
import os
import subprocess
import sys


def collect_data(duration, interval=1):
    """Collect data from the live cluster."""
    print(f"\n📡 Collecting live telemetry for {duration}s...")
    python_exe = "/home/dev/projects/.venv/bin/python" if os.path.exists("/home/dev/projects/.venv/bin/python") else sys.executable
    cmd = [
        python_exe, "prediction/data_collector.py",
        "--output", "data/training",
        "--duration", str(duration),
        "--interval", str(interval),
    ]
    subprocess.run(cmd, cwd="/home/dev/load-balancer")


def retrain(data_path=None, epochs=100):
    """Retrain the model on collected data."""
    import shutil
    from datetime import datetime
    
    model_path = "models/lstm_predictor.pt"
    if os.path.exists(model_path):
        backup_path = f"models/lstm_predictor_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pt"
        print(f"\n💾 Backing up existing model to {backup_path}")
        shutil.copy2(model_path, backup_path)
        
    print(f"\n🧠 Retraining LSTM model (epochs={epochs})...")
    
    python_exe = "/home/dev/projects/.venv/bin/python" if os.path.exists("/home/dev/projects/.venv/bin/python") else sys.executable
    cmd = [
        python_exe, "prediction/train.py",
        "--epochs", str(epochs),
        "--output", "models/lstm_predictor.pt",
    ]
    
    if data_path:
        cmd += ["--data", data_path]
    else:
        cmd.append("--generate-data")
    
    subprocess.run(cmd, cwd="/home/dev/load-balancer")


def main():
    parser = argparse.ArgumentParser(description='HYDRA-LB Model Retrain Pipeline')
    parser.add_argument('--collect-duration', type=int, default=0,
                        help='Collect live data for N seconds first (0=skip)')
    parser.add_argument('--data', type=str, default=None,
                        help='Path to existing training data CSV')
    parser.add_argument('--epochs', type=int, default=100,
                        help='Training epochs (default: 100)')
    
    args = parser.parse_args()
    
    # Step 1: Collect data if requested
    if args.collect_duration > 0:
        collect_data(args.collect_duration)
    
    # Step 2: Find data
    data_path = args.data
    if not data_path and args.collect_duration > 0:
        # Use most recently collected file
        files = sorted(glob.glob("data/training/telemetry_*.csv"))
        if files:
            data_path = files[-1]
            print(f"  Using: {data_path}")
    
    # Step 3: Retrain
    retrain(data_path, args.epochs)
    
    print(f"\n✅ Done! Model saved to models/lstm_predictor.pt")
    print(f"   Restart controllers to load the new model.")


if __name__ == '__main__':
    main()
