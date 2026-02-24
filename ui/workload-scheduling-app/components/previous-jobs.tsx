"use client"

import { useState, useEffect } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { History, X, Loader2, Calendar, MapPin, Leaf } from "lucide-react"
import { ScrollArea } from "@/components/ui/scroll-area"

interface ScheduleBlock {
  timestamp: string
  location: string
  schedule_id: string
  additional_load: number
}

interface JobSummary {
  schedule_id: string
  scheduled_blocks: ScheduleBlock[]
  impact?: {
    carbon_intensity?: number
    total_emissions?: number
    sci?: number
  }
  unoptimizedResult?: {
    schedule_id: string
    scheduled_blocks?: ScheduleBlock[]
    impact?: {
      carbon_intensity?: number
      total_emissions?: number
      sci?: number
    }
  }
  start_time?: string
  end_time?: string
}

interface PreviousJobsProps {
  onClose: () => void
  onSelectJob: (job: JobSummary) => void
}

export function PreviousJobs({ onClose, onSelectJob }: PreviousJobsProps) {
  const [jobs, setJobs] = useState<JobSummary[]>([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    const fetchPreviousJobs = async () => {
      setLoading(true)
      try {
        // Fetch all schedule blocks (no time filter = all jobs)
        const response = await fetch("/api/schedules")
        
        if (!response.ok) {
          throw new Error(`Failed to fetch jobs: ${response.status}`)
        }

        const raw = await response.json()

        // Validate response is an array of ScheduleBlock objects
        if (!Array.isArray(raw)) {
          throw new Error("Unexpected schedule response shape")
        }

        // Sanitize blocks (ensure required fields exist and are correct types)
        const blocks = raw.filter((b: any) => {
          return (
            b &&
            typeof b.timestamp === "string" &&
            typeof b.location === "string" &&
            typeof b.schedule_id === "string" &&
            typeof b.additional_load === "number"
          )
        }) as ScheduleBlock[]
        
        // Group blocks by schedule_id to create job summaries
        const jobMap = new Map<string, ScheduleBlock[]>()
        
        for (const block of blocks) {
          if (!jobMap.has(block.schedule_id)) {
            jobMap.set(block.schedule_id, [])
          }
          jobMap.get(block.schedule_id)?.push(block)
        }

        // Convert to job summaries and fetch impact data for each
        const jobSummaries: JobSummary[] = await Promise.all(
          Array.from(jobMap.entries()).map(async ([schedule_id, blocks]) => {
            const timestamps = blocks.map(b => new Date(b.timestamp).getTime())
            const start_time = new Date(Math.min(...timestamps)).toISOString()
            const end_time = new Date(Math.max(...timestamps) + 5 * 60 * 1000).toISOString()
            
            const jobSummary: JobSummary = {
              schedule_id,
              scheduled_blocks: blocks,
              start_time,
              end_time,
            }

            // Fetch full schedule details to get impact data
            try {
              const scheduleResponse = await fetch(`/api/schedules/${schedule_id}`)
              if (scheduleResponse.ok) {
                const scheduleData = await scheduleResponse.json()
                if (scheduleData.impact) {
                  jobSummary.impact = scheduleData.impact
                }
                if (scheduleData.unoptimizedResult) {
                  jobSummary.unoptimizedResult = scheduleData.unoptimizedResult
                }
              }
            } catch (err) {
              console.error(`Failed to fetch impact for schedule ${schedule_id}:`, err)
              // Continue anyway, impact will just be undefined
            }

            return jobSummary
          })
        )

        // Sort by start time (most recent first)
        jobSummaries.sort((a, b) => {
          const timeA = a.start_time ? new Date(a.start_time).getTime() : 0
          const timeB = b.start_time ? new Date(b.start_time).getTime() : 0
          return timeB - timeA
        })

        setJobs(jobSummaries)
      } catch (error) {
        console.error("Error fetching previous jobs:", error)
        setJobs([])
      } finally {
        setLoading(false)
      }
    }

    fetchPreviousJobs()
  }, [])

  const formatDateTime = (isoString: string) => {
    return new Date(isoString).toLocaleString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    })
  }

  const getUniqueLocations = (blocks: ScheduleBlock[]) => {
    const locations = new Set(blocks.map(b => b.location))
    return Array.from(locations)
  }

  const getTotalLoad = (blocks: ScheduleBlock[]) => {
    return blocks.reduce((sum, b) => sum + b.additional_load, 0)
  }

  return (
    <Card className="border-2 shadow-lg">
      <CardHeader className="flex flex-row items-start justify-between">
        <div>
          <CardTitle className="flex items-center gap-2">
            <History className="h-5 w-5 text-primary" />
            Previous Jobs
          </CardTitle>
          <CardDescription>View and manage previously scheduled jobs</CardDescription>
        </div>
        <Button variant="ghost" size="icon" onClick={onClose}>
          <X className="h-4 w-4" />
        </Button>
      </CardHeader>

      <CardContent>
        {loading ? (
          <div className="flex items-center justify-center h-64">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          </div>
        ) : jobs.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-64 text-muted-foreground">
            <History className="h-12 w-12 mb-4 opacity-20" />
            <p className="text-lg font-medium">No previous jobs found</p>
            <p className="text-sm">Schedule a job to see it here</p>
          </div>
        ) : (
          <ScrollArea className="h-[500px] pr-4">
            <div className="space-y-3">
              {jobs.map((job) => (
                <Card
                  key={job.schedule_id}
                  className="cursor-pointer transition-all hover:border-primary hover:shadow-md"
                  onClick={() => onSelectJob(job)}
                >
                  <CardContent className="p-4">
                    <div className="space-y-3">
                      {/* Job ID Header */}
                      <div className="flex items-start justify-between">
                        <div>
                          <p className="font-mono text-sm font-medium">{job.schedule_id}</p>
                          <p className="text-xs text-muted-foreground mt-0.5">
                            {job.scheduled_blocks.length} blocks
                          </p>
                        </div>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="text-primary hover:text-primary h-8"
                          onClick={(e) => {
                            e.stopPropagation()
                            onSelectJob(job)
                          }}
                        >
                          View Details →
                        </Button>
                      </div>

                      {/* Job Details */}
                      <div className="grid grid-cols-2 gap-3 text-sm">
                        <div className="flex items-start gap-2">
                          <Calendar className="h-4 w-4 text-muted-foreground mt-0.5 shrink-0" />
                          <div className="min-w-0">
                            <p className="text-xs text-muted-foreground">Time Range</p>
                            <p className="text-xs font-medium truncate">
                              {job.start_time ? formatDateTime(job.start_time) : "N/A"}
                            </p>
                            <p className="text-xs text-muted-foreground truncate">
                              to {job.end_time ? new Date(job.end_time).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" }) : "N/A"}
                            </p>
                          </div>
                        </div>

                        <div className="flex items-start gap-2">
                          <MapPin className="h-4 w-4 text-muted-foreground mt-0.5 shrink-0" />
                          <div className="min-w-0">
                            <p className="text-xs text-muted-foreground">Locations</p>
                            <p className="text-xs font-medium">
                              {getUniqueLocations(job.scheduled_blocks).length} data centre(s)
                            </p>
                            <p className="text-xs text-muted-foreground truncate">
                              {getUniqueLocations(job.scheduled_blocks).join(", ")}
                            </p>
                          </div>
                        </div>
                      </div>

                        {/* Total Load */}
                        <div className="flex items-center flex-wrap gap-2 pt-2 border-t">
                          <Leaf className="h-4 w-4 text-primary" />
                          <span className="text-xs text-muted-foreground">Total Load:</span>
                          <span className="text-sm font-medium">{getTotalLoad(job.scheduled_blocks).toFixed(2)} kWh</span>
                          {job.impact?.total_emissions && (
                            <>
                              <span className="text-xs text-muted-foreground mx-1">•</span>
                              <span className="text-xs text-muted-foreground">Emissions:</span>
                              <span className="text-sm font-medium text-primary">
                                {job.impact.total_emissions.toFixed(2)} kg CO₂
                              </span>
                            </>
                          )}
                          {job.impact?.total_emissions && job.unoptimizedResult?.impact?.total_emissions && job.unoptimizedResult.impact.total_emissions > job.impact.total_emissions && (
                            <>
                              <span className="text-xs text-muted-foreground mx-1">•</span>
                              <span className="text-xs font-medium text-emerald-600 bg-emerald-500/10 px-1.5 py-0.5 rounded-sm">
                                {(((job.unoptimizedResult.impact.total_emissions - job.impact.total_emissions) / job.unoptimizedResult.impact.total_emissions) * 100).toFixed(1)}% savings
                              </span>
                            </>
                          )}
                        </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          </ScrollArea>
        )}
      </CardContent>
    </Card>
  )
}
