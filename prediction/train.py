#!/usr/bin/env python3
import argparse
import os
import torch
import torch.nn as nn
from torch.utils.data import DataLoader
from dataset import LoadDataset, save_synthetic_data
from model import LoadPredictor
from pathlib import Path

def train(model, loader, criterion, optimizer, device):
    """Single training epoch."""
    model.train()
    total_loss = 0
    for X, y in loader:
        X, y = X.to(device), y.to(device)
        optimizer.zero_grad()
        out = model(X)
        loss = criterion(out, y)
        loss.backward()
        # Gradient clipping to prevent exploding loss in LSTM
        nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
        optimizer.step()
        total_loss += loss.item()
    return total_loss / max(1, len(loader))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--epochs', type=int, default=20)
    parser.add_argument('--data', type=str, default=None)
    parser.add_argument('--generate-data', action='store_true')
    parser.add_argument('--output', type=str, default='models/lstm_predictor.pt')
    args = parser.parse_args()
    
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"Using device: {device}")
    
    # Setup paths
    project_root = Path("/home/dev/load-balancer")
    data_dir = project_root / "data/training"
    data_dir.mkdir(parents=True, exist_ok=True)
    
    model_save_path = project_root / args.output
    model_save_path.parent.mkdir(parents=True, exist_ok=True)
    
    data_path = args.data
    if args.generate_data or data_path is None:
        data_file = data_dir / 'synthetic_telemetry.csv'
        print(f"Generating synthetic training data...")
        save_synthetic_data(data_file, num_samples=10000)
        data_path = data_file
        
    print(f"Loading data from: {data_path}")
    dataset = TelemetryDataset(data_path=data_path, lookback=30, horizon=5)
    
    # Handle extremely short datasets (from short 30s benchmark runs)
    batch_size = min(64, max(1, len(dataset)))
    print(f"Total samples: {len(dataset)}, Batch size: {batch_size}")
    
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=True)
    
    # Instantiate the original architecture
    model = LoadPredictor(
        input_size=4, 
        output_size=5, 
        hidden_size=128, 
        num_layers=2,
        use_attention=True,
        bidirectional=True
    ).to(device)
    
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
    criterion = nn.MSELoss()
    
    print(f"Starting training for {args.epochs} epochs...")
    for epoch in range(args.epochs):
        loss = train(model, loader, criterion, optimizer, device)
        print(f"============================================================\n  Batch 0/1, Loss: {loss:.6f}")
        
    # Standard format matching the predictor.py LoadPredictorInference class
    torch.save({
        'model_state_dict': model.state_dict(),
        'config': {
            'model': {
                'input_size': 4, 
                'output_size': 5, 
                'hidden_size': 128, 
                'num_layers': 2,
                'use_attention': True,
                'bidirectional': True
            }
        }
    }, str(model_save_path))
    
    print("✅ Done! Model saved to models/lstm_predictor.pt")
    print("   Restart controllers to load the new model.")

if __name__ == '__main__':
    main()
