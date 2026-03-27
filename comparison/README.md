# Algorithmic Carbon Optimization: Comparison Analysis
This directory contains the experimental framework, raw data, and final reporting comparing our Deterministic DP Scheduling Algorithm against the industry-standard Green Software Foundation (GSF) Carbon Aware SDK.

## Executive Summary
Through rigorous simulation, we demonstrate that our DP-based scheduler consistently outperforms the GSF SDK baseline. While the SDK optimizes for a single, contiguous temporal block at a single location, our algorithm utilizes a relaxed constraint model that incorporates temporal splitting (pausing/resuming) and spatial routing (geographic arbitrage).

## Key Comparative Files
* [Comparison report](comparison_report.md): The full technical analysis detailing the 44.1% carbon reduction achieved through spatio-temporal optimization.

* [Emissions Hierarchy Graphs](graphs/plot_baseline_validation_spatial_difference.png): Visualizations showing that while temporal flexibility provides a ~9% improvement, spatial routing acts as a 5x multiplier for carbon savings.

## Core Findings
* **Spatial Dominance**: Decomposing the savings reveals that geographic flexibility is significantly more impactful than temporal splitting alone.

* **Deterministic Integrity**: The DP algorithm mathematically guarantees emissions equal to or lower than the baseline by only splitting workloads when green savings outweigh startup overhead.

* **Scale Invariance**: Proportional carbon savings remain stable regardless of model size (14B vs 140B parameters) or system power draw.

* **Sub-Second Overhead**: Despite the increased complexity of the action space, the algorithm maintains linear scaling with a sub-second execution time.

## Methodology & Fairness
To ensure an "apples-to-apples" comparison, we implemented a Standardized API Integration so both engines use identical carbon forecast data. Additionally, we granted the GSF SDK a "Best-Site" advantage, manually identifying the single lowest-carbon data center for the baseline before running the comparison.