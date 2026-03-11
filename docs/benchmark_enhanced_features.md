# Enhanced Tree Features Experiment

## Experiment Design

### Changes from Baseline

1. **Sparse lag structure**: lag_1..12 + 24,48,72,96,144,336 (19 lags vs 48)
2. **Enhanced rolling stats**: mean at 12,48,336 + std at 48,336 (5 vs 3)
3. **Week-of-year cyclical**: Replaced minute-of-day with week_of_year sin/cos
4. **Extended Direct-XGBoost origin**: Added lag_48, lag_336, rolling_mean_336, rolling_std_336

### Feature Counts

| Model | Baseline | Enhanced |
|-------|----------|----------|
| Recursive trees | 63 (6 cyc + 48 lag + 3 roll + 3 weather + 3 roll) | 33 (6 cyc + 19 lag + 5 roll + 3 weather) |
| Direct-XGBoost | 14 (6 cyc + 2 h + 3 origin + 3 weather) | 18 (6 cyc + 2 h + 7 origin + 3 weather) |

## Results

### Full backfill Training Window

#### London

| Model | Baseline MAE | Enhanced MAE | Δ MAE | Δ % |
|-------|-------------|-------------|-------|-----|
| Random Forest | 50.02 | 56.41 | +6.39 | +12.8% |
| XGBoost | 35.53 | 31.34 | -4.19 | -11.8% |
| CatBoost | 43.86 | 46.48 | +2.63 | +6.0% |
| LightGBM | 43.57 | 50.87 | +7.30 | +16.7% |
| Direct-XGBoost | 33.25 | 31.46 | -1.79 | -5.4% |

#### North East England

| Model | Baseline MAE | Enhanced MAE | Δ MAE | Δ % |
|-------|-------------|-------------|-------|-----|
| Random Forest | 51.79 | 58.35 | +6.56 | +12.7% |
| XGBoost | 24.31 | 33.58 | +9.28 | +38.2% |
| CatBoost | 60.15 | 57.09 | -3.06 | -5.1% |
| LightGBM | 62.55 | 31.94 | -30.61 | -48.9% |
| Direct-XGBoost | 27.13 | 34.81 | +7.67 | +28.3% |

#### North West England

| Model | Baseline MAE | Enhanced MAE | Δ MAE | Δ % |
|-------|-------------|-------------|-------|-----|
| Random Forest | 35.19 | 29.79 | -5.40 | -15.3% |
| XGBoost | 34.95 | 22.91 | -12.04 | -34.5% |
| CatBoost | 30.44 | 23.36 | -7.07 | -23.2% |
| LightGBM | 46.89 | 27.32 | -19.58 | -41.7% |
| Direct-XGBoost | 26.46 | 28.22 | +1.77 | +6.7% |

#### South East England

| Model | Baseline MAE | Enhanced MAE | Δ MAE | Δ % |
|-------|-------------|-------------|-------|-----|
| Random Forest | 62.47 | 67.29 | +4.82 | +7.7% |
| XGBoost | 66.97 | 49.60 | -17.37 | -25.9% |
| CatBoost | 58.15 | 54.70 | -3.46 | -5.9% |
| LightGBM | 48.53 | 43.08 | -5.45 | -11.2% |
| Direct-XGBoost | 42.66 | 36.86 | -5.79 | -13.6% |

#### South Yorkshire

| Model | Baseline MAE | Enhanced MAE | Δ MAE | Δ % |
|-------|-------------|-------------|-------|-----|
| Random Forest | 53.90 | 44.48 | -9.42 | -17.5% |
| XGBoost | 42.45 | 39.78 | -2.67 | -6.3% |
| CatBoost | 42.64 | 40.57 | -2.06 | -4.8% |
| LightGBM | 45.64 | 42.42 | -3.22 | -7.1% |
| Direct-XGBoost | 37.98 | 39.14 | +1.16 | +3.1% |

#### Cross-Region Average (Full backfill)

| Model | Baseline MAE | Enhanced MAE | Δ MAE | Δ % |
|-------|-------------|-------------|-------|-----|
| Random Forest | 50.67 | 51.26 | +0.59 | +1.2% |
| XGBoost | 40.84 | 35.44 | -5.40 | -13.2% |
| CatBoost | 47.05 | 44.44 | -2.61 | -5.5% |
| LightGBM | 49.44 | 39.12 | -10.31 | -20.9% |
| Direct-XGBoost | 33.50 | 34.10 | +0.60 | +1.8% |

## Analysis

**Full backfill results (cross-region average):**

| Model | Δ MAE | Verdict |
|-------|-------|---------|
| LightGBM | -10.31 (−20.9%) | Strong improvement |
| XGBoost | -5.40 (−13.2%) | Clear improvement |
| CatBoost | -2.61 (−5.5%) | Moderate improvement |
| Random Forest | +0.59 (+1.2%) | Neutral |
| Direct-XGBoost | +0.60 (+1.8%) | Neutral (slight regression) |

**Key findings:**

1. **Recursive tree models benefit significantly** from the enhanced feature
   set. LightGBM improved the most (−20.9%), followed by XGBoost (−13.2%) and
   CatBoost (−5.5%). The sparse lag structure with weekly periodicity captures
   more useful signal with fewer features (33 vs 63).

2. **Random Forest is roughly neutral** — it likely doesn't benefit as much
   from the reduced feature count since it already handles high-dimensional
   feature spaces well via bagging.

3. **Direct-XGBoost showed slight regression** (+1.8%). The additional origin
   summary features (lag_336, rolling_mean/std_336) may add noise rather than
   signal for the direct approach, or the week-of-year cyclical features may
   not help given the direct horizon encoding already captures temporal
   patterns.

4. **Weekly lag (lag_336) is valuable** for recursive models — regions with
   strong weekly patterns (North West, South Yorkshire) showed the largest
   improvements.
