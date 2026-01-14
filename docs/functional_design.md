# Functional Design Specification

This document outlines the core features, functional requirements, and logical design of the Carbon-Aware AI Agent system.

## 1. Core Concepts

### 1.1. Workload Blocks
The fundamental unit of state in the system is a **Workload Block**. A block represents a discrete unit of compute load at a specific location for a specific duration.

**Structure:**
- **ID**: Unique identifier.
- **Source**: `BASELINE` (external/pre-existing load) or `SCHEDULED` (user-submitted job).
- **Location**: Data center identifier (e.g., `us-west-1`).
- **Time Interval**: Start time and Duration (or End time).
- **Magnitude**: The amount of load (e.g., kW, GPU utilization).
- **Job Metadata**: (Optional) Reference to the parent Job ID if applicable.

### 1.2. The Global Schedule
The **Global Schedule** is the aggregation of all Workload Blocks across all locations. It represents the complete state of the system:
$$ \text{Total Load}(t, \text{location}) = \sum \text{Block}_{\text{load}}(t, \text{location}) $$
*Where the sum includes both Baseline blocks and Scheduled blocks.*

## 2. Component Responsibilities

To achieve a persistent and stateful system, the responsibilities are divided as follows:

### 2.1. Stats Component (State Manager)
The Stats component is expanded from a simple data provider to the **Persistence Layer** and **State Manager** of the system.

*   **Responsibilities:**
    *   **Ingestion:** Continues to ingest external data (Weather, Grid Carbon, Baseline Load).
    *   **Block Registry:** Maintains the database of all `SCHEDULED` workload blocks committed by the Scheduler.
    *   **Aggregation:** dynamic calculation of "Total Load" by combining stored `SCHEDULED` blocks with ingested `BASELINE` forecasts.
    *   **API Extensions:**
        *   `GET /schedule`: Retrieve active blocks.
        *   `POST /schedule`: Commit new blocks (persist a scheduled job).
        *   `DELETE /schedule`: Remove blocks.

### 2.2. Scheduler Component (Logic Core)
The Scheduler remains the stateless brain of the operation. It does not store the schedule locally but queries the Stats component to rebuild the state when needed.

*   **Responsibilities:**
    *   **Optimization:** Calculates optimal placement of new jobs based on data retrieved from Stats.
    *   **Transaction Coordinator:** Ensures that once a schedule is computed, it is "committed" to the Stats component.

## 3. Feature Workflows

### 3.1. Job Scheduling (The "Write" Path)
This feature allows a client to submit a job specification and receive a confirmed, carbon-optimized schedule.

1.  **Submission**: Client `POST`s a Job Spec (Type, Load, Window) to the Scheduler.
2.  **Context Assembly**:
    *   Scheduler requests **Carbon Forecasts** from Stats.
    *   Scheduler requests **Current Schedule/Load** from Stats (Baseline + Scheduled).
3.  **Optimization**:
    *   Scheduler identifies time slots where $\text{Carbon Intensity} \times \text{Load}$ is minimized.
    *   It ensures $\text{Total Load} + \text{New Job} \le \text{Capacity}$.
4.  **Commit**:
    *   Scheduler generates a set of new **Workload Blocks** representing the job.
    *   Scheduler `POST`s these blocks to the Stats component to persist them.
5.  **Response**: Scheduler returns the plan to the client.

### 3.2. Schedule Visualization (The "Read" Path)
This feature allows the client to view the global state of the data centers, seeing both the background "baseline" load and the jobs they have scheduled.

1.  **Request**: Client `GET`s the schedule from the Scheduler.
2.  **Retrieval**: Scheduler queries the Stats component for all active blocks within the requested window.
3.  **Presentation**: Scheduler formats the blocks (distinguishing between Baseline and Scheduled) and returns them to the UI.

### 3.3. Conflict Resolution (Implicit)
By treating the Stats component as the "Ledger", race conditions (e.g., two schedulers running at once) can be managed. If the Stats component receives a new block that pushes load over capacity (because another job was just scheduled), it can reject the `POST`, forcing the Scheduler to re-optimize. *(Note: This is a future resiliency feature, but the design supports it).*
