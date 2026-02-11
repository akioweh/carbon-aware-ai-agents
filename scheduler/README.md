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

### Parallelized Scheduling Algorithm

> [!SUMMARY]  
> We wanted some concurrency or parallelism in the scheduling algorithm because
> pain is fun. We could've either designed the system to allow multiple
> schedulers to run concurrently or parallelized the scheduling algorithm
> itself.  
> We decided to **parallelize the algorithm itself**.  
> Reasoning: running concurrent schedulers is fundamentally impractical due to
> data consistency issues: each scheduling instance must read some shared state
> (calender) at the start and write to it at the end. Thus, any outside changes
> during a scheduling run would invalidate the entire run. As the scheduling is
> a computation-bound problem, this would result in a lot of wasted work as
> everything would remain effectively serial due to locking.
>
> A parallelized algorithm will run faster and decrease latency and throughput.

The algorithm has two stages:

1. **Per-location pre-computation**: for each location, calculate, for all
   workload amounts, the best (least emissions) schedule.
2. **Aggregation of results**: consider all combinations of per-location
   schedules to find the overall best schedule.

The first part is a dynamic programming algorithm and is trivially
parallelizable as each location is independent. The second part is a "multiple
choice" knapsack problem. This is harder to parallelize, but technically each
"row" of the DP passes can be parallelized.

The implementation should use an efficient thread polling strategy and place
care in minimizing data flow (memory bandwidth) and synchronization overhead.
