"use client"

import React, { useState, useEffect, useRef, useMemo, memo } from "react"
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
  timeMs: number
  jobs: { schedule_id: string; load: number }[]
  totalLoad: number
}

interface WorkloadCalendarProps {
  onClose?: () => void
  scheduleId?: string
}

const BLOCK_DURATION_MS = 5 * 60 * 1000

const formatDateShort = (date: Date) => date.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" })

interface DataCenterChartProps {
  dc: { id: string; name: string; backendLocation: string }
  intervals: AggregatedInterval[]
  dcForecastTimeseries: any[]
  nowLineValue: string | null
  globalSCIDomain: [number, number]
  isFirst: boolean
  isLast: boolean
  chartHeight: number
}

const DataCenterChart = memo(function DataCenterChart({
  dc,
  intervals,
  dcForecastTimeseries,
  nowLineValue,
  globalSCIDomain,
  isFirst,
  isLast,
  chartHeight
}: DataCenterChartProps) {
  const chartData = useMemo(() => {
    if (!intervals || intervals.length === 0) return []

    const mergedData = []
    let fIndex = 0
    const tsLen = dcForecastTimeseries.length

    for (let i = 0; i < intervals.length; i++) {
      const interval = intervals[i]
      const tTime = interval.timeMs // Use pre-calculated timestamp to avoid .getTime()

      let closestForecast = null
      if (tsLen > 0) {
        while (
          fIndex < tsLen - 1 &&
          new Date(dcForecastTimeseries[fIndex + 1].timestamp).getTime() <= tTime
        ) {
          fIndex++
        }
        const currTime = new Date(dcForecastTimeseries[fIndex].timestamp).getTime()
        if (currTime <= tTime) {
          closestForecast = dcForecastTimeseries[fIndex]
        }
      }

      const capacity = closestForecast ? scaleDataByConstantToPFLOP(closestForecast.capacity) : null
      const loadAmount = closestForecast ? scaleDataByConstantToPFLOP(closestForecast.load) : null

      // OPTIMIZATION: Use pre-calculated totalLoad instead of looping through jobs with .reduce()!
      const jobLoad = scaleDataByConstantToPFLOP(interval.totalLoad)

      const outsideLoadRange: [number, number] | null = (capacity !== null && loadAmount !== null)
        ? [Math.max(0, capacity - loadAmount), capacity] as [number, number]
        : null

      mergedData.push({
        time: interval.time.toISOString(),
        timestamp: tTime,
        totalLoad: jobLoad,
        rawJobs: interval.jobs,
        carbon_intensity: closestForecast ? closestForecast.carbon_intensity : null,
        load: loadAmount,
        capacity,
        outsideLoadRange
      })
    }

    // Flat-Line Data Decimation
    if (mergedData.length <= 2) return mergedData
    const pruned = [mergedData[0]]
    for (let i = 1; i < mergedData.length - 1; i++) {
      const prev = mergedData[i - 1]
      const curr = mergedData[i]
      const next = mergedData[i + 1]

      const isIdentical =
        prev.totalLoad === curr.totalLoad && curr.totalLoad === next.totalLoad &&
        prev.carbon_intensity === curr.carbon_intensity && curr.carbon_intensity === next.carbon_intensity &&
        prev.load === curr.load && curr.load === next.load &&
        prev.capacity === curr.capacity && curr.capacity === next.capacity &&
        prev.outsideLoadRange?.[0] === curr.outsideLoadRange?.[0] && curr.outsideLoadRange?.[0] === next.outsideLoadRange?.[0] &&
        prev.outsideLoadRange?.[1] === curr.outsideLoadRange?.[1] && curr.outsideLoadRange?.[1] === next.outsideLoadRange?.[1]

      if (!isIdentical) {
        pruned.push(curr)
      }
    }
    pruned.push(mergedData[mergedData.length - 1])

    return pruned
  }, [intervals, dcForecastTimeseries])

  const dynamicMaxValue = useMemo(() => {
    const maxDataValue = Math.max(50, ...chartData.flatMap((d: any) => [d.totalLoad, d.capacity || 0]))
    return Math.ceil(maxDataValue / 10) * 10
  }, [chartData])

  return (
    <div
      className="w-full chart-wrapper"
      style={{
        contentVisibility: "auto",
        containIntrinsicSize: `${chartHeight}px`
      } as React.CSSProperties}
    >
      <div className="mb-1 text-xs font-semibold text-foreground sticky left-0 z-20 bg-background pr-2 w-fit">
        {`${dc.id} - ${dc.name}`}
      </div>
      <div className="relative w-full" style={{ height: `${chartHeight}px` }}>
        <div className="absolute -left-10 top-0 bottom-0 flex flex-col justify-between text-[10px] text-muted-foreground z-10 w-8 text-right pr-2">
          <span>{dynamicMaxValue}</span><span>0</span>
        </div>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={chartData} margin={{ top: 0, right: 0, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id={`colorScheduled-${dc.id}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#059669" stopOpacity={0.8} />
                <stop offset="95%" stopColor="#059669" stopOpacity={0.1} />
              </linearGradient>
              <linearGradient id={`colorOutside-${dc.id}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.6} />
                <stop offset="95%" stopColor="#3b82f6" stopOpacity={0.2} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" vertical={false} opacity={0.3} />
            <XAxis
              dataKey="timestamp"
              type="number"
              scale="time"
              domain={['dataMin', 'dataMax']}
              tickFormatter={(time) => new Date(time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
              minTickGap={50}
              interval="preserveStartEnd"
              tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }}
              axisLine={false}
              tickLine={false}
              hide={!isLast}
            />
            <YAxis yAxisId="left" domain={[0, dynamicMaxValue]} hide={true} />
            <YAxis yAxisId="right" orientation="right" hide={true} domain={globalSCIDomain} />
            <Tooltip
              useTranslate3d={true}
              isAnimationActive={false}
              content={({ active, payload }) => {
                if (active && payload && payload.length) {
                  const data = payload[0].payload
                  return (
                    <div className="bg-popover text-popover-foreground text-xs rounded-md px-3 py-2 shadow-md border z-50">
                      <p className="font-medium border-b mb-1">
                        {new Date(data.time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                      </p>
                      {data.carbon_intensity != null && <p className="text-red-500 font-semibold">Carbon-Intensity: {Number(data.carbon_intensity).toFixed(2)}</p>}
                      {data.capacity != null && <p className="text-purple-600 font-semibold">Capacity: {Number(data.capacity).toFixed(1)} PFLO</p>}
                      {data.load != null && <p className="text-blue-500 font-semibold">Outside-Load: {Number(data.load).toFixed(1)} PFLO</p>}
                      <p className="text-muted-foreground mt-1">Job Load: {Number(data.totalLoad).toFixed(2)} PFLO</p>
                    </div>
                  )
                }
                return null
              }}
            />
            <Area yAxisId="left" type="monotone" dataKey="outsideLoadRange" stroke="#3b82f6" fill={`url(#colorOutside-${dc.id})`} fillOpacity={1} isAnimationActive={false} activeDot={false} />
            <Area yAxisId="left" type="monotone" dataKey="totalLoad" stroke="#059669" fill={`url(#colorScheduled-${dc.id})`} isAnimationActive={false} activeDot={{ r: 3, strokeWidth: 0, fill: "#059669" }} />
            <Line yAxisId="right" type="monotone" dataKey="carbon_intensity" stroke="#FF0000" strokeWidth={2} dot={false} isAnimationActive={false} activeDot={{ r: 3, strokeWidth: 0, fill: "#EE4000" }} />
            <Line yAxisId="left" type="monotone" dataKey="capacity" stroke="#a855f7" strokeWidth={2} dot={false} isAnimationActive={false} activeDot={false} />

            {intervals.filter(d => d.time.getHours() === 0 && d.time.getMinutes() === 0).map((d, k) => (
              <ReferenceLine
                key={k}
                yAxisId="left"
                x={d.timeMs}
                stroke="#94a3b8"
                strokeDasharray="4 4"
                label={isFirst ? { position: "insideTopLeft", value: formatDateShort(d.time), fontSize: 10 } : undefined}
              />
            ))}
            {nowLineValue && (
              <ReferenceLine
                yAxisId="left"
                x={new Date(nowLineValue).getTime()}
                stroke="#f59e0b"
                strokeWidth={2}
                label={isFirst ? { position: "insideTopRight", value: "Now", fontSize: 11, fontWeight: 600, fill: "#f59e0b" } : undefined}
              />
            )}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}, (prev, next) => {
  return prev.nowLineValue === next.nowLineValue &&
    prev.intervals === next.intervals &&
    prev.dcForecastTimeseries === next.dcForecastTimeseries &&
    prev.isLast === next.isLast &&
    prev.isFirst === next.isFirst &&
    prev.globalSCIDomain[0] === next.globalSCIDomain[0] &&
    prev.globalSCIDomain[1] === next.globalSCIDomain[1]
})

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

  // NOTE: Sequential Request Waterfall kept intact as requested.
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
        }
        // No schedules => no forecast fetch: the chart wouldn't render the data anyway
        // (intervalsPerDC early-returns empty when blocks is empty), and an unparameterized
        // /api/forecast call has been observed to take ~10s, blocking page interactivity.
      } catch (err) {
        console.error("Error fetching data:", err)
      } finally {
        setLoading(false)
      }
    }
    fetchData()
  }, [])

  const globalSCIDomain = useMemo(() => {
    if (!forecasts || forecasts.length === 0) return [0, 1] as [number, number]
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
    if (min === Infinity || max === -Infinity) return [0, 1] as [number, number]
    const padding = (max - min) * 0.05
    return [Math.max(0, min - padding), max + padding] as [number, number]
  }, [forecasts])

  // OPTIMIZATION: CPU-Freeze fix. O(1) mathematical block-to-interval routing.
  const { intervalsPerDC } = useMemo(() => {
    if (blocks.length === 0 || dataCenters.length === 0) {
      const defaultIntervals: Record<string, AggregatedInterval[]> = {}
      for (const dc of dataCenters) defaultIntervals[dc.id] = []
      return {
        intervalsPerDC: defaultIntervals,
        rangeStart: new Date(),
        rangeEnd: new Date(),
      }
    }

    // 1. Pre-parse all dates immediately to avoid GC freezes
    let minTime = Infinity
    let maxTime = -Infinity
    const parsedBlocks = blocks.map(b => {
      const startMs = new Date(b.timestamp).getTime()
      const endMs = startMs + BLOCK_DURATION_MS
      if (startMs < minTime) minTime = startMs
      if (endMs > maxTime) maxTime = endMs
      return { ...b, startMs, endMs }
    })

    // 2. Define strict boundaries
    const rangeStart = new Date(minTime)
    rangeStart.setMinutes(0, 0, 0)
    const rangeStartMs = rangeStart.getTime()

    const rangeEnd = new Date(maxTime)
    if (rangeEnd.getMinutes() > 0 || rangeEnd.getSeconds() > 0) {
      rangeEnd.setMinutes(0, 0, 0); rangeEnd.setHours(rangeEnd.getHours() + 1)
    }
    const rangeEndMs = rangeEnd.getTime()

    // 3. Initialize fast O(1) structures
    const intervalsPerDC: Record<string, any[]> = {}
    const dcLookup: Record<string, string> = {}

    for (const dc of dataCenters) {
      intervalsPerDC[dc.id] = []
      dcLookup[dc.backendLocation] = dc.id // Setup reverse mapping

      for (let t = rangeStartMs; t < rangeEndMs; t += BLOCK_DURATION_MS) {
        intervalsPerDC[dc.id].push({
          time: new Date(t),
          timeMs: t,
          jobMap: new Map(), // Temp map for deduplicating overlaps rapidly
          totalLoad: 0
        })
      }
    }

    // 4. Mathematical Array-Index matching (No nested iteration over intervals!)
    for (let i = 0; i < parsedBlocks.length; i++) {
      const block = parsedBlocks[i]
      const dcId = dcLookup[block.location]
      if (!dcId) continue

      const dcIntervals = intervalsPerDC[dcId]

      const startIdx = Math.max(0, Math.floor((block.startMs - rangeStartMs) / BLOCK_DURATION_MS))
      const endIdx = Math.floor((block.endMs - 1 - rangeStartMs) / BLOCK_DURATION_MS) // -1 prevents spillover

      for (let idx = startIdx; idx <= endIdx; idx++) {
        if (idx >= 0 && idx < dcIntervals.length) {
          const interval = dcIntervals[idx]
          const existingLoad = interval.jobMap.get(block.schedule_id) || 0
          interval.jobMap.set(block.schedule_id, existingLoad + block.additional_load)
        }
      }
    }

    // 5. Clean maps back into final standard Arrays & Precalculate load
    for (const dc of dataCenters) {
      for (let i = 0; i < intervalsPerDC[dc.id].length; i++) {
        const interval = intervalsPerDC[dc.id][i]
        let total = 0
        const jobs: { schedule_id: string; load: number }[] = []

        interval.jobMap.forEach((load: number, schedule_id: string) => {
          total += load
          jobs.push({ schedule_id, load })
        })

        interval.jobs = jobs
        interval.totalLoad = total // <--- Passed down cleanly
        delete interval.jobMap
      }
    }

    return { intervalsPerDC, rangeStart, rangeEnd }
  }, [blocks, dataCenters])

  const chartHeight = 120
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
      const diff = Math.abs(d.timeMs - now)
      if (diff < closestDiff) {
        closestDiff = diff
        closest = d.time.toISOString()
      }
    }
    return closest && closestDiff < 5 * 60 * 1000 ? closest : null
  }, [sampleIntervals, firstDcId])

  const forecastLookupMap = useMemo(() => {
    const map = new Map<string, any[]>()
    forecasts.forEach(f => map.set(f.location, f.timeseries || []))
    return map
  }, [forecasts])

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

  return (
    <Card className="border-2 shadow-lg">
      <CardHeader className="flex flex-row items-start justify-between">
        <div>
          <CardTitle className="flex items-center gap-2">
            <CalendarIcon className="h-5 w-5 text-primary" />Workload Calendar
          </CardTitle>
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
                  const intervals = intervalsPerDC[dc.id] || []
                  const dcForecastTimeseries = forecastLookupMap.get(dc.backendLocation) || []

                  return (
                    <DataCenterChart
                      key={dc.id}
                      dc={dc}
                      intervals={intervals}
                      dcForecastTimeseries={dcForecastTimeseries}
                      nowLineValue={nowLineValue}
                      globalSCIDomain={globalSCIDomain}
                      isFirst={i === 0}
                      isLast={i === dataCenters.length - 1}
                      chartHeight={chartHeight}
                    />
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