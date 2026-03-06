# Carbon Intensity Prediction Benchmark

## Overview

This report compares 9 forecasting models (5 statistical + 4 ML tree-based) on real UK carbon intensity data (gCO2/kWh). Models are evaluated on 7 metrics that measure both point accuracy and shape capture. The benchmark tests different training window sizes to assess the effect of data volume on prediction quality.

## Test Setup

| Parameter | Value |
|-----------|-------|
| **Data source** | `carbon_intensity.db` (UK Carbon Intensity API) |
| **Regions** | London, North East England, North West England, South East England, South Yorkshire |
| **Date range** | 2025-12-06 11:30:00+00:00 to 2026-03-06 11:00:00+00:00 |
| **Total readings** | 21480 |
| **Frequency** | 30-minute intervals |
| **Test set** | Last 7 days |
| **Training (7-day)** | 336 points (6 days) |
| **Training (Full backfill)** | 3960 points (82 days) |

## Raw Data

![Raw Data](benchmark_raw_data.png)

## Metrics Explained

| Metric | Purpose |
|--------|---------|
| **MAE** | Mean Absolute Error — primary accuracy in gCO2/kWh |
| **MSE** | Mean Squared Error — penalizes large errors quadratically |
| **RMSE** | Root MSE — same scale as MAE, sensitive to outliers |
| **R-squared** | Fraction of variance explained; negative = worse than predicting the mean |
| **Adjusted R-squared** | R-squared penalized by number of model features |
| **Spectral Entropy** | Entropy of residual periodogram, scaled to [0,1]. High = residuals are white noise (good). Low = model missed periodic structure |
| **KL Divergence** | KL divergence between actual and predicted distributions. Low = predictions distribution matches actual. High = model distorts the shape |

## Results: 7-day

### Accuracy Table

| Model | MAE | RMSE | R2 | Spectral_Entropy | KL_Divergence | Time (s) |
|-------|-------|-------|-------|-------|-------|----------|
| Ridge | 46.01 | 60.25 | -0.400 | 0.376 | 0.905 | 0.00 |
| SARIMAX | 70.87 | 86.88 | -1.821 | 0.373 | 1.155 | 0.75 |
| Seasonal Naive | 43.52 | 57.17 | -0.328 | 0.447 | 0.449 | 0.00 |
| Fourier | 57.39 | 65.26 | -0.803 | 0.399 | 1.015 | 0.00 |
| Holt-Winters | 101.95 | 116.29 | -6.474 | 0.410 | 1.650 | 0.14 |
| Random Forest | 11.09 | 16.95 | 0.887 | 0.731 | 0.446 | 5.04 |
| XGBoost | 12.83 | 18.89 | 0.847 | 0.700 | 0.449 | 0.69 |
| CatBoost | 21.55 | 31.03 | 0.510 | 0.539 | 0.465 | 0.53 |
| LightGBM | 12.13 | 18.46 | 0.857 | 0.729 | 0.379 | 0.57 |

*Averaged across 5 regions. Lower MAE/RMSE/KL is better. Higher R2/Spectral Entropy is better.*

### Predictions vs Actual

![Predictions 7-day](benchmark_predictions_7-day.png)

### Zoomed 48-Hour Detail

![48h Detail 7-day](benchmark_zoom_48h_7-day.png)

## Results: Full backfill

### Accuracy Table

| Model | MAE | RMSE | R2 | Spectral_Entropy | KL_Divergence | Time (s) |
|-------|-------|-------|-------|-------|-------|----------|
| Ridge | 43.33 | 52.38 | -0.054 | 0.376 | 1.059 | 0.00 |
| SARIMAX | 61.44 | 77.45 | -1.334 | 0.384 | 0.900 | 1.86 |
| Seasonal Naive | 43.52 | 57.17 | -0.328 | 0.447 | 0.449 | 0.00 |
| Fourier | 42.84 | 51.59 | -0.041 | 0.369 | 0.977 | 0.00 |
| Holt-Winters | 87.04 | 102.41 | -4.192 | 0.346 | 1.646 | 0.89 |
| Random Forest | 6.531 | 9.595 | 0.961 | 0.893 | 0.129 | 6.72 |
| XGBoost | 6.783 | 9.852 | 0.959 | 0.884 | 0.119 | 0.78 |
| CatBoost | 6.869 | 9.923 | 0.959 | 0.871 | 0.121 | 0.66 |
| LightGBM | 6.617 | 9.635 | 0.961 | 0.893 | 0.084 | 0.85 |

*Averaged across 5 regions. Lower MAE/RMSE/KL is better. Higher R2/Spectral Entropy is better.*

### Predictions vs Actual

![Predictions Full backfill](benchmark_predictions_full_backfill.png)

### Zoomed 48-Hour Detail

![48h Detail Full backfill](benchmark_zoom_48h_full_backfill.png)

## Training Data Volume Comparison

![Training Comparison](benchmark_training_comparison.png)

This chart compares MAE across training windows. Models that improve significantly with more data have learned meaningful temporal patterns. Models that stay flat or get worse may be overfitting or are insensitive to training volume.

## Residual Analysis — 7-day

![Residuals 7-day](benchmark_residuals_7-day.png)

**Spectral Entropy** near 1.0 means the model's residuals look like white noise — it captured all the periodic structure in the data. Values below 0.8 suggest the model missed recurring patterns. The **ACF plot** shows autocorrelation in residuals; significant spikes at lag 48 (1 day) or lag 336 (1 week) indicate unmodelled seasonality.

## Residual Analysis — Full backfill

![Residuals Full backfill](benchmark_residuals_full_backfill.png)

**Spectral Entropy** near 1.0 means the model's residuals look like white noise — it captured all the periodic structure in the data. Values below 0.8 suggest the model missed recurring patterns. The **ACF plot** shows autocorrelation in residuals; significant spikes at lag 48 (1 day) or lag 336 (1 week) indicate unmodelled seasonality.

## Metrics Heatmap — 7-day

![Heatmap 7-day](benchmark_heatmap_7-day.png)

## Metrics Heatmap — Full backfill

![Heatmap Full backfill](benchmark_heatmap_full_backfill.png)

## Model Details

### Statistical Models

- **Ridge Regression**: Ridge(alpha=1.0) with cyclical sin/cos features for hour, day-of-week, minute-of-day. Fast, interpretable, but limited to capturing smooth seasonality.
- **SARIMAX**: SARIMAX(1,0,1)(1,0,1,48) with training capped at 14 days. Captures autoregressive momentum and seasonal patterns. Slower to fit.
- **Seasonal Naive**: Repeats the last 7 days of training data. Zero parameters, instant. Strong baseline when weekly patterns dominate.
- **Fourier Regression**: 3 daily + 2 weekly harmonics solved via OLS (numpy.linalg.lstsq). Prophet's core math without the overhead.
- **Holt-Winters**: Triple exponential smoothing with additive trend and seasonality (seasonal_periods=48). Struggles with noisy, multi-seasonal data.

### ML Tree-Based Models

- **Random Forest**: RF(n_estimators=200, max_depth=15) with lag + cyclical features. Walk-forward evaluation using actual history for lag computation.
- **XGBoost**: XGB(n_estimators=200, max_depth=6, lr=0.1). Gradient-boosted trees with the same feature set and walk-forward evaluation.
- **CatBoost**: CB(iterations=200, depth=6, lr=0.1). Ordered boosting with symmetric trees. Walk-forward evaluation.
- **LightGBM**: LGBM(n_estimators=200, max_depth=6, lr=0.1). Histogram-based gradient boosting. Walk-forward evaluation.

## Key Findings

**7-day** — Top 3 by MAE:
1. Random Forest: MAE = 11.09 gCO2/kWh
2. LightGBM: MAE = 12.13 gCO2/kWh
3. XGBoost: MAE = 12.83 gCO2/kWh

**Full backfill** — Top 3 by MAE:
1. Random Forest: MAE = 6.53 gCO2/kWh
2. LightGBM: MAE = 6.62 gCO2/kWh
3. XGBoost: MAE = 6.78 gCO2/kWh

**Shape capture**: Models with high spectral entropy and low KL divergence capture the shape of carbon intensity better, not just minimizing mean error. Tree-based models with lag features tend to score well here because they can replicate recent patterns.

**Training volume effect**: More training data generally helps autoregressive models (SARIMAX, tree models) but has diminishing returns for models that only use time-of-day features (Ridge, Fourier).

**Speed/accuracy tradeoffs**: Ridge and Fourier are near-instant. SARIMAX and tree models take seconds. For production use, the best model depends on whether you need sub-second predictions or can afford batch computation.

## Conclusion

### Statistical vs ML: Settled

ML tree-based models dominate statistical models by every metric. On full backfill data, ML models achieve MAE 6.5–6.9 gCO2/kWh versus 42–87 for statistical methods. R-squared is ~0.96 for all four ML models; every statistical model scores negative (worse than predicting the mean). Spectral entropy tells the same story: ML residuals are near-white-noise (0.87–0.89) while statistical residuals retain massive unmodelled structure (0.35–0.45). This gap is not a tuning issue — it reflects a fundamental advantage of lag-based features over time-of-day features for carbon intensity forecasting.

### Is MAE Foolproof?

No. MAE is a useful starting point, but it has three blind spots that matter for scheduling:

1. **MAE treats all errors equally.** A 10 gCO2/kWh error during a low-carbon window — exactly when the scheduler should be dispatching work — is operationally costlier than the same error during a high-carbon peak. MAE doesn't distinguish between the two.
2. **MAE is an average.** Two models with identical MAE can have very different error distributions. One might nail most points but badly miss peaks; another might have consistent moderate errors everywhere. The average hides this.
3. **MAE doesn't measure shape.** A model that outputs a flat line near the test set mean can score a reasonable MAE on noisy data, but it's useless for scheduling because it never identifies good windows versus bad ones.

Among the four ML models, the full backfill MAE spread is just 0.34 gCO2/kWh (6.53 to 6.87). That's within noise margin. MAE alone cannot pick a winner here.

### What Distinguishes the ML Models

When MAE is a tie, shape-capture metrics break the deadlock:

| Model | MAE | R2 | Spectral Entropy | KL Divergence |
|-------|------|----|------------------|---------------|
| Random Forest | 6.53 | 0.961 | **0.893** | 0.129 |
| LightGBM | 6.62 | 0.961 | **0.893** | **0.084** |
| XGBoost | 6.78 | 0.959 | 0.884 | 0.119 |
| CatBoost | 6.87 | 0.959 | 0.871 | 0.121 |

**KL Divergence** is the clearest separator. LightGBM scores 0.084 — its prediction distribution most closely matches the actual carbon intensity distribution. The other three cluster at 0.12–0.13. This means LightGBM is less likely to flatten peaks or compress the range of predicted values, which directly matters for a scheduler that needs to distinguish clean windows from dirty ones.

**Spectral Entropy** splits the field into two tiers: Random Forest and LightGBM (0.893) versus XGBoost and CatBoost (0.87–0.88). Higher entropy means the residuals contain less leftover periodic structure — the model has captured more of the signal.

**Resource efficiency** matters because the Stats service runs on a constrained Oracle cloud server. Random Forest takes 6.72s to train (200 full independent trees, all held in memory) versus LightGBM's 0.85s (~8x faster). LightGBM's histogram binning (~255 bins per feature) also produces a significantly smaller memory footprint than RF's full tree storage. Even though predictions are pre-computed in a background batch job, 8x less CPU time and lower RAM usage is meaningful on a resource-limited machine.

### Recommendation

**LightGBM.** It ties Random Forest on spectral entropy (0.893) and wins on KL divergence (0.084 vs 0.129), meaning its prediction distribution most faithfully reproduces reality. The MAE gap is just 0.09 gCO2/kWh (6.62 vs 6.53) — negligible. What breaks the tie is resource efficiency: LightGBM trains ~8x faster and uses significantly less memory, which matters on the constrained Oracle server hosting the Stats service.

### Caveat

Walk-forward evaluation builds lag features from actual historical values at each test step. This is realistic for this scheduler, which has continuous access to the UK Carbon Intensity API and maintains a local database of recent readings. However, these results would not generalize to a setting without a live data feed — without recent actuals, lag features degrade and ML model performance would drop significantly.

## Methodology Notes

- **Walk-forward evaluation** for tree models: trained once, then at each test step lag features are built from actual historical values (not predictions). This simulates production usage where recent actuals are available.
- **SARIMAX training cap**: Limited to 14 days to avoid excessive fit time. This is consistent with the production predictor.
- **No hyperparameter tuning**: All models use reasonable defaults. Results could improve with tuning, but the comparison is fair since no model was optimized.
- **Spectral entropy**: Computed from the periodogram of residuals, normalized to [0,1]. Shannon entropy of the normalized power spectral density.
- **KL divergence**: Histogram-based (50 bins) with Laplace smoothing. Measures distributional similarity between actual and predicted values.
