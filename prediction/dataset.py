"""
PyTorch Dataset for Load Prediction

Handles sliding window creation and train/val/test splits
for time series load prediction.
"""

import numpy as np
import pandas as pd
import torch
from torch.utils.data import Dataset, DataLoader
from typing import Optional, Tuple
from pathlib import Path


class LoadDataset(Dataset):
    """
    Dataset for load prediction with sliding window sequences.
    
    Features:
        - packet_rate: Packets per second
        - flow_count: Number of active flows
        - byte_rate: Bytes per second  
        - switch_count: Connected switches
        
    Creates sequences of length `lookback` to predict `horizon` future values.
    """
    
    def __init__(
        self,
        data: np.ndarray | pd.DataFrame,
        lookback: int = 10,
        horizon: int = 5,
        target_col: int = 0,  # packet_rate is default target
        normalize: bool = True,
        scaler_params: Optional[dict] = None
    ):
        """
        Initialize the dataset.
        
        Args:
            data: Array of shape [timesteps, features] or DataFrame
            lookback: Number of past timesteps to use as input
            horizon: Number of future timesteps to predict
            target_col: Index of column to predict (default: 0 = packet_rate)
            normalize: Whether to normalize features
            scaler_params: Optional pre-computed mean/std for normalization
        """
        self.lookback = lookback
        self.horizon = horizon
        self.target_col = target_col
        self.normalize = normalize
        
        # Convert DataFrame to numpy
        if isinstance(data, pd.DataFrame):
            data = data.values.astype(np.float32)
        else:
            data = data.astype(np.float32)
            
        # Store original data
        self.raw_data = data
        
        # Normalize if requested
        if normalize:
            if scaler_params is not None:
                self.mean = scaler_params['mean']
                self.std = scaler_params['std']
            else:
                self.mean = data.mean(axis=0)
                self.std = data.std(axis=0)
                # Prevent division by zero
                self.std[self.std == 0] = 1.0
                
            self.data = (data - self.mean) / self.std
        else:
            self.data = data
            self.mean = np.zeros(data.shape[1])
            self.std = np.ones(data.shape[1])
        
        # Create sequences
        self.X, self.y = self._create_sequences()
        
    def _create_sequences(self) -> Tuple[np.ndarray, np.ndarray]:
        """Create sliding window sequences."""
        X, y = [], []
        
        for i in range(len(self.data) - self.lookback - self.horizon + 1):
            # Input: lookback timesteps of all features
            X.append(self.data[i:i + self.lookback])
            
            # Target: horizon timesteps of target column
            y.append(self.data[i + self.lookback:i + self.lookback + self.horizon, self.target_col])
        
        return np.array(X), np.array(y)
    
    def __len__(self) -> int:
        return len(self.X)
    
    def __getitem__(self, idx: int) -> Tuple[torch.Tensor, torch.Tensor]:
        return (
            torch.tensor(self.X[idx], dtype=torch.float32),
            torch.tensor(self.y[idx], dtype=torch.float32)
        )
    
    def get_scaler_params(self) -> dict:
        """Get normalization parameters for use in inference."""
        return {'mean': self.mean, 'std': self.std}
    
    def inverse_transform(self, predictions: np.ndarray) -> np.ndarray:
        """Convert normalized predictions back to original scale."""
        if self.normalize:
            return predictions * self.std[self.target_col] + self.mean[self.target_col]
        return predictions


def create_dataloaders(
    data_path: str | Path,
    lookback: int = 10,
    horizon: int = 5,
    batch_size: int = 32,
    train_ratio: float = 0.7,
    val_ratio: float = 0.15,
    num_workers: int = 0
) -> Tuple[DataLoader, DataLoader, DataLoader, dict]:
    """
    Create train, validation, and test dataloaders.
    
    Args:
        data_path: Path to CSV file with telemetry data
        lookback: Sequence length for input
        horizon: Prediction horizon
        batch_size: Batch size
        train_ratio: Fraction for training
        val_ratio: Fraction for validation
        num_workers: DataLoader workers
        
    Returns:
        train_loader, val_loader, test_loader, scaler_params
    """
    # Load data
    df = pd.read_csv(data_path)
    
    # Expected columns: timestamp, packet_rate, flow_count, byte_rate, switch_count
    feature_cols = ['packet_rate', 'flow_count', 'byte_rate', 'switch_count']
    
    # Filter to feature columns if they exist
    available_cols = [c for c in feature_cols if c in df.columns]
    if not available_cols:
        # Use all numeric columns except timestamp
        available_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        
    data = df[available_cols].values
    
    # Split data (temporal split - no shuffling!)
    n = len(data)
    train_end = int(n * train_ratio)
    val_end = int(n * (train_ratio + val_ratio))
    
    train_data = data[:train_end]
    val_data = data[train_end:val_end]
    test_data = data[val_end:]
    
    # Create datasets (use training stats for normalization)
    train_dataset = LoadDataset(train_data, lookback, horizon, normalize=True)
    scaler_params = train_dataset.get_scaler_params()
    
    val_dataset = LoadDataset(val_data, lookback, horizon, normalize=True, scaler_params=scaler_params)
    test_dataset = LoadDataset(test_data, lookback, horizon, normalize=True, scaler_params=scaler_params)
    
    # Create dataloaders
    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True, num_workers=num_workers)
    val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False, num_workers=num_workers)
    test_loader = DataLoader(test_dataset, batch_size=batch_size, shuffle=False, num_workers=num_workers)
    
    return train_loader, val_loader, test_loader, scaler_params


def generate_synthetic_data(
    num_samples: int = 10000,
    num_features: int = 4,
    noise_level: float = 0.1,
    seed: int = 42
) -> np.ndarray:
    """
    Generate synthetic traffic data for initial training/testing.
    
    Patterns included:
        - Diurnal (day/night) cycle
        - Hourly micro-fluctuations
        - Random bursts
        - Gradual trend
        
    Args:
        num_samples: Number of timesteps
        num_features: Number of features
        noise_level: Noise standard deviation
        seed: Random seed
        
    Returns:
        Synthetic data array [num_samples, num_features]
    """
    np.random.seed(seed)
    
    t = np.arange(num_samples)
    
    # Base diurnal pattern (24-hour cycle, ~288 samples per day at 5-min intervals)
    samples_per_day = 288
    diurnal = 50 + 30 * np.sin(2 * np.pi * t / samples_per_day)
    
    # Hourly fluctuations
    samples_per_hour = 12
    hourly = 10 * np.sin(2 * np.pi * t / samples_per_hour)
    
    # Random bursts (sparse)
    bursts = np.zeros(num_samples)
    burst_indices = np.random.choice(num_samples, size=num_samples // 50, replace=False)
    bursts[burst_indices] = np.random.exponential(30, size=len(burst_indices))
    
    # Gradual trend
    trend = 0.001 * t
    
    # Combine for packet_rate
    packet_rate = diurnal + hourly + bursts + trend + np.random.normal(0, noise_level * 10, num_samples)
    packet_rate = np.clip(packet_rate, 0, None)  # Non-negative
    
    # Flow count (correlated with packet rate)
    flow_count = packet_rate * 0.8 + np.random.normal(0, 5, num_samples)
    flow_count = np.clip(flow_count, 0, None)
    
    # Byte rate (correlated)
    byte_rate = packet_rate * 1500 + np.random.normal(0, 1000, num_samples)
    byte_rate = np.clip(byte_rate, 0, None)
    
    # Switch count (mostly stable with occasional changes)
    switch_count = np.full(num_samples, 4.0)
    switch_change_points = np.random.choice(num_samples, size=10, replace=False)
    for i, point in enumerate(sorted(switch_change_points)):
        switch_count[point:] = np.random.choice([3, 4, 5, 6])
    
    # Stack features
    data = np.column_stack([packet_rate, flow_count, byte_rate, switch_count])
    
    return data.astype(np.float32)


def save_synthetic_data(output_path: str | Path, num_samples: int = 10000):
    """Generate and save synthetic data to CSV."""
    data = generate_synthetic_data(num_samples)
    
    df = pd.DataFrame(data, columns=['packet_rate', 'flow_count', 'byte_rate', 'switch_count'])
    df.insert(0, 'timestamp', pd.date_range(start='2026-01-01', periods=num_samples, freq='5min'))
    
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    
    print(f"Saved synthetic data ({num_samples} samples) to {output_path}")
    return df
