"use client"

import { useState, useEffect } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { History, X, Loader2, Calendar, MapPin, Leaf } from "lucide-react"
import { ScrollArea } from "@/components/ui/scroll-area"
import { JobSummary, ScheduleBlock } from "../types/schedule"

interface PreviousJobsProps {
  onClose: () => void
  onSelectJob: (job: JobSummary) => void
}

function formatDatacenterId(id: string): string {
  const match = id.match(/Data-Center-(\d+)/i)
  if (!match) return id
  return `Data Center ${match[1]}`
}

export function PreviousJobs({ onClose, onSelectJob }: PreviousJobsProps) {
  const [jobs, setJobs] = useState<JobSummary[]>([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    const fetchPreviousJobs = async () => {
      setLoading(true)
      try {
        const summaryRes = await fetch("/api/schedules/summary")
        if (!summaryRes.ok) throw new Error(`Failed to fetch summaries: ${summaryRes.status}`)

        const rawSummaries = await summaryRes.json()
        if (!Array.isArray(rawSummaries)) throw new Error("Unexpected schedule summaries response shape")

        // Convert to job summaries using the new enriched fields from the backend
        const jobSummaries: JobSummary[] = rawSummaries.map((s: any) => {
          return {
            schedule_id: s.schedule_id,
            start_time: s.start_time,
            end_time: s.end_time,
            impact: s.impact,
            locations: s.locations || [],
            total_load: s.total_load || 0,
            block_count: s.block_count || 0,
            scheduled_blocks: [], // Empty for now, will be fetched when selected
            unoptimizedResult: s.trivialImpact ? {
              schedule_id: s.schedule_id,
              impact: s.trivialImpact
            } : undefined
          }
        })

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
                      {/* Compact Card Details */}
                      <div className="flex flex-row items-center justify-between gap-4">
                        <div className="flex items-center gap-4">
                          <div className="flex flex-col">
                            <p className="font-semibold text-base text-primary tracking-tight">{job.schedule_id}</p>
                            <p className="text-xs text-muted-foreground">
                              {(job as any).block_count || job.scheduled_blocks?.length || 0} block{((job as any).block_count || job.scheduled_blocks?.length || 0) !== 1 && 's'}
                            </p>
                          </div>
                          
                          <div className="hidden sm:flex h-8 w-px bg-border mx-2" />

                          <div className="flex flex-col gap-1 text-sm">
                            <div className="flex items-center gap-2 text-muted-foreground">
                              <Calendar className="h-3.5 w-3.5" />
                              <span className="text-xs font-medium text-foreground">
                                {job.start_time ? formatDateTime(job.start_time) : "N/A"} - {job.end_time ? new Date(job.end_time).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" }) : "N/A"}
                              </span>
                            </div>
                            <div className="flex items-center gap-2 text-muted-foreground">
                              <MapPin className="h-3.5 w-3.5" />
                              <span className="text-xs">
                                {((job as any).locations?.length) || getUniqueLocations(job.scheduled_blocks).length} data centre(s) ({((job as any).locations || getUniqueLocations(job.scheduled_blocks)).map((location: string) => formatDatacenterId(location)).join(", ")})
                              </span>
                            </div>
                          </div>
                        </div>

                        <Button
                          variant="ghost"
                          size="sm"
                          className="shrink-0 h-8"
                          onClick={(e) => {
                            e.stopPropagation()
                            onSelectJob(job)
                          }}
                        >
                          View Details &rarr;
                        </Button>
                      </div>

                      {/* Total Load and Impacts */}
                      <div className="flex items-center flex-wrap gap-x-4 gap-y-2 pt-3 mt-1 border-t border-border/50">
                        <div className="flex items-center gap-1.5">
                          <Leaf className="h-3.5 w-3.5 text-emerald-500" />
                          <span className="text-xs font-medium">{((job as any).total_load || getTotalLoad(job.scheduled_blocks)).toFixed(2)} kWh</span>
                        </div>
                        
                        {job.impact?.total_emissions && (
                          <div className="flex items-center gap-1.5">
                            <span className="text-xs text-muted-foreground">Emissions:</span>
                            <span className="text-xs font-semibold">{job.impact.total_emissions.toFixed(2)} kg CO₂</span>
                          </div>
                        )}
                        
                        {job.impact?.total_emissions && job.unoptimizedResult?.impact?.total_emissions && job.unoptimizedResult.impact.total_emissions > job.impact.total_emissions && (
                          <div className="flex items-center">
                            <span className="text-[10px] font-bold text-emerald-700 bg-emerald-100/80 px-2 py-0.5 rounded-full">
                              -{(((job.unoptimizedResult.impact.total_emissions - job.impact.total_emissions) / job.unoptimizedResult.impact.total_emissions) * 100).toFixed(1)}% savings
                            </span>
                          </div>
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
