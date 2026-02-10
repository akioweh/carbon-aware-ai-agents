"use client"

import { useState, useEffect, useRef } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Leaf, ArrowLeft, Loader2, Trash2 } from "lucide-react"
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
  job_id: string
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
  // User's input time range
  earliestStart?: string
  latestFinish?: string
  onBack?: () => void
  onCancel?: () => void
}

const DATA_CENTERS = [
  { id: "dc1", name: "Data Centre 1", location: "us-west-1" },
  { id: "dc2", name: "Data Centre 2", location: "us-east-1" },
  { id: "dc3", name: "Data Centre 3", location: "eu-central-1" },
  { id: "dc4", name: "Data Centre 4", location: "ap-southeast-1" },
  { id: "dc5", name: "Data Centre 5", location: "sa-east-1" },
]

// Map location strings to DC IDs
function locationToDcId(location: string): string | undefined {
  const dc = DATA_CENTERS.find(d => d.location === location)
  return dc?.id
}

// At the top of ScheduleResult.tsx, outside the component
function convertBlocksToWorkload(blocks: any[], start: Date, end: Date, newJobId?: string) {
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
      .filter(b => b.job_id !== newJobId)
      .reduce((sum, b) => sum + (typeof b.additional_load === 'number' ? b.additional_load : 0), 0)

    const newJob = matching
      .filter(b => b.job_id === newJobId)
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

export function ScheduleResult({ result, earliestStart, latestFinish, onBack, onCancel }: ScheduleResultProps) {
  const [selectedDC, setSelectedDC] = useState(DATA_CENTERS[0].id)
  const [workloadData, setWorkloadData] = useState<WorkloadInterval[]>([])
  const [loading, setLoading] = useState(false)
  const [cancelling, setCancelling] = useState(false)
  const scrollContainerRef = useRef<HTMLDivElement>(null)

  // Get impact values (support both new and legacy format)
  const carbonIntensity = result.impact?.carbon_intensity ?? result.carbon_intensity
  const totalEmissions = result.impact?.total_emissions ?? result.estimated_emissions_kg
  const sci = result.impact?.sci ?? result.sci_per_unit

  // Calculate time range from user input or scheduled blocks
  const getTimeRange = () => {
    if (earliestStart && latestFinish) {
      return {
        start: new Date(earliestStart),
        end: new Date(latestFinish)
      }
    }
    
    if (result.scheduled_blocks && result.scheduled_blocks.length > 0) {
      const timestamps = result.scheduled_blocks.map(b => new Date(b.timestamp).getTime())
      return {
        start: new Date(Math.min(...timestamps)),
        end: new Date(Math.max(...timestamps) + 5 * 60 * 1000)
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

  // Update workload data when data center changes
  useEffect(() => {
  const loadWorkload = async () => {
    setLoading(true)

    const { start, end } = getTimeRange()

    try {
      // Align requested window to 5-minute boundaries so backend (which filters by block start)
      // returns the neighboring blocks even if the UI time range begins at an off-boundary.
      const intervalMs = 5 * 60 * 1000
      const fetchStart = floorToInterval(start, intervalMs)
      const fetchEnd = ceilToInterval(end, intervalMs)

      // Fetch all scheduled blocks in the time range (aligned to 5-min)
      const res = await fetch(
        `/api/schedule?start_time=${fetchStart.toISOString()}&end_time=${fetchEnd.toISOString()}`
      )

      if (!res.ok) {
        throw new Error(`Failed to fetch schedule: ${res.status}`)
      }

      const raw = await res.json()

      if (!Array.isArray(raw)) {
        throw new Error("Unexpected schedule response shape")
      }

      // Sanitize blocks (ensure required fields exist and are correct types)
      const blocks = raw.filter((b: any) => {
        return (
          b &&
          typeof b.timestamp === "string" &&
          typeof b.location === "string" &&
          typeof b.job_id === "string" &&
          typeof b.additional_load === "number"
        )
      })

      // Map server location -> dc id for filtering
      const dcBlocks = blocks.filter(
        (b: any) => locationToDcId(b.location) === selectedDC
      )

      // Determine new job id from result (prefer job_id then schedule_id)
      const newJobId = result.job_id ?? result.schedule_id

      // Convert blocks → workload intervals for your chart
      const intervals = convertBlocksToWorkload(dcBlocks, start, end, newJobId)

      setWorkloadData(intervals)
    } catch (err) {
      console.error("Failed to load workload", err)
      setWorkloadData([])
    } finally {
      setLoading(false)
    }
  }

  loadWorkload()
}, [selectedDC, result.scheduled_blocks, result.job_id, result.schedule_id, earliestStart, latestFinish])

  const handleCancel = async () => {
    setCancelling(true)
    try {
      const response = await fetch(`/api/schedule/${result.schedule_id}`, {
        method: "DELETE",
      })
      
      if (response.ok) {
        onCancel?.()
      } else {
        // For demo, still call onCancel
        onCancel?.()
      }
    } catch (error) {
      // For demo purposes, still proceed with cancel
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

  const maxValue = Math.max(...workloadData.map(d => d.existing + d.newJob), 100)
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
              <AlertDialogAction onClick={handleCancel} className="bg-destructive text-destructive-foreground hover:bg-destructive/90">
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

      {/* Data Center Workload View */}
      <Card>
        <CardHeader>
          <CardTitle>Data Centre Workload Distribution</CardTitle>
          <CardDescription>
            Showing workload from {formatDateTime(rangeStart.toISOString())} to {formatDateTime(rangeEnd.toISOString())} (5-minute intervals)
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
              {/* Y-axis labels (kWh) */}
              <div className="absolute left-0 top-0 bottom-8 w-12 flex flex-col justify-between text-xs text-muted-foreground pr-2">
                <span>{maxValue.toFixed(1)} kWh</span>
                <span>{(maxValue * 0.75).toFixed(1)} kWh</span>
                <span>{(maxValue * 0.5).toFixed(1)} kWh</span>
                <span>{(maxValue * 0.25).toFixed(1)} kWh</span>
                <span>0 kWh</span>
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
