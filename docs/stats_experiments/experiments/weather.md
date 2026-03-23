# Weather-Enriched Features Experiment (Phase 5)

## Experiment Design

### Hypothesis

Richer weather features and engineered transformations improve forecast
accuracy, especially at longer horizons (day 3-7) where lag features
are stale but weather forecasts remain fresh exogenous signals.

### Weather Features

**Original (3):** wind_speed_10m, temperature_2m, shortwave_radiation

**New raw (8):** wind_speed_100m, wind_gusts_10m, wind_direction_10m,
cloud_cover, relative_humidity_2m, pressure_msl, diffuse_radiation,
direct_normal_irradiance

**Engineered (4):**
- wind_power_proxy = wind_speed_100m³ (cubic power law)
- wind_power_proxy_10m = wind_speed_10m³
- solar_effective = shortwave_radiation × (1 - cloud_cover/100)
- temp_demand_proxy = |temperature - 18|

### Variants

| Variant | Weather Features | Count |
|---------|-----------------|-------|
| Baseline (Phase 4) | 3 original raw | 3 |
| A: Extended raw | 11 raw | 11 |
| B: Extended + engineered | 11 raw + 4 engineered | 15 |
| C: Engineered only | 3 original + 4 engineered | 7 |

## Results

### Variant A_extended_raw

| Model | London | North East England | North West England | South East England | South Yorkshire | Cross-Region Avg |
|-------|-------|-------|-------|-------|-------|----------------|
| Random Forest | 32.09 | 32.13 | 23.20 | 36.46 | 39.61 | **32.70** |
| XGBoost | 35.72 | 18.83 | 22.47 | 37.39 | 40.31 | **30.94** |
| CatBoost | 36.40 | 25.42 | 23.94 | 30.40 | 32.70 | **29.77** |
| LightGBM | 35.09 | 24.32 | 27.30 | 36.00 | 35.20 | **31.58** |
| Direct-XGBoost | 28.97 | 27.59 | 24.87 | 30.35 | 35.68 | **29.49** |

### Variant B_extended_engineered

| Model | London | North East England | North West England | South East England | South Yorkshire | Cross-Region Avg |
|-------|-------|-------|-------|-------|-------|----------------|
| Random Forest | 34.40 | 30.01 | 22.66 | 37.22 | 39.01 | **32.66** |
| XGBoost | 47.07 | 19.19 | 22.26 | 43.55 | 30.70 | **32.55** |
| CatBoost | 36.38 | 21.97 | 27.08 | 35.56 | 32.76 | **30.75** |
| LightGBM | 31.64 | 42.23 | 24.80 | 29.91 | 31.38 | **31.99** |
| Direct-XGBoost | 30.76 | 26.96 | 21.59 | 34.19 | 36.62 | **30.02** |

### Variant C_engineered_only

| Model | London | North East England | North West England | South East England | South Yorkshire | Cross-Region Avg |
|-------|-------|-------|-------|-------|-------|----------------|
| Random Forest | 32.20 | 40.02 | 25.04 | 29.46 | 39.07 | **33.16** |
| XGBoost | 59.60 | 18.83 | 28.80 | 66.91 | 39.13 | **42.66** |
| CatBoost | 33.22 | 30.88 | 24.31 | 34.35 | 31.37 | **30.82** |
| LightGBM | 35.09 | 18.69 | 24.30 | 40.93 | 34.92 | **30.79** |
| Direct-XGBoost | 32.04 | 31.95 | 26.77 | 34.47 | 36.31 | **32.31** |

## Comparison with Phase 4 Baseline

| Model | Baseline | Variant A | Variant B | Variant C | Best Delta |
|-------|----------|-----------|-----------|-----------|------------|
| Random Forest | 36.34 | 32.70 | 32.66 | 33.16 | -3.68 |
| XGBoost | 43.91 | 30.94 | 32.55 | 42.66 | -12.97 |
| CatBoost | 33.02 | 29.77 | 30.75 | 30.82 | -3.25 |
| LightGBM | 40.79 | 31.58 | 31.99 | 30.79 | -10.00 |
| Direct-XGBoost | 37.84 | 29.49 | 30.02 | 32.31 | -8.34 |

*Negative delta = weather variant improved over baseline.*

## Per-Horizon MAE Analysis

MAE at different forecast horizons (cross-region average):

### Random Forest

| Horizon | Baseline | Variant A | Variant B | Variant C |
|---------|----------|-----------|-----------|-----------|
| Day 1 | 24.99 | 22.62 | 22.77 | 22.36 |
| Day 3 | 34.51 | 32.71 | 34.63 | 33.54 |
| Day 5 | 34.30 | 31.52 | 27.51 | 28.72 |
| Day 7 | 59.74 | 51.02 | 52.08 | 52.23 |

### XGBoost

| Horizon | Baseline | Variant A | Variant B | Variant C |
|---------|----------|-----------|-----------|-----------|
| Day 1 | 26.64 | 17.87 | 15.90 | 21.21 |
| Day 3 | 55.72 | 34.30 | 38.67 | 64.22 |
| Day 5 | 56.03 | 31.08 | 42.28 | 49.74 |
| Day 7 | 39.71 | 36.86 | 28.61 | 26.74 |

### CatBoost

| Horizon | Baseline | Variant A | Variant B | Variant C |
|---------|----------|-----------|-----------|-----------|
| Day 1 | 25.31 | 20.57 | 18.74 | 21.23 |
| Day 3 | 37.17 | 31.16 | 32.03 | 35.04 |
| Day 5 | 29.12 | 29.23 | 29.20 | 28.03 |
| Day 7 | 46.53 | 39.10 | 44.57 | 39.88 |

### LightGBM

| Horizon | Baseline | Variant A | Variant B | Variant C |
|---------|----------|-----------|-----------|-----------|
| Day 1 | 17.34 | 17.28 | 20.04 | 16.07 |
| Day 3 | 50.86 | 37.84 | 39.03 | 40.85 |
| Day 5 | 53.05 | 29.68 | 25.95 | 36.32 |
| Day 7 | 31.57 | 40.08 | 37.39 | 29.07 |

### Direct-XGBoost

| Horizon | Baseline | Variant A | Variant B | Variant C |
|---------|----------|-----------|-----------|-----------|
| Day 1 | 29.54 | 24.90 | 25.15 | 25.85 |
| Day 3 | 45.17 | 35.27 | 36.48 | 41.70 |
| Day 5 | 36.55 | 27.45 | 29.57 | 30.98 |
| Day 7 | 32.82 | 19.01 | 16.70 | 23.35 |
