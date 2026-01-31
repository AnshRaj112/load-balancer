#!/usr/bin/env python3
"""
Model Evaluation Script

Evaluates trained prediction model on test data and generates
visualizations comparing predicted vs actual load.
"""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import torch
import torch.nn as nn

from model import LoadPredictor
from dataset import LoadDataset


def load_model(model_path: str) -> tuple[LoadPredictor, dict]:
    """Load trained model and config."""
    checkpoint = torch.load(model_path, map_location='cpu')
    
    config = checkpoint['config']
    model = LoadPredictor(**config['model'])
    model.load_state_dict(checkpoint['model_state_dict'])
    model.eval()
    
    scaler_params = checkpoint.get('scaler_params', None)
    
    return model, scaler_params, config


def evaluate_model(
    model: LoadPredictor,
    test_data: np.ndarray,
    lookback: int = 10,
    horizon: int = 5,
    scaler_params: dict = None
) -> dict:
    """
    Evaluate model on test data.
    
    Returns:
        Dictionary with metrics and predictions
    """
    dataset = LoadDataset(
        test_data, 
        lookback=lookback, 
        horizon=horizon,
        scaler_params=scaler_params
    )
    
    all_predictions = []
    all_targets = []
    
    with torch.no_grad():
        for i in range(len(dataset)):
            X, y = dataset[i]
            X = X.unsqueeze(0)  # Add batch dim
            
            pred = model(X).squeeze().numpy()
            target = y.numpy()
            
            # Inverse transform
            if scaler_params is not None:
                pred = dataset.inverse_transform(pred)
                target = dataset.inverse_transform(target)
            
            all_predictions.append(pred)
            all_targets.append(target)
    
    predictions = np.array(all_predictions)
    targets = np.array(all_targets)
    
    # Calculate metrics
    mse = np.mean((predictions - targets) ** 2)
    rmse = np.sqrt(mse)
    mae = np.mean(np.abs(predictions - targets))
    mape = np.mean(np.abs((predictions - targets) / (targets + 1e-8))) * 100
    
    # Per-horizon metrics
    horizon_mae = np.mean(np.abs(predictions - targets), axis=0)
    horizon_mape = np.mean(np.abs((predictions - targets) / (targets + 1e-8)), axis=0) * 100
    
    # Correlation
    correlations = [np.corrcoef(predictions[:, h], targets[:, h])[0, 1] 
                    for h in range(horizon)]
    
    return {
        'mse': mse,
        'rmse': rmse,
        'mae': mae,
        'mape': mape,
        'horizon_mae': horizon_mae,
        'horizon_mape': horizon_mape,
        'correlations': correlations,
        'predictions': predictions,
        'targets': targets
    }


def plot_predictions(
    predictions: np.ndarray,
    targets: np.ndarray,
    output_path: str = None,
    title: str = "Load Prediction Results"
):
    """Plot predicted vs actual values."""
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    
    # Plot 1: Time series comparison (first horizon step)
    ax1 = axes[0, 0]
    n_points = min(200, len(predictions))
    ax1.plot(targets[:n_points, 0], label='Actual', alpha=0.8)
    ax1.plot(predictions[:n_points, 0], label='Predicted', alpha=0.8)
    ax1.set_xlabel('Time Step')
    ax1.set_ylabel('Load')
    ax1.set_title('Predicted vs Actual (t+1)')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    
    # Plot 2: Scatter plot
    ax2 = axes[0, 1]
    ax2.scatter(targets[:, 0], predictions[:, 0], alpha=0.5, s=10)
    min_val = min(targets[:, 0].min(), predictions[:, 0].min())
    max_val = max(targets[:, 0].max(), predictions[:, 0].max())
    ax2.plot([min_val, max_val], [min_val, max_val], 'r--', label='Perfect')
    ax2.set_xlabel('Actual')
    ax2.set_ylabel('Predicted')
    ax2.set_title('Prediction Accuracy (t+1)')
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    
    # Plot 3: Error distribution
    ax3 = axes[1, 0]
    errors = predictions[:, 0] - targets[:, 0]
    ax3.hist(errors, bins=50, alpha=0.7, edgecolor='black')
    ax3.axvline(x=0, color='r', linestyle='--')
    ax3.set_xlabel('Prediction Error')
    ax3.set_ylabel('Frequency')
    ax3.set_title(f'Error Distribution (Mean: {errors.mean():.3f})')
    ax3.grid(True, alpha=0.3)
    
    # Plot 4: Per-horizon metrics
    ax4 = axes[1, 1]
    horizons = list(range(1, predictions.shape[1] + 1))
    mae_per_horizon = np.mean(np.abs(predictions - targets), axis=0)
    ax4.bar(horizons, mae_per_horizon, alpha=0.7)
    ax4.set_xlabel('Prediction Horizon')
    ax4.set_ylabel('MAE')
    ax4.set_title('MAE by Prediction Horizon')
    ax4.grid(True, alpha=0.3)
    
    plt.suptitle(title, fontsize=14)
    plt.tight_layout()
    
    if output_path:
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        print(f"Saved plot to {output_path}")
    
    plt.show()


def main():
    parser = argparse.ArgumentParser(description='Evaluate Load Prediction Model')
    parser.add_argument('--model', type=str, default='models/lstm_predictor.pt',
                        help='Path to trained model')
    parser.add_argument('--data', type=str, required=True,
                        help='Path to test data CSV')
    parser.add_argument('--output', type=str, default=None,
                        help='Path to save evaluation plot')
    
    args = parser.parse_args()
    
    # Load model
    print(f"Loading model from {args.model}...")
    model, scaler_params, config = load_model(args.model)
    
    # Load data
    print(f"Loading test data from {args.data}...")
    df = pd.read_csv(args.data)
    feature_cols = ['packet_rate', 'flow_count', 'byte_rate', 'switch_count']
    available_cols = [c for c in feature_cols if c in df.columns]
    test_data = df[available_cols].values
    
    # Evaluate
    print("Evaluating model...")
    results = evaluate_model(
        model, test_data,
        lookback=config['data']['lookback'],
        horizon=config['data']['horizon'],
        scaler_params=scaler_params
    )
    
    # Print results
    print("\n" + "=" * 50)
    print("EVALUATION RESULTS")
    print("=" * 50)
    print(f"MSE:  {results['mse']:.6f}")
    print(f"RMSE: {results['rmse']:.6f}")
    print(f"MAE:  {results['mae']:.6f}")
    print(f"MAPE: {results['mape']:.2f}%")
    
    print("\nPer-Horizon Performance:")
    for h in range(len(results['horizon_mae'])):
        print(f"  t+{h+1}: MAE={results['horizon_mae'][h]:.4f}, "
              f"MAPE={results['horizon_mape'][h]:.2f}%, "
              f"Corr={results['correlations'][h]:.4f}")
    
    # Plot
    output_path = args.output or 'data/evaluation_results.png'
    plot_predictions(results['predictions'], results['targets'], output_path)


if __name__ == '__main__':
    main()
