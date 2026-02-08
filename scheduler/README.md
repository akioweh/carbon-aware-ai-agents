# Scheduler Component

## Development Setup

Please follow [the coding style guide](./CODING_STYLE.md)

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

## System Design

This section documents the scheduler component's internal architecture, data
flows, and the engineering rationale behind key design decisions.

For the broader multi-component system design (Scheduler, Stats, UI), see
[`docs/system_component_design.md`](../docs/system_component_design.md).

### Architecture Overview

```
src/
├── controllers/
│   └── ScheduleController       # HTTP layer: request routing + orchestration
├── SchedulingQueue               # Lock-free coroutine task queue
├── Scheduler                     # Pure optimization engine (stateless)
├── Calendar                      # Persistence service (Drogon ORM)
├── StatsAPIClient                # External data fetching (Stats component)
├── structs/                      # Domain types and API DTOs
├── DtoMappers/                   # DB model <-> domain type conversions
├── exceptions/                   # Domain exceptions + global handler
├── models/                       # Auto-generated Drogon ORM models
└── utils/
    ├── Coro                      # Custom coroutine combinator (when_all)
    └── Utils                     # Time parsing, HTTP helpers
```

The scheduler is a Drogon HTTP server (C++23, coroutine-based) that exposes a
REST API for carbon-aware workload scheduling. Internally, it is structured as a
layered pipeline:

```
HTTP Request
    │
    ▼
Controller ──► SchedulingQueue ──► Scheduler ──► StatsAPIClient
    │                                  │              │
    │                                  │         Stats component
    │                                  │         (external, Python)
    │                                  │
    │              SchedulerOutput ◄───┘
    │              (InternalBlock[] + ScheduleImpact)
    │
    ├──► CalendarService::add(output) ──► PostgreSQL
    │         │
    │         └── returns DB-assigned job ID
    │
    ├──  Constructs ScheduleResult (API DTO) with real job ID
    │
    ▼
HTTP Response
```

Each layer has a single, well-defined responsibility. The boundaries are
enforced through distinct types at each interface (internal types for
computation, DTOs for API responses, ORM models for persistence).

### Type System and Layered Boundaries

The system uses distinct types at each architectural boundary to enforce
separation of concerns:

| Type                       | Layer          | Purpose                                           |
| -------------------------- | -------------- | ------------------------------------------------- |
| `JobRequest`               | API input      | Deserialized from HTTP request body               |
| `InternalBlock`            | Core Optimizer | Represents a work allocation in `SchedulerOutput` |
| `SchedulerOutput`          | Core Optimizer | Aggregates work allocations and impact metrics    |
| `ScheduleBlock`            | API DTO        | Analogous to `InternalBlock` but in API format    |
| `ScheduleResult`           | API DTO        | Analogous to `ScheduleBlock` but in API format    |
| `JobModel` / `ImpactModel` | ORM            | Auto-generated Drogon ORM for PostgreSQL          |

The key distinction is between `InternalBlock` (what the optimizer produces) and
`ScheduleBlock` (what the API returns). The optimizer has no knowledge of
persistence or job IDs — it produces raw allocation results. The controller is
responsible for persisting, obtaining the DB-assigned ID, and constructing the
API response. This prevents the optimizer from being coupled to persistence and
the external API (that requires stability).  
Moreover, the optimizer does not directly work on API structures because a
terse, linearized format allows for higher computational efficiency from higher
data locality reduced memory bandwidth.

The `DtoMappers` layer (niebloid pattern via `fromDto`/`toDto`) bridges the ORM
models and domain types, keeping conversion logic isolated from both business
logic and persistence code.

### Data Flows

#### 1. Schedule Creation (`POST /api/schedule`)

This is the primary flow. A user submits a job specification, and the system
returns an optimized schedule with a real, DB-assigned identifier.

```
Client
  │
  │  POST /api/schedule { job_type, workload_amount, earliest_start, latest_finish }
  ▼
ScheduleController::calculateSchedule
  │
  │  1. Enqueue job via SchedulingQueue
  ▼
SchedulingQueue::computeSchedule
  │  Suspends caller coroutine, pushes SchedulerTask onto lock-free queue.
  │  Consumer loop (runTasks) pops and runs tasks serially.
  ▼
Scheduler::scheduleJob
  │
  │  2a. Fetch data (concurrent via when_all):
  │      ├── StatsAPIClient::getAllDatacenters()
  │      │     ├── GET /locations                  → location list
  │      │     └── for each location (concurrent via when_all):
  │      │           ├── GET /locations/{id}/metrics/forecast_load
  │      │           └── GET /locations/{id}/metrics/forecast_greenness
  │      │
  │      └── CalendarService::get(start, end)      → existing schedule blocks
  │
  │  2b. Run optimization:
  │      ├── calc_single() per location (parallel via std::async)
  │      └── calc_multiple() merges via knapsack DP (parallel via std::for_each)
  │
  │  Returns SchedulerOutput { InternalBlock[], ScheduleImpact }
  │  (no job ID — the optimizer doesn't know about persistence)
  ▼
ScheduleController (resumed)
  │
  │  3. Persist: CalendarService::add(output)
  │     └── INSERT impact row → DB returns auto-increment ID
  │     └── INSERT block rows with foreign key to impact
  │     └── Returns job ID as string
  │
  │  4. Construct API DTO:
  │     └── InternalBlock[] + job ID → ScheduleBlock[]
  │     └── SchedulerOutput + job ID → ScheduleResult
  │
  ▼
Client receives ScheduleResult { schedule_id, schedule[], impact }
```

#### 2. Schedule Query (`GET /api/schedule`)

```
Client
  │
  │  GET /api/schedule?start_time=...&end_time=...
  ▼
ScheduleController::getSchedule
  │
  │  CalendarService::get(start, end)
  │  └── SELECT from Jobs WHERE timestamp in [start, end)
  │  └── ORM models → ScheduleBlock[] via DtoMappers::fromDto
  │
  ▼
Client receives ScheduleBlock[] (each block carries its job ID from the DB)
```

This read path goes directly from the controller to the calendar service — no
queue or optimizer involvement, as it's a pure DB lookup.

#### 3. Schedule Deletion (`DELETE /api/schedule/{schedule_id}`)

```
Client
  │
  │  DELETE /api/schedule/{schedule_id}
  ▼
CalendarService::deleteSchedule(id)
  │
  │  DELETE FROM Impacts WHERE id = ?
  │  (cascade deletes associated Jobs rows)
  │
  ▼
Client receives 200 OK
```

### Component Design Notes

#### SchedulingQueue: Thread-safe Serialized Execution Queueing

The scheduling queue serializes scheduling tasks so that only one optimization
runs at a time. This is a deliberate design choice, not a limitation.

**Serial execution?**: see above discussion on the scheduling algorithm on why
we chose to parallelize the algorithm itself instead of allowing concurrent
execution.

**Lock-free queue?**: because why not :)

**Coroutines?**: using vanilla functions would require the queue to explicitly
store and manage the input data each yet-to-run task. This would create
mandatory coupling between the queue and the scheduler's data structures.
Instead, by using coroutines that are constructed eagerly (but with immediate
suspension), we can abstract away the input data in the coroutine frame. Thus,
the queue manages coroutines, through their standard interface, without coupling
against the exact functions it must execute.

> [TODO]  
> currently the queue code does couple somewhat with the scheduler functions...
> it should be made fully generic as a "serial task queue".

#### Scheduler: Stateless Optimization Engine

The scheduler is deliberately stateless — it receives all necessary data as
inputs (from `StatsAPIClient` and `CalendarService`) and returns a pure result.
This makes it testable in isolation and ensures no hidden state leaks between
scheduling runs.

**Data fetching is concurrent**: `StatsAPIClient::getAllDatacenters()` fans out
to all locations concurrently using `scheduler::coro::when_all` .

**Computation is parallel**: the per-location DP (`calc_single`) runs each
location on a separate thread via `std::async`. The knapsack merge
(`calc_multiple`) parallelizes across work amounts via
`std::for_each(execution::par, ...)`.

#### CalendarService: Thin Persistence Layer

The calendar service is a thin wrapper over Drogon's ORM (`CoroMapper`). It
handles transactional writes (impact + blocks in one transaction) and
query-by-criteria reads. It does not perform business logic or data
transformations beyond what the `DtoMappers` provide.

`add()` returns the DB-assigned job ID as `std::string`, enabling the controller
to construct API DTOs with stable identifiers.

#### StatsAPIClient: External Data Gateway

The stats API client fetches load forecasts, greenness forecasts, and location
metadata from the external Stats component (a Python FastAPI service at
`http://127.0.0.1:5000`).

It produces `Datacenter` structs (a denormalized view combining load, greenness,
and capacity data per location) which the scheduler consumes directly. Load and
greenness data for each location are fetched concurrently (`when_all`), then
joined by timestamp.

#### Exception Handling

Domain exceptions are mapped to HTTP status codes via a global exception handler
registered at startup (`scheduler::exceptions::registerExceptionHandler()`):

| Exception             | HTTP Status | Meaning                                           |
| --------------------- | ----------- | ------------------------------------------------- |
| `ValidationException` | 422         | Malformed or semantically invalid request         |
| `SchedulingException` | 409         | Valid request, but infeasible given current state |
| (anything else)       | 500         | Unexpected internal error (drogon default)        |

`ValidationException` is thrown during request deserialization (in the
`drogon::fromRequest` specializations). `SchedulingException` is thrown by the
optimizer when the request is valid but the constraints cannot be satisfied
(e.g. insufficient capacity, empty time window, no available locations).

#### Coroutine Infrastructure (`utils/Coro.hpp`)

`scheduler::coro::when_all` is a custom coroutine combinator that runs multiple
`drogon::Task<T>` coroutines concurrently and suspends the caller until all
complete. It supports both variadic (heterogeneous types via `tuple`) and
homogeneous (`vector<Task<T>>`) overloads.

Key implementation details:

- Each child task runs via `drogon::async_run` (scheduled on the event loop's
  thread pool)
- A shared `ResultContext` tracks completion via `atomic<size_t> remaining`
- The last task to complete resumes the caller via
  `continuation.exchange(WAITING_CONTINUATION)`, handling the race where the
  caller hasn't suspended yet
- Exceptions are captured lock-free (first-writer-wins via
  `atomic<char> exceptionState`) and rethrown in `await_resume`
