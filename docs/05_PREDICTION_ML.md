# HYDRA-LB: Prediction (ML) Document

---

## 1. Overview

HYDRA-LB uses a **bidirectional LSTM with temporal attention** to forecast controller load 3–5 seconds into the future. The prediction pipeline has four stages:

```
Telemetry → Dataset → Training → Inference
```

| Stage | File | Input | Output |
|---|---|---|---|
| Data collection | `data_collector.py` | Prometheus metrics | CSV files |
| Training data | `dataset.py` | Google Cluster Traces / Synthetic | CSV files |
| Training | `train.py` | CSV → DataLoader | `.pt` checkpoint |
| Inference | `predictor.py` | Sliding window | Predicted loads |

---

## 2. From Telemetry to Dataset

### 2.1 Live Data Collection (`prediction/data_collector.py`)

Collects metrics from running controllers by scraping their Prometheus endpoints:

```python
CONTROLLER_ENDPOINTS = [
    "http://172.20.0.10:9100/metrics",
    "http://172.20.0.11:9100/metrics",
    "http://172.20.0.12:9100/metrics",
]
```

**Features extracted** from each controller:

| Feature | Prometheus Metric | Interpretation |
|---|---|---|
| `packet_rate` | `hydra_packet_rate` / `packet_in_total` | Traffic intensity |
| `flow_count` | `hydra_flow_count` | Control plane complexity |
| `byte_rate` | `hydra_byte_rate` / `bytes_total` | Throughput |
| `switch_count` | `hydra_switch_count` | Controller responsibility |

**Collection loop**:
```python
while time.time() - start_time < duration:
    for endpoint in endpoints:
        metrics = collect_from_controller(endpoint)   # HTTP GET + parse
        features = extract_features(metrics)          # Extract 4 features
        writer.writerow(features)                     # Append to CSV
    time.sleep(interval)  # Default: 1 second
```

**Output CSV format**:
```csv
timestamp,controller_id,packet_rate,flow_count,byte_rate,switch_count
2025-01-01T12:00:01,1,450.5,25,120000.0,7
2025-01-01T12:00:01,2,120.2,10,45000.0,6
```

### 2.2 Training Data: Google Cluster Traces

The primary training data comes from the **Google Cluster Traces** dataset, which records per-machine CPU and memory usage across thousands of servers over a 29-day period. We extract rolling aggregate resource-consumption windows, resample them at one-second granularity, and map the resulting time series to our four-feature schema (`packet_rate`, `flow_count`, `byte_rate`, `switch_count`) via proportional scaling. This exposes the model to realistic burst, skew, and diurnal patterns found in production datacenters.

### 2.3 Synthetic Data Generation (Fallback)

For initial prototyping when no real data is available, `dataset.py` provides a synthetic data generator:

```python
def save_synthetic_data(filepath, num_samples=10000):
    t = np.linspace(0, 100, num_samples)
    data = {
        'packet_rate': 50 + 30 * np.sin(t * 0.5) + np.random.normal(0, 5, num_samples),
        'flow_count':  5  + 3  * np.cos(t * 0.3) + np.random.normal(0, 1, num_samples),
        'byte_rate':   30 + 20 * np.sin(t * 0.7) + np.random.normal(0, 3, num_samples),
        'switch_count': 3 + 1  * np.sin(t * 0.1) + np.random.normal(0, 0.5, num_samples),
    }
```

> **Note**: The production model is trained on Google Cluster Traces. Synthetic data is available as a fallback for rapid prototyping but should not be used for final evaluation.

---

## 3. Dataset Windowing

### 3.1 `LoadDataset` (PyTorch Dataset)

```python
class LoadDataset(Dataset):
    def __init__(self, data_path=None, lookback=30, horizon=5):
        # Load CSV
        df = pd.read_csv(data_path)
        # Clip outliers (important for stability)
        for col in ['packet_rate', 'flow_count', 'byte_rate', 'switch_count']:
            upper = df[col].quantile(0.99)
            df[col] = df[col].clip(upper=upper)
        # Scale (×30 to align with inference scaling)
        self.values = df[features].values * 30.0
```

**Sliding window**:
```
Sample i:
  X = values[i : i + lookback]     # Shape: [30, 4]
  y = values[i + lookback : i + lookback + horizon, 0]  # Shape: [5]
                                                          # (packet_rate only)
```

**Visual representation**:
```
Time: [0, 1, 2, ..., 29, 30, 31, 32, 33, 34, ...]
       \_____________X_____________/\_____y_____/
       Window of 30 timesteps       Next 5 packet_rates
```

**Key detail**: `y` only contains `packet_rate` (column 0). The model predicts only this single feature, not all four.

### 3.2 Input/Output Shapes

| Tensor | Shape | Description |
|---|---|---|
| `X` (input) | `[batch, 30, 4]` | 30 timesteps × 4 features |
| `y` (target) | `[batch, 5]` | Next 5 values of `packet_rate` |
| Model output | `[batch, output_size]` | Predicted packet rates (default: 5 or 3) |

---

## 4. LSTM Architecture (`prediction/model.py`)

### 4.1 `LoadPredictor` — Full Model

```
Input: [batch, 30, 4]
  │
  ▼
┌───────────────────────────────────────────┐
│ BiLSTM Layer 1                             │
│ input_size=4, hidden_size=128, layers=2    │
│ bidirectional=True → output_size=256       │
│ dropout=0.3                                │
│ Output: [batch, 30, 256]                   │
└─────────────────┬─────────────────────────┘
                  │
                  ▼
┌───────────────────────────────────────────┐
│ TemporalAttention                          │
│ input_size=256                             │
│ Learns which of the 30 timesteps matters   │
│ Output: [batch, 256] (weighted context)    │
│ + attention_weights: [batch, 30]           │
└─────────────────┬─────────────────────────┘
                  │
                  ▼
┌───────────────────────────────────────────┐
│ Dropout (p=0.3)                            │
└─────────────────┬─────────────────────────┘
                  │
                  ▼
┌───────────────────────────────────────────┐
│ Fully Connected: 256 → 64 → ReLU          │
│ Fully Connected: 64 → output_size          │
│ Output: [batch, 3 or 5]                    │
└───────────────────────────────────────────┘
```

### 4.2 LSTM Details

```python
self.lstm = nn.LSTM(
    input_size=input_size,      # 4 features
    hidden_size=hidden_size,    # 128
    num_layers=num_layers,      # 2 (stacked)
    batch_first=True,
    dropout=0.3,
    bidirectional=True          # → output dim = 2 × 128 = 256
)
```

**Why bidirectional?** A bidirectional LSTM processes the sequence both forward (past → present) and backward (present → past). For time series, this allows the model to learn patterns where both trends and reversals matter. For example, "traffic decreased but is about to spike" is better captured by looking at the sequence in both directions.

**Why 2 layers?** Stacking 2 LSTM layers provides hierarchical feature extraction: Layer 1 captures basic temporal patterns, Layer 2 captures higher-level patterns from Layer 1's representations.

### 4.3 Temporal Attention (`prediction/attention.py`)

```python
class TemporalAttention(nn.Module):
    def __init__(self, hidden_size):
        self.W = nn.Linear(hidden_size, hidden_size)
        self.v = nn.Linear(hidden_size, 1, bias=False)

    def forward(self, lstm_output):
        # lstm_output shape: [batch, 30, 256]
        energy = torch.tanh(self.W(lstm_output))    # [batch, 30, 256]
        scores = self.v(energy).squeeze(-1)          # [batch, 30]
        weights = F.softmax(scores, dim=1)            # [batch, 30]
        context = torch.bmm(weights.unsqueeze(1), lstm_output)  # [batch, 1, 256]
        return context.squeeze(1), weights
```

**Simple explanation**: Not all past timesteps are equally relevant for predicting the future. Attention assigns a weight to each of the 30 past observations. If a traffic spike happened 5 seconds ago, the model can learn to focus more on that recent spike.

**Technical explanation**: The attention mechanism is:
1. **Energy function**: `e_t = tanh(W × h_t)` — transforms each hidden state
2. **Score**: `s_t = v^T × e_t` — projects to scalar
3. **Weights**: `α_t = softmax(s)` — normalized to sum to 1
4. **Context**: `c = Σ(α_t × h_t)` — weighted sum of hidden states

**Multi-Head Attention** (`MultiHeadTemporalAttention`): Also included for experimentation. Uses Q/K/V projections with scaled dot-product attention, similar to Transformers. Not used in the default model configuration.

### 4.4 `LoadPredictorLite` — Lightweight Variant

```python
class LoadPredictorLite(nn.Module):
    # Single layer, unidirectional LSTM, no attention
    # For resource-constrained environments
```

Not used in production but available for experimentation with lower-capacity models.

---

## 5. Training Process (`prediction/train.py`)

### 5.1 Training Loop

```python
def train(model, loader, criterion, optimizer, device):
    model.train()
    for X, y in loader:
        optimizer.zero_grad()
        out = model(X)
        loss = criterion(out, y)    # MSE Loss
        loss.backward()
        nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)  # Gradient clipping
        optimizer.step()
```

**Loss function**: MSE (Mean Squared Error) — standard for regression tasks.

**Gradient clipping**: `max_norm=1.0`. LSTMs are prone to exploding gradients, especially with long sequences. Clipping prevents this.

**Optimizer**: Adam with `lr=0.001`.

### 5.2 Hyperparameters

```python
model = LoadPredictor(
    input_size=4,           # 4 features
    output_size=5,          # Predict 5 timesteps ahead
    hidden_size=128,        # LSTM hidden dimension
    num_layers=2,           # Stacked LSTM layers
    use_attention=True,     # Enable temporal attention
    bidirectional=True      # Bidirectional LSTM
)
```

**Default training config**:
- Epochs: 20
- Batch size: 64 (or `min(64, len(dataset))` for small datasets)
- Learning rate: 0.001

### 5.3 Checkpoint Format

```python
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
}, model_save_path)
```

The checkpoint contains both the weights and the architecture config. This allows `predictor.py` to reconstruct the model without hardcoding hyperparameters.

---

## 6. Inference Flow (`controller/predictor.py`)

### 6.1 Initialization

```python
class LoadPredictorInference:
    def __init__(self, model_path, lookback=30, num_features=4):
        self.lookback = lookback
        self.observations = deque(maxlen=lookback)   # Sliding window
        self._load_model(model_path)
```

### 6.2 Adding Observations

```python
def add_observation(self, packet_rate, flow_count, byte_rate, switch_count):
    obs = [packet_rate, flow_count, byte_rate, switch_count]
    if len(self.observations) == 0:
        # Pad buffer with first observation (cold start)
        for _ in range(self.lookback):
            self.observations.append(obs.copy())
    else:
        self.observations.append(obs)
```

**Cold start strategy**: The first observation is replicated 30 times to fill the buffer immediately. This allows predictions to start from the very first observation, though they'll be less accurate until real data fills the buffer.

### 6.3 Prediction

```python
def predict(self):
    with self._lock:
        obs_array = np.array(list(self.observations))   # [30, 4]
        # Normalize
        obs_mean = obs_array.mean(axis=0)
        obs_std = obs_array.std(axis=0) + 1e-8
        obs_normalized = (obs_array - obs_mean) / obs_std

        x = torch.tensor(obs_normalized, dtype=torch.float32).unsqueeze(0)  # [1, 30, 4]

        with torch.no_grad():
            predictions = self.model(x)   # [1, output_size]

        # Inverse transform (restore original scale)
        predictions = predictions.squeeze().cpu().numpy()
        predictions = predictions * obs_std[0] + obs_mean[0]  # Only packet_rate

        self._last_predictions = predictions
        return predictions
```

**Normalization**: Z-score normalization using the **current window's statistics**. This is important because live data distribution shifts over time. Using window-local statistics adapts to the current scale.

**Inverse transform**: Only `obs_std[0]` and `obs_mean[0]` are used (index 0 = `packet_rate`) because predictions are for packet rate only.

### 6.4 Thread Safety

```python
self._lock = threading.Lock()
```

The `predict()` method uses a lock because:
- The monitoring thread calls `add_observation()` every 1 second
- `predict()` reads the observation buffer
- Without locking, the buffer could change mid-prediction

---

## 7. Example Data & Prediction Trace

### Input (30 timesteps of scaled metrics):

```
Timestep  packet_rate  flow_count  byte_rate  switch_count
t-29      28.5         5.0         15.3       3.0
t-28      29.1         5.0         16.1       3.0
...
t-1       35.2         6.0         18.5       4.0
t-0       38.7         6.0         20.1       4.0
```

### After Z-score normalization:

```
Mean: [32.1, 5.4, 17.2, 3.3]    Std: [4.2, 0.5, 2.1, 0.5]

t-29: [-0.86, -0.80, -0.90, -0.60]
t-0:  [+1.57, +1.20, +1.38, +1.40]
```

### LSTM → Attention → FC:

```
LSTM output: [1, 30, 256]
Attention weights: [1, 30]  ← higher weights on recent timesteps
Context vector: [1, 256]
FC1: [1, 64]
FC2: [1, 3]                 ← predictions (normalized)
```

### After inverse transform:

```
predictions = [1.12, 1.48, 2.01] × 4.2 + 32.1
            = [36.8, 38.3, 40.5]           ← predicted packet_rate at t+1, t+2, t+3
```

### Converted to load scores by ryu_app.py:

```
For t+3: predicted_packet_rate = 40.5
p_score = min(100, 40.5) = 40.5    (already scaled / 30 was applied earlier)
f_score = min(100, 6 × 10) = 60.0   (current flow count)
s_score = min(100, 4 × 20) = 80.0   (current switch count)

predicted_load = 40.5×0.5 + 60×0.3 + 80×0.2
               = 20.25 + 18.0 + 16.0
               = 54.25
```

---

## 8. Assumptions & Limitations

### Assumptions

1. **Traffic representativeness**: The model is trained on Google Cluster Traces, which captures realistic datacenter patterns (bursts, skew, diurnal cycles). However, specific deployment environments may exhibit patterns not well-represented in this dataset.
2. **Feature independence**: Each feature is normalized independently. Correlations between features are learned by the LSTM but not explicitly modeled.
3. **Fixed lookback**: 30 timesteps = 30 seconds of history. This may be too short for capturing long-term trends or too long for very rapid changes.
4. **Only packet_rate predicted**: Other features are assumed stable over the prediction horizon.

### Limitations

1. **No online learning**: The model is loaded once at startup. It doesn't adapt to new patterns during runtime. For deployment-specific tuning, retraining on live data is recommended.
2. **Cold start**: First predictions are based on 30 copies of the first observation — inaccurate for ~30 seconds.
3. **Scale sensitivity**: The `/30.0` scaling factor in `ryu_app.py` is hardcoded and may not be appropriate for all traffic levels.
4. **No uncertainty estimates**: The model outputs point predictions. It doesn't indicate confidence, so the optimizer can't distinguish between high-confidence and low-confidence predictions.

---

## 9. Retraining Process

### Option 1: Retrain with live data

```bash
# Step 1: Collect live data (5 minutes)
python prediction/data_collector.py --duration 300 --output data/training/

# Step 2: Retrain
python prediction/train.py --data data/training/telemetry_*.csv --epochs 100 --output models/lstm_predictor.pt

# Step 3: Restart controllers to load new model
docker compose restart ryu-controller-1 ryu-controller-2 ryu-controller-3
```

### Option 2: Automated pipeline

```bash
python benchmarks/retrain_model.py --collect-duration 300 --epochs 100
```

This script:
1. Collects live data
2. Backs up existing model
3. Retrains
4. Saves new model

### Option 3: Continuous learning during experiments

```bash
python benchmarks/run_experiment.py --strategy hydra_proactive --workload burst --continuous-learning
```

This runs data collection and retraining in the background while experiments execute.
