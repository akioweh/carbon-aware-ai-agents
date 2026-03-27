# Performance Optimization Benchmarks
This directory contains the methodology, benchmarking suite, and comparative analysis used to evaluate hardware-specific optimizations for the Scheduling Algorithm.

## Overview
The benchmarks in this folder were conducted to quantify the performance gains from transitioning from a scalar implementation to a cache-aware and SIMD-accelerated (AVX-512) engine. The goal was to reduce peak latency while maintaining the mathematical integrity of the scheduling results.

## Benchmarked Files
* [Methodology](methodology.md): Outlines the testing environment, hardware consistency, and the mathematical constants—such as the fixed resolution of 10,000—used to ensure a fair comparison.

* [Performance](performance_comparison.png): A visualization of execution time (seconds) vs. workload complexity for the three algorithm versions: First_Solution, Cache_Optimization, and Cache_and_Vectorization_Optimization.

* [SpeedUp](relative_speedup.png): A chart highlighting the speedup factor of the optimized versions relative to the baseline, demonstrating peak gains of up to 4.0x.

* [Report](report.md): The final comprehensive analysis. It details how refactoring to a Struct of Arrays (SoA) and implementing AVX-512 vectorization resulted in a 75% reduction in peak latency and improved CPU cycle efficiency from 42% to 85%.

## Tools & Automation
In addition to the analysis, this folder includes the software required to reproduce these results:

* Benchmark Runner: Scripts to swap the SchedulingAlgo file, execute the test cases 5 times per workload, and calculate the average execution time.

* Visualization Engine: Tools to process the raw benchmarking data and generate the performance comparison and speedup graphs found in this report.

## Key Findings
* **Cache Optimization**: Reduced performance "jitter" and provided a more predictable latency profile through improved data locality (SoA layout).

* **SIMD Vectorization**: Drastically lowered execution times for complex tasks from ~15 seconds to under 4 seconds.

* **Asymptotic Scaling**: Confirmed that as workload increases, performance curves converge due to the fixed-resolution methodology.