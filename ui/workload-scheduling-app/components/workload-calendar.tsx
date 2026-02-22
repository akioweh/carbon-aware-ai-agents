"use client"

import { useState, useEffect, useRef, useMemo } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { CalendarIcon, X, Loader2 } from "lucide-react"

interface ScheduleBlock {
  timestamp: string
  location: string
  job_id: string
  additional_load: number
}

interface AggregatedInterval {
  time: Date
  endTime: Date
  jobs: { job_id: string; load: number }[]
}

interface WorkloadCalendarProps {
  onClose: () => void
  scheduleId?: string
}

const DATA_CENTERS = [
  { id: "dc1", name: "Data Centre 1", location: "us-west-1" },
  { id: "dc2", name: "Data Centre 2", location: "us-east-1" },
  { id: "dc3", name: "Data Centre 3", location: "eu-central-1" },
  { id: "dc4", name: "Data Centre 4", location: "ap-southeast-1" },
  { id: "dc5", name: "Data Centre 5", location: "sa-east-1" },
]

const BLOCK_DURATION_MS = 5 * 60 * 1000

// Choose interval aggregation and bar width based on total time span
function getDisplayParams(spanMs: number) {
  const spanDays = spanMs / (1000 * 60 * 60 * 24)

  const tiers = [
    { maxDays: 1.5,      intervalMin: 5,   barWidth: 4 },
    { maxDays: 3,        intervalMin: 5,   barWidth: 3 },
    { maxDays: 7,        intervalMin: 15,  barWidth: 3 },
    { maxDays: 14,       intervalMin: 30,  barWidth: 3 },
    { maxDays: 30,       intervalMin: 60,  barWidth: 3 },
    { maxDays: 60,       intervalMin: 120, barWidth: 2 },
    { maxDays: Infinity, intervalMin: 360, barWidth: 2 },
  ]

  const tier = tiers.find(t => spanDays <= t.maxDays) || tiers[tiers.length - 1]

  return {
    intervalMs: tier.intervalMin * 60 * 1000,
    barWidth: tier.barWidth,
    gap: 1,
  }
}

export function WorkloadCalendar({ onClose, scheduleId }: WorkloadCalendarProps) {
  const [selectedDC, setSelectedDC] = useState(DATA_CENTERS[0].id)
  const [blocks, setBlocks] = useState<ScheduleBlock[]>([])
  const [loading, setLoading] = useState(false)
  const scrollContainerRef = useRef<HTMLDivElement>(null)

  // Fetch all blocks across all data centers once on mount
  useEffect(() => {
    const fetchData = async () => {
      setLoading(true)
      try {
        // Fetch all schedules across all datacenters (no schedule_id or datacenter filter)
        const response = await fetch(`/api/schedules`)
        if (!response.ok) {
          console.error(`Failed to fetch schedules: ${response.status}`)
          setBlocks([])
          return
        }
        const data = await response.json()
        // Response should be an array of ScheduleBlock objects
        if (Array.isArray(data)) {
          setBlocks(data)
        } else {
          console.error("Unexpected response format from /api/schedule")
          setBlocks([])
        }
      } catch (err) {
        console.error("Error fetching schedules:", err)
        setBlocks([])
      } finally {
        setLoading(false)
      }
    }
    fetchData()
  }, [])

  // Derive time range, display params, and aggregated intervals
  const { intervals, rangeStart, rangeEnd, displayParams } = useMemo(() => {
    if (blocks.length === 0) {
      return {
        intervals: [] as AggregatedInterval[],
        rangeStart: new Date(),
        rangeEnd: new Date(),
        displayParams: getDisplayParams(0),
      }
    }

    // Time range from ALL blocks (consistent across DC tabs)
    const allTimestamps = blocks.map(b => new Date(b.timestamp).getTime())
    const minTime = Math.min(...allTimestamps)
    const maxTime = Math.max(...allTimestamps) + BLOCK_DURATION_MS

    // Pad to hour boundaries for a clean axis
    const rangeStart = new Date(minTime)
    rangeStart.setMinutes(0, 0, 0)
    const rangeEnd = new Date(maxTime)
    if (rangeEnd.getMinutes() > 0 || rangeEnd.getSeconds() > 0) {
      rangeEnd.setMinutes(0, 0, 0)
      rangeEnd.setHours(rangeEnd.getHours() + 1)
    }

    const spanMs = rangeEnd.getTime() - rangeStart.getTime()
    const dp = getDisplayParams(spanMs)

    // Filter blocks for the selected DC
    const dcLocation = DATA_CENTERS.find(dc => dc.id === selectedDC)?.location
    const dcBlocks = dcLocation ? blocks.filter(b => b.location === dcLocation) : []

    // Build aggregated intervals
    const intervals: AggregatedInterval[] = []
    for (let t = rangeStart.getTime(); t < rangeEnd.getTime(); t += dp.intervalMs) {
      const intervalEnd = t + dp.intervalMs
      const activeJobs: { job_id: string; load: number }[] = []

      for (const block of dcBlocks) {
        if (!block.timestamp || typeof block.additional_load !== "number") continue
        const blockStart = new Date(block.timestamp).getTime()
        const blockEnd = blockStart + BLOCK_DURATION_MS
        if (blockStart < intervalEnd && blockEnd > t) {
          const existing = activeJobs.find(j => j.job_id === block.job_id)
          if (existing) {
            existing.load += block.additional_load
          } else {
            activeJobs.push({ job_id: block.job_id, load: block.additional_load })
          }
        }
      }

      intervals.push({
        time: new Date(t),
        endTime: new Date(intervalEnd),
        jobs: activeJobs,
      })
    }

    return { intervals, rangeStart, rangeEnd, displayParams: dp }
  }, [blocks, selectedDC])

  const maxValue = Math.max(
    ...intervals.map(d => d.jobs.reduce((sum, j) => sum + j.load, 0)),
    1,
  )

  // Day boundary markers
  const dayBoundaries = useMemo(() => {
    const boundaries: { index: number; date: Date }[] = []
    let lastDateStr = ""
    intervals.forEach((interval, index) => {
      const dateStr = interval.time.toDateString()
      if (dateStr !== lastDateStr) {
        boundaries.push({ index, date: new Date(interval.time) })
        lastDateStr = dateStr
      }
    })
    return boundaries
  }, [intervals])

  // Time-axis labels (shown when there is enough horizontal space)
  const timeLabels = useMemo(() => {
    const labels: { index: number; text: string }[] = []
    const pxPerBar = displayParams.barWidth + displayParams.gap
    const barsPerHour = 60 * 60 * 1000 / displayParams.intervalMs
    const pxPerHour = barsPerHour * pxPerBar

    let labelFreqHours: number
    if (pxPerHour >= 40) labelFreqHours = 3
    else if (pxPerHour >= 15) labelFreqHours = 6
    else if (pxPerHour >= 4) labelFreqHours = 12
    else return labels // too compressed for time labels

    intervals.forEach((interval, index) => {
      const h = interval.time.getHours()
      const m = interval.time.getMinutes()
      if (m === 0 && h % labelFreqHours === 0) {
        labels.push({
          index,
          text: interval.time.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" }),
        })
      }
    })
    return labels
  }, [intervals, displayParams])

  const chartHeight = 192
  const pxPerBar = displayParams.barWidth + displayParams.gap
  const totalWidth = intervals.length * pxPerBar

  const formatDateShort = (date: Date) =>
    date.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" })

  const formatDateRange = (start: Date, end: Date) => {
    const opts: Intl.DateTimeFormatOptions = { weekday: "short", month: "short", day: "numeric" }
    return `${start.toLocaleDateString("en-US", opts)} \u2013 ${end.toLocaleDateString("en-US", opts)}`
  }

  return (
    <Card className="border-2 shadow-lg">
      <CardHeader className="flex flex-row items-start justify-between">
        <div>
          <CardTitle className="flex items-center gap-2">
            <CalendarIcon className="h-5 w-5 text-primary" />
            Workload Calendar
          </CardTitle>
          <CardDescription>
            {blocks.length > 0
              ? formatDateRange(rangeStart, rangeEnd)
              : "View scheduled jobs across data centres"}
          </CardDescription>
        </div>
        <Button variant="ghost" size="icon" onClick={onClose}>
          <X className="h-4 w-4" />
        </Button>
      </CardHeader>

      <CardContent className="space-y-4">
        {/* Data Centre Tabs */}
        <Tabs value={selectedDC} onValueChange={setSelectedDC}>
          <TabsList className="grid w-full grid-cols-5">
            {DATA_CENTERS.map((dc) => (
              <TabsTrigger key={dc.id} value={dc.id} className="text-xs sm:text-sm">
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

        {/* Chart */}
        {loading ? (
          <div className="flex items-center justify-center h-64">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          </div>
        ) : intervals.length === 0 ? (
          <div className="flex items-center justify-center h-64 text-muted-foreground">
            {scheduleId ? "No scheduled blocks for this data centre" : "Schedule a job to see workload data"}
          </div>
        ) : (
          <div className="relative">
            {/* Y-axis labels */}
            <div
              className="absolute left-0 top-6 flex flex-col justify-between text-xs text-muted-foreground pr-2 z-10 w-14"
              style={{ height: `${chartHeight}px` }}
            >
              <span>{maxValue.toFixed(1)}</span>
              <span>{(maxValue * 0.75).toFixed(1)}</span>
              <span>{(maxValue * 0.5).toFixed(1)}</span>
              <span>{(maxValue * 0.25).toFixed(1)}</span>
              <span>0 kWh</span>
            </div>

            {/* Scrollable chart area */}
            <div ref={scrollContainerRef} className="ml-14 overflow-x-auto pb-2">
              <div
                className="relative"
                style={{
                  width: `${totalWidth}px`,
                  height: `${chartHeight + 52}px`,
                  paddingTop: "24px",
                }}
              >
                {/* Day labels + vertical separators */}
                {dayBoundaries.map((boundary, i) => {
                  const x = boundary.index * pxPerBar
                  const nextX =
                    i < dayBoundaries.length - 1
                      ? dayBoundaries[i + 1].index * pxPerBar
                      : totalWidth
                  const dayWidth = nextX - x

                  return (
                    <div key={`day-${i}`}>
                      {/* Day label above chart */}
                      <div
                        className="absolute top-0 text-[11px] font-medium text-foreground truncate"
                        style={{ left: `${x + 2}px`, maxWidth: `${dayWidth - 4}px` }}
                      >
                        {formatDateShort(boundary.date)}
                      </div>
                      {/* Vertical dashed separator between days */}
                      {i > 0 && (
                        <div
                          className="absolute border-l border-dashed border-muted-foreground/40"
                          style={{ left: `${x}px`, top: "20px", height: `${chartHeight + 4}px` }}
                        />
                      )}
                    </div>
                  )
                })}

                {/* Bars */}
                <div
                  className="absolute flex items-end"
                  style={{ top: "24px", left: 0, height: `${chartHeight}px` }}
                >
                  {intervals.map((interval, index) => {
                    const jobsLoad = interval.jobs.reduce((sum, j) => sum + j.load, 0)
                    const jobsPx = (jobsLoad / maxValue) * chartHeight

                    return (
                      <div
                        key={index}
                        className="relative group shrink-0"
                        style={{ width: `${pxPerBar}px`, height: `${chartHeight}px` }}
                      >
                        {/* Tooltip */}
                        <div
                          className="absolute bottom-full mb-2 hidden group-hover:block z-20 pointer-events-none"
                          style={{ left: "50%", transform: "translateX(-50%)" }}
                        >
                          <div className="bg-popover text-popover-foreground text-xs rounded-md px-2 py-1 shadow-md whitespace-nowrap border">
                            <p className="font-medium">
                              {interval.time.toLocaleDateString("en-US", { month: "short", day: "numeric" })}{" "}
                              {interval.time.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" })}
                            </p>
                            {interval.jobs.length > 0 ? (
                              <div>
                                <p className="text-muted-foreground">
                                  Total: {jobsLoad.toFixed(2)} kWh
                                </p>
                                <div className="border-t mt-1 pt-1">
                                  {interval.jobs.map((job, j) => (
                                    <p key={j} className="text-blue-500">
                                      {job.job_id}: {job.load.toFixed(2)} kWh
                                    </p>
                                  ))}
                                </div>
                              </div>
                            ) : (
                              <p className="text-muted-foreground">No scheduled load</p>
                            )}
                          </div>
                        </div>

                        {/* Coloured bar */}
                        {jobsPx > 0 && (
                          <div
                            className="absolute bottom-0 bg-blue-500 rounded-t-sm"
                            style={{
                              height: `${Math.max(jobsPx, 1)}px`,
                              width: `${displayParams.barWidth}px`,
                            }}
                          />
                        )}
                      </div>
                    )
                  })}
                </div>

                {/* Time labels below chart */}
                {timeLabels.map((label) => (
                  <span
                    key={`time-${label.index}`}
                    className="absolute text-[10px] text-muted-foreground whitespace-nowrap"
                    style={{
                      left: `${label.index * pxPerBar}px`,
                      top: `${chartHeight + 28}px`,
                    }}
                  >
                    {label.text}
                  </span>
                ))}
              </div>
            </div>
          </div>
        )}

        {intervals.length > 0 && (
          <p className="text-xs text-muted-foreground text-center">
            Scroll horizontally to view the full schedule
          </p>
        )}
      </CardContent>
    </Card>
  )
}
