# Inter-Component APIs

This document briefs the design and realization of the communication interfaces
used between the three components.

## Overview

The system comprises three components that communicate via RESTful HTTP APIs:

1. **Scheduler** - Core optimization logic for workload placement
2. **Stats** - Environmental and operational data provider
3. **UI** - User interface for job submission and visualization

> [!TIP]  
> See the [systems component design document](./system_component_design.md) for
> more details on this architecture

Two OpenAPI v3 schemas define the HTTP APIs that power the interactions:

- **[scheduler/openapi.yaml](../scheduler/openapi.yaml)** - the programmatic
  interface to the scheduling system; exposed by the Scheduler for the UI to
  call
- **[stats/openapi.yaml](../stats/openapi.yaml)** - the unified data platform
  interface; exposed by the Stats for the Scheduler to call

Naturally, the interconnection APIs and the overall system weakly follow a
RESTful design (e.g. a request-response pipeline).

## Design Philosophy

The schemas should give way to effective, clean implementations in software.
E.g. in-memory data layout and serialized structures should align well to
minimize translation overheads.

- Design-first: prioritize objective, optimal systems design over _existing_
  implementation details; implementation iteratively improves as needed
- Pragmatic: consider the content, size, and timings of data flow to structure
  endpoints that lend themselves to their use cases
- Simplicity: capture only the necessary information, but using natural model
  structures to avoid over-terseness
- Extensibility: apply a decent level of abstraction in model design and avoid
  over-fitting to current implementation details
- Standardization: consider standardized encodings and definitions before
  inventing proprietary ones

## Common Models

### Workload Block

A **Workload Block** is the fundamental unit of state in the system. It
represents a discrete unit of compute load at a specific location for a specific
duration. **Currently, each block represents a 5-minute interval.**

Workload Blocks can represent compute load both "owned" by us (i.e. scheduled
jobs) and of external origin (i.e. baseline load at data centers).

> [!NOTE]  
> this is the current model used in the Scheduler API; more fields may be needed
> to implement later features

| Field             | Type     | Description                                 |
| ----------------- | -------- | ------------------------------------------- |
| `timestamp`       | `string` | (Start) time of the block (ISO 8601 format) |
| `location`        | `string` | Datacenter GUID (name)                      |
| `job_id`          | `string` | Job GUID                                    |
| `additional_load` | `number` | Amount of compute                           |

> [!TIP]  
> The formal schema definition is in
> [scheduler/openapi.yaml](../scheduler/openapi.yaml), called `ScheduledBlock`.

### Job Specification

A **Job Specification** describes the requirements and constraints of a job. As
the Scheduler always and only outputs the optimal placement, the specification
is the only way to influence the scheduling outcome.

| Field                    | Type     | Description                                              |
| ------------------------ | -------- | -------------------------------------------------------- |
| `job_type`               | `string` | Nature of the workload (e.g., training, inference)       |
| `workload_amount`        | `number` | Quantitative measure of compute (wrt. job type)          |
| `earliest_start`         | `string` | Earliest permissible start time (ISO 8601 format)        |
| `latest_finish`          | `string` | Latest permissible finish time (ISO 8601 format)         |
| `additional_constraints` | `object` | Key-value pairs for extra constraints (currently unused) |

> [!TIP]  
> The formal schema definition is in
> [scheduler/openapi.yaml](../scheduler/openapi.yaml), called `JobRequest`.

## API Interactions

> [!NOTE]  
> "A -> B" means a call dispatched by A to B; A sends the request, and B
> responds with information.

### 1. UI → Scheduler: Job Submission & Management

The Scheduler's API exposes all user-facing functionality, primarily focused on
viewing the current schedule and submitting new jobs for carbon-aware
optimization.

**Endpoints:**

- **`GET /api/schedule`**: Retrieves the complete schedule of all currently
  planned jobs across data centers. This allows the UI to visualize the global
  state of workloads.
- **`POST /api/schedule`**: The optimization operation. Accepts a job
  specification and returns an optimized placement plan (without persisting it).

**Unit Interaction Sequence:**

1. **Job Request (Preview)**: The user submits a description of a job along its
   execution requirements:
   - **Type**: The nature of the workload (used in normalizing the amount of
     work).
   - **Workload Amount**: A quantitative measure of the compute required.
   - **Time Window**: temporal constraint on the schedule placement.
   - **Constraints**: additional parameters to refine placement.

2. **Optimization**: The scheduler processes this request by finding time slots
   and locations that minimize carbon impact while satisfying all constraints.
   (This involves querying the Stats component for necessary data.)

3. **Schedule Response (Proposal)**: On success, the API returns:
   - **Schedule Info**: Specific time allocations at designated locations with
     associated loads.
   - **Impact Metrics**: Projected environmental impact data, including unit and
     total carbon emissions and the SCI score.

4. **Commitment**: The user accepts the proposal. The client sends the selected
   Workload Blocks back to the Scheduler/Stats (?). **Note**: API TBD (could
   directly go to Stats or pass through Scheduler).

### 2. Scheduler → Stats: Data Retrieval & State Management

The Stats component serves two critical roles:

1. **Context Provider**: Aggregates and forecasts environmental data (Carbon
   Intensity, Weather) and Baseline Load.
2. **State Manager**: Persists the "Global Schedule" by storing the Workload
   Blocks committed by the Scheduler.

**Endpoints:**

> [!WARNING]  
> currently the Stats API Schema is completely inaccurate and problematic; it
> requires significant rework before this section can be meaningfully populated
