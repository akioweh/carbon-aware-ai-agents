# Performance Optimization Methodology

## Methodology Overview
All optimizations were conducted using the latest version of the software. The core testing process involved swapping only the `SchedulingAlgo` file, with minor adjustments to ensure compatibility with the updated model.

### Test Environment & Constants
*   **Hardware Consistency:** All benchmarks were performed on the same physical machine to ensure environmental stability.
*   **Stats Component:** A consistent local instance of the stats component was used for all runs.
*   **Fixed Resolution:** The resolution was set to **10,000** for every test case.
*   **Sampling:** For each workload length, the algorithm was executed **5 times**, and the final metric was calculated as the **average execution time**.

---

## Technical Considerations

### Asymptotic Behavior
As the workload increases, the relative amount of computation decreases due to the **fixed resolution**. Consequently, performance curves across different versions of the algorithm will tend to meet asymptotically as the workload amount approaches infinity.

### Computational Complexity
The primary computational load is concentrated within the `SchedulingAlgo` hot-path (nested loops). The complexity can be broken down into the following discretized components:

| Variable | Definition / Calculation |
| :--- | :--- |
| **`tot_work`** | Equal to the fixed **resolution** (post-discretization). |
| **`max_wi`** | Capacity after discretization, roughly calculated as: <br> $max\_wi \approx \frac{capacity \times resolution}{tot\_work}$ |
| **`n`** | Number of time blocks; remains **constant** under a fixed window size. |

Hence the total amount of is $$\left(n \cdot \frac{resolution^2 \cdot capacity}{tot\_work}\right)$$ where **capacity** is a constant from datacenters.
