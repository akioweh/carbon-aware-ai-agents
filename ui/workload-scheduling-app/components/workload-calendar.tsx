"use client"

import { useState, useEffect, useRef, useMemo } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { CalendarIcon, X, Loader2 } from "lucide-react"
import { Area, AreaChart, CartesianGrid, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine } from "recharts"

interface ScheduleBlock {
  timestamp: string
  location: string
  schedule_id: string
  additional_load: number
}

interface AggregatedInterval {
  time: Date
  endTime: Date
  jobs: { schedule_id: string; load: number }[]
}

interface WorkloadCalendarProps {
  onClose: () => void
  scheduleId?: string
}

const DATA_CENTERS = [
  { id: "dc1", name: "Data Centre 1", backendLocation: "Data-Center-1" },
  { id: "dc2", name: "Data Centre 2", backendLocation: "Data-Center-2" },
  { id: "dc3", name: "Data Centre 3", backendLocation: "Data-Center-3" },
  { id: "dc4", name: "Data Centre 4", backendLocation: "Data-Center-4" },
  { id: "dc5", name: "Data Centre 5", backendLocation: "Data-Center-5" },
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

    // Filter blocks for the selected DC using the backend location name
    const dcBackendLocation = DATA_CENTERS.find(dc => dc.id === selectedDC)?.backendLocation
    const dcBlocks = dcBackendLocation ? blocks.filter(b => b.location === dcBackendLocation) : []

    // Build aggregated intervals
    const intervals: AggregatedInterval[] = []
    for (let t = rangeStart.getTime(); t < rangeEnd.getTime(); t += dp.intervalMs) {
      const intervalEnd = t + dp.intervalMs
      const activeJobs: { schedule_id: string; load: number }[] = []

      for (const block of dcBlocks) {
        if (!block.timestamp || typeof block.additional_load !== "number") continue
        const blockStart = new Date(block.timestamp).getTime()
        const blockEnd = blockStart + BLOCK_DURATION_MS
        if (blockStart < intervalEnd && blockEnd > t) {
          const existing = activeJobs.find(j => j.schedule_id === block.schedule_id)
          if (existing) {
            existing.load += block.additional_load
          } else {
            activeJobs.push({ schedule_id: block.schedule_id, load: block.additional_load })
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

  // Fixed Y-axis: all data centers have capacity of 50
  const maxValue = 50

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
            <span className="text-muted-foreground">Scheduled Jobs</span>
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
              <span>50</span>
              <span>37.5</span>
              <span>25</span>
              <span>12.5</span>
              <span>0</span>
            </div>

            {/* Scrollable chart area */}
            <div ref={scrollContainerRef} className="ml-14 overflow-x-auto pb-2">
              <div
                className="relative"
                style={{
                  width: `${Math.max(intervals.length * 12, 600)}px`,
                  height: `${chartHeight + 52}px`,
                  paddingTop: "24px",
                }}
              >
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart
                    data={intervals.map(i => ({
                      time: i.time.toISOString(),
                      totalLoad: i.jobs.reduce((sum, j) => sum + j.load, 0),
                      rawJobs: i.jobs
                    }))}
                    margin={{ top: 0, right: 0, left: 0, bottom: 0 }}
                  >
                    <defs>
                      <linearGradient id="colorScheduled" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.8}/>
                        <stop offset="95%" stopColor="#3b82f6" stopOpacity={0.1}/>
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} opacity={0.3} />
                    <XAxis 
                      dataKey="time" 
                      tickFormatter={(time) => {
                        return new Date(time).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" })
                      }} 
                      tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }}
                      minTickGap={30}
                      axisLine={false}
                      tickLine={false}
                    />
                    <YAxis 
                      domain={[0, maxValue]} 
                      hide={true}
                    />
                    <Tooltip 
                      content={({ active, payload, label }) => {
                        if (active && payload && payload.length) {
                          const data = payload[0].payload;
                          return (
                            <div className="bg-popover text-popover-foreground text-xs rounded-md px-3 py-2 shadow-md border">
                              <p className="font-medium mb-1 border-b pb-1">
                                {new Date(label).toLocaleDateString("en-US", { month: "short", day: "numeric" })}{" "}
                                {new Date(label).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" })}
                              </p>
                              {data.rawJobs && data.rawJobs.length > 0 ? (
                                <div className="space-y-1">
                                  <p className="text-muted-foreground font-semibold">
                                    Total Load: {Number(payload[0].value).toFixed(2)} kWh
                                  </p>
                                  <div className="border-t mt-1 pt-1 space-y-0.5">
                                    {data.rawJobs.map((job: any, j: number) => (
                                      <p key={j} className="text-blue-500">
                                        <span className="font-medium">{job.schedule_id}</span>: {Number(job.load).toFixed(2)} 
                                      </p>
                                    ))}
                                  </div>
                                </div>
                              ) : (
                                <p className="text-muted-foreground">No scheduled load</p>
                              )}
                            </div>
                          );
                        }
                        return null;
                      }}
                    />
                  {/* Add day boundary markers via ReferenceLine */}
                  {intervals.filter(d => d.time.getHours() === 0 && d.time.getMinutes() === 0).map((d, i) => (
                    <ReferenceLine 
                      key={`midnight-${i}`} 
                      x={d.time.toISOString()} 
                      stroke="hsl(var(--foreground))" 
                      strokeDasharray="3 3" 
                      opacity={0.3} 
                      label={{ position: "insideTopLeft", value: formatDateShort(d.time), fill: "hsl(var(--foreground))", fontSize: 11 }}
                    />
                  ))}
                    <Area 
                      type="monotone" 
                      dataKey="totalLoad" 
                      stroke="#3b82f6" 
                      fill="url(#colorScheduled)" 
                      isAnimationActive={false}
                    />
                  </AreaChart>
                </ResponsiveContainer>
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
