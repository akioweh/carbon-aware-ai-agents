# Inter-Component APIs

This document briefs the design and realization of the communication interfaces used between the three components.

## Overview

The system comprises three components that communicate via RESTful HTTP APIs:

1. **Scheduler** - Core optimization logic for workload placement
2. **Stats** - Environmental and operational data provider
3. **UI** - User interface for job submission and visualization

> [!TIP]
> See the [systems component design document](./system_component_design.md) for more details on this architecture

Two OpenAPI v3 schemas define the HTTP APIs that power the interactions:

- **[scheduler/openapi.yaml](../scheduler/openapi.yaml)** - the programmatic interface to the scheduling system; exposed by the Scheduler for the UI to call
- **[stats/openapi.yaml](../stats/openapi.yaml)** - the unified data platform interface; exposed by the Stats for the Scheduler to call

Naturally, the interconnection APIs and the overall system weakly follow a RESTful design (e.g. a request-response pipeline).

## Design Philosophy

The schemas should give way to effective, clean implementations in software.
E.g. in-memory data layout and serialized structures should align well to minimize translation overheads.

- Design-first: prioritize objective, optimal systems design over _existing_ implementation details; implementation iteratively improves as needed
- Pragmatic: consider the content, size, and timings of data flow to structure endpoints that lend themselves to their use cases
- Simplicity: capture only the necessary information, but using natural model structures to avoid over-terseness
- Extensibility: apply a decent level of abstraction in model design and avoid over-fitting to current implementation details
- Standardization: consider standardized encodings and definitions before inventing proprietary ones

## API Interactions

> [!NOTE]
> "A -> B" means a call dispatched by A to B; A sends the request, and B responds with information.

### 1. UI → Scheduler: Job Submission

The Scheduler's API exposes all user-facing functionality, primarily focused on viewing the current schedule and submitting new jobs for carbon-aware optimization.

**Endpoints:**

- **`GET /api/schedule`**: Retrieves the complete schedule of all currently planned jobs across data centers. This allows the UI to visualize the global state of workloads.
- **`POST /api/schedule`**: The core operation. Accepts a job specification and returns an optimized placement plan.

**Unit Interaction Sequence:**

1. **Job Request**: The user submits a description of a job along its execution requirements:
   - **Type**: The nature of the workload (used in normalizing the amount of work).
   - **Workload Amount**: A quantitative measure of the compute required.
   - **Time Window**: temporal constraint on the schedule placement.
   - **Constraints**: additional parameters to refine placement.

2. **Optimization**: The scheduler processes this request by finding time slots and locations that minimize carbon impact while satisfying all constraints. (This involves querying the Stats component for necessary data.)

3. **Schedule Response**: On success, the API returns:
   - **Schedule Info**: Specific time allocations at designated locations with associated loads.
   - **Impact Metrics**: Projected environmental impact data, including unit and total carbon emissions and the SCI score.

### 2. Scheduler → Stats: Data Retrieval

The Scheduler requires various data (e.g. environmental, data center state) from external sources.
The Stats component exposes a unified API for the Scheduler to retrieve this information and abstracts away the actual work of ingesting the external data sources.

> [!NOTE]
> currently the Stats API Schema is completely inaccurate and along this section, requires significant rework
