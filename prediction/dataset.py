import pandas as pd
import numpy as np
import torch
from torch.utils.data import Dataset
import csv
import math
from datetime import datetime, timedelta

def save_synthetic_data(output_path, num_samples=10000):
    """Generates synthetic telemetry mapping to the HYDRA-LB distribution."""
    print(f"Generating {num_samples} synthetic samples to {output_path}...")
    with open(output_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['timestamp', 'controller_id', 'packet_rate', 'flow_count', 'byte_rate', 'switch_count'])
        
        base_time = datetime.now()
        for i in range(num_samples):
            # Generate a sine wave with some noise to represent diurnal/burst load cycles
            t = i * 0.1
            packet_rate = 1500 + 1000 * math.sin(t) + np.random.normal(0, 100)
            flow_count = 500 + 200 * math.cos(t) + np.random.normal(0, 50)
            byte_rate = packet_rate * 512 + np.random.normal(0, 5000)
            switch_count = 5
            
            timestamp = (base_time + timedelta(seconds=i)).isoformat()
            writer.writerow([timestamp, 1, max(0, packet_rate), max(0, flow_count), max(0, byte_rate), switch_count])


class LoadDataset(Dataset):
    """PyTorch Dataset for Loading Telemetry Sequences."""
    def __init__(self, data_path, lookback=30, horizon=5):
        self.lookback = lookback
        self.horizon = horizon
        self.features = ['packet_rate', 'flow_count', 'byte_rate', 'switch_count']
        
        df = pd.read_csv(data_path)
            
        # Optional: Smooth very wild spikes
        df['packet_rate'] = df['packet_rate'].clip(lower=0)
        df['flow_count'] = df['flow_count'].clip(lower=0)
        df['byte_rate'] = df['byte_rate'].clip(lower=0)
        
        # Scale packet_rate and byte_rate by 30 to match original normalization logic used in ryu_app.py
        if 'packet_rate' in df.columns:
            df['packet_rate'] = df['packet_rate'] / 30.0
            df['byte_rate'] = df['byte_rate'] / 30.0
            
        data = df[self.features].values
        
        self.X, self.y = [], []
        # Create sliding windows
        for i in range(len(data) - lookback - horizon + 1):
            self.X.append(data[i:i+lookback])
            # The target is the packet_rate (first feature) for the next `horizon` steps
            self.y.append(data[i+lookback:i+lookback+horizon, 0])
            
        self.X = torch.FloatTensor(np.array(self.X))
        self.y = torch.FloatTensor(np.array(self.y))
        
    def __len__(self):
        return len(self.X)
        
    def __getitem__(self, idx):
        return self.X[idx], self.y[idx]
