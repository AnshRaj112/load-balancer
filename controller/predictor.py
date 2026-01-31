"""
Predictor Wrapper for Controller Integration

Lightweight inference wrapper that loads a trained model and
provides thread-safe predictions for the Ryu controller.
"""

import threading
from pathlib import Path
from collections import deque
from typing import Optional

import numpy as np

# Try to import torch, fall back gracefully if not available
try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    print("Warning: PyTorch not available. Prediction module disabled.")


class LoadPredictorInference:
    """
    Thread-safe inference wrapper for load prediction.
    
    Maintains a sliding window of recent observations and
    provides predictions on demand.
    
    Usage:
        predictor = LoadPredictorInference('models/lstm_predictor.pt')
        predictor.add_observation(packet_rate, flow_count, byte_rate, switch_count)
        predictions = predictor.predict()  # Returns next 5 load values
    """
    
    def __init__(
        self,
        model_path: str,
        lookback: int = 10,
        device: str = 'cpu'
    ):
        """
        Initialize the predictor.
        
        Args:
            model_path: Path to trained model checkpoint
            lookback: Number of past observations to use
            device: Device to run inference on ('cpu' or 'cuda')
        """
        self.lookback = lookback
        self.device = device
        self.lock = threading.Lock()
        
        # Observation buffer
        self.observations = deque(maxlen=lookback)
        
        # Model state
        self.model = None
        self.scaler_params = None
        self.model_loaded = False
        
        if TORCH_AVAILABLE:
            self._load_model(model_path)
    
    def _load_model(self, model_path: str):
        """Load trained model from checkpoint."""
        model_path = Path(model_path)
        
        if not model_path.exists():
            print(f"Warning: Model not found at {model_path}. Predictions disabled.")
            return
        
        try:
            # Import here to avoid circular imports
            import sys
            sys.path.insert(0, str(model_path.parent.parent / 'prediction'))
            from prediction.model import LoadPredictor
            
            checkpoint = torch.load(model_path, map_location=self.device)
            
            config = checkpoint.get('config', {}).get('model', {})
            self.model = LoadPredictor(
                input_size=config.get('input_size', 4),
                hidden_size=config.get('hidden_size', 64),
                output_size=config.get('output_size', 5),
                bidirectional=config.get('bidirectional', True),
                use_attention=config.get('use_attention', True)
            )
            
            self.model.load_state_dict(checkpoint['model_state_dict'])
            self.model.to(self.device)
            self.model.eval()
            
            self.scaler_params = checkpoint.get('scaler_params', None)
            self.model_loaded = True
            
            print(f"Loaded prediction model from {model_path}")
            
        except Exception as e:
            print(f"Warning: Failed to load model: {e}")
            self.model_loaded = False
    
    def add_observation(
        self,
        packet_rate: float,
        flow_count: float,
        byte_rate: float,
        switch_count: float
    ):
        """
        Add a new observation to the sliding window.
        
        Call this every stats_interval with current metrics.
        """
        observation = np.array([packet_rate, flow_count, byte_rate, switch_count], 
                               dtype=np.float32)
        
        with self.lock:
            self.observations.append(observation)
    
    def can_predict(self) -> bool:
        """Check if we have enough observations to predict."""
        return self.model_loaded and len(self.observations) >= self.lookback
    
    def predict(self) -> Optional[np.ndarray]:
        """
        Get load predictions for next steps.
        
        Returns:
            Array of predicted load values [horizon], or None if not ready
        """
        if not self.can_predict():
            return None
        
        with self.lock:
            # Get recent observations
            obs_array = np.array(list(self.observations), dtype=np.float32)
        
        try:
            # Normalize if we have scaler params
            if self.scaler_params is not None:
                mean = self.scaler_params['mean']
                std = self.scaler_params['std']
                obs_array = (obs_array - mean) / std
            
            # Convert to tensor
            x = torch.tensor(obs_array, dtype=torch.float32).unsqueeze(0)
            x = x.to(self.device)
            
            # Predict
            with torch.no_grad():
                predictions = self.model(x).squeeze().cpu().numpy()
            
            # Inverse transform
            if self.scaler_params is not None:
                target_col = 0  # packet_rate
                predictions = predictions * std[target_col] + mean[target_col]
            
            return predictions
            
        except Exception as e:
            print(f"Prediction error: {e}")
            return None
    
    def get_predicted_load(self, horizon: int = 1) -> float:
        """
        Get predicted load for a specific horizon.
        
        Args:
            horizon: Steps ahead to predict (1-5)
            
        Returns:
            Predicted load value, or -1 if not available
        """
        predictions = self.predict()
        
        if predictions is None:
            return -1.0
        
        horizon = max(1, min(horizon, len(predictions)))
        return float(predictions[horizon - 1])
    
    def get_all_predictions(self) -> dict:
        """
        Get all predictions as a dictionary.
        
        Returns:
            Dict with t+1 through t+5 predictions
        """
        predictions = self.predict()
        
        if predictions is None:
            return {}
        
        return {f"t+{i+1}": float(predictions[i]) for i in range(len(predictions))}


# Global predictor instance for controller use
_predictor_instance: Optional[LoadPredictorInference] = None


def get_predictor(model_path: str = None) -> Optional[LoadPredictorInference]:
    """
    Get or create the global predictor instance.
    
    Args:
        model_path: Path to model (only used on first call)
        
    Returns:
        LoadPredictorInference instance
    """
    global _predictor_instance
    
    if _predictor_instance is None and model_path:
        _predictor_instance = LoadPredictorInference(model_path)
    
    return _predictor_instance
