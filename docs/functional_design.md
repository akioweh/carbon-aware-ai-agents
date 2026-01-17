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

The core user interaction follows a two-phase "Preview-Commit" workflow. This
ensures users can review the computed schedule and environmental impact of a job
before approving it for deployment. (Even though we persist it immediately, it will be 
deleted if user decides to reject it.)

#### Phase 1: Optimization (Persistence)

1. **Submission**: Client `POST`s a Job Spec to the Scheduler.
2. **Calculation**:
   - Scheduler fetches _Context_ (grid carbon, already-scheduled jobs, data
     center load) from Stats.
   - Scheduler computes the optimal placement to minimize carbon impact.
   - _Crucially, the Scheduler will immediately persists this result._
3. **Response**: Scheduler returns the **Proposed Schedule** (Workload Blocks +
   Impact Metrics) to the Client.
4. **Persistence**:
   - Write to DB

#### Phase 2: Commitment (Deletion)

1. **User Decision**: The user reviews the proposal in the UI.
   - **Discard**: User cancels the schedule.
   - **Accept**: User confirms - no further action is taken.
2. **Reject**: Client `DELETE`s the rejected **Workload ID** to the "Delete" endpoint of scheduler.
3. **Deletion**: Scheduler deletes the previously persisted schedule.


### Schedule Visualization

This feature allows the client to view the global state of the data centers,
seeing both the background "baseline" load and the jobs they have scheduled.

1. **Request**: Client `GET`s the schedule from the Scheduler, in any time interval.
2. **Presentation**: The UI displays the data in some nice calendar format or
   something :).

### Scheduled Job Details View

This feature allows users to inspect the details of a previously scheduled job.
The viewable information is the same as the "Proposed Schedule" from the
optimization phase (i.e., the environmental impact metrics).

1. **Request**: Client `GET`s the specific schedule from the Scheduler using schedule_id.
2. **Presentation**: The UI displays all the details related to this job, including 
   same information as in "Proposed Schedule" response.
