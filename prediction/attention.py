"""
Temporal Attention Mechanism for Load Prediction

Applies attention weights to LSTM hidden states to focus on
the most relevant past timesteps for prediction.
"""

import torch
import torch.nn as nn
import torch.nn.functional as F


class TemporalAttention(nn.Module):
    """
    Temporal attention mechanism for time series.
    
    Given a sequence of hidden states, computes attention weights
    that indicate the importance of each timestep for prediction.
    
    This helps the model focus on relevant patterns like:
    - Recent spikes that might continue
    - Periodic patterns (e.g., hourly cycles)
    - Anomalous events that predict future load
    """
    
    def __init__(self, hidden_size: int, attention_size: int = 32):
        """
        Args:
            hidden_size: Size of input hidden states
            attention_size: Size of attention projection layer
        """
        super().__init__()
        
        self.hidden_size = hidden_size
        self.attention_size = attention_size
        
        # Attention scoring layers
        self.W = nn.Linear(hidden_size, attention_size, bias=False)
        self.v = nn.Linear(attention_size, 1, bias=False)
        
    def forward(self, hidden_states: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        """
        Apply attention to sequence of hidden states.
        
        Args:
            hidden_states: [batch, seq_len, hidden_size]
            
        Returns:
            context: Weighted sum of hidden states [batch, hidden_size]
            attention_weights: Attention scores [batch, seq_len]
        """
        # Project hidden states: [batch, seq_len, attention_size]
        energy = torch.tanh(self.W(hidden_states))
        
        # Compute attention scores: [batch, seq_len, 1]
        scores = self.v(energy)
        
        # Squeeze and apply softmax: [batch, seq_len]
        attention_weights = F.softmax(scores.squeeze(-1), dim=-1)
        
        # Compute weighted sum (context vector): [batch, hidden_size]
        context = torch.bmm(attention_weights.unsqueeze(1), hidden_states).squeeze(1)
        
        return context, attention_weights


class MultiHeadTemporalAttention(nn.Module):
    """
    Multi-head version of temporal attention for richer representations.
    """
    
    def __init__(self, hidden_size: int, num_heads: int = 4, dropout: float = 0.1):
        """
        Args:
            hidden_size: Size of input hidden states
            num_heads: Number of attention heads
            dropout: Dropout rate
        """
        super().__init__()
        
        assert hidden_size % num_heads == 0, "hidden_size must be divisible by num_heads"
        
        self.hidden_size = hidden_size
        self.num_heads = num_heads
        self.head_size = hidden_size // num_heads
        
        # Query, Key, Value projections
        self.query = nn.Linear(hidden_size, hidden_size)
        self.key = nn.Linear(hidden_size, hidden_size)
        self.value = nn.Linear(hidden_size, hidden_size)
        
        # Output projection
        self.output = nn.Linear(hidden_size, hidden_size)
        
        self.dropout = nn.Dropout(dropout)
        
    def forward(self, hidden_states: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        """
        Apply multi-head attention.
        
        Args:
            hidden_states: [batch, seq_len, hidden_size]
            
        Returns:
            output: Attended hidden states [batch, seq_len, hidden_size]
            attention_weights: Attention scores [batch, num_heads, seq_len, seq_len]
        """
        batch_size, seq_len, _ = hidden_states.shape
        
        # Project to Q, K, V and reshape for multi-head
        Q = self.query(hidden_states).view(batch_size, seq_len, self.num_heads, self.head_size).transpose(1, 2)
        K = self.key(hidden_states).view(batch_size, seq_len, self.num_heads, self.head_size).transpose(1, 2)
        V = self.value(hidden_states).view(batch_size, seq_len, self.num_heads, self.head_size).transpose(1, 2)
        
        # Compute attention scores
        scores = torch.matmul(Q, K.transpose(-2, -1)) / (self.head_size ** 0.5)
        attention_weights = F.softmax(scores, dim=-1)
        attention_weights = self.dropout(attention_weights)
        
        # Apply attention to values
        context = torch.matmul(attention_weights, V)
        
        # Reshape and project output
        context = context.transpose(1, 2).contiguous().view(batch_size, seq_len, self.hidden_size)
        output = self.output(context)
        
        return output, attention_weights
