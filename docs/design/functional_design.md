# Functional Design Specification

Some stuff on how specific features are achieved (technical implementation and
data flow).

## Core Concepts

### Workload Blocks

See the [API Schemas](./api-schemas.md) for details.  
The fundamental unit of state in the system is a **Workload Block**. A block
represents a discrete unit of compute load at a specific location for a specific
duration.

### The Global Schedule

The **Global Schedule** is the aggregation of all Workload Blocks consisting of
both the background "baseline load" at data centers and the jobs scheduled by
users. It represents the complete picture of compute load across all data
centers.

When optimizing a placement for a new job at any moment, the Scheduler inspects
the global schedule to determine the available capacity at data centers.

## Feature Workflows

### Job Scheduling

The core user interaction follows a two-phase Commit–Cancel workflow. This
design guarantees that the schedule shown to the user exactly reflects how the
job will execute.

> [!NOTE]  
> A traditional “preview” is not viable because the scheduling environment is
> shared: other users may submit jobs between preview and confirmation, causing
> the final schedule to differ. To prevent this, the system commits the schedule
> immediately, then allows the user to cancel if desired. As a result, the
> schedule the user sees cannot worsen due to concurrent submissions.

#### Phase 1: Commitment (Optimization and Persistence)

1. **Submission**: Client `POST`s a Job Spec to the Scheduler.
2. **Calculation**:
   - Scheduler fetches _Context_ (grid carbon, already-scheduled jobs, data
     center load) from Stats.
   - Scheduler computes the optimal placement to minimize carbon impact.
3. **Persistence**: The Scheduler immediately persists the computed schedule to
   the database, reserving the required resources.
4. **Response**: Scheduler returns the optimized schedule (Workload Blocks) and
   Impact metrics to the Client.

#### Phase 2: User Decision (Cancellation Option)

1. **User Decision**: The user reviews the proposal in the UI.
   - **Cancel**: Client `DELETE`s the rejected **Workload ID** to the "Delete"
     endpoint of scheduler.
   - **Accept**: User confirms - no further action is taken.
2. **Deletion**: Scheduler deletes the previously persisted schedule.

### Schedule Visualization

This feature allows the client to view the global state of the data centers,
seeing both the background "baseline" load and the jobs they have scheduled.

1. **Request**: Client `GET`s the schedule from the Scheduler, in any time
   interval.
2. **Presentation**: The UI displays the data in some nice calendar format or
   something :).

### Scheduled Job Details View

This feature allows users to inspect the details of a previously scheduled job.
The viewable information is the same as the "Proposed Schedule" from the
optimization phase (i.e., the environmental impact metrics).

1. **Request**: Client `GET`s the specific schedule from the Scheduler using
   schedule_id.
2. **Presentation**: The UI displays all the details related to this job,
   including same information as in "Proposed Schedule" response.
