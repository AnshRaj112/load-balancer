"""
LSTM-based Load Prediction Model

Architecture:
    Input: [batch, seq_len=10, features=4]
        ↓
    LSTM Layer 1 (bidirectional, hidden=64)
        ↓
    Temporal Attention
        ↓
    LSTM Layer 2 (hidden=32)
        ↓
    Dense → Output: [batch, horizon=5]
"""

import torch
import torch.nn as nn
from typing import Optional

# Handle both module and script imports
try:
    from .attention import TemporalAttention
except ImportError:
    from attention import TemporalAttention


class LoadPredictor(nn.Module):
    """
    LSTM-based load prediction model with temporal attention.
    
    Predicts future controller load based on historical telemetry.
    
    Input features:
        - packet_rate: Packets per second
        - flow_count: Number of active flows
        - byte_rate: Bytes per second
        - switch_count: Number of connected switches
    """
    
    def __init__(
        self,
        input_size: int = 4,
        hidden_size: int = 64,
        num_layers: int = 2,
        output_size: int = 5,
        dropout: float = 0.2,
        bidirectional: bool = True,
        use_attention: bool = True
    ):
        """
        Initialize the load predictor.
        
        Args:
            input_size: Number of input features (default: 4)
            hidden_size: LSTM hidden dimension (default: 64)
            num_layers: Number of LSTM layers (default: 2)
            output_size: Prediction horizon (default: 5)
            dropout: Dropout rate (default: 0.2)
            bidirectional: Use bidirectional LSTM (default: True)
            use_attention: Use temporal attention (default: True)
        """
        super().__init__()
        
        self.input_size = input_size
        self.hidden_size = hidden_size
        self.num_layers = num_layers
        self.output_size = output_size
        self.bidirectional = bidirectional
        self.use_attention = use_attention
        
        # Direction multiplier for hidden size
        self.num_directions = 2 if bidirectional else 1
        
        # Layer normalization for input
        self.input_norm = nn.LayerNorm(input_size)
        
        # First LSTM layer (possibly bidirectional)
        self.lstm1 = nn.LSTM(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=1,
            batch_first=True,
            dropout=0,
            bidirectional=bidirectional
        )
        
        # Temporal attention
        lstm1_output_size = hidden_size * self.num_directions
        if use_attention:
            self.attention = TemporalAttention(
                hidden_size=lstm1_output_size,
                attention_size=32
            )
        
        # Second LSTM layer
        self.lstm2 = nn.LSTM(
            input_size=lstm1_output_size,
            hidden_size=hidden_size // 2,
            num_layers=1,
            batch_first=True,
            dropout=0,
            bidirectional=False
        )
        
        # Dropout
        self.dropout = nn.Dropout(dropout)
        
        # Output layers
        self.fc1 = nn.Linear(hidden_size // 2, hidden_size // 4)
        self.fc2 = nn.Linear(hidden_size // 4, output_size)
        
        # Activation
        self.relu = nn.ReLU()
        
    def forward(
        self, 
        x: torch.Tensor,
        return_attention: bool = False
    ) -> torch.Tensor | tuple[torch.Tensor, torch.Tensor]:
        """
        Forward pass.
        
        Args:
            x: Input tensor [batch, seq_len, input_size]
            return_attention: If True, also return attention weights
            
        Returns:
            predictions: [batch, output_size]
            attention_weights: [batch, seq_len] (if return_attention=True)
        """
        # Normalize input
        x = self.input_norm(x)
        
        # First LSTM layer
        lstm1_out, _ = self.lstm1(x)  # [batch, seq_len, hidden*directions]
        lstm1_out = self.dropout(lstm1_out)
        
        # Apply attention
        attention_weights = None
        if self.use_attention:
            context, attention_weights = self.attention(lstm1_out)
            # Expand context for second LSTM
            lstm2_input = context.unsqueeze(1)  # [batch, 1, hidden*directions]
        else:
            # Use last hidden state
            lstm2_input = lstm1_out[:, -1:, :]  # [batch, 1, hidden*directions]
        
        # Second LSTM layer
        lstm2_out, (hidden, _) = self.lstm2(lstm2_input)
        
        # Use final hidden state
        out = hidden.squeeze(0)  # [batch, hidden//2]
        out = self.dropout(out)
        
        # Output layers
        out = self.relu(self.fc1(out))
        predictions = self.fc2(out)  # [batch, output_size]
        
        if return_attention:
            return predictions, attention_weights
        return predictions
    
    def predict(self, x: torch.Tensor) -> torch.Tensor:
        """
        Make predictions (inference mode).
        
        Args:
            x: Input tensor [batch, seq_len, input_size]
            
        Returns:
            predictions: [batch, output_size]
        """
        self.eval()
        with torch.no_grad():
            return self.forward(x)


class LoadPredictorLite(nn.Module):
    """
    Lightweight version for resource-constrained inference.
    Uses single-layer unidirectional LSTM without attention.
    """
    
    def __init__(
        self,
        input_size: int = 4,
        hidden_size: int = 32,
        output_size: int = 5
    ):
        super().__init__()
        
        self.lstm = nn.LSTM(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=1,
            batch_first=True
        )
        
        self.fc = nn.Linear(hidden_size, output_size)
        
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        _, (hidden, _) = self.lstm(x)
        return self.fc(hidden.squeeze(0))


def create_model(config: Optional[dict] = None) -> LoadPredictor:
    """
    Factory function to create a model from config.
    
    Args:
        config: Optional configuration dictionary
        
    Returns:
        Initialized LoadPredictor model
    """
    default_config = {
        'input_size': 4,
        'hidden_size': 64,
        'num_layers': 2,
        'output_size': 5,
        'dropout': 0.2,
        'bidirectional': True,
        'use_attention': True
    }
    
    if config:
        default_config.update(config)
    
    return LoadPredictor(**default_config)
