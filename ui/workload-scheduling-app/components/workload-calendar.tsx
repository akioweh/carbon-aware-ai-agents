"use client"

import { useState, useEffect, useRef, useMemo } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { CalendarIcon, X, Loader2 } from "lucide-react"
import {
  Area,
  ComposedChart,
  Line,
  CartesianGrid,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine
} from "recharts"
import { ScheduleBlock } from "../types/schedule"

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
const MAX_LOAD_VALUE = 50

export function WorkloadCalendar({ onClose, scheduleId }: WorkloadCalendarProps) {
  const [selectedDC, setSelectedDC] = useState(DATA_CENTERS[0].id)
  const [blocks, setBlocks] = useState<ScheduleBlock[]>([])
  const [forecasts, setForecasts] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const scrollContainerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true)
      try {
        const [schedulesRes, forecastsRes] = await Promise.all([
          fetch(`/api/schedules`),
          fetch(`/api/forecast`)
        ])
        if (schedulesRes.ok) {
          const scheduleData = await schedulesRes.json()
          setBlocks(Array.isArray(scheduleData) ? scheduleData : [])
        }
        if (forecastsRes.ok) {
          const forecastData = await forecastsRes.json()
          setForecasts(Array.isArray(forecastData) ? forecastData : [])
        }
      } catch (err) {
        console.error("Error fetching data:", err)
      } finally {
        setLoading(false)
      }
    }
    fetchData()
  }, [])

  // Calculate synchronized domain for SCI across ALL charts
  const globalSCIDomain = useMemo(() => {
    if (!forecasts || forecasts.length === 0) return [0, 1]
    let min = Infinity
    let max = -Infinity
    forecasts.forEach(dc => {
      dc.timeseries?.forEach((point: any) => {
        if (typeof point.carbon_intensity === "number") {
          min = Math.min(min, point.carbon_intensity)
          max = Math.max(max, point.carbon_intensity)
        }
      })
    })
    if (min === Infinity || max === -Infinity) return [0, 1]
    const padding = (max - min) * 0.05
    return [min - padding, max + padding]
  }, [forecasts])

  const { intervalsPerDC, rangeStart, rangeEnd } = useMemo(() => {
    if (blocks.length === 0) {
      const defaultIntervals: Record<string, AggregatedInterval[]> = {}
      for (const dc of DATA_CENTERS) defaultIntervals[dc.id] = []
      return { intervalsPerDC: defaultIntervals, rangeStart: new Date(), rangeEnd: new Date() }
    }

    const allTimestamps = blocks.map(b => new Date(b.timestamp).getTime())
    const minTime = Math.min(...allTimestamps)
    const maxTime = Math.max(...allTimestamps) + BLOCK_DURATION_MS

    const rangeStart = new Date(minTime)
    rangeStart.setMinutes(0, 0, 0)
    const rangeEnd = new Date(maxTime)
    if (rangeEnd.getMinutes() > 0 || rangeEnd.getSeconds() > 0) {
      rangeEnd.setMinutes(0, 0, 0); rangeEnd.setHours(rangeEnd.getHours() + 1);
    }

    const intervalsPerDC: Record<string, AggregatedInterval[]> = {}
    for (const dc of DATA_CENTERS) {
      intervalsPerDC[dc.id] = []
      const dcBlocks = blocks.filter(b => b.location === dc.backendLocation)
      for (let t = rangeStart.getTime(); t < rangeEnd.getTime(); t += BLOCK_DURATION_MS) {
        const intervalEnd = t + BLOCK_DURATION_MS
        const activeJobs: { schedule_id: string; load: number }[] = []
        for (const block of dcBlocks) {
          const blockStart = new Date(block.timestamp).getTime()
          const blockEnd = blockStart + BLOCK_DURATION_MS
          if (blockStart < intervalEnd && blockEnd > t) {
            const existing = activeJobs.find(j => j.schedule_id === block.schedule_id)
            if (existing) existing.load += block.additional_load
            else activeJobs.push({ schedule_id: block.schedule_id, load: block.additional_load })
          }
        }
        intervalsPerDC[dc.id].push({ time: new Date(t), endTime: new Date(intervalEnd), jobs: activeJobs })
      }
    }
    return { intervalsPerDC, rangeStart, rangeEnd }
  }, [blocks])

  const chartHeight = 120
  const sampleIntervals = intervalsPerDC[DATA_CENTERS[0].id] || []
  const hasData = sampleIntervals.length > 0
  const pxPerBar = 2

  const formatDateShort = (date: Date) => date.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" })

  return (
    <Card className="border-2 shadow-lg">
      <CardHeader className="flex flex-row items-start justify-between">
        <div>
          <CardTitle className="flex items-center gap-2"><CalendarIcon className="h-5 w-5 text-primary" />Workload Calendar</CardTitle>
          <CardDescription>{hasData ? "Scheduled jobs across data centres" : "No data available"}</CardDescription>
        </div>
        <Button variant="ghost" size="icon" onClick={onClose}><X className="h-4 w-4" /></Button>
      </CardHeader>

      <CardContent className="space-y-4 pt-4">
        <div className="flex flex-wrap items-center gap-4 text-sm pb-2 border-b">
          <div className="flex items-center gap-2"><div className="h-3 w-3 rounded bg-green-500" /><span className="text-muted-foreground">Scheduled</span></div>
          <div className="flex items-center gap-2"><div className="h-1 w-4 rounded bg-red-500" /><span className="text-muted-foreground">Carbon-Intensity</span></div>
          <div className="flex items-center gap-2"><div className="h-1 w-4 rounded bg-blue-400" /><span className="text-muted-foreground">Outside-Load</span></div>
        </div>

        {loading ? (
          <div className="flex items-center justify-center h-64"><Loader2 className="h-8 w-8 animate-spin text-muted-foreground" /></div>
        ) : !hasData ? (
          <div className="flex items-center justify-center h-64 text-muted-foreground">No scheduled blocks found</div>
        ) : (
          <div className="relative">
            <div ref={scrollContainerRef} className="overflow-x-auto pb-4 custom-scrollbar">
              <div className="relative flex flex-col gap-4" style={{ width: `${Math.max(sampleIntervals.length * pxPerBar, 800)}px`, paddingLeft: "40px", paddingRight: "20px" }}>
                {DATA_CENTERS.map((dc, i) => {
                  const intervals = intervalsPerDC[dc.id]
                  const dcForecastTimeseries = forecasts.find(f => f.location === dc.backendLocation)?.timeseries || []
                  const chartData = intervals.map(interval => {
                    const tTime = interval.time.getTime()
                    const closestForecast = dcForecastTimeseries.reduce((prev: any, curr: any) => {
                      const currTime = new Date(curr.timestamp).getTime()
                      return currTime <= tTime ? curr : prev
                    }, null)
                    return {
                      time: interval.time.toISOString(),
                      totalLoad: interval.jobs.reduce((sum, j) => sum + j.load, 0),
                      rawJobs: interval.jobs,
                      carbon_intensity: closestForecast ? closestForecast.carbon_intensity : null,
                      load: closestForecast ? closestForecast.load : null
                    }
                  })

                  return (
                    <div key={dc.id} className="relative w-full" style={{ height: `${chartHeight}px` }}>
                      <div className="absolute -left-10 top-0 bottom-0 flex flex-col justify-between text-[10px] text-muted-foreground z-10 w-8 text-right pr-2">
                        <span>{MAX_LOAD_VALUE}</span><span>0</span>
                      </div>
                      <div className="absolute top-2 left-2 z-20 bg-background/80 backdrop-blur-sm px-2 py-0.5 rounded text-xs font-semibold border shadow-sm">{dc.name}</div>
                      <ResponsiveContainer width="100%" height="100%">
                        <ComposedChart data={chartData} margin={{ top: 0, right: 0, left: 0, bottom: 0 }}>
                          <defs>
                            <linearGradient id={`colorScheduled-${dc.id}`} x1="0" y1="0" x2="0" y2="1">
                              <stop offset="5%" stopColor="#059669" stopOpacity={0.8} /><stop offset="95%" stopColor="#059669" stopOpacity={0.1} />
                            </linearGradient>
                          </defs>
                          <CartesianGrid strokeDasharray="3 3" vertical={false} opacity={0.3} />
                          <XAxis
                            dataKey="time"
                            hide={i !== DATA_CENTERS.length - 1}
                            tickFormatter={(time) => new Date(time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                            interval={11 * 3} // Shows a label every 12th point (every hour if 5-min intervals)
                            tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }}
                            axisLine={false}
                            tickLine={false}
                          />
                          <YAxis yAxisId="left" domain={[0, MAX_LOAD_VALUE]} hide={true} />
                          <YAxis yAxisId="right" orientation="right" hide={true} domain={globalSCIDomain} />
                          <Tooltip
                            content={({ active, payload, label }) => {
                              if (active && payload && payload.length) {
                                const data = payload[0].payload;
                                return (
                                  <div className="bg-popover text-popover-foreground text-xs rounded-md px-3 py-2 shadow-md border z-50">
                                    <p className="font-medium border-b mb-1">{new Date(label).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</p>
                                    {data.carbon_intensity != null && <p className="text-red-500">Carbon-Intensity: {data.carbon_intensity.toFixed(2)}</p>}
                                    {data.load != null && <p className="text-blue-500">Load: {data.load.toFixed(2)}</p>}
                                    <p className="text-muted-foreground">Job Load: {data.totalLoad.toFixed(2)} kWh</p>
                                  </div>
                                );
                              }
                              return null;
                            }}
                          />
                          <Area yAxisId="left" type="monotone" dataKey="totalLoad" stroke="#059669" fill={`url(#colorScheduled-${dc.id})`} isAnimationActive={false} />
                          <Line yAxisId="right" type="monotone" dataKey="carbon_intensity" stroke="#FF0000" strokeWidth={2} dot={false} isAnimationActive={false} />
                          <Line yAxisId="left" type="monotone" dataKey="load" stroke="#3b82f6" strokeWidth={1} dot={false} isAnimationActive={false} />
                          {intervals.filter(d => d.time.getHours() === 0 && d.time.getMinutes() === 0).map((d, k) => (
                            <ReferenceLine key={k} yAxisId="left" x={d.time.toISOString()} stroke="#94a3b8" strokeDasharray="4 4" label={i === 0 ? { position: "insideTopLeft", value: formatDateShort(d.time), fontSize: 10 } : undefined} />
                          ))}
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