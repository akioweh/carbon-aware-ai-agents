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
import { useActiveDatacenters } from "@/hooks/use-active-datacenters"
import { scaleDataByConstantToPFLOP } from "./schedule-result"

interface AggregatedInterval {
  time: Date
  endTime: Date
  jobs: { schedule_id: string; load: number }[]
}

interface WorkloadCalendarProps {
  onClose?: () => void
  scheduleId?: string
}

const BLOCK_DURATION_MS = 5 * 60 * 1000

export function WorkloadCalendar({ onClose, scheduleId }: WorkloadCalendarProps) {
  const { datacenters: activeDatacenters, loading: datacentersLoading } = useActiveDatacenters()
  const dataCenters = useMemo(
    () => activeDatacenters.map((dc) => ({ id: dc.id, name: dc.name, backendLocation: dc.id })),
    [activeDatacenters]
  )
  const [blocks, setBlocks] = useState<ScheduleBlock[]>([])
  const [forecasts, setForecasts] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const scrollContainerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true)
      try {
        const schedulesRes = await fetch(`/api/schedules`)
        let scheduleData: any[] = []

        if (schedulesRes.ok) {
          scheduleData = await schedulesRes.json()
          setBlocks(Array.isArray(scheduleData) ? scheduleData : [])
        }

        if (scheduleData.length > 0) {
          const allTimestamps = scheduleData.map((b: any) => new Date(b.timestamp).getTime())
          const start = new Date(Math.min(...allTimestamps))
          start.setMinutes(0, 0, 0)

          const end = new Date(Math.max(...allTimestamps) + BLOCK_DURATION_MS)
          end.setMinutes(0, 0, 0)
          end.setHours(end.getHours() + 1)

          const forecastsRes = await fetch(`/api/forecast?start_time=${encodeURIComponent(start.toISOString())}&end_time=${encodeURIComponent(end.toISOString())}`)
          if (forecastsRes.ok) {
            const forecastData = await forecastsRes.json()
            setForecasts(Array.isArray(forecastData) ? forecastData : [])
          }
        } else {
          const forecastsRes = await fetch(`/api/forecast`)
          if (forecastsRes.ok) {
            const forecastData = await forecastsRes.json()
            setForecasts(Array.isArray(forecastData) ? forecastData : [])
          }
        }
      } catch (err) {
        console.error("Error fetching data:", err)
      } finally {
        setLoading(false)
      }
    }
    fetchData()
  }, [])

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
    return [Math.max(0, min - padding), max + padding]
  }, [forecasts])

  const { intervalsPerDC, rangeStart, rangeEnd } = useMemo(() => {
    if (blocks.length === 0) {
      const defaultIntervals: Record<string, AggregatedInterval[]> = {}
      for (const dc of dataCenters) defaultIntervals[dc.id] = []
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
      rangeEnd.setMinutes(0, 0, 0); rangeEnd.setHours(rangeEnd.getHours() + 1);
    }

    const intervalsPerDC: Record<string, AggregatedInterval[]> = {}
    for (const dc of dataCenters) {
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
  }, [blocks, dataCenters])

  const chartHeight = 120 // compact height since we are stacking 5 of them

  // Use the first DC's intervals to calculate total width and shared boundaries
  const firstDcId = dataCenters[0]?.id
  const sampleIntervals = firstDcId ? intervalsPerDC[firstDcId] || [] : []
  const hasData = sampleIntervals.length > 0
  const pxPerBar = 2

  const nowLineValue = useMemo(() => {
    if (!firstDcId || sampleIntervals.length === 0) return null
    const now = Date.now()
    let closest: string | null = null
    let closestDiff = Infinity
    for (const d of sampleIntervals) {
      const diff = Math.abs(d.time.getTime() - now)
      if (diff < closestDiff) {
        closestDiff = diff
        closest = d.time.toISOString()
      }
    }
    return closest && closestDiff < 5 * 60 * 1000 ? closest : null
  }, [sampleIntervals, firstDcId])

  useEffect(() => {
    if (!loading && sampleIntervals.length > 0 && scrollContainerRef.current) {
      const container = scrollContainerRef.current
      let targetScroll = container.scrollWidth
      if (nowLineValue) {
        const nowIndex = sampleIntervals.findIndex((d) => d.time.toISOString() === nowLineValue)
        if (nowIndex !== -1) {
          const pixelPosition = (nowIndex / sampleIntervals.length) * container.scrollWidth
          targetScroll = pixelPosition - container.clientWidth / 2
        }
      }
      container.scrollLeft = Math.max(0, targetScroll)
    }
  }, [loading, sampleIntervals, nowLineValue])

  const formatDateShort = (date: Date) => date.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" })
  return (
    <Card className="border-2 shadow-lg">
      <CardHeader className="flex flex-row items-start justify-between">
        <div>
          <CardTitle className="flex items-center gap-2"><CalendarIcon className="h-5 w-5 text-primary" />Workload Calendar</CardTitle>
          <CardDescription>{hasData ? "Scheduled jobs across data centres" : "No data available"}</CardDescription>
        </div>
        {onClose && (
          <Button variant="ghost" size="icon" onClick={onClose}><X className="h-4 w-4" /></Button>
        )}
      </CardHeader>

      <CardContent className="space-y-4 pt-4">
        <div className="flex flex-wrap items-center gap-4 text-sm pb-2 border-b">
          <div className="flex items-center gap-2"><div className="h-3 w-3 rounded bg-green-500" /><span className="text-muted-foreground">Scheduled</span></div>
          <div className="flex items-center gap-2"><div className="h-1 w-4 rounded bg-red-500" /><span className="text-muted-foreground">Carbon-Intensity</span></div>
          <div className="flex items-center gap-2"><div className="h-3 w-3 rounded bg-blue-400" /><span className="text-muted-foreground">Outside-Load</span></div>
          <div className="flex items-center gap-2"><div className="h-1 w-4 rounded bg-purple-500" /><span className="text-muted-foreground">Capacity</span></div>
          <div className="flex items-center gap-2"><div className="h-4 w-0.5 rounded bg-amber-500" /><span className="text-muted-foreground">Now</span></div>
        </div>

        {/* Chart */}
        {loading || datacentersLoading ? (
          <div className="flex items-center justify-center h-64">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          </div>
        ) : dataCenters.length === 0 ? (
          <div className="flex items-center justify-center h-64 text-muted-foreground">
            No active data centers configured
          </div>
        ) : !hasData ? (
          <div className="flex items-center justify-center h-64 text-muted-foreground">No scheduled blocks found</div>
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
                {dataCenters.map((dc, i) => {
                  const intervals = intervalsPerDC[dc.id]
                  const dcForecastTimeseries = forecasts.find(f => f.location === dc.backendLocation)?.timeseries || []

                  const chartData = intervals.map(interval => {
                    const tTime = interval.time.getTime()
                    const closestForecast = dcForecastTimeseries.reduce((prev: any, curr: any) => {
                      const currTime = new Date(curr.timestamp).getTime()
                      return currTime <= tTime ? curr : prev
                    }, null)

                    const capacity = closestForecast ? scaleDataByConstantToPFLOP(closestForecast.capacity) : null;
                    const loadAmount = closestForecast ? scaleDataByConstantToPFLOP(closestForecast.load) : null;
                    const jobLoad = scaleDataByConstantToPFLOP(interval.jobs.reduce((sum, j) => sum + j.load, 0));

                    const outsideLoadRange: [number, number] | null = (capacity !== null && loadAmount !== null)
                      ? [Math.max(0, capacity - loadAmount), capacity] as [number, number]
                      : null;

                    return {
                      time: interval.time.toISOString(),
                      totalLoad: jobLoad,
                      rawJobs: interval.jobs,
                      carbon_intensity: closestForecast ? closestForecast.carbon_intensity : null,
                      load: loadAmount,
                      capacity,
                      outsideLoadRange
                    }
                  })

                  // Calculate a dynamic max value so the capacity line fits
                  const maxDataValue = Math.max(
                    50,
                    ...chartData.flatMap(d => [d.totalLoad, d.capacity || 0])
                  );
                  const dynamicMaxValue = Math.ceil(maxDataValue / 10) * 10;

                  return (
                    <div key={dc.id} className="w-full">
                      <div className="mb-1 text-xs font-semibold text-foreground sticky left-0 z-20 bg-background pr-2 w-fit">{`${dc.id} - ${dc.name}`}</div>
                      <div className="relative w-full" style={{ height: `${chartHeight}px` }}>
                        <div className="absolute -left-10 top-0 bottom-0 flex flex-col justify-between text-[10px] text-muted-foreground z-10 w-8 text-right pr-2">
                          <span>{dynamicMaxValue}</span><span>0</span>
                        </div>
                        <ResponsiveContainer width="100%" height="100%">
                          <ComposedChart data={chartData} margin={{ top: 0, right: 0, left: 0, bottom: 0 }}>
                            <defs>
                              <linearGradient id={`colorScheduled-${dc.id}`} x1="0" y1="0" x2="0" y2="1">
                                <stop offset="5%" stopColor="#059669" stopOpacity={0.8} /><stop offset="95%" stopColor="#059669" stopOpacity={0.1} />
                              </linearGradient>
                              <linearGradient id={`colorOutside-${dc.id}`} x1="0" y1="0" x2="0" y2="1">
                                <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.6} /><stop offset="95%" stopColor="#3b82f6" stopOpacity={0.2} />
                              </linearGradient>
                            </defs>
                            <CartesianGrid strokeDasharray="3 3" vertical={false} opacity={0.3} />
                            <XAxis
                              dataKey="time"
                              tickFormatter={(time) => new Date(time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                              interval={11 * 3}
                              tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }}
                              axisLine={false}
                              tickLine={false}
                              hide={i !== dataCenters.length - 1}
                            />
                            <YAxis yAxisId="left" domain={[0, dynamicMaxValue]} hide={true} />
                            <YAxis yAxisId="right" orientation="right" hide={true} domain={globalSCIDomain} />
                            <Tooltip
                              content={({ active, payload, label }) => {
                                if (active && payload && payload.length) {
                                  const data = payload[0].payload;
                                  return (
                                    <div className="bg-popover text-popover-foreground text-xs rounded-md px-3 py-2 shadow-md border z-50">
                                      <p className="font-medium border-b mb-1">{new Date(label).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</p>
                                      {data.carbon_intensity != null && <p className="text-red-500 font-semibold">Carbon-Intensity: {Number(data.carbon_intensity).toFixed(2)}</p>}
                                      {data.capacity != null && <p className="text-purple-600 font-semibold">Capacity: {Number(data.capacity).toFixed(1)} PFLO</p>}
                                      {data.load != null && <p className="text-blue-500 font-semibold">Outside-Load: {Number(data.load).toFixed(1)} PFLO</p>}
                                      <p className="text-muted-foreground mt-1">Job Load: {Number(data.totalLoad).toFixed(2)} PFLO</p>
                                    </div>
                                  );
                                }
                                return null;
                              }}
                            />
                            <Area yAxisId="left" type="monotone" dataKey="outsideLoadRange" stroke="#3b82f6" fill={`url(#colorOutside-${dc.id})`} fillOpacity={1} isAnimationActive={false} />
                            <Area yAxisId="left" type="monotone" dataKey="totalLoad" stroke="#059669" fill={`url(#colorScheduled-${dc.id})`} isAnimationActive={false} />
                            <Line yAxisId="right" type="monotone" dataKey="carbon_intensity" stroke="#FF0000" strokeWidth={2} dot={false} isAnimationActive={false} />
                            <Line yAxisId="left" type="monotone" dataKey="capacity" stroke="#a855f7" strokeWidth={2} dot={false} isAnimationActive={false} />

                            {intervals.filter(d => d.time.getHours() === 0 && d.time.getMinutes() === 0).map((d, k) => (
                              <ReferenceLine key={k} yAxisId="left" x={d.time.toISOString()} stroke="#94a3b8" strokeDasharray="4 4" label={i === 0 ? { position: "insideTopLeft", value: formatDateShort(d.time), fontSize: 10 } : undefined} />
                            ))}
                            {nowLineValue && (
                              <ReferenceLine yAxisId="left" x={nowLineValue} stroke="#f59e0b" strokeWidth={2} label={i === 0 ? { position: "insideTopRight", value: "Now", fontSize: 11, fontWeight: 600, fill: "#f59e0b" } : undefined} />
                            )}
                          </ComposedChart>
                        </ResponsiveContainer>
                      </div>
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