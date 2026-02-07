# Advanced Time-Window Scheduling Algorithm

This document details the implementation of the `TimeWindowScheduler`, a
high-performance, carbon-aware scheduling engine designed for streaming
time-series data. It solves the resource allocation problem with non-convex
costs (specifically, startup penalties) using a Rolling-Window Segment Tree over
the $(\min, +)$-semiring.

## Overview

The scheduler manages a continuous stream of time blocks (representing 5-minute
intervals). It allows users to:

1. **Stream Data**: continuously add new forecast blocks (rolling window).
2. **Query Costs**: Calculate the optimal cost to schedule a job $W$ over a
    specific time range $[T_{start}, T_{end}]$ without modifying state.
3. **Reserve Resources**: Permanently allocate work to the optimal blocks,
    updating the state for future queries.

### Key Features

- **Non-Convex Optimization**: Handles "startup penalties" (extra energy/cost
  required to spin up a resource) which standard greedy or convex solvers cannot
  handle.
- **Rolling Window**: Efficiently handles infinite streams of data by
  maintaining a fixed-size circular buffer mapped to a static Segment Tree.
- **Transactional Updates**: Supports a "Solve-Commit" pattern where allocations
  are only applied if the entire request is feasible and optimal.

## Core Concepts

### 1. The Profile Matrix (Algebraic Structure)

The fundamental unit of computation is the **Profile Matrix** ($\mathcal{M}$).
It encapsulates the cost function of a time interval, parameterized by the state
of the system at the interval boundaries.

$$ \mathcal{M} = \begin{bmatrix} f_{00}(w) & f_{01}(w) \\ f_{10}(w) & f_{11}(w)
\end{bmatrix} $$

- **States**:
  - `0`: **Inactive** (Work $w=0$).
  - `1`: **Active** (Work $w > 0$).
- **Entries**: $f_{uv}(w)$ is the minimum cost to perform exactly $w$ units of
  net work, starting in state $u$ and ending in state $v$.
- **Work Resolution**: The work $w$ is discretized (integer steps up to
  `MAX_WORK_RESOLUTION`).

### 2. Min-Plus Convolution (`operator*`)

Merging two adjacent time intervals (Interval $A$ followed by Interval $B$) is
equivalent to matrix multiplication over the Min-Plus semiring.

$$ (A * B)_{uv}(w) = \min_{k \in \{0,1\}} \min_{0 \le i \le w} \left(
A_{uk}(i) + B_{kv}(w-i) \right) $$

- **Associativity**: This operation is associative, allowing us to use a Segment
  Tree to combine arbitrary ranges efficiently.
- **Complexity**: $O(W^2)$ per merge, where $W$ is `MAX_WORK_RESOLUTION`.

### 3. Iterative Segment Tree (PURQ)

The system uses a **Point Update Range Query (PURQ)** Segment Tree
implementation.

- **Structure**: Iterative (non-recursive), array-based for cache locality.
- **Mapping**: A logical rolling window `[head, tail]` is mapped modulo
  `MAX_BLOCKS` to the physical leaves of the tree.
- **Updates**: When a block is added or modified (reserved), only the affected
  leaf and its ancestors are recomputed ($O(\log N \cdot W^2)$).

## Workflows

### Adding Blocks (Rolling Update)

When a new 5-minute block arrives:

1.  If the buffer is full, the `head` pointer advances (effectively popping the
    oldest block).
2.  The new block data is written to `block_store_[tail % MAX]`.
3.  A `ProfileMatrix` is computed for the leaf node:
    - Applies the startup penalty $P$ for transitions from Inactive $\to$ Active
      ($0 \to 1$).
    - Calculates linear costs based on `(Load + w) / Capacity / Greenness`.
4.  The Segment Tree updates the leaf and re-merges up to the root.

### Querying Cost

To find the minimum cost for work $W$ in range $[L, R]$:

1.  Identify the $O(\log N)$ nodes covering $[L, R]$ in the Segment Tree.
2.  Multiply their matrices sequentially using `operator*`.
3.  The result is a single matrix representing the entire range.
4.  The answer is $\min_{u,v} \text{Result}_{uv}(W)$.

### Reserving Resources (Solve-Commit)

Reservation is a two-phase process:

1.  **Solve (Forward Pass)**:
    - Compute the prefix products of the matrices covering the range.
    - Determine the global minimum cost and the optimal **End State**
      ($v_{opt}$) and **Start State** ($u_{opt}$).

2.  **Commit (Backward Pass)**:
    - Drill down from the last node to the first.
    - At each step, find the "split point" $(w_{left}, w_{right})$ and
      intermediate state $k$ that produced the optimal cost.
    - Recursively descend to leaf nodes.
    - **Update**: At the leaf level, convert the assigned Net Work back to
      Physical Work (adding penalties if applicable), update the `initial_load`
      of the block, and refresh the leaf matrix.
    - **Refresh**: Recompute the tree nodes on the path back up to reflect the
      increased load (capacity consumption).

## Configuration & Complexity

### Constants

- `MAX_WORK_RESOLUTION` (default: 200): Discretization steps for work. Limits
  the maximum schedulable batch size.
- `MAX_BLOCKS` (default: 16384): Window size.
  $16384 \times 5 \text{min} \approx 56 \text{ days}$.
- `PENALTY_WORK_P` (default: 20.0): Equivalent work units added as a penalty for
  starting a machine.

### Time Complexity

- **Update**: $O(\log N \cdot W^2)$
- **Query**: $O(\log N \cdot W^2)$
- **Reserve**: $O((K + \log N) \cdot W^2)$, where $K$ is the number of blocks modified.
  - Efficiently updates only the affected leaves and the minimal set of ancestors (boundaries).

_Note: Since $W$ is small constant (200), these operations are very fast in
practice._

## Usage Example

```cpp
# include "TimeWindowScheduler.hpp"

// 1. Initialize
scheduler::TimeWindowScheduler sched(1.0); // 1.0 work units per discrete step

// 2. Add Data
sched.addBlock({
    .capacity = 100.0,
    .initial_load = 10.0,
    .greenness = 0.8,
    .location_id = "us-east-1",
    .timestamp = std::chrono::system_clock::now()
});

// 3. Query (Hypothetical)
// Check cost to schedule 50 units over the next 12 blocks (1 hour)
double cost = sched.query(0, 11, 50.0);

if (cost != -1.0) { // If feasible
    // 4. Reserve (Commit)
    auto schedule = sched.reserve(0, 11, 50.0);

    // 'schedule' contains vector<InternalBlock> with specific allocations
    for (const auto& block : schedule) {
        std::cout << "Allocated " << block.additionalLoad
                  << " at " << block.location_id << std::endl;
    }
}
```
