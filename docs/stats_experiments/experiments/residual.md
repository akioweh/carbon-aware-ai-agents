# Persistence Residual Target Experiment

## Approach

Instead of predicting raw carbon intensity, models predict `y - lag_1`
(deviation from persistence). Final prediction = `lag_1 + model(features)`.
Features (lags, rolling stats) remain computed on raw values.

## Results

### Full backfill Training Window

| Model | Baseline MAE | Enhanced MAE | Residual MAE | Δ vs Baseline | Δ vs Enhanced |
|-------|-------------|-------------|-------------|--------------|--------------|
| Random Forest | 50.67 | 51.26 | 46.61 | -4.07 | -4.66 |
| XGBoost | 40.84 | 35.44 | 37.16 | -3.68 | +1.72 |
| CatBoost | 47.05 | 44.44 | 41.04 | -6.01 | -3.40 |
| LightGBM | 49.44 | 39.12 | 39.70 | -9.73 | +0.58 |
| Direct-XGBoost | 33.50 | 34.10 | 34.47 | +0.97 | +0.37 |

## Analysis

Negative delta = improvement (residual is better).
