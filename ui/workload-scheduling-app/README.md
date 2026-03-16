# Carbon-Aware Workload Scheduler

A web application for scheduling AI workloads across data centers with minimal environmental impact. The frontend communicates with a C scheduler backend through REST API endpoints.

## Features

### ✅ Scheduling Form Page

- **Workload Configuration**: Enter workload amount, job type, data center preference, and time constraints
- **Calendar View Button**: Opens a full calendar view showing existing datacenter load and scheduled jobs
- **Date Selection**: Select any date to view workload distribution across all 5 data centers
- **Interactive Bar Chart**: Scrollable bar chart displays workload in 5-minute intervals across the entire day
- **Job Differentiation**: 
  - Gray bars represent existing datacenter base load
  - Blue bars represent scheduled job workloads
  - API endpoint `GET /api/schedule` returns all scheduled blocks with job IDs and additional load amounts

### ✅ Schedule Results Page

- **Time-Ranged Visualization**: Bar chart displays workload only between user's inputted start and end time
- **Multi-Datacenter View**: Tabs to switch between 5 different data centers
- **Environmental Impact**: Displays carbon intensity, total emissions, and SCI metrics
- **Cancel Job Button**: 
  - Alert dialog confirms before deletion
  - Calls `DELETE /api/schedule/{schedule_id}` to remove job from schedule
  - Returns user to scheduling form after cancellation

## API Integration

The application uses the following endpoints based on the OpenAPI schema:

### `POST /api/schedule`
Creates a new scheduled job with optimal placement:
- **Request**: Job type, workload amount, earliest start, latest finish
- **Response**: Schedule ID, scheduled blocks, environmental impact

### `GET /api/schedule`
Fetches all scheduled blocks within an optional time range:
- **Query Params**: `start_time`, `end_time` (optional)
- **Response**: Array of schedule blocks with timestamp, location, job_id, additional_load

### `GET /api/schedule/{schedule_id}`
Fetches a specific schedule by ID:
- **Response**: Complete schedule details with blocks and impact

### `DELETE /api/schedule/{schedule_id}`
Removes a scheduled job from the system:
- **Response**: Confirmation message

## Components

- **`SchedulingForm`**: Main form for configuring and submitting workload jobs
- **`WorkloadCalendar`**: Calendar view with datacenter workload visualization
- **`ScheduleResult`**: Results page showing scheduled job with environmental impact and controls

## Tech Stack

- **Next.js 16** with App Router
- **React 19.2** with Server Components
- **TypeScript** for type safety
- **Tailwind CSS v4** for styling
- **shadcn/ui** components
- **date-fns** for date formatting

## Running the Project

```bash
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) to view the application.

## Notes

- The current implementation includes mock API routes for demonstration
- Connect to your C scheduler backend by updating the API route handlers
- Time intervals are set to 5 minutes to match the scheduler's block duration
- All times use ISO 8601 format for API communication
