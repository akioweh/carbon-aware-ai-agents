Goal: Optimize the placement, scheduling, and execution of AI workloads across cloud and on-premise environments to minimize environmental impact. The framework evaluates energy use, carbon emissions, water consumption, and critical-materials wear, applying the Software Carbon Intensity (SCI) metric from the Green Software Foundation.

1. Problem & Objectives

Problem. AI workloads (e.g., training large models, inference services) are resource-intensive and often deployed without sustainability considerations. Grid carbon intensity varies by region and time, data centers differ in PUE/WUE, and on-premise deployments can be underutilized. Optimizing across hybrid (cloud + on-prem) options is rarely done.

Objectives.

    Minimize lifecycle impact per AI workload: CO₂e, kWh, water (L), and critical-materials wear using SCI.
    Optimize across multi-cloud and on-premise clusters.
    Respect SLOs (latency, throughput), budgets, and compliance/policy.
    Provide explainable, auditable sustainability decisions.

Non-functional. Pluggable data sources, low-latency decision-making, integration with AI platforms (MLflow, Kubeflow, PyTorch, TensorFlow), strong observability.

2. Key Concepts & Data Inputs

   Grid carbon intensity (real-time & forecast).
   Facility efficiency: PUE/WUE for cloud + on-prem facilities.
   On-prem telemetry: server power draw, cooling overhead, utilization.
   SCI metric:
   SCI = (Energy × Carbon Intensity) / Functional Unit
   Functional Unit examples: per training epoch, per inference request, per GB processed.
   Temporal flexibility: allowable scheduling shifts.
   Hardware reuse: maximize existing on-prem clusters before provisioning new cloud capacity.
   Resource right-sizing: GPUs/CPUs sized per workload.
   Cost context: on-prem TCO + cloud rates.
   Compliance: residency, sovereignty, and internal sustainability targets.

3. Scoring & Optimization Model

Vector per candidate (cloud region or on-prem site):

    SCI_i (kgCO₂e per functional unit)
    W_i (L water per functional unit)
    M_i (critical-materials wear proxy)
    K_i (cost), L_i (latency), P_i (policy risk)

Filters. Discard infeasible (policy violations, unavailable hardware, SLO breaches).

Objective. Minimize SCI, then water, then cost — configurable via lexicographic or weighted scalarization.

Example score:
Score_i = wSCI·SCÎ_i + wW·Ŵ_i + wM·M̂_i + wK·K̂_i + wL·L̂_i – ReuseBonus_i

Temporal optimization. Deferrable training jobs can shift across hours/days to align with clean-energy windows.

Hybrid optimization. Compare cloud vs on-prem cost and SCI to choose best placement.

4. Agent Responsibilities (Hybrid Focus)

   Carbon & Energy Intelligence Agent. Considers cloud grid mix and on-prem facility power sources.
   Capacity & Placement Agent. Checks cloud quotas and on-prem cluster utilization.
   Optimizer Agent. Balances cloud elasticity with on-prem sustainability.
   Feedback/Accounting Agent. Issues SCI per workload whether cloud-hosted or on-prem.

5. Workload Contract (AI-specific)

   workload_id, type (training, inference, batch AI job)
   functional_unit (epoch, request, GB)
   resources (GPU/TPU/CPU, memory, storage)
   temporal_flexibility (earliest_start, latest_finish)
   policy (allowed providers/sites)
   budget + objective_profile (weights)

Outputs: placement decision (cloud region/on-prem site, timing, shape), expected SCI, water, cost, compliance proof.

6. Worked SCI Examples

Training (Cloud)

    Energy: 4,000 kWh, Intensity 0.25 kg/kWh, Emissions = 1,000 kgCO₂e.
    Functional unit: 20 epochs → SCI = 50 kg/epoch.
    If deferred to cleaner grid (0.10 kg/kWh) → SCI = 20 kg/epoch.

Inference (On-Prem)

    1M requests/day, on-prem cluster draws 50 kWh/day, intensity 0.15 kg/kWh.
    Emissions = 7.5 kg/day → SCI = 7.5 / 1,000,000 = 7.5×10⁻⁶ kg = 7.5 mg/request.
    If moved to cloud with dirtier grid (0.40 kg/kWh) → SCI = 20 mg/request.
    Optimizer favors on-prem in this scenario.
