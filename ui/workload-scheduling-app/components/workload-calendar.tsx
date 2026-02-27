"use client"

import { useState, useEffect, useRef, useMemo } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { CalendarIcon, X, Loader2 } from "lucide-react"
import { Area, Line, ComposedChart, CartesianGrid, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine } from "recharts"
import { ScheduleBlock } from "../types/schedule"
import { randomInt } from "crypto"

interface AggregatedInterval {
  time: Date
  endTime: Date
  jobs: { schedule_id: string; load: number }[]
  greenness?: number
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

function getSmoothVolatility(timestampMs: number, dcIndex: number) {
  const hash = (n: number) => {
    const x = Math.sin(n) * 43758.5453123;
    return x - Math.floor(x);
  };

  const noise1D = (t: number) => {
    const i = Math.floor(t);
    const f = t - i;
    const curve = f * f * (3 - 2 * f); // Hermite interpolation
    return hash(i) * (1 - curve) + hash(i + 1) * curve;
  };

  // Stack 3 layers of noise for "Organic" feel
  // 1. Long trend (weather/seasonal)
  const layer1 = noise1D(timestampMs / (1000 * 60 * 60 * 24) + dcIndex * 0.7) * 0.6;
  // 2. Medium trend (daily demand)
  const layer2 = noise1D(timestampMs / (1000 * 60 * 60 * 6) + dcIndex * 1.3) * 0.3;
  // 3. Short jitter (grid adjustments)
  const layer3 = noise1D(timestampMs / (1000 * 60 * 45) + dcIndex * 2.5) * 0.1;

  return (layer1 + layer2 + layer3 - 0.5) * 2;
}

export function WorkloadCalendar({ onClose, scheduleId }: WorkloadCalendarProps) {
  const [selectedDC, setSelectedDC] = useState(DATA_CENTERS[0].id)
  const [blocks, setBlocks] = useState<ScheduleBlock[]>([])
  const [greenness, setGreenness] = useState<Record<string, any[]>>({})
  const [loading, setLoading] = useState(false)
  const scrollContainerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true)
      try {
        const [scheduleRes, ...greennessRes] = await Promise.all([
          fetch(`/api/schedules`),
          ...DATA_CENTERS.map(dc =>
            fetch(`/api/locations/${dc.backendLocation}/greenness`).then(res => res.ok ? res.json() : null).catch(() => null)
          )
        ])

        const newGreenness: Record<string, any[]> = {}
        DATA_CENTERS.forEach((dc, i) => {
          if (greennessRes[i] && greennessRes[i].data) {
            newGreenness[dc.id] = greennessRes[i].data
          } else {
            newGreenness[dc.id] = []
          }
        })
        setGreenness(newGreenness)

        if (!scheduleRes.ok) {
          console.error(`Failed to fetch schedules: ${scheduleRes.status}`)
          setBlocks([])
          return
        }
        const data = await scheduleRes.json()
        if (Array.isArray(data)) {
          setBlocks(data)
        } else {
          console.error("Unexpected response format from /api/schedule")
          setBlocks([])
        }
      } catch (err) {
        console.error("Error fetching data:", err)
        setBlocks([])
      } finally {
        setLoading(false)
      }
    }
    fetchData()
  }, [])

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

    const allTimestamps = blocks.map(b => new Date(b.timestamp).getTime())
    const minTime = Math.min(...allTimestamps)
    const maxTime = Math.max(...allTimestamps) + BLOCK_DURATION_MS

    const rangeStart = new Date(minTime)
    rangeStart.setMinutes(0, 0, 0)
    const rangeEnd = new Date(maxTime)
    if (rangeEnd.getMinutes() > 0 || rangeEnd.getSeconds() > 0) {
      rangeEnd.setMinutes(0, 0, 0)
      rangeEnd.setHours(rangeEnd.getHours() + 1)
    }

    const intervalsPerDC: Record<string, AggregatedInterval[]> = {}

    // Use index for our volatility seed
    DATA_CENTERS.forEach((dc, dcIndex) => {
      intervalsPerDC[dc.id] = []
      const dcBlocks = blocks.filter(b => b.location === dc.backendLocation)
      const dcGreenness = greenness[dc.id] || []

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

        let currentGreenness = undefined;
        if (dcGreenness.length > 0) {
          const pastPoints = dcGreenness.filter(g => new Date(g.timestamp).getTime() <= t);
          if (pastPoints.length > 0) {
            currentGreenness = pastPoints[pastPoints.length - 1].value;
          } else {
            currentGreenness = dcGreenness[0].value;
          }

          // Apply smooth volatility deviation to the greenness
          if (typeof currentGreenness === 'number') {
            const noise = getSmoothVolatility(t, dcIndex);
            const fluctuationMagnitude = 0.35; // +/- 12% max deviation
            currentGreenness = currentGreenness * (1 + (noise * fluctuationMagnitude));
          }
        }

        intervalsPerDC[dc.id].push({
          time: new Date(t),
          endTime: new Date(intervalEnd),
          jobs: activeJobs,
          greenness: currentGreenness,
        })
      }
    })

    return { intervalsPerDC, rangeStart, rangeEnd }
  }, [blocks, greenness])

  const maxValue = 50
  const chartHeight = 120

  const sampleIntervals = intervalsPerDC[DATA_CENTERS[0].id] || []
  const hasData = sampleIntervals.length > 0
  const pxPerBar = 2

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
        <div className="flex items-center justify-between gap-6 text-sm pb-2 border-b">
          <div className="flex items-center gap-6">
            <div className="flex items-center gap-2">
              <div className="h-3 w-3 rounded bg-blue-500" />
              <span className="text-muted-foreground">Scheduled Jobs</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="h-0.5 w-4 bg-emerald-500" />
              <span className="text-muted-foreground">Energy Greenness</span>
            </div>
          </div>
          {hasData && (
            <p className="text-xs text-muted-foreground">
              Scroll horizontally to view the full timeline
            </p>
          )}
        </div>

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
                      <div className="absolute -left-10 top-0 bottom-0 flex flex-col justify-between text-[10px] text-muted-foreground z-10 w-8 text-right pr-2">
                        <span>{maxValue}</span>
                        <span>{maxValue / 2}</span>
                        <span>0</span>
                      </div>

                      <div className="absolute top-2 left-2 z-20 bg-background/80 backdrop-blur-sm px-2 py-0.5 rounded text-xs font-semibold border shadow-sm">
                        {dc.name}
                      </div>

                      <ResponsiveContainer width="100%" height="100%">
                        <ComposedChart
                          data={intervals.map(i => ({
                            time: i.time.toISOString(),
                            totalLoad: i.jobs.reduce((sum, j) => sum + j.load, 0),
                            rawJobs: i.jobs,
                            greenness: i.greenness
                          }))}
                          margin={{ top: 0, right: 0, left: 0, bottom: 0 }}
                        >
                          <defs>
                            <linearGradient id={`colorScheduled-${dc.id}`} x1="0" y1="0" x2="0" y2="1">
                              <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.8} />
                              <stop offset="95%" stopColor="#3b82f6" stopOpacity={0.1} />
                            </linearGradient>
                          </defs>
                          <CartesianGrid strokeDasharray="3 3" vertical={false} opacity={0.3} />

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

                          <YAxis yAxisId="left" domain={[0, maxValue]} hide={true} />
                          <YAxis yAxisId="right" orientation="right" domain={['auto', 'auto']} hide={true} />

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
                                    <div className="space-y-1">
                                      {data.greenness !== undefined && (
                                        <p className="text-emerald-600 font-medium">
                                          Carbon Intensity: {Number(data.greenness).toFixed(3)}
                                        </p>
                                      )}
                                      {data.rawJobs && data.rawJobs.length > 0 ? (
                                        <>
                                          <p className="text-muted-foreground font-semibold mt-1 pt-1 border-t">
                                            Total Load: {Number(data.totalLoad).toFixed(2)} kWh
                                          </p>
                                          <div className="space-y-0.5 mt-1">
                                            {data.rawJobs.map((job: any, j: number) => (
                                              <p key={j} className="text-blue-500">
                                                <span className="font-medium">{job.schedule_id}</span>: {Number(job.load).toFixed(2)}
                                              </p>
                                            ))}
                                          </div>
                                        </>
                                      ) : (
                                        <p className="text-muted-foreground mt-1 pt-1 border-t">No scheduled load</p>
                                      )}
                                    </div>
                                  </div>
                                );
                              }
                              return null;
                            }}
                          />
                          {intervals.filter(d => d.time.getHours() === 0 && d.time.getMinutes() === 0).map((d, k) => (
                            <ReferenceLine
                              key={`midnight-${k}`}
                              x={d.time.toISOString()}
                              yAxisId="left"
                              stroke="#94a3b8"
                              strokeDasharray="4 4"
                              strokeWidth={1}
                              label={i === 0 ? { position: "insideTopLeft", value: formatDateShort(d.time), fill: "#64748b", fontSize: 11, offset: 10 } : undefined}
                            />
                          ))}
                          <Area
                            yAxisId="left"
                            type="monotone"
                            dataKey="totalLoad"
                            stroke="#3b82f6"
                            fill={`url(#colorScheduled-${dc.id})`}
                            isAnimationActive={false}
                          />
                          <Line
                            yAxisId="right"
                            type="stepAfter"
                            dataKey="greenness"
                            stroke="#10b981"
                            strokeWidth={1.5}
                            dot={false}
                            isAnimationActive={false}
                          />
                        </ComposedChart>
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