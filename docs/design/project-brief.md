# Project Brief: Carbon-Aware AI Workload Scheduler
**Client: NTT DATA**
**Team: Team 25**

## Overview & Objective
The Carbon-Aware AI Workload Scheduler is an end-to-end platform designed to minimize the environmental impact of resource-intensive AI operations. Instead of scheduling jobs based purely on speed or cost, the system dynamically shifts workloads to data centers and time windows where the energy grid's carbon intensity is lowest.

## Key Features & Capabilities
Spatio-Temporal Routing: Optimizes task placement across multiple geographic locations and timeframes using 7-day, 5-minute resolution carbon forecasts.

- Workload Discretization: Breaks naturally parallelizable AI jobs into shorter, discrete blocks to exploit optimal clean energy windows.

- Physical Constraint Modeling: Mathematically accounts for the real-world energy overheads of pausing and resuming jobs, such as the power required to transfer model weights into VRAM.

- Direct Comparison: Generates both an optimized schedule and an unoptimized baseline, presenting a side-by-side UI comparison of the carbon saved.

- Standardized Reporting: Produces environmental impact estimates that align with recognized methodologies like the Software Carbon Intensity (SCI) standard.