"use client"

import { useState, useEffect, useRef } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Leaf, ArrowLeft, Loader2, Trash2, TrendingDown, ArrowRight } from "lucide-react"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog"

interface ScheduleBlock {
  timestamp: string
  location: string
  schedule_id: string
  additional_load: number
}

interface WorkloadInterval {
  time: string
  existing: number
  newJob: number
}

interface ScheduleResultProps {
  result: {
    schedule_id: string
    scheduled_blocks?: ScheduleBlock[]
    impact?: {
      carbon_intensity?: number
      total_emissions?: number
      sci?: number
    }
    // Legacy fields for backwards compatibility
    job_id?: string
    location?: string
    start_time?: string
    end_time?: string
    carbon_intensity?: number
    estimated_emissions_kg?: number
    sci_per_unit?: number
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
  // User's input time range
  earliestStart?: string
  latestFinish?: string
  onBack?: () => void
  onCancel?: () => void
}

const DATA_CENTERS = [
  { id: "dc1", name: "Data Centre 1", backendLocation: "Data-Center-1" },
  { id: "dc2", name: "Data Centre 2", backendLocation: "Data-Center-2" },
  { id: "dc3", name: "Data Centre 3", backendLocation: "Data-Center-3" },
  { id: "dc4", name: "Data Centre 4", backendLocation: "Data-Center-4" },
  { id: "dc5", name: "Data Centre 5", backendLocation: "Data-Center-5" },
]

// Map location strings to DC IDs
function locationToDcId(location: string): string | undefined {
  const dc = DATA_CENTERS.find(d => d.backendLocation === location)
  return dc?.id
}

// At the top of ScheduleResult.tsx, outside the component
function convertBlocksToWorkload(blocks: any[], start: Date, end: Date, newScheduleId?: string) {
  const intervalMs = 5 * 60 * 1000
  const intervals: WorkloadInterval[] = []

  for (let t = start.getTime(); t <= end.getTime(); t += intervalMs) {
    const timestamp = new Date(t)
    const intervalStart = t
    const intervalEnd = t + intervalMs

    // Consider a block part of this interval if it overlaps the interval window
    const matching = blocks.filter(b => {
      if (!b || !b.timestamp) return false
      const blockStart = new Date(b.timestamp).getTime()
      const blockEnd = blockStart + intervalMs
      return blockStart < intervalEnd && blockEnd > intervalStart
    })

    const existing = matching
      .filter(b => b.schedule_id !== newScheduleId)
      .reduce((sum, b) => sum + (typeof b.additional_load === 'number' ? b.additional_load : 0), 0)

    const newJob = matching
      .filter(b => b.schedule_id === newScheduleId)
      .reduce((sum, b) => sum + (typeof b.additional_load === 'number' ? b.additional_load : 0), 0)

    intervals.push({ 
      time: timestamp.toISOString(), 
      existing, 
      newJob 
    })
  }

  return intervals
}

// Align a Date to interval boundaries (ms)
function floorToInterval(d: Date, ms: number) {
  return new Date(Math.floor(d.getTime() / ms) * ms)
}

function ceilToInterval(d: Date, ms: number) {
  return new Date(Math.ceil(d.getTime() / ms) * ms)
}

export function ScheduleResult({ result, unoptimizedResult, earliestStart, latestFinish, onBack, onCancel }: ScheduleResultProps) {
  const [selectedDC, setSelectedDC] = useState(DATA_CENTERS[0].id)
  const [workloadData, setWorkloadData] = useState<WorkloadInterval[]>([])
  const [loading, setLoading] = useState(false)
  const [cancelling, setCancelling] = useState(false)
  const [allBlocks, setAllBlocks] = useState<any[]>([])
  const scrollContainerRef = useRef<HTMLDivElement>(null)

  // Get impact values (support both new and legacy format)
  const carbonIntensity = result.impact?.carbon_intensity ?? result.carbon_intensity
  const totalEmissions = result.impact?.total_emissions ?? result.estimated_emissions_kg
  const sci = result.impact?.sci ?? result.sci_per_unit

  // Get unoptimized comparison values
  const unoptimizedComparison = {
    carbon_intensity: unoptimizedResult?.impact?.carbon_intensity,
    total_emissions: unoptimizedResult?.impact?.total_emissions,
    sci: unoptimizedResult?.impact?.sci,
  }

  // Calculate time range from scheduled blocks of THIS job only
  const getTimeRange = () => {
    // Use only the new job's scheduled blocks for time range
    if (result.scheduled_blocks && result.scheduled_blocks.length > 0) {
      const timestamps = result.scheduled_blocks.map(b => new Date(b.timestamp).getTime())
      return {
        start: new Date(Math.min(...timestamps)),
        end: new Date(Math.max(...timestamps) + 5 * 60 * 1000)
      }
    }
    
    // Fallback to user input
    if (earliestStart && latestFinish) {
      return {
        start: new Date(earliestStart),
        end: new Date(latestFinish)
      }
    }
    
    // Fallback to legacy fields or default
    if (result.start_time && result.end_time) {
      return {
        start: new Date(result.start_time),
        end: new Date(result.end_time)
      }
    }
    
    // Default to 4 hour window
    const now = new Date()
    now.setHours(8, 0, 0, 0)
    return {
      start: now,
      end: new Date(now.getTime() + 4 * 60 * 60 * 1000)
    }
  }

  // Fetch: (1) the new job's blocks, (2) all existing blocks, then combine
  useEffect(() => {
    const loadBlocks = async () => {
      setLoading(true)
      try {
        // Fetch the specific schedule's blocks (the new job)
        const scheduleRes = await fetch(`/api/schedules/${result.schedule_id}`)
        if (!scheduleRes.ok) {
          throw new Error(`Failed to fetch schedule: ${scheduleRes.status}`)
        }
        const scheduleData = await scheduleRes.json()
        const newJobBlocks = Array.isArray(scheduleData.scheduled_blocks) 
          ? scheduleData.scheduled_blocks 
          : []

        // Fetch all blocks to get existing workload
        const allRes = await fetch(`/api/schedules`)
        if (!allRes.ok) {
          throw new Error(`Failed to fetch all schedules: ${allRes.status}`)
        }
        const allData = await allRes.json()
        const allBlocks = Array.isArray(allData) ? allData : []

        // Combine: mark new job blocks and include all blocks
        const combined = allBlocks.map((b: any) => ({
          ...b,
          // If this block is from the new job (by schedule_id), mark it
          // Note: new job blocks will have schedule_id = result.schedule_id
        }))

        // Add new job blocks if not already included
        const combinedWithNewJob = [...combined]
        for (const block of newJobBlocks) {
          if (!combinedWithNewJob.find((b: any) => 
            b.timestamp === block.timestamp && 
            b.schedule_id === block.schedule_id
          )) {
            combinedWithNewJob.push(block)
          }
        }

        setAllBlocks(combinedWithNewJob)
      } catch (err) {
        console.error("Failed to load blocks", err)
        setAllBlocks([])
      } finally {
        setLoading(false)
      }
    }

    loadBlocks()
  }, [result.schedule_id])

  // Update workload data when data center changes (uses cached allBlocks)
  useEffect(() => {
    const { start, end } = getTimeRange()

    // Filter blocks by selected DC using backend location name
    const dcBlocks = allBlocks.filter(
      (b: any) => locationToDcId(b.location) === selectedDC
    )

    // Use schedule_id to identify new job blocks
    const newJobScheduleId = result.schedule_id

    // Convert blocks → workload intervals for chart
    const intervals = convertBlocksToWorkload(dcBlocks, start, end, newJobScheduleId)

    setWorkloadData(intervals)
  }, [selectedDC, allBlocks, result.schedule_id])

  const handleCancel = async () => {
    setCancelling(true)
    try {
      const response = await fetch(`/api/schedules/${result.schedule_id}`, {
        method: "DELETE",
      })
      
      if (response.ok) {
        onCancel?.()
      } else {
        onCancel?.()
      }
    } catch (error) {
      onCancel?.()
    } finally {
      setCancelling(false)
    }
  }

  const formatTime = (isoString: string) => {
    return new Date(isoString).toLocaleTimeString("en-US", {
      hour: "2-digit",
      minute: "2-digit",
    })
  }
  
  const formatDateTime = (isoString: string) => {
    return new Date(isoString).toLocaleString("en-US", {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    })
  }

  // Fixed Y-axis: all data centers have capacity of 50
  const maxValue = 50
  const { start: rangeStart, end: rangeEnd } = getTimeRange()

  return (
    <div className="space-y-6">
      {/* Header with Back and Cancel buttons */}
      <div className="flex items-center justify-between">
        {onBack && (
          <Button variant="ghost" onClick={onBack} className="gap-2">
            <ArrowLeft className="h-4 w-4" />
            Schedule Another Job
          </Button>
        )}
        
        <AlertDialog>
          <AlertDialogTrigger asChild>
            <Button variant="destructive" className="gap-2" disabled={cancelling}>
              {cancelling ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Trash2 className="h-4 w-4" />
              )}
              Cancel Job
            </Button>
          </AlertDialogTrigger>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Cancel Scheduled Job?</AlertDialogTitle>
              <AlertDialogDescription>
                This will remove the job (ID: {result.schedule_id}) from the schedule. 
                This action cannot be undone.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Keep Job</AlertDialogCancel>
              <AlertDialogAction onClick={handleCancel} className="bg-destructive text-white hover:bg-destructive/90">
                Cancel Job
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </div>

      {/* Environmental Impact - Now at Top */}
      {(carbonIntensity !== undefined || totalEmissions !== undefined || sci !== undefined) && (
        <Card className="border-2 border-primary/20 bg-primary/5">
          <CardHeader className="pb-4">
            <div className="flex items-center gap-2">
              <Leaf className="h-5 w-5 text-primary" />
              <CardTitle>Environmental Impact</CardTitle>
            </div>
            <CardDescription>Estimated carbon footprint for this scheduled job</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid gap-4 sm:grid-cols-3">
              {carbonIntensity !== undefined && (
                <div className="rounded-lg bg-background p-4 space-y-1">
                  <p className="text-xs text-muted-foreground">Carbon Intensity</p>
                  <p className="text-3xl font-bold text-primary">{carbonIntensity.toFixed(3)}</p>
                  <p className="text-xs text-muted-foreground">kg CO2/kWh</p>
                </div>
              )}

              {totalEmissions !== undefined && (
                <div className="rounded-lg bg-background p-4 space-y-1">
                  <p className="text-xs text-muted-foreground">Total Emissions</p>
                  <p className="text-3xl font-bold text-primary">{totalEmissions.toFixed(2)}</p>
                  <p className="text-xs text-muted-foreground">kg CO2</p>
                </div>
              )}

              {sci !== undefined && (
                <div className="rounded-lg bg-background p-4 space-y-1">
                  <p className="text-xs text-muted-foreground">SCI per Unit</p>
                  <p className="text-3xl font-bold text-primary">{sci.toFixed(2)}</p>
                  <p className="text-xs text-muted-foreground">kg CO2e/unit</p>
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Impact Comparison Card */}
      {unoptimizedResult && (
        <Card className="border-2 border-orange-200 bg-orange-50/50">
          <CardHeader className="pb-4">
            <div className="flex items-center gap-2">
              <TrendingDown className="h-5 w-5 text-orange-600" />
              <CardTitle>Impact Comparison</CardTitle>
            </div>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {/* Carbon Intensity Comparison */}
              {carbonIntensity !== undefined && unoptimizedComparison.carbon_intensity !== undefined && (
                <div className="rounded-lg border bg-background p-4">
                  <p className="text-sm font-medium mb-3">Carbon Intensity</p>
                  <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-3">
                    <div className="text-center">
                      <p className="text-xs text-muted-foreground mb-1">Unoptimised</p>
                      <p className="text-2xl font-bold text-orange-600">{unoptimizedComparison.carbon_intensity.toFixed(3)}</p>
                      <p className="text-xs text-muted-foreground mt-1">kg CO2/kWh</p>
                    </div>
                    <ArrowRight className="h-5 w-5 text-muted-foreground flex-shrink-0" />
                    <div className="text-center">
                      <p className="text-xs text-muted-foreground mb-1">Optimised</p>
                      <p className="text-2xl font-bold text-primary">{carbonIntensity.toFixed(3)}</p>
                      <p className="text-xs text-muted-foreground mt-1">kg CO2/kWh</p>
                    </div>
                  </div>
                  {unoptimizedComparison.carbon_intensity > 0 && (
                    <div className="mt-3 text-center">
                      <p className="text-sm font-medium text-emerald-600">
                        {(((unoptimizedComparison.carbon_intensity - carbonIntensity) / unoptimizedComparison.carbon_intensity) * 100).toFixed(1)}% reduction
                      </p>
                    </div>
                  )}
                </div>
              )}

              {/* Total Emissions Comparison */}
              {totalEmissions !== undefined && unoptimizedComparison.total_emissions !== undefined && (
                <div className="rounded-lg border bg-background p-4">
                  <p className="text-sm font-medium mb-3">Total Emissions</p>
                  <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-3">
                    <div className="text-center">
                      <p className="text-xs text-muted-foreground mb-1">Unoptimised</p>
                      <p className="text-2xl font-bold text-orange-600">{unoptimizedComparison.total_emissions.toFixed(2)}</p>
                      <p className="text-xs text-muted-foreground mt-1">kg CO2</p>
                    </div>
                    <ArrowRight className="h-5 w-5 text-muted-foreground flex-shrink-0" />
                    <div className="text-center">
                      <p className="text-xs text-muted-foreground mb-1">Optimised</p>
                      <p className="text-2xl font-bold text-primary">{totalEmissions.toFixed(2)}</p>
                      <p className="text-xs text-muted-foreground mt-1">kg CO2</p>
                    </div>
                  </div>
                  {unoptimizedComparison.total_emissions > 0 && (
                    <div className="mt-3 text-center">
                      <p className="text-sm font-medium text-emerald-600">
                        {(((unoptimizedComparison.total_emissions - totalEmissions) / unoptimizedComparison.total_emissions) * 100).toFixed(1)}% reduction
                      </p>
                    </div>
                  )}
                </div>
              )}

              {/* SCI Comparison */}
              {sci !== undefined && unoptimizedComparison.sci !== undefined && (
                <div className="rounded-lg border bg-background p-4">
                  <p className="text-sm font-medium mb-3">SCI per Unit</p>
                  <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-3">
                    <div className="text-center">
                      <p className="text-xs text-muted-foreground mb-1">Unoptimised</p>
                      <p className="text-2xl font-bold text-orange-600">{unoptimizedComparison.sci.toFixed(2)}</p>
                      <p className="text-xs text-muted-foreground mt-1">kg CO2e/unit</p>
                    </div>
                    <ArrowRight className="h-5 w-5 text-muted-foreground flex-shrink-0" />
                    <div className="text-center">
                      <p className="text-xs text-muted-foreground mb-1">Optimised</p>
                      <p className="text-2xl font-bold text-primary">{sci.toFixed(2)}</p>
                      <p className="text-xs text-muted-foreground mt-1">kg CO2e/unit</p>
                    </div>
                  </div>
                  {unoptimizedComparison.sci > 0 && (
                    <div className="mt-3 text-center">
                      <p className="text-sm font-medium text-emerald-600">
                        {(((unoptimizedComparison.sci - sci) / unoptimizedComparison.sci) * 100).toFixed(1)}% reduction
                      </p>
                    </div>
                  )}
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Data Center Workload View */}
      <Card>
        <CardHeader>
          <CardTitle>Data Centre Workload Distribution</CardTitle>
          <CardDescription>
            Showing workload from {formatDateTime(rangeStart.toISOString())} to {formatDateTime(rangeEnd.toISOString())}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Data Center Tabs */}
          <Tabs value={selectedDC} onValueChange={setSelectedDC}>
            <TabsList className="grid w-full grid-cols-5">
              {DATA_CENTERS.map((dc) => (
                <TabsTrigger 
                  key={dc.id} 
                  value={dc.id}
                  className="text-xs sm:text-sm"
                >
                  DC {dc.id.slice(-1)}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>

          {/* Legend */}
          <div className="flex items-center gap-6 text-sm">
            <div className="flex items-center gap-2">
              <div className="h-3 w-3 rounded bg-gray-400" />
              <span className="text-muted-foreground">Existing Workload</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="h-3 w-3 rounded bg-emerald-500" />
              <span className="text-muted-foreground">New Job</span>
            </div>
          </div>

          {/* Bar Chart */}
          {loading ? (
            <div className="flex items-center justify-center h-64">
              <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
          ) : (
            <div className="relative">
              {/* Y-axis labels (fixed 0-50) */}
              <div className="absolute left-0 top-0 bottom-8 w-12 flex flex-col justify-between text-xs text-muted-foreground pr-2">
                <span>50</span>
                <span>37.5</span>
                <span>25</span>
                <span>12.5</span>
                <span>0</span>
              </div>
              
              {/* Scrollable Chart Area */}
              <div 
                ref={scrollContainerRef}
                className="ml-12 overflow-x-auto pb-8"
              >
                <div 
                  className="flex items-end gap-1 min-w-max"
                  style={{ width: `${Math.max(workloadData.length * 12, 400)}px`, height: "192px" }}
                >
                  {workloadData.map((interval, index) => {
                    const chartHeight = 192
                    const existingPx = (interval.existing / maxValue) * chartHeight
                    const newJobPx = (interval.newJob / maxValue) * chartHeight
                    
                    return (
                      <div 
                        key={index} 
                        className="flex flex-col items-center group relative"
                        style={{ width: "8px", height: `${chartHeight}px` }}
                      >
                        {/* Tooltip */}
                        <div className="absolute bottom-full mb-2 hidden group-hover:block z-10">
                          <div className="bg-popover text-popover-foreground text-xs rounded-md px-2 py-1 shadow-md whitespace-nowrap border">
                            <p className="font-medium">{formatTime(interval.time)}</p>
                            <p className="text-muted-foreground">Existing: {interval.existing} kWh</p>
                            {interval.newJob > 0 && <p className="text-emerald-500">New Job: {interval.newJob} kWh</p>}
                          </div>
                        </div>
                        
                        {/* Stacked Bar - positioned from bottom */}
                        <div className="absolute bottom-0 w-full flex flex-col-reverse">
                          {/* Existing workload (bottom) */}
                          <div 
                            className="w-full bg-gray-400 rounded-t-sm"
                            style={{ height: `${existingPx}px` }}
                          />
                          {/* New job (top) */}
                          {interval.newJob > 0 && (
                            <div 
                              className="w-full bg-emerald-500 rounded-t-sm"
                              style={{ height: `${newJobPx}px` }}
                            />
                          )}
                        </div>
                        
                        {/* X-axis label (show every 6th = 30 min) */}
                        {index % 6 === 0 && (
                          <span className="absolute -bottom-6 text-[10px] text-muted-foreground whitespace-nowrap">
                            {formatTime(interval.time)}
                          </span>
                        )}
                      </div>
                    )
                  })}
                </div>
              </div>
            </div>
          )}

          <p className="text-xs text-muted-foreground text-center">
            Scroll horizontally to view all time intervals
          </p>
        </CardContent>
      </Card>

      {/* Schedule Info Footer */}
      <div className="flex flex-wrap items-center justify-between gap-4 text-sm text-muted-foreground px-1">
        <div>
          <span className="text-foreground font-medium">Schedule ID:</span>{" "}
          <span className="font-mono">{result.schedule_id}</span>
        </div>
        {result.job_id && (
          <div>
            <span className="text-foreground font-medium">Job ID:</span>{" "}
            <span className="font-mono">{result.job_id}</span>
          </div>
        )}
      </div>
    </div>
  )
}
