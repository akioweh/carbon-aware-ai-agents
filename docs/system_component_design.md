# System Design Specification

This document briefs on the architectural design of this software system.

## Overview

The System will be comprised of three independent components:

- Scheduler: the core logical computational program
- Stats: ingests and forecasts external data under a uniform interface for the Scheduler
- UI: a web-app to take user input and display Scheduler output

The components are independent software processes separated on an area-of-concern basis.
The components will interact and communicate using HTTP (RESTful) APIs.
Having the API on the network layer maximizes modularity, allowing each component to be developed
both in parallel and in whatever language and dev stack that is the most appropriate for the job.

## Components

### Scheduler

This is the core logical program that determines the best "deployment schedule" for
a given AI workload to "minimize environmental impact".

The environmental and stateful data required for the scheduling is obtained from
the Stats component.
Ultimately, the user interacts with the scheduler via the UI, where the outputs
are also visualized/displayed.

### Stats

The scheduling work requires multiple types of data,
each of which may have multiple sources:

- environmental (per location over time): grid carbon intensity, weather, etc.
- data center state (per center): current load, total capacity, etc.
- temporary constraints (misc factors)

The Stats component should integrate with these sources and relay the data,
potentially with forecasts, to the Scheduler under an uniform interface.

Of course, this component also handles data sanitation, normalization, persistence, etc.

### UI

Standard server-side rendered web-app.
This component provides the human-computer interface.

The main interfaces will include:

- visualizations of data center states together with the environmental costs at each
- task input / control
- presentation of the scheduler output for a task

## Interconnection

```mermaid
---
config:
  layout: elk
---
flowchart TB
 subgraph External_Group["External Data Sources"]
    direction LR
        Grid["Grid Carbon Intensity"]
        Weather["Weather Data"]
        DC_State["DC Load & Capacity"]
        Costs["<b>Cost Context</b><br>$$ per Compute Unit"]
  end
 subgraph UI_Comp["UI Component"]
    direction TB
        UI_In["Input Handler"]
        UI_View["Dashboard / Visualizer"]
  end
 subgraph Sched_Comp["Scheduler Component"]
    direction TB
        Solver["<b>Logic Core</b><br>Constraint Solver"]
  end
 subgraph Stats_Comp["Stats Component"]
    direction TB
        Ingest["Data Ingestion"]
        DB[("History DB")]
        Forecast["Forecasting Engine"]
        Norm["Normalizer / API Interface"]
  end
 subgraph System["Software System"]
    direction TB
        UI_Comp
        Sched_Comp
        Stats_Comp
  end
    Ingest <-- Read/Write --> DB
    Ingest --> Forecast
    DB -. Historical Patterns .-> Forecast
    Forecast --> Norm
    User(("User")) -- Defines --> JobSpec["<b>Job Specification</b><br>-----------------------<br><b>Unit:</b> Functional Unit<br><b>Workload:</b> Estimated Qty<br><b>Constraints:</b> Earliest Start / Latest Finish<br><b>Reqs:</b> Throughput / Latency"]
    JobSpec -- Submits --> UI_In
    UI_In -- "1. Task Request" --> Solver
    Solver -. "4. Schedule Output" .-> UI_View
    UI_View -- Displays --> User
    Grid ==> Ingest
    Weather ==> Ingest
    DC_State ==> Ingest
    Costs ==> Ingest
    Solver -- "2. Query State" --> Norm
    Norm -. "3. Normalized Forecasts" .-> Solver

     Grid:::external
     Weather:::external
     DC_State:::external
     Costs:::external
     UI_In:::internal
     UI_View:::internal
     Solver:::internal
     Ingest:::internal
     DB:::database
     Forecast:::internal
     Norm:::internal
     User:::actor
     JobSpec:::dataNode
    classDef component fill:#e1bee7,stroke:#4a148c,stroke-width:2px
    classDef internal fill:#ffffff,stroke:#7b1fa2,stroke-width:1px
    classDef database fill:#fff9c4,stroke:#fbc02d,stroke-width:1px
    classDef actor fill:#ffffff,stroke:#000000,stroke-width:1px
    classDef external fill:#eeeeee,stroke:#999999,stroke-width:1px,stroke-dasharray: 4 4
    classDef dataNode fill:#e3f2fd,stroke:#1565c0,stroke-width:2px
```

```mermad
sequenceDiagram
    autonumber
    actor U as User
    participant UI as UI Component
    participant Sched as Scheduler
    participant Stats as Stats Component
    participant DB as Stats DB
    participant Ext as External Sources<br>(Grid, Cost, Weather)

    %% -- Phase 1: Background Ingestion Loop --
    note over Stats, Ext: Background Process
    loop Constant Data Ingestion
        Ext->>Stats: Raw Data (Costs, Weather, Grid)
        Stats->>DB: Persist History
        DB-->>Stats: Read Historical Patterns
        Stats->>Stats: Generate Forecasts & Normalize
    end

    %% -- Phase 2: User Action --
    note over U, Sched: Interactive Process
    U->>UI: Input Job Spec<br>(Units, Constraints, Reqs)

    %% UI to Scheduler
    UI->>Sched: POST /api/schedule<br>{ "job_spec": { ... } }
    activate Sched

    %% Scheduler needs context
    Sched->>Stats: GET /api/context?window=start_end
    activate Stats
    Stats-->>Sched: 200 OK <br>{ "cost_context": { ... } }
    deactivate Stats

    %% Logic Calculation
    Sched->>Sched: Run Constraint Solver<br>(Job Spec + Cost Context)

    %% Return Result
    Sched-->>UI: 200 OK<br>{ "schedule": { ... } }
    deactivate Sched

    UI->>U: Display Visualization & Schedule
```

## Rendered Diagrams

![](./system_block_diag.svg)

![](./sequence_diag.svg)
