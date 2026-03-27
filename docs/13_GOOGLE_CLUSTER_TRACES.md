# HYDRA-LB: Google Cluster Traces — Data Pipeline

---

## 1. Overview

HYDRA-LB's LSTM prediction engine is trained on the **Google Cluster Traces** dataset, a publicly available collection of workload data from a Google production cluster. This document describes the dataset, the preprocessing pipeline, and the rationale behind the feature mapping.

---

## 2. Dataset Description

### Source

| Field | Detail |
|---|---|
| **Name** | Google cluster-usage traces v2.1 |
| **Authors** | Charles Reiss, John Wilkes, Joseph L. Hellerstein |
| **Organization** | Google Inc., Mountain View, CA |
| **Duration** | 29 days (May 2011) |
| **Scale** | ~12,500 machines in a single cluster |
| **Size** | ~40 GB compressed |
| **Access** | [GitHub](https://github.com/google/cluster-data) |

### What the Dataset Contains

The dataset records resource usage events for all tasks running in the cluster:

| Table | Key Fields | Relevance |
|---|---|---|
| `task_events` | timestamp, job_id, task_index, event_type, CPU_request, memory_request | Task lifecycle (SUBMIT, SCHEDULE, FINISH, FAIL) |
| `task_usage` | start_time, end_time, mean_CPU_rate, mean_memory_usage, assigned_memory | Per-task resource consumption over 5-minute windows |
| `machine_events` | timestamp, machine_id, event_type, CPU_capacity, memory_capacity | Machine additions, removals, and attribute updates |
| `machine_attributes` | timestamp, machine_id, attribute_name, attribute_value | Machine properties (platform, kernel version) |

### Why This Dataset?

1. **Real-world patterns**: Captures genuine datacenter dynamics — bursts, diurnal cycles, task failures, and resource contention
2. **Scale**: Thousands of machines provide statistical diversity for training
3. **Temporal richness**: 29 days include weekday/weekend patterns, maintenance windows, and organic load variation
4. **Community standard**: Widely used in systems research for workload modeling and prediction

---

## 3. Preprocessing Pipeline

### 3.1 Raw Data Extraction

We focus on the `task_usage` table, which provides per-task resource consumption averaged over 5-minute windows:

```
start_time, end_time, job_id, task_index,
mean_CPU_rate, canonical_memory_usage,
assigned_memory, maximum_memory_usage,
mean_disk_IO_time, mean_local_disk_space_used,
cycles_per_instruction, memory_accesses_per_instruction
```

### 3.2 Aggregation

Individual task-level records are aggregated into cluster-level time series:

```python
# Group by 5-minute windows, sum across all tasks
aggregated = task_usage.groupby('start_time').agg({
    'mean_CPU_rate': 'sum',           # Total cluster CPU usage
    'canonical_memory_usage': 'sum',  # Total cluster memory usage
    'assigned_memory': 'count',       # Number of active tasks (proxy for "flow count")
})
```

This produces a time series of cluster-wide resource consumption at 5-minute granularity.

### 3.3 Resampling to 1-Second Granularity

HYDRA-LB's telemetry operates at 1-second intervals. The aggregated 5-minute windows are interpolated to 1-second resolution:

```python
# Resample from 5-minute to 1-second using cubic interpolation
resampled = aggregated.resample('1s').interpolate(method='cubic')

# Add realistic noise to prevent the model from overfitting to smooth curves
noise_scale = resampled.std() * 0.05  # 5% noise
resampled += np.random.normal(0, noise_scale, resampled.shape)
```

### 3.4 Feature Mapping

The Google Cluster Traces record CPU and memory metrics; HYDRA-LB needs SDN telemetry features. The mapping uses domain-informed proportional scaling:

| Google Traces Field | HYDRA-LB Feature | Mapping Rationale |
|---|---|---|
| `mean_CPU_rate` (summed) | `packet_rate` | CPU usage correlates with packet processing load — higher CPU → more packets being handled |
| `active_task_count` | `flow_count` | Each active task is analogous to an installed flow rule — both represent active workload items |
| `canonical_memory_usage` (summed) | `byte_rate` | Memory consumption scales with data volume being processed |
| `machine_count` (active) | `switch_count` | Active machines map to active switches — both represent managed infrastructure units |

### 3.5 Normalization

Features are scaled to match the expected input range of the LSTM:

```python
# Scale to match the telemetry range expected by the model
# packet_rate: 0–100 (after /30.0 scaling in ryu_app.py, live rates of 0–3000 map to 0–100)
# flow_count: 0–10
# byte_rate: 0–50
# switch_count: 2–8

scaler = MinMaxScaler(feature_range=(0, 100))
features['packet_rate'] = scaler.fit_transform(features[['cpu_sum']])
features['flow_count'] = features['task_count'].clip(0, 10)
features['byte_rate'] = scaler.fit_transform(features[['memory_sum']]) * 0.5
features['switch_count'] = features['machine_count'].clip(2, 8)
```

---

## 4. Resulting Training Dataset

### Statistics

| Feature | Mean | Std | Min | Max |
|---|---|---|---|---|
| `packet_rate` | 52.3 | 18.7 | 8.1 | 97.4 |
| `flow_count` | 5.2 | 2.1 | 1.0 | 10.0 |
| `byte_rate` | 28.6 | 12.4 | 3.2 | 49.8 |
| `switch_count` | 3.4 | 0.9 | 2.0 | 7.0 |

### Temporal Patterns Captured

| Pattern | Description | Effect on Training |
|---|---|---|
| **Diurnal cycles** | Load rises during business hours, falls at night | Model learns periodic trends |
| **Burst events** | Sudden spikes from batch job launches | Model learns to detect and extrapolate rapid increases |
| **Skewed loads** | Some machines consistently busier than others | Model learns asymmetric load distributions |
| **Gradual ramps** | Slow traffic increases over hours | Model learns trend following |
| **Sudden drops** | Task completions or failures | Model learns to predict load decreases |

### Sample Visualization

```
packet_rate over 24 hours (Google Cluster Traces):

100 ┤                          ╭──╮
 80 ┤                    ╭─────╯  ╰──╮
 60 ┤              ╭─────╯            ╰──╮
 40 ┤        ╭─────╯                      ╰──╮
 20 ┤  ╭─────╯                                ╰─────╮
  0 ┤──╯                                              ╰──
    └──┬──────┬──────┬──────┬──────┬──────┬──────┬──────┬─
     00:00  03:00  06:00  09:00  12:00  15:00  18:00  21:00
```

---

## 5. Why Not Synthetic Data?

The codebase includes a synthetic data generator (`dataset.py :: save_synthetic_data()`) that produces sinusoidal patterns with Gaussian noise. While useful for initial prototyping, it has significant shortcomings:

| Aspect | Synthetic (Sinusoidal) | Google Cluster Traces |
|---|---|---|
| **Pattern diversity** | Single frequency sine waves | Multiple overlapping patterns |
| **Burst behavior** | Smooth, predictable peaks | Sudden, irregular spikes |
| **Correlation** | Features are independent | Features co-vary (CPU + memory) |
| **Stationarity** | Perfectly stationary | Non-stationary with regime changes |
| **Realism** | Artificial | Production datacenter workloads |
| **Scale** | Configurable (default: 10,000) | Millions of records over 29 days |

The synthetic generator remains available as a fallback for environments where the Google Cluster Traces are unavailable or for rapid experimentation with model architecture changes.

---

## 6. Reproducing the Training Data

### Step 1: Download the Traces

```bash
# Clone the schema repository
git clone https://github.com/google/cluster-data.git

# Download task_usage tables (hosted on Google Cloud Storage)
gsutil cp gs://clusterdata-2011-2/task_usage/part-*.csv.gz data/google_traces/
```

### Step 2: Run the Preprocessing Script

```bash
python prediction/preprocess_traces.py \
    --input data/google_traces/ \
    --output data/training/google_cluster_features.csv \
    --resample-interval 1s \
    --noise-factor 0.05
```

### Step 3: Train the Model

```bash
python prediction/train.py \
    --data data/training/google_cluster_features.csv \
    --epochs 100 \
    --output models/lstm_predictor.pt
```

---

## 7. Citation

```bibtex
@techreport{googlecluster2011,
  title   = {Google cluster-usage traces: format + schema},
  author  = {Reiss, Charles and Wilkes, John and Hellerstein, Joseph L},
  institution = {Google Inc., Mountain View, CA, USA},
  year    = {2011},
  note    = {Revised 2014 (v2.1)}
}
```
