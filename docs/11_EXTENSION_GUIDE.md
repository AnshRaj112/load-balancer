# HYDRA-LB: Extension Guide

---

## 1. Proposed Improvements

### Improvement 1: Multi-Variate Prediction

**What to change**: Predict all 4 features (`packet_rate`, `flow_count`, `byte_rate`, `switch_count`) instead of just `packet_rate`.

**Where in code**:
- `prediction/dataset.py` — Change `y` target to include all 4 features
- `prediction/model.py` — Change `output_size` from 3/5 to 4×3=12 (4 features × 3 timesteps)
- `controller/ryu_app.py` (`_update_predictions()`) — Use predicted `flow_count` and `switch_count` instead of current values

**Impact**: More accurate predicted load scores, especially after migrations (switch_count changes immediately). Currently, the predicted load score only varies based on packet_rate; with multi-variate prediction, the optimizer can anticipate flow table growth and switch redistribution effects.

**Difficulty**: ⭐⭐ (Low) — Architectural change is minimal.

---

### Improvement 2: Uncertainty-Aware Optimization

**What to change**: Replace point predictions with prediction intervals. Only trigger migration when the model is confident.

**Where in code**:
- `prediction/model.py` — Add a variance head: second output branch predicting `σ²`
- `controller/predictor.py` — Return `(mean, variance)` instead of just `mean`
- `controller/optimizer.py` — Only migrate if `predicted_variance - 2σ > threshold`

**Impact**: Prevents unnecessary migrations when the model is uncertain. Currently, a noisy prediction of 80 triggers migration even if the model is unsure. With uncertainty, it would correctly avoid action when confidence is low.

**Difficulty**: ⭐⭐⭐ (Medium) — Requires changing the loss function to negative log-likelihood.

---

### Improvement 3: Online Incremental Learning

**What to change**: Periodically fine-tune the LSTM on recent live data without restarting.

**Where in code**:
- `controller/predictor.py` — Add a `fine_tune(recent_data)` method
- `controller/ryu_app.py` — Every 5 minutes, collect last 300 observations and call `fine_tune()`
- `prediction/train.py` — Add a `fine_tune_checkpoint()` function for few-epoch training

**Impact**: Adapts to concept drift (changing traffic patterns) without manual retraining. Essential for production environments where traffic distribution changes over hours/days.

**Difficulty**: ⭐⭐⭐ (Medium) — Must handle thread safety (training while inference runs).

---

### Improvement 4: Batch Migration with Pre-Installation

**What to change**: Migrate multiple switches at once, and pre-install flow rules on the receiving controller before executing the role change.

**Where in code**:
- `controller/optimizer.py` — Return a list of `MigrationDecision` instead of a single one
- `controller/ryu_app.py` (`_execute_migration()`) — Fetch MAC table from old controller, pre-install flows on new controller, then change roles
- Add a REST endpoint: `GET /mac_table/{dpid}` to export MAC table entries

**Impact**: Faster rebalancing (5 switches moved in 30s instead of 150s) and zero-downtime migration (no flooding period because flows are pre-installed).

**Difficulty**: ⭐⭐⭐⭐ (High) — Requires careful ordering of operations to avoid split-brain.

---

### Improvement 5: Adaptive Variance Threshold

**What to change**: Automatically adjust the variance threshold based on cluster size and current load distribution.

**Where in code**:
- `controller/optimizer.py` — Replace static `self.variance_threshold` with dynamic computation

**Impact**: System works correctly with any number of controllers without manual tuning.

**Difficulty**: ⭐ (Very Low) — Simple formula change.

---

## 2. Step-by-Step Implementation: Multi-Variate Prediction

This section provides a complete implementation guide for **Improvement 1**.

### Step 1: Modify the Dataset (`prediction/dataset.py`)

**Current**: Target `y` is only `packet_rate` (column 0):
```python
y = self.values[i + self.lookback : i + self.lookback + self.horizon, 0]
```

**Changed**: Target `y` includes all 4 features:

```python
# In LoadDataset.__getitem__()
# Before:
y = self.values[i + self.lookback : i + self.lookback + self.horizon, 0]  # Shape: [horizon]

# After:
y = self.values[i + self.lookback : i + self.lookback + self.horizon, :]  # Shape: [horizon, 4]
y = y.flatten()  # Shape: [horizon × 4]
```

**New output shape**: For horizon=3, `y` becomes `[12]` (3 timesteps × 4 features).

### Step 2: Modify the Model (`prediction/model.py`)

**Change `output_size`**:

```python
# In create_model() or wherever the model is instantiated:
model = LoadPredictor(
    input_size=4,
    output_size=12,        # Changed: 3 timesteps × 4 features
    hidden_size=128,
    num_layers=2,
    use_attention=True,
    bidirectional=True
)
```

No changes needed to the LSTM or attention architecture — only the final FC layer output dimension changes automatically because `output_size` is used in `nn.Linear(64, output_size)`.

### Step 3: Modify the Training Script (`prediction/train.py`)

**Update model instantiation**:

```python
model = LoadPredictor(
    input_size=4,
    output_size=12,        # Changed
    hidden_size=128,
    num_layers=2,
    use_attention=True,
    bidirectional=True
).to(device)
```

**Update checkpoint config**:

```python
torch.save({
    'model_state_dict': model.state_dict(),
    'config': {
        'model': {
            'input_size': 4,
            'output_size': 12,     # Changed
            'hidden_size': 128,
            'num_layers': 2,
            'use_attention': True,
            'bidirectional': True
        }
    }
}, model_save_path)
```

### Step 4: Modify the Predictor (`controller/predictor.py`)

**Change the `predict()` method**:

```python
def predict(self):
    with self._lock:
        obs_array = np.array(list(self.observations))   # [30, 4]
        obs_mean = obs_array.mean(axis=0)                 # [4]
        obs_std = obs_array.std(axis=0) + 1e-8            # [4]
        obs_normalized = (obs_array - obs_mean) / obs_std

        x = torch.tensor(obs_normalized, dtype=torch.float32).unsqueeze(0)

        with torch.no_grad():
            raw = self.model(x).squeeze().cpu().numpy()   # [12]

        # Reshape to [3, 4] → 3 timesteps × 4 features
        predictions = raw.reshape(self.horizon, self.num_features)

        # Inverse transform each feature
        for f in range(self.num_features):
            predictions[:, f] = predictions[:, f] * obs_std[f] + obs_mean[f]

        self._last_predictions = predictions  # [3, 4]
        return predictions
```

**Add new accessor methods**:

```python
def get_predicted_feature(self, timestep, feature_idx):
    """Get predicted value for a specific feature at a specific future timestep."""
    if self._last_predictions is None:
        return -1.0
    return float(self._last_predictions[timestep, feature_idx])

def get_all_predictions(self):
    """Returns dict: {'t+1': [pr, fc, br, sc], 't+2': [...], 't+3': [...]}"""
    if self._last_predictions is None:
        return {}
    return {
        f't+{i+1}': self._last_predictions[i].tolist()
        for i in range(self._last_predictions.shape[0])
    }
```

### Step 5: Modify the Controller (`controller/ryu_app.py`)

**Update `_update_predictions()`**:

```python
def _update_predictions(self):
    if self.predictor is None or not self.predictor.can_predict():
        return

    scaled_pr = self.packet_rate / 30.0
    scaled_br = self.byte_rate / 30.0
    self.predictor.add_observation(scaled_pr, self.flow_count, scaled_br, self.switch_count)

    predictions = self.predictor.get_all_predictions()
    # predictions = {'t+1': [pr, fc, br, sc], 't+2': [...], 't+3': [...]}

    self.predicted_load = []
    for i in range(1, 6):
        key = f't+{i}'
        if key in predictions:
            pred = predictions[key]
            pred_pr, pred_fc, pred_br, pred_sc = pred
            # Use ALL predicted features
            p_score = min(100, max(0, pred_pr))
            f_score = min(100, max(0, pred_fc * 10.0))    # Now predicted!
            s_score = min(100, max(0, pred_sc * 20.0))    # Now predicted!
            self.predicted_load.append(p_score * 0.5 + f_score * 0.3 + s_score * 0.2)
        else:
            self.predicted_load.append(-1.0)
```

### Step 6: Retrain the Model

```bash
python prediction/train.py --generate-data --epochs 50 --output models/lstm_predictor.pt
```

### Step 7: Verify

```bash
# Restart controllers
docker compose restart

# Check predictions include all features
curl http://localhost:9100/metrics | grep predicted
# Should show updated predicted load scores

# Run experiment
python benchmarks/run_experiment.py --strategy hydra_proactive --workload burst --runs 3
```

### Expected Impact

| Metric | Before (Single Feature) | After (Multi-Variate) |
|---|---|---|
| Predicted load accuracy | Moderate | Higher |
| Unnecessary migrations | Some (due to stale flow/switch counts) | Fewer |
| Post-migration prediction | Inaccurate (switch_count changes) | Accurate |
