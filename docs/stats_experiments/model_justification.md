# Model Justification: Enhanced Direct-Ridge (RidgeFull)

> **Production model: RidgeFull (Enhanced Direct-Ridge) -- AVG MAE 24.88**
> A 24.6% improvement over the previous production model (Direct-Ridge,
> MAE 32.99), achieved through richer feature engineering, full
> historical data, and StandardScaler preprocessing.

## 1. Single Model Experiments

This project has undergone five phases of systematic experimentation to
find the best carbon intensity forecasting model, documented in
[experiment_report.md](./experiment_report.md). The progression:

### Phase 1: Baseline Benchmark (18 Models)

A comprehensive comparison of 18 forecasting approaches -- statistical,
tree-based, deep learning, and foundation models -- established
Direct-Ridge as the production model at MAE 32.99. This beat all 17
competitors on the full backfill training set (~83 days, ~3,972
points). Key results:

| Model            | MAE   | Notes                            |
| ---------------- | ----- | -------------------------------- |
| Direct-Ridge     | 32.99 | Winner -- simple, fast, accurate |
| Ridge            | 33.04 | Near-identical to Direct-Ridge   |
| Direct-XGBoost   | 33.50 | Close third                      |
| Fourier          | 35.78 | Pure periodic decomposition      |
| Seasonal Naive   | 42.20 | Repeat-last-week baseline        |
| Transformer-10K  | 42.44 | Best neural approach             |
| SARIMAX          | 64.32 | Classical time series             |
| Holt-Winters     | 93.14 | Worst performer                  |

![Phase 1 Benchmark Heatmap](./benchmarks/benchmark_heatmap_full_backfill.png)

### Phases 2--4: Feature Engineering and Data Expansion

Subsequent phases focused on improving tree-based models through
enhanced features (Phase 2), residual targets (Phase 3), and full-year
seasonal data (Phase 4). CatBoost reached MAE 31.63 in Phase 4 --
the first model to beat Direct-Ridge's 32.99.

### Phase 5: Weather Enrichment

Extended weather features (11 raw from Open-Meteo instead of 3) gave
every tree model a significant boost. Direct-XGBoost with Weather
Variant A hit MAE 29.49 -- a 10.6% improvement over Direct-Ridge.

![Weather Feature Comparison](./experiments/weather_comparison.png)

#### Weather Feature Ablation

Weather features are the single most impactful predictor category.
The ablation study from the
[comparison_report.md](./benchmarks/comparison_report.md) (Full
Backfill results) demonstrates this clearly:

| Model           | With Weather | No Weather | Delta  |
| --------------- | ------------ | ---------- | ------ |
| Direct-Ridge    | 32.99        | 44.54      | -11.56 |
| Ridge           | 33.04        | 43.61      | -10.57 |
| Direct-XGBoost  | 33.50        | 40.80      | -7.30  |
| XGBoost         | 40.84        | 47.28      | -6.44  |
| Transformer-10K | 42.44        | 60.69      | -18.25 |
| CatBoost        | 47.05        | 45.34      | +1.70  |
| Random Forest   | 50.67        | 47.27      | +3.40  |
| LightGBM        | 49.44        | 45.14      | +4.30  |

Direct-Ridge benefits most from weather among non-transformer models
(-11.56 MAE). This is because carbon intensity is fundamentally driven
by weather: wind speed determines wind generation, solar radiation
determines solar generation, and temperature drives heating/cooling
demand. A linear model with properly engineered weather features
captures these relationships directly.

The finding that weather _hurts_ recursive tree models (CatBoost +1.70,
RF +3.40, LightGBM +4.30) is explained by the 336-step recursive
forecasting: lag-1 weather values become stale by step 10, yet the
model still conditions on them for all 336 steps. Direct models avoid
this because each horizon step gets its own weather features
independently.

## 2. Ensemble Experiments

After Phase 5, discussions with the client motivated further
experimentation to push accuracy beyond MAE 29.49. The goal was to
explore combinations of models -- including neural networks, gradient
boosting, and ensembles -- to achieve better predictions.

Evaluation in this phase switched from a simple train/test split to a
**train/validation/test** split: training on all data up to 14 days
before the latest reading, a 7-day validation window (used for
ensemble weight selection), and a held-out 7-day test window. This
prevents information leakage from the validation-based ensemble
strategies (val-weighted, val-drop) into the test evaluation.

### 2.1 Feature Engineering Overhaul

The single largest improvement came from expanding feature engineering
from 14 features to 65 features:

| Feature Group  | Old (14 features)               | New (65 features)                                                                                               |
| -------------- | ------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| Temporal       | 2 sin/cos pairs (hour, dow)     | 22 features: 6 Fourier harmonics for hour-of-day, 2 for day-of-week, 2 for day-of-year, weekend flag, night flag |
| Horizon        | 1 feature (h/336)               | 4 features: h, h-squared, h-cubed, log(h)                                                                       |
| Origin stats   | 3 (last, mean, std)             | 13 (+ median, min, max, 7-day stats, lag_24h, lag_7d, trend, same_hour_mean)                                    |
| Weather        | 3 raw                           | 16 (10 raw + 6 engineered: wind_power, wind_ramp, pressure_change, solar_clearness, temp_deviation, wind_dir sin/cos) |
| Interactions   | 0                               | 10 (last x horizon, weekend x hour, wind x hour, solar x hour, etc.)                                            |
| Preprocessing  | None                            | StandardScaler + RidgeCV (8 alpha candidates)                                                                    |

Key changes explained:

- **Richer Fourier harmonics**: 6 harmonics for hour-of-day capture
  complex intra-day patterns (e.g., morning ramp, midday solar peak,
  evening demand surge) that 1 harmonic misses entirely.
- **Polynomial horizon encoding**: h-cubed and log(h) let the model
  learn non-linear forecast degradation -- accuracy typically decays
  faster at short horizons and plateaus at long horizons.
- **Extended origin statistics**: Median, min, max, and 7-day rolling
  stats give the model a richer picture of recent carbon intensity
  behaviour. The lag_24h and lag_7d features capture same-time-yesterday
  and same-time-last-week values directly.
- **Engineered weather features**: wind_power (wind-cubed, proportional
  to actual turbine output), solar_clearness (radiation / 1000),
  pressure_change (frontal systems), and wind_ramp (wind speed
  change) encode domain-relevant physical relationships.
- **Interaction features**: Cross-terms like last_value x horizon and
  wind_speed x hour_sin let a linear model capture multiplicative
  effects that would otherwise require non-linear models.
- **StandardScaler**: Critical for Ridge regression -- without
  normalisation, features with large absolute values (e.g., pressure
  ~1013 hPa) dominate features with small values (e.g., wind_dir_sin
  in [-1, 1]).
- **RidgeCV**: Automatically selects the best regularisation alpha from
  8 candidates [0.01, 0.1, 0.5, 1.0, 5.0, 10.0, 50.0, 100.0],
  removing the need for manual hyperparameter tuning.

### 2.2 Full Historical Data

The new model reads directly from `carbon_intensity.db`, using the
full historical record (~17,488 readings per region, approximately 1
year of data) instead of the previous 60-day cap. This provides:

- More seasonal coverage (summer + winter patterns)
- More weather regime diversity (calm vs. stormy periods)
- Better estimation of long-range origin statistics (7-day rolling
  windows require 7+ days of history to be meaningful)

### 2.3 Weather Caching

A pickle-based caching layer for Open-Meteo weather data
(`.weather_cache/`) enables fast repeated access during
experimentation and benchmarking without hitting API rate limits.

### 2.4 Individual Model Results

The following models were trained on the 65-feature set and evaluated
independently:

| Model                         | AVG MAE     | Time / Region | Notes                                              |
| ----------------------------- | ----------- | ------------- | -------------------------------------------------- |
| **RidgeFull**                 | **24.88**   | < 1 sec       | 65 features, full year, StandardScaler             |
| RidgeBase (no interactions)   | 25.22       | < 1 sec       | 55 features, no interaction terms                  |
| PyTorch MLP (2048,1024,512)   | 27.30-28.20 | 3-5 min       | Dropout+BatchNorm+GELU, inconsistent across runs   |
| LightGBM                      | 27.70-27.86 | 5-10 sec      | 150K subsample, num_leaves=255                     |
| Conditioned MLP (all regions) | 30.45       | 5+ min        | One-hot region encoding, did not help              |

### 2.5 Ensemble Strategy Results

Various ensemble strategies were tested, combining subsets of the
individual models above:

| Ensemble Strategy   | Models Combined                    | AVG MAE     |
| ------------------- | ---------------------------------- | ----------- |
| Median ensemble     | RidgeF, RidgeBase, MLP, LightGBM   | 24.85       |
| Val-weighted        | RidgeF, RidgeBase, MLP, LightGBM   | 24.78-24.83 |
| Trimmed mean        | RidgeF, RidgeBase, MLP             | 24.76-25.08 |

The best ensemble (median, MAE 24.85) improves over RidgeFull (24.88)
by only **0.03 MAE** (0.1%). This marginal improvement does not justify
the added complexity -- see Section 4.3 for the full argument.

### 2.6 Actual vs Predicted

![RidgeFull Actual vs Predicted](./analysis/ridgefull_actual_vs_predicted.png)

## 3. Why RidgeFull Over an Ensemble?

The best ensemble (median of RidgeF, RidgeBase, MLP, LightGBM) achieves
MAE 24.85 vs RidgeFull's 24.88 -- a **0.03 improvement** (0.1%):

- **Marginal accuracy gain**: 0.03 MAE is within measurement noise and
  not worth the added complexity.
- **4x model maintenance**: Four models to train, debug, and monitor
  instead of one. Each model has its own failure modes and
  hyperparameters.
- **MLP training latency**: The MLP component takes 3-5 minutes to
  train per region. In a 5-region production system, this adds 15-25
  minutes to each prediction cycle -- unacceptable for an API that
  needs to respond in seconds. For predicting 14 regions, thats even more. 
- **Inconsistent improvement**: The ensemble sometimes hurts on
  specific regions where MLP or LightGBM predictions pull the
  aggregate away from Ridge's correct answer.

## 4. Future Work

Potential approaches to improve accuracy further:

- **Weather forecast integration**: Using multi-day weather _forecasts_
  instead of lag-1 observations could improve long-horizon accuracy,
  where weather signals are most valuable but currently stale.
- **Cross-region modelling**: Joint forecasting across regions could
  capture spatial correlations (e.g., wind fronts moving from North
  to South).
- **Online learning**: Continuous model updates as new data arrives,
  adapting to regime changes faster than periodic retraining.
- **Additional exogenous features**: Gas prices, interconnector flows,
  or day-ahead market data could provide leading indicators of
  generation mix changes.
