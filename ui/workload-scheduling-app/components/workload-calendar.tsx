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
  const { intervalsPerDC, rangeStart, rangeEnd } = useMemo(() => {
    if (blocks.length === 0) {
      const defaultIntervals: Record<string, AggregatedInterval[]> = {}
      for (const dc of DATA_CENTERS) defaultIntervals[dc.id] = []
      return {
        intervalsPerDC: defaultIntervals,
        rangeStart: new Date(),
        rangeEnd: new Date(),
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
    // We remove the getDisplayParams downsampling because we want to see full resolution

    // Build aggregated intervals per DC
    const intervalsPerDC: Record<string, AggregatedInterval[]> = {}
    for (const dc of DATA_CENTERS) {
      intervalsPerDC[dc.id] = []
      const dcBlocks = blocks.filter(b => b.location === dc.backendLocation)
      
      for (let t = rangeStart.getTime(); t < rangeEnd.getTime(); t += BLOCK_DURATION_MS) {
        const intervalEnd = t + BLOCK_DURATION_MS
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

        intervalsPerDC[dc.id].push({
          time: new Date(t),
          endTime: new Date(intervalEnd),
          jobs: activeJobs,
        })
      }
    }

    return { intervalsPerDC, rangeStart, rangeEnd }
  }, [blocks])

  const maxValue = 50
  const chartHeight = 120 // compact height since we are stacking 5 of them

  // Use the first DC's intervals to calculate total width and shared boundaries
  const sampleIntervals = intervalsPerDC[DATA_CENTERS[0].id] || []
  const hasData = sampleIntervals.length > 0
  const pxPerBar = 2 // very compact
  const totalWidth = sampleIntervals.length * pxPerBar

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

      <CardContent className="space-y-4 pt-4">
        {/* Legend */}
        <div className="flex items-center justify-between gap-6 text-sm pb-2 border-b">
          <div className="flex items-center gap-2">
            <div className="h-3 w-3 rounded bg-blue-500" />
            <span className="text-muted-foreground">Scheduled Jobs</span>
          </div>
          {hasData && (
            <p className="text-xs text-muted-foreground">
              Scroll horizontally to view the full timeline
            </p>
          )}
        </div>

        {/* Chart */}
        {loading ? (
          <div className="flex items-center justify-center h-64">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          </div>
        ) : !hasData ? (
          <div className="flex items-center justify-center h-64 text-muted-foreground">
            {scheduleId ? "No scheduled blocks found" : "Schedule a job to see workload data"}
          </div>
        ) : (
          <div className="relative">
            {/* Scrollable container for ALL DCs synchronized */}
            <div ref={scrollContainerRef} className="overflow-x-auto pb-4 custom-scrollbar">
              <div
                className="relative flex flex-col gap-4"
                style={{
                  width: `${Math.max(sampleIntervals.length * pxPerBar, 800)}px`,
                  paddingLeft: "40px",
                  paddingRight: "20px"
                }}
              >
                {DATA_CENTERS.map((dc, i) => {
                  const intervals = intervalsPerDC[dc.id]
                  return (
                    <div key={dc.id} className="relative w-full" style={{ height: `${chartHeight}px` }}>
                      {/* Fixed Y-axis labels per chart */}
                      <div className="absolute -left-10 top-0 bottom-0 flex flex-col justify-between text-[10px] text-muted-foreground z-10 w-8 text-right pr-2">
                        <span>{maxValue}</span>
                        <span>{maxValue / 2}</span>
                        <span>0</span>
                      </div>
                      
                      {/* Floating Data Center Label */}
                      <div className="absolute top-2 left-2 z-20 bg-background/80 backdrop-blur-sm px-2 py-0.5 rounded text-xs font-semibold border shadow-sm">
                        {dc.name}
                      </div>

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
                            <linearGradient id={`colorScheduled-${dc.id}`} x1="0" y1="0" x2="0" y2="1">
                              <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.8}/>
                              <stop offset="95%" stopColor="#3b82f6" stopOpacity={0.1}/>
                            </linearGradient>
                          </defs>
                          <CartesianGrid strokeDasharray="3 3" vertical={false} opacity={0.3} />
                          
                          {/* Only show XAxis on the very last chart to save space */}
                          <XAxis 
                            dataKey="time" 
                            tickFormatter={(time) => {
                              return new Date(time).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" })
                            }} 
                            tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }}
                            minTickGap={60}
                            axisLine={false}
                            tickLine={false}
                            hide={i !== DATA_CENTERS.length - 1}
                          />
                          
                          <YAxis domain={[0, maxValue]} hide={true} />
                          
                          <Tooltip 
                            content={({ active, payload, label }) => {
                              if (active && payload && payload.length) {
                                const data = payload[0].payload;
                                return (
                                  <div className="bg-popover text-popover-foreground text-xs rounded-md px-3 py-2 shadow-md border z-50 relative">
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
                          {intervals.filter(d => d.time.getHours() === 0 && d.time.getMinutes() === 0).map((d, k) => (
                            <ReferenceLine 
                              key={`midnight-${k}`} 
                              x={d.time.toISOString()} 
                              stroke="#94a3b8" 
                              strokeDasharray="4 4" 
                              strokeWidth={1}
                              label={i === 0 ? { position: "insideTopLeft", value: formatDateShort(d.time), fill: "#64748b", fontSize: 11, offset: 10 } : undefined}
                            />
                          ))}
                          <Area 
                            type="monotone" 
                            dataKey="totalLoad" 
                            stroke="#3b82f6" 
                            fill={`url(#colorScheduled-${dc.id})`} 
                            isAnimationActive={false}
                          />
                        </AreaChart>
                      </ResponsiveContainer>
                    </div>
                  )
                })}
              </div>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
