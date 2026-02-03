"use client"

import { useState, useEffect, useRef } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Calendar } from "@/components/ui/calendar"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { CalendarIcon, X, Loader2 } from "lucide-react"
import { format } from "date-fns"

interface ScheduleBlock {
  timestamp: string
  location: string
  job_id: string
  additional_load: number
}

interface WorkloadInterval {
  time: string
  existing: number
  jobs: { job_id: string; load: number }[]
}

interface WorkloadCalendarProps {
  onClose: () => void
}

const DATA_CENTERS = [
  { id: "dc1", name: "Data Centre 1", location: "us-west-1" },
  { id: "dc2", name: "Data Centre 2", location: "us-east-1" },
  { id: "dc3", name: "Data Centre 3", location: "eu-central-1" },
  { id: "dc4", name: "Data Centre 4", location: "ap-southeast-1" },
  { id: "dc5", name: "Data Centre 5", location: "sa-east-1" },
]

// Mock data generator removed — component now relies solely on the `/api/schedule` endpoint for schedule blocks
// (If you later want a local fallback for offline dev, we can add an explicit mock path or feature flag.)

export function WorkloadCalendar({ onClose }: WorkloadCalendarProps) {
  const [selectedDate, setSelectedDate] = useState<Date>(new Date())
  const [selectedDC, setSelectedDC] = useState(DATA_CENTERS[0].id)
  const [workloadData, setWorkloadData] = useState<WorkloadInterval[]>([])
  const [loading, setLoading] = useState(false)
  const [calendarOpen, setCalendarOpen] = useState(false)
  const scrollContainerRef = useRef<HTMLDivElement>(null)

  // Fetch workload data when date or data center changes
  useEffect(() => {
    const fetchData = async () => {
      setLoading(true)
      
      try {
        const startTime = new Date(selectedDate)
        startTime.setHours(0, 0, 0, 0)
        const endTime = new Date(selectedDate)
        endTime.setHours(23, 59, 59, 999)
        
        const response = await fetch(
          `/api/schedule?start_time=${startTime.toISOString()}&end_time=${endTime.toISOString()}`
        )
        
        if (!response.ok) {
          console.error("[v0] API call failed:", response.status, await response.text())
          setWorkloadData([])
          return
        }

        const blocks = await response.json()

        if (!Array.isArray(blocks)) {
          console.error("[v0] Unexpected schedule response shape:", blocks)
          setWorkloadData([])
          return
        }

        console.log("[v0] Fetched schedule blocks:", blocks)
        
        // Process blocks into intervals with real data
        const intervals = processScheduleBlocks(selectedDate, selectedDC, blocks)
        setWorkloadData(intervals)
      } catch (error) {
        console.log("[v0] Error fetching schedule:", error)
        setWorkloadData([])
      } finally {
        setLoading(false)
      }
    }
    
    fetchData()
  }, [selectedDate, selectedDC])

  // Process schedule blocks into interval data structure using real API schedule blocks
  function processScheduleBlocks(
    date: Date,
    dcId: string,
    blocks: ScheduleBlock[]
  ): WorkloadInterval[] {
    const intervals: WorkloadInterval[] = []
    const dcIndex = parseInt(dcId.slice(-1)) - 1
    const dcLocation = DATA_CENTERS[dcIndex]?.location

    if (!dcLocation) {
      console.warn("Unknown data centre id:", dcId)
      return intervals
    }

    // Create intervals for the entire day (288 x 5-minute intervals)
    const totalIntervals = 288
    const intervalMs = 5 * 60 * 1000

    for (let i = 0; i < totalIntervals; i++) {
      const currentTime = new Date(date)
      currentTime.setHours(0, 0, 0, 0)
      currentTime.setMinutes(i * 5)

      const currentTimeEnd = new Date(currentTime.getTime() + intervalMs)

      const activeJobs: { job_id: string; load: number }[] = []

      for (const block of blocks) {
        // Basic validation to avoid runtime errors
        if (!block || !block.timestamp || !block.location || typeof block.additional_load !== "number" || !block.job_id) continue

        // Only consider blocks for this datacenter
        if (block.location !== dcLocation) continue

        const blockTime = new Date(block.timestamp)
        const blockEndTime = new Date(blockTime.getTime() + intervalMs)

        // If block overlaps the interval, accumulate its additional_load for that job
        if (blockTime < currentTimeEnd && blockEndTime > currentTime) {
          const existingJob = activeJobs.find(j => j.job_id === block.job_id)
          if (existingJob) {
            existingJob.load += block.additional_load
          } else {
            activeJobs.push({ job_id: block.job_id, load: block.additional_load })
          }
        }
      }

      intervals.push({
        time: currentTime.toISOString(),
        existing: 0, // baseline 'existing' not provided by API; treat as 0 kWh
        jobs: activeJobs,
      })
    }

    return intervals
  }

  const formatTime = (isoString: string) => {
    return new Date(isoString).toLocaleTimeString("en-US", {
      hour: "2-digit",
      minute: "2-digit",
    })
  }

  const maxValue = Math.max(
    ...workloadData.map(d => d.existing + d.jobs.reduce((sum, j) => sum + j.load, 0)),
    1
  )

  return (
    <Card className="border-2 shadow-lg">
      <CardHeader className="flex flex-row items-start justify-between">
        <div>
          <CardTitle className="flex items-center gap-2">
            <CalendarIcon className="h-5 w-5 text-primary" />
            Workload Calendar
          </CardTitle>
          <CardDescription>View existing workloads and scheduled jobs across data centres</CardDescription>
        </div>
        <Button variant="ghost" size="icon" onClick={onClose}>
          <X className="h-4 w-4" />
        </Button>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Date Picker */}
        <div className="flex items-center gap-4">
          <Popover open={calendarOpen} onOpenChange={setCalendarOpen}>
            <PopoverTrigger asChild>
              <Button variant="outline" className="w-[240px] justify-start text-left font-normal bg-transparent">
                <CalendarIcon className="mr-2 h-4 w-4" />
                {format(selectedDate, "PPP")}
              </Button>
            </PopoverTrigger>
            <PopoverContent className="w-auto p-0" align="start">
              <Calendar
                mode="single"
                selected={selectedDate}
                onSelect={(date) => {
                  if (date) {
                    setSelectedDate(date)
                    setCalendarOpen(false)
                  }
                }}
                initialFocus
              />
            </PopoverContent>
          </Popover>
        </div>

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
            <div className="h-3 w-3 rounded bg-blue-500" />
            <span className="text-muted-foreground">Scheduled Jobs (kWh)</span>
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
                className="flex items-end gap-[2px] min-w-max"
                style={{ width: `${workloadData.length * 6}px`, height: "192px" }}
              >
                {workloadData.map((interval, index) => {
                  const chartHeight = 192
                  const existingPx = (interval.existing / maxValue) * chartHeight
                  const jobsLoad = interval.jobs.reduce((sum, j) => sum + j.load, 0)
                  const jobsPx = (jobsLoad / maxValue) * chartHeight
                  
                  return (
                    <div 
                      key={index} 
                      className="flex flex-col items-center group relative"
                      style={{ width: "4px", height: `${chartHeight}px` }}
                    >
                      {/* Tooltip */}
                      <div className="absolute bottom-full mb-2 hidden group-hover:block z-10">
                        <div className="bg-popover text-popover-foreground text-xs rounded-md px-2 py-1 shadow-md whitespace-nowrap border">
                          <p className="font-medium">{formatTime(interval.time)}</p>
                          {interval.jobs.length > 0 ? (
                            <div>
                              <p className="text-muted-foreground">Total scheduled: {interval.jobs.reduce((s, j) => s + j.load, 0)} kWh</p>
                              <div className="border-t mt-1 pt-1">
                                {interval.jobs.map((job, i) => (
                                  <p key={i} className="text-blue-500">{job.job_id}: {job.load} kWh</p>
                                ))}
                              </div>
                            </div>
                          ) : (
                            <p className="text-muted-foreground">No scheduled load</p>
                          )}
                        </div>
                      </div>
                      {/* Stacked Bar - positioned from bottom */}
                      <div className="absolute bottom-0 w-full flex flex-col-reverse">
                        {/* Base load (bottom) */}
                        <div 
                          className="w-full bg-gray-400"
                          style={{ height: `${existingPx}px` }}
                        />
                        {/* Scheduled jobs (top) */}
                        {jobsPx > 0 && (
                          <div 
                            className="w-full bg-blue-500"
                            style={{ height: `${jobsPx}px` }}
                          />
                        )}
                      </div>
                      
                      {/* X-axis label (show every hour = 12 intervals) */}
                      {index % 12 === 0 && (
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
          Scroll horizontally to view the full day (5-minute intervals)
        </p>
      </CardContent>
    </Card>
  )
}
