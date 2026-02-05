# Scheduler Component

## Development Setup

### Software

C++23!  
Application code should maximally leverage the newest (up to std++23) language
and STL features!

**Library Dependencies:**

- `drogon` (latest stable)
- `boost` (latest stable)

### Toolchain

CMake-based C++.

Tested working configurations:

- Windows \[MSys2 (toolchain) + `vcpkg` (package manager)\]: was not fun to get
  working
- Arch \[`drogon` via paru\]

If you are developing on a new platform/setup and think a generic version of
your CMake configuration could be used by others too, add it to
[`CMakePresets.json`](./CMakePresets.json)!  
However, remember that your personal CMake configurations (like hard-coded
paths) should live in the (untracked) `CMakeUserPresets.json`.

For consistent ergonomics, use `clangd` with `clang-tidy` and `clang-format`.
Their configuration files are tracked for consistent linting and formatting

### Quickstart

0. Ensure your have a working toolchain and the two dependencies installed
1. Find your appropriate preset in [`CMakePresets.json`](./CMakePresets.json) or
   add what's missing
2. Run `cmake --preset <preset name>` (in this directory) to generate build
   files
3. Your editor should detect project settings now from
   [`compile_commands.json`](./compile_commands.json)
4. Build anytime using `cmake --build build/<preset name>`
5. Output binary is at `./build/<preset name>/scheduler(.exe)`

### Testing

The component uses `Boost.Test`.

To run the tests:

1. Build the tests:

   ```bash
   cmake --build build/<preset name> --target <test_name>
   # OR build everything
   cmake --build build/<preset name>
   ```

2. Run via CTest:

   ```bash
   cd build/<preset name>
   ctest --output-on-failure
   ```

**Build Configuration:**

- The core (`src/`) is compiled as an Object Library `scheduler_core`.
- The tests link against `scheduler_core` to test internal logic without
  recompilation.

## Implementation Details

### Scheduling Algorithm

#### Problem Formalization

**1. Single-location case**

Given is a sequence of $n$ blocks numbered $1$ to $n$;  
each `block` $b_i$ is associated with an `existing_load` $l_i$ and `max_load`
$r_i$.  
Also given is total work $W$ to be allocated over the blocks.  
Each $b_i$ has a non-decreasing cost function $c_i(\text{load})$.

The optimization problem is to distribute the work $W$ over the blocks into
$w_1$, $w_2$, $...$, $w_n$ such that $\sum w_i\ \ge\ W$, $w_i + l_i\ \le\ r_i$
and the total additional cost incurred, $\sum [c_i(l_i + w_i) - c_i(l_i)]$, is
minimized.  
There is also an additional penalty for non-continuous allocations: for each
$i > 1$ where $w_i > 0$ and $w_{i-1} = 0$, an additional penalty work $P$ must
be added to $W$: $\sum w_i\ \ge\ W + kP$, where $k$ is the number of such $i$.

At this point, the problem is well-defined, but there remains one very important
distinction: are $l_i$, $r_i$, and the cost function continuous or discrete
values?  
If discrete, we can use DP techniques... if continuous, we'd be fucked.  
Conclusion: the values are discrete, due to algorithmic difficulties :)

Without the penalty for non-continuous allocations, this is a classic "resource
allocation" DP problem. The penalty condition can be modeled as a simple
transformation.

$$
\sum w_i\ \ge\ W + kP \\
\sum w_i - kP\ \ge\ W
$$

...where we define "effective work" $E = \sum w_i - kP$.  
Clearly, we have again

$$
 E\ \ge\ W
$$

Now, we minimize the cost over $E$ instead of $\sum w_i$.

**2. Multi-location case**

Everything is the same as above, except we have $m$ locations, each represented
as an independent sequence of blocks.  
Now, we're allocating $W$ over not one sequence of $n$ blocks but a
2-dimensional $m\times n$ surface of blocks.

#### Additional Discussion

- For case 1, we've considered forms of Lagrangian Relaxation for continuous
  values, but abandoned as cost functions are not convex.
- DP is probably the best way to go (discretizing values) and has the most
  freedom (if we were to add additional scheduling constraints, since it makes
  the least assumptions).

**Multi-to-single location reduction**:

In addition to the bullet points above, a DP solution also transforms nicely to
the multi-location case: we can first solve an augmented single-location problem
for each location and then combine the results to solve case 2.

Specifically, for each individual location, instead of computing against just
the total work $W$, we compute an optimal allocation $\{w_i\}$ for all
$W' \in [0, W]$.  
Once we know the optimal allocation for each location for all possible
workloads, we can run a second algorithm to find the optimal combination of
per-location allocations that meets the total workload requirement.

This can be formalized into two steps:

1. **Per-location pre-computation**: for each location, calculate, for all
   workload amounts, the optimal allocation.
2. **Aggregation of results**: consider all combinations of per-location
   allocations to find the overall optimal allocation.

For step 2, we formally have a set of cost-work pairs $(c_{i,j}, w_{i,j})$ where
$i \le m$ is the location and $j \le W$ is the workload amount. If we partition
the set into $m$ buckets by location, we have a "multiple choice" knapsack
problem: we must choose exactly one element from each bucket to minimize total
cost while ensuring the total work done meets the requirement.

**Discretization**:

For some continuous variable $x \in [l, r]$, we can choose some resolution $s$
to split the range into $s$ equal-sized intervals; we'd have some
$e = \lceil (r - l) / s\rceil$ and deal with integer multiples of $e$.

#### Parallelization

A parallelized algorithm will run faster, decreasing latency and increasing
throughput.

> [!SUMMARY]  
> We wanted some concurrency or parallelism in the scheduling algorithm because
> pain is fun. We could've either designed the system to allow multiple
> schedulers to run concurrently or parallelized the scheduling algorithm
> itself.  
> We decided to **parallelize the algorithm itself**.  
> Reasoning: running concurrent schedulers is fundamentally impractical due to
> data consistency issues: each scheduling instance must read some shared state
> (the calender) at the start and write to it at the end. Thus, any outside
> changes during a scheduling run would invalidate the entire run. As the
> scheduling is a computation-bound problem, this would result in a lot of
> wasted work as everything would remain effectively serial due to locking.
>
> The first part is a dynamic programming algorithm and is trivially
> parallelizable as each location is independent. The second part is a "multiple
> choice" knapsack problem. This is harder to parallelize, but technically each
> "row" of the DP passes can be parallelized.

The implementation should use an efficient thread polling strategy and place
care in minimizing data flow (memory bandwidth) and synchronization overhead.
