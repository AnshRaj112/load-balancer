#!/usr/bin/env python3
"""
Training Script for Load Prediction Model

Usage:
    # Generate synthetic data and train
    python prediction/train.py --generate-data --epochs 100
    
    # Train with existing data
    python prediction/train.py --data data/training/telemetry.csv --epochs 100
    
    # View training in TensorBoard
    tensorboard --logdir runs/prediction
"""

import argparse
import yaml
import time
import sys
from pathlib import Path
from datetime import datetime

# Add parent directory to path for imports when running as script
sys.path.insert(0, str(Path(__file__).parent))

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader
from torch.utils.tensorboard import SummaryWriter

from model import LoadPredictor, create_model
from dataset import LoadDataset, create_dataloaders, save_synthetic_data


def train_epoch(
    model: nn.Module,
    train_loader: DataLoader,
    criterion: nn.Module,
    optimizer: torch.optim.Optimizer,
    device: torch.device,
    epoch: int,
    writer: SummaryWriter,
    log_interval: int = 10
) -> float:
    """Train for one epoch."""
    model.train()
    total_loss = 0.0
    num_batches = 0
    
    for batch_idx, (X, y) in enumerate(train_loader):
        X, y = X.to(device), y.to(device)
        
        optimizer.zero_grad()
        predictions = model(X)
        loss = criterion(predictions, y)
        loss.backward()
        
        # Gradient clipping
        torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
        
        optimizer.step()
        
        total_loss += loss.item()
        num_batches += 1
        
        # Log to TensorBoard
        global_step = epoch * len(train_loader) + batch_idx
        if batch_idx % log_interval == 0:
            writer.add_scalar('Loss/train_step', loss.item(), global_step)
            
            if batch_idx % (log_interval * 5) == 0:
                print(f'  Batch {batch_idx}/{len(train_loader)}, Loss: {loss.item():.6f}')
    
    avg_loss = total_loss / num_batches
    return avg_loss


def validate(
    model: nn.Module,
    val_loader: DataLoader,
    criterion: nn.Module,
    device: torch.device
) -> tuple[float, float, float]:
    """Validate model."""
    model.eval()
    total_loss = 0.0
    total_mae = 0.0
    total_mape = 0.0
    num_batches = 0
    
    with torch.no_grad():
        for X, y in val_loader:
            X, y = X.to(device), y.to(device)
            
            predictions = model(X)
            loss = criterion(predictions, y)
            
            total_loss += loss.item()
            
            # Calculate MAE
            mae = torch.mean(torch.abs(predictions - y)).item()
            total_mae += mae
            
            # Calculate MAPE (avoid division by zero)
            mape = torch.mean(torch.abs((predictions - y) / (y + 1e-8))).item() * 100
            total_mape += mape
            
            num_batches += 1
    
    avg_loss = total_loss / num_batches
    avg_mae = total_mae / num_batches
    avg_mape = total_mape / num_batches
    
    return avg_loss, avg_mae, avg_mape


def train(
    config_path: str = 'prediction/config.yaml',
    data_path: str = None,
    generate_data: bool = False,
    epochs: int = None,
    output_model: str = None
):
    """Main training function."""
    
    # Load config
    project_root = Path(__file__).parent.parent
    config_file = project_root / config_path if not Path(config_path).is_absolute() else Path(config_path)
    
    with open(config_file) as f:
        config = yaml.safe_load(f)
    
    # Override with command line args
    if epochs:
        config['training']['epochs'] = epochs
    if output_model:
        config['paths']['model_save'] = output_model
    
    # Setup device
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"Using device: {device}")
    
    # Setup paths
    data_dir = project_root / config['paths']['data_dir']
    data_dir.mkdir(parents=True, exist_ok=True)
    
    model_save_path = project_root / config['paths']['model_save']
    model_save_path.parent.mkdir(parents=True, exist_ok=True)
    
    tensorboard_dir = project_root / config['paths']['tensorboard_dir']
    
    # Generate or load data
    if generate_data or data_path is None:
        data_file = data_dir / 'synthetic_telemetry.csv'
        print(f"Generating synthetic training data...")
        save_synthetic_data(data_file, num_samples=10000)
        data_path = data_file
    else:
        data_path = Path(data_path) if not Path(data_path).is_absolute() else Path(data_path)
        if not data_path.exists():
            data_path = project_root / data_path
    
    print(f"Loading data from: {data_path}")
    
    # Create dataloaders
    train_loader, val_loader, test_loader, scaler_params = create_dataloaders(
        data_path=data_path,
        lookback=config['data']['lookback'],
        horizon=config['data']['horizon'],
        batch_size=config['training']['batch_size'],
        train_ratio=config['data']['train_ratio'],
        val_ratio=config['data']['val_ratio']
    )
    
    print(f"Train batches: {len(train_loader)}, Val batches: {len(val_loader)}, Test batches: {len(test_loader)}")
    
    # Create model
    model = create_model(config['model']).to(device)
    print(f"\nModel architecture:")
    print(model)
    print(f"Total parameters: {sum(p.numel() for p in model.parameters()):,}")
    
    # Loss, optimizer, scheduler
    criterion = nn.MSELoss()
    optimizer = torch.optim.Adam(
        model.parameters(),
        lr=config['training']['learning_rate'],
        weight_decay=config['training']['weight_decay']
    )
    
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer,
        mode='min',
        factor=config['scheduler']['factor'],
        patience=config['scheduler']['patience']
    )
    
    # TensorBoard writer
    run_name = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    writer = SummaryWriter(tensorboard_dir / run_name)
    
    # Log config
    writer.add_text('config', yaml.dump(config))
    
    # Training loop
    best_val_loss = float('inf')
    patience_counter = 0
    
    print(f"\nStarting training for {config['training']['epochs']} epochs...")
    print("=" * 60)
    
    start_time = time.time()
    
    for epoch in range(config['training']['epochs']):
        epoch_start = time.time()
        
        # Train
        train_loss = train_epoch(
            model, train_loader, criterion, optimizer, device,
            epoch, writer, config['logging']['log_interval']
        )
        
        # Validate
        val_loss, val_mae, val_mape = validate(model, val_loader, criterion, device)
        
        # Update scheduler
        scheduler.step(val_loss)
        
        # Log to TensorBoard
        writer.add_scalar('Loss/train', train_loss, epoch)
        writer.add_scalar('Loss/val', val_loss, epoch)
        writer.add_scalar('Metrics/MAE', val_mae, epoch)
        writer.add_scalar('Metrics/MAPE', val_mape, epoch)
        writer.add_scalar('LR', optimizer.param_groups[0]['lr'], epoch)
        
        epoch_time = time.time() - epoch_start
        
        print(f"Epoch {epoch+1:3d}/{config['training']['epochs']} | "
              f"Train Loss: {train_loss:.6f} | Val Loss: {val_loss:.6f} | "
              f"MAE: {val_mae:.4f} | MAPE: {val_mape:.2f}% | "
              f"Time: {epoch_time:.1f}s")
        
        # Check for improvement
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            patience_counter = 0
            
            # Save best model
            checkpoint = {
                'epoch': epoch,
                'model_state_dict': model.state_dict(),
                'optimizer_state_dict': optimizer.state_dict(),
                'val_loss': val_loss,
                'val_mae': val_mae,
                'val_mape': val_mape,
                'config': config,
                'scaler_params': scaler_params
            }
            torch.save(checkpoint, model_save_path)
            print(f"  ✓ Saved best model (val_loss: {val_loss:.6f})")
        else:
            patience_counter += 1
            if patience_counter >= config['training']['patience']:
                print(f"\nEarly stopping after {epoch+1} epochs (no improvement for {patience_counter} epochs)")
                break
    
    total_time = time.time() - start_time
    print("=" * 60)
    print(f"Training complete in {total_time/60:.1f} minutes")
    print(f"Best validation loss: {best_val_loss:.6f}")
    print(f"Model saved to: {model_save_path}")
    
    # Test evaluation
    print("\nEvaluating on test set...")
    
    # Load best model
    checkpoint = torch.load(model_save_path)
    model.load_state_dict(checkpoint['model_state_dict'])
    
    test_loss, test_mae, test_mape = validate(model, test_loader, criterion, device)
    print(f"Test Loss: {test_loss:.6f} | Test MAE: {test_mae:.4f} | Test MAPE: {test_mape:.2f}%")
    
    writer.add_scalar('Loss/test', test_loss)
    writer.add_scalar('Metrics/test_MAE', test_mae)
    writer.add_scalar('Metrics/test_MAPE', test_mape)
    
    writer.close()
    
    return model


def main():
    parser = argparse.ArgumentParser(description='Train Load Prediction Model')
    parser.add_argument('--config', type=str, default='prediction/config.yaml',
                        help='Path to config file')
    parser.add_argument('--data', type=str, default=None,
                        help='Path to training data CSV')
    parser.add_argument('--generate-data', action='store_true',
                        help='Generate synthetic training data')
    parser.add_argument('--epochs', type=int, default=None,
                        help='Number of epochs (overrides config)')
    parser.add_argument('--output', type=str, default=None,
                        help='Output model path (overrides config)')
    
    args = parser.parse_args()
    
    train(
        config_path=args.config,
        data_path=args.data,
        generate_data=args.generate_data,
        epochs=args.epochs,
        output_model=args.output
    )


if __name__ == '__main__':
    main()
