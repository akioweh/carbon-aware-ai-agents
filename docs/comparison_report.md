# Prophet Alternatives: Benchmark Report

## Overview

This report compares Meta Prophet against 5 lightweight alternatives for forecasting datacenter **load** (0-50 scale) and **greenness** (0-100 scale). The goal is to find a method that matches or beats Prophet's accuracy while being lighter in dependencies and runtime.

## Test Setup

| Parameter | Load | Greenness |
|-----------|------|-----------|
| **Data source** | `cache.db` (synthetic) | `carbon_intensity.db` (real UK Carbon Intensity API) |
| **Location** | Data-Center-1 | Region 13 (London) |
| **Training set** | 23 days (6,624 pts, 5-min intervals) | Jan 31 - Feb 6 (336 pts, 30-min intervals) |
| **Test set** | 7 days (2,475 pts) | Feb 7 - Feb 13 (336 pts) |

Load data is synthetic. Greenness data is **real carbon intensity** from the UK grid, collected via the Carbon Intensity API, deduplicated to unique 30-minute readings. All methods were given identical training data and evaluated against the same held-out test period.

---

## Results

### Accuracy

| Method | MAE Load | RMSE Load | MAE Greenness | RMSE Greenness |
|--------|----------|-----------|---------------|----------------|
| Prophet | 4.26 | 5.71 | 21.44 | 23.95 |
| Holt-Winters | 6.57 | 7.50 | 32.34 | 37.12 |
| SARIMAX | 7.50 | 8.39 | **9.62** | **11.94** |
| Linear Regression | 5.76 | 7.10 | 12.27 | 15.38 |
| Fourier Regression | 5.14 | 6.36 | 15.65 | 18.79 |
| **Seasonal Naive** | **1.58** | **2.55** | **10.62** | **13.69** |

*Bold = best or near-best in category. Lower is better.*

### Speed

| Method | Total Time (s) | Speedup vs Prophet |
|--------|----------------|--------------------|
| Prophet | 0.95 | 1x |
| Holt-Winters | 0.14 | 7x |
| SARIMAX | 3.05 | 0.3x (slower) |
| Linear Regression | 0.01 | **95x** |
| Fourier Regression | 0.01 | **95x** |
| Seasonal Naive | 0.00 | **instant** |

### Dependencies

| Method | Extra Dependencies | Approx. Install Size |
|--------|-------------------|---------------------|
| Prophet | `prophet`, `cmdstanpy`, `pystan`, Stan compiler | ~200+ MB |
| Holt-Winters | `statsmodels` | ~30 MB |
| SARIMAX | `statsmodels` | ~30 MB |
| Linear Regression | `scikit-learn` | ~40 MB |
| Fourier Regression | None (`numpy` only, already required by pandas) | **0 MB** |
| Seasonal Naive | None (`pandas` only) | **0 MB** |

---

## Method Details

### 1. Prophet (baseline)
- **Config:** `daily_seasonality=True`, `weekly_seasonality=True`
- **How it works:** Decomposes time series into trend + seasonality using Fourier terms, fit via Stan's MAP optimizer. Automatic changepoint detection.
- **Result:** Second-worst on real greenness (MAE 21.44). Prophet's complex model overfits on limited training data and misses the non-periodic variability in real carbon intensity. Decent on synthetic load (4.26) where patterns are clean and predictable. **Not recommended — heavy dependencies, mediocre accuracy on real data.**

### 2. Holt-Winters (Triple Exponential Smoothing)
- **Config:** Additive trend + additive seasonality, `seasonal_periods=24` (hourly resampling)
- **How it works:** Exponential smoothing with level, trend, and seasonal components. Resampled to hourly, then interpolated back.
- **Result:** Worst greenness accuracy (MAE 32.34). The single-seasonality limitation and trend extrapolation produce poor forecasts. **Not recommended.**

### 3. SARIMAX
- **Config:** `order=(1,1,1)`, `seasonal_order=(1,1,1,24)` on hourly data
- **How it works:** Seasonal ARIMA with autoregressive and moving average components. Captures momentum and recent patterns rather than just seasonality.
- **Result:** Best greenness accuracy (MAE 9.62) — ARIMA's autoregressive nature handles the real-world variability in carbon intensity well. But it's the slowest method (3.05s) and worst on load (7.50). **Best for greenness accuracy if speed is not a concern.**

### 4. Linear Regression with Seasonal Features
- **Config:** Ridge regression (alpha=1.0) with cyclical sin/cos features for hour, day-of-week, minute-of-day, plus linear trend
- **How it works:** Encodes time features as cyclical variables, fits a regularised linear model. Interval-agnostic — works on any frequency.
- **Result:** Solid greenness accuracy (MAE 12.27), fast (0.01s). A good balanced option. **Solid choice if you want a modelling approach with scikit-learn.**

### 5. Fourier Regression (OLS)
- **Config:** 3 daily harmonics, 2 weekly harmonics, linear trend. Auto-detects data interval. Solved with `numpy.linalg.lstsq`.
- **How it works:** Explicit sine/cosine terms at daily and weekly frequencies — Prophet's core math without the overhead.
- **Result:** Middle-of-pack greenness (MAE 15.65), second-best load (5.14), fast (0.01s), zero dependencies. **Good all-rounder, fully transparent.**

### 6. Seasonal Naive
- **Config:** Repeat the last 7 days of training data as the forecast. Auto-detects data interval.
- **How it works:** Assumes next week looks like last week. No model fitting.
- **Result:** Dominates load (MAE 1.58) and near-best on greenness (MAE 10.62). Instant. Zero dependencies. **Surprisingly strong on real data.**

---

## Key Insight: Prophet Dominated on Synthetic Data, Failed on Real Data

Our initial benchmarks used synthetic greenness data generated by `generate_history.py`. On that data, Prophet was the clear winner — it achieved the best greenness MAE (12.13) and appeared to justify its heavy dependency footprint. Every alternative looked like a compromise.

But when we replaced the synthetic greenness with real carbon intensity data from the UK grid, the rankings inverted completely. Prophet dropped from 1st to 5th place, with a greenness MAE of 21.44 — more than double the best alternative (SARIMAX at 9.62).

| Method | Greenness MAE (synthetic) | Rank | Greenness MAE (real) | Rank |
|--------|--------------------------|------|---------------------|------|
| Prophet | **12.13** | 1st | 21.44 | 5th |
| SARIMAX | 12.27 | 2nd | **9.62** | **1st** |
| Linear Regression | 12.41 | 3rd | 12.27 | 3rd |
| Fourier Regression | 12.72 | 4th | 15.65 | 4th |
| Seasonal Naive | 16.09 | 5th | 10.62 | 2nd |
| Holt-Winters | 26.99 | 6th | 32.34 | 6th |

**Why this happened:** The synthetic data in `generate_history.py` produces clean, smooth seasonal patterns — exactly the kind of signal Prophet is designed for. It uses sine waves for daily cycles and gentle random walks for trends. Prophet's Fourier decomposition and changepoint detection are perfectly suited to this.

Real carbon intensity is fundamentally different. It's driven by:
- **Weather** — wind speed directly determines how much generation comes from wind farms, causing sharp, unpredictable swings
- **Demand spikes** — cold snaps, industrial demand, and events cause sudden load increases that fire up gas plants
- **Grid dispatch decisions** — which power stations are brought online depends on market prices, maintenance schedules, and interconnector availability
- **Time of day** — there is a daily pattern, but it's noisy and varies significantly day-to-day

Prophet's model assumes the signal is primarily composed of smooth seasonal components plus a piecewise-linear trend with changepoints. When the signal has significant non-periodic variability (as real carbon data does), Prophet fits the noise in the training data and extrapolates it poorly. With only 7 days of training data, the changepoint detection is especially prone to overfitting.

Simpler methods like SARIMAX and Seasonal Naive outperform precisely because they don't try to model structure that isn't there. SARIMAX captures short-term momentum (today's intensity is correlated with yesterday's). Seasonal Naive assumes next week looks like last week — a surprisingly good heuristic for carbon intensity, which does have stable weekly patterns despite the daily noise.

**The lesson:** benchmarking on synthetic data can give misleading results. The properties of generated data (smooth seasonality, predictable trends) may not match the real signal at all. Always validate against real data before choosing a forecasting method.

---

### Overall recommendation

**Replace Prophet with Linear Regression** as the default. It's near-best, quicker, and has zero dependencies. SariIf greenness accuracy needs to be maximised, add SARIMAX as an option.

---
