export interface ScheduleImpact {
  carbon_intensity: number
  total_emissions: number
  carbon_intensity: number
}

export interface ScheduleBlock {
  timestamp: string
  location: string
  schedule_id: string
  additional_load: number
}

export interface ScheduleData {
  schedule_id: string
  scheduled_blocks: ScheduleBlock[]
  impact: ScheduleImpact
}

export interface JobScheduleResponse extends ScheduleData {
  message?: string
}

export interface ScheduleSummary {
  schedule_id: string
  message?: string
  impact: ScheduleImpact
  trivialImpact?: ScheduleImpact
}

export interface JobSummary extends ScheduleSummary {
  start_time: string
  end_time: string
  scheduled_blocks: ScheduleBlock[]
  unoptimizedResult?: Partial<ScheduleData>
}