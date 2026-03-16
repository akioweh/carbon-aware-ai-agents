# Seasonal Data Expansion Experiment

## Experiment Design

### Data

- **Training**: Up to 1 year of UK carbon intensity data (expanded from 90-day winter)
- **Test**: Last 7 days

### Best Variant per Model

| Model | Variant | Prior MAE (90d) |
|-------|---------|----------------|
| Random Forest | residual | 46.61 |
| XGBoost | enhanced | 35.44 |
| CatBoost | residual | 41.04 |
| LightGBM | enhanced | 39.12 |
| Direct-XGBoost | baseline | 33.50 |

### Seasonal Features

- 11 cyclical: hour, dow, week, month, day-of-year sin/cos + daylight proxy
- 21 lags: 1-12, 24, 48, 72, 96, 144, 336, 672 (2wk), 1344 (4wk)
- 8 rolling: mean/std at 12, 48, 336, 672, 1344
- 3 weather: wind speed, temperature, solar radiation

## Results

### full_year

| Model | Variant | London | North East England | North West England | South East England | South Yorkshire | Cross-Region Avg |
|-------|---------|-------|-------|-------|-------|-------|----------------|
| Random Forest | residual | 35.17 | 34.90 | 27.57 | 33.05 | 44.18 | **34.97** |
| XGBoost | enhanced | 58.84 | 20.25 | 26.64 | 66.42 | 47.42 | **43.91** |
| CatBoost | residual | 41.16 | 25.51 | 24.48 | 33.19 | 33.82 | **31.63** |
| LightGBM | enhanced | 47.66 | 37.69 | 26.51 | 56.75 | 35.31 | **40.79** |
| Direct-XGBoost | baseline | 43.51 | 30.56 | 27.07 | 43.26 | 44.29 | **37.74** |

## Comparison with Prior Experiments (90-day)

| Model | 90-day MAE | Seasonal MAE | Delta |
|-------|-----------|-------------|-------|
| Random Forest | 46.61 | 34.97 | -11.64 |
| XGBoost | 35.44 | 43.91 | +8.47 |
| CatBoost | 41.04 | 31.63 | -9.41 |
| LightGBM | 39.12 | 40.79 | +1.67 |
| Direct-XGBoost | 33.50 | 37.74 | +4.24 |

*Negative delta = seasonal is better (more data helped).*
