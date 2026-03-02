"use client"

import { useState, useEffect, useRef, useMemo } from "react"
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
import { Area, ComposedChart, Line, CartesianGrid, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine } from "recharts"
import { JobScheduleResponse, ScheduleData, ScheduleBlock } from "../types/schedule"

interface WorkloadInterval {
  time: string
  existing: number
  newJob: number
  greeness?: number | null
  load?: number | null
}

interface ScheduleResultProps {
  result: JobScheduleResponse
  unoptimizedResult?: ScheduleData
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

function locationToDcId(location: string): string | undefined {
  const dc = DATA_CENTERS.find(d => d.backendLocation === location)
  return dc?.id
}

function convertBlocksToWorkload(blocks: any[], start: Date, end: Date, newScheduleId?: string) {
  const intervalMs = 5 * 60 * 1000
  const intervals: WorkloadInterval[] = []

  for (let t = start.getTime(); t <= end.getTime(); t += intervalMs) {
    const timestamp = new Date(t)
    const intervalStart = t

    const matching = blocks.filter(b => {
      if (!b || !b.timestamp) return false
      const blockTime = new Date(b.timestamp).getTime()
      return Math.abs(blockTime - intervalStart) < 60000
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

export function ScheduleResult({ result, unoptimizedResult, earliestStart, latestFinish, onBack, onCancel }: ScheduleResultProps) {
  const [selectedDC, setSelectedDC] = useState(DATA_CENTERS[0].id)
  const [workloadData, setWorkloadData] = useState<WorkloadInterval[]>([])
  const [loading, setLoading] = useState(false)
  const [cancelling, setCancelling] = useState(false)
  const [allBlocks, setAllBlocks] = useState<any[]>([])
  const [showTrivial, setShowTrivial] = useState(false)
  const [forecasts, setForecasts] = useState<any[]>([])

  const [fetchedOptData, setFetchedOptData] = useState<any>(null)
  const [fetchedUnoptData, setFetchedUnoptData] = useState<ScheduleData | null>(null)

  const globalGreennessDomain = useMemo(() => {
    if (!forecasts || forecasts.length === 0) return [0, 1]
    let min = Infinity
    let max = -Infinity
    forecasts.forEach(dc => {
      dc.timeseries?.forEach((point: any) => {
        if (typeof point.greeness === "number") {
          min = Math.min(min, point.greeness)
          max = Math.max(max, point.greeness)
        }
      })
    })
    if (min === Infinity || max === -Infinity) return [0, 1]
    const padding = (max - min) * 0.05
    return [min - padding, max + padding]
  }, [forecasts])

  const optData = fetchedOptData || result
  let unoptData = fetchedUnoptData || unoptimizedResult || null

  if (unoptData && (('error' in unoptData) || (unoptData.scheduled_blocks && unoptData.scheduled_blocks.length === 0))) {
    if ('error' in unoptData || (unoptData.scheduled_blocks && unoptData.scheduled_blocks.length === 0)) {
      unoptData = null;
    }
  }

  const activeImpact = showTrivial && unoptData ? unoptData.impact : optData.impact
  const carbonIntensity = activeImpact?.carbon_intensity
  const totalEmissions = activeImpact?.total_emissions
  const sci = activeImpact?.sci

  const unoptimizedComparison = {
    carbon_intensity: unoptData?.impact?.carbon_intensity,
    total_emissions: unoptData?.impact?.total_emissions,
    sci: unoptData?.impact?.sci,
  }

  const getTimeRange = (blocks?: any[]) => {
    const jobBlocksFromState = allBlocks.filter(b => b.schedule_id === result.schedule_id);
    const trivialBlocksFromState = allBlocks.filter(b => b.schedule_id === `${result.schedule_id}_trivial`);
    const optBlocks = blocks ? blocks.filter(b => b.schedule_id === result.schedule_id) : (jobBlocksFromState.length > 0 ? jobBlocksFromState : (result.scheduled_blocks || []));
    const unoptBlocks = blocks ? blocks.filter(b => b.schedule_id === `${result.schedule_id}_trivial`) : (trivialBlocksFromState.length > 0 ? trivialBlocksFromState : (unoptData?.scheduled_blocks || []));
    const allRelevantBlocks = [...optBlocks, ...unoptBlocks];

    if (allRelevantBlocks.length > 0) {
      const timestamps = allRelevantBlocks.map((b: any) => new Date(b.timestamp).getTime())
      return {
        start: new Date(Math.min(...timestamps) - 15 * 60 * 1000),
        end: new Date(Math.max(...timestamps) + 20 * 60 * 1000)
      }
    }
    if (earliestStart && latestFinish) {
      return {
        start: new Date(new Date(earliestStart).getTime() - 15 * 60 * 1000),
        end: new Date(new Date(latestFinish).getTime() + 15 * 60 * 1000)
      }
    }
    const now = new Date()
    now.setHours(8, 0, 0, 0)
    return { start: now, end: new Date(now.getTime() + 4 * 60 * 60 * 1000) }
  }

  useEffect(() => {
    const loadBlocks = async () => {
      setLoading(true)
      try {
        let newJobBlocks: any[] = [];
        let unoptJobBlocks: any[] = [];
        const [scheduleRes, trivialRes, forecastRes] = await Promise.all([
          fetch(`/api/schedules/${result.schedule_id}`),
          fetch(`/api/schedules/${result.schedule_id}/trivial`).catch(() => null),
          fetch(`/api/forecast`)
        ])

        if (!scheduleRes.ok) throw new Error(`Failed to fetch schedule: ${scheduleRes.status}`)
        const scheduleData = await scheduleRes.json()
        setFetchedOptData(scheduleData)
        newJobBlocks = Array.isArray(scheduleData.scheduled_blocks) ? scheduleData.scheduled_blocks : []

        if (trivialRes && trivialRes.ok) {
          const trivialData = await trivialRes.json();
          if (trivialData && Array.isArray(trivialData.scheduled_blocks)) {
            unoptJobBlocks = trivialData.scheduled_blocks;
            setFetchedUnoptData(trivialData);
          }
        }

        const { start, end } = getTimeRange([...newJobBlocks, ...unoptJobBlocks])
        const allRes = await fetch(`/api/schedules?start_time=${encodeURIComponent(start.toISOString())}&end_time=${encodeURIComponent(end.toISOString())}`)
        if (!allRes.ok) throw new Error(`Failed to fetch window schedules: ${allRes.status}`)
        const allData = await allRes.json()
        const allBlocksRaw = Array.isArray(allData) ? allData : []

        let combinedWithNewJob = [...allBlocksRaw]
        for (const block of newJobBlocks) {
          if (!combinedWithNewJob.find((b: any) => b.timestamp === block.timestamp && b.schedule_id === block.schedule_id)) {
            combinedWithNewJob.push(block)
          }
        }
        if (unoptJobBlocks.length > 0) {
          for (const block of unoptJobBlocks) {
            const trivialBlock = { ...block, schedule_id: `${block.schedule_id}_trivial` }
            if (!combinedWithNewJob.find((b: any) => b.timestamp === trivialBlock.timestamp && b.schedule_id === trivialBlock.schedule_id)) {
              combinedWithNewJob.push(trivialBlock)
            }
          }
        }
        setAllBlocks(combinedWithNewJob)

        if (newJobBlocks.length > 0) {
          const hasLoadOnCurrentDc = newJobBlocks.some((b: any) => locationToDcId(b.location) === selectedDC);
          if (!hasLoadOnCurrentDc) {
            const firstActiveDc = locationToDcId(newJobBlocks[0].location);
            if (firstActiveDc) setSelectedDC(firstActiveDc);
          }
        }

        if (forecastRes && forecastRes.ok) {
          const forecastData = await forecastRes.json()
          setForecasts(Array.isArray(forecastData) ? forecastData : [])
        }
      } catch (err) {
        console.error("Failed to load blocks", err)
      } finally {
        setLoading(false)
      }
    }
    loadBlocks()
  }, [result.schedule_id])

  useEffect(() => {
    const { start, end } = getTimeRange()
    const dcBlocks = allBlocks.filter((b: any) => locationToDcId(b.location) === selectedDC)
    const newJobScheduleId = showTrivial && unoptData ? `${unoptData.schedule_id}_trivial` : result.schedule_id
    const otherVariantScheduleId = showTrivial && unoptData ? result.schedule_id : `${unoptData?.schedule_id}_trivial`
    const realBlocks = dcBlocks.filter((b: any) => b.schedule_id !== otherVariantScheduleId)

    const selectedBackendLocation = DATA_CENTERS.find(d => d.id === selectedDC)?.backendLocation
    const dcForecastTimeseries = forecasts.find(f => f.location === selectedBackendLocation)?.timeseries || []

    const intervals = convertBlocksToWorkload(realBlocks, start, end, newJobScheduleId)
      .map(interval => {
        const tTime = new Date(interval.time).getTime()
        const closestForecast = dcForecastTimeseries.reduce((prev: any, curr: any) => {
          const currTime = new Date(curr.timestamp).getTime()
          if (currTime <= tTime) return curr
          return prev
        }, null)

        return {
          ...interval,
          greeness: closestForecast ? closestForecast.greeness : null,
          load: closestForecast ? closestForecast.load : null
        }
      })
    setWorkloadData(intervals)
  }, [selectedDC, allBlocks, result.schedule_id, showTrivial, unoptData, forecasts])

  const handleCancel = async () => {
    setCancelling(true)
    try {
      await fetch(`/api/schedules/${result.schedule_id}`, { method: "DELETE" })
      onCancel?.()
    } catch (error) {
      onCancel?.()
    } finally {
      setCancelling(false)
    }
  }

  const formatTime = (isoString: string) => new Date(isoString).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" })
  const formatDateTime = (isoString: string) => new Date(isoString).toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })

  const maxValue = 50
  const { start: rangeStart, end: rangeEnd } = getTimeRange()

  return (
    <div className="space-y-6">
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
              {cancelling ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
              Cancel Job
            </Button>
          </AlertDialogTrigger>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Cancel Scheduled Job?</AlertDialogTitle>
              <AlertDialogDescription>
                This will remove the job (ID: {result.schedule_id}) from the schedule.
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

      {(carbonIntensity !== undefined || totalEmissions !== undefined || sci !== undefined) && (
        <Card className={`border-2 ${showTrivial ? "border-orange-200 bg-orange-50/50" : "border-primary/20 bg-primary/5"}`}>
          <CardHeader className="pb-2">
            <div className="flex flex-row items-center justify-between">
              <div className="flex items-center gap-2">
                {showTrivial ? <TrendingDown className="h-5 w-5 text-orange-600" /> : <Leaf className="h-5 w-5 text-primary" />}
                <CardTitle>Environmental Impact</CardTitle>
              </div>
              {unoptData && (
                <div className="flex items-center gap-2 text-sm bg-background p-1 rounded-md border">
                  <Button variant={!showTrivial ? "default" : "ghost"} size="sm" onClick={() => setShowTrivial(false)}>Optimised</Button>
                  <Button variant={showTrivial ? "default" : "ghost"} size="sm" onClick={() => setShowTrivial(true)}>Unoptimised</Button>
                </div>
              )}
            </div>
          </CardHeader>
          <CardContent className="pt-0">
            <div className="grid gap-4 sm:grid-cols-3">
              {/* Carbon Intensity Card */}
              <div className="rounded-lg bg-background p-4 space-y-1 relative overflow-hidden">
                {!showTrivial && unoptimizedComparison.carbon_intensity && (
                  <div className="absolute top-2 right-2 flex items-center gap-0.5 text-[10px] font-medium text-emerald-600 bg-emerald-50 px-1.5 py-0.5 rounded-full border border-emerald-100">
                    {-Math.max(0, ((unoptimizedComparison.carbon_intensity - (carbonIntensity || 0)) / unoptimizedComparison.carbon_intensity) * 100).toFixed(0)}%
                  </div>
                )}
                <p className="text-xs text-muted-foreground">Carbon Intensity</p>
                <p className={`text-3xl font-bold ${showTrivial ? "text-orange-600" : "text-primary"}`}>{carbonIntensity?.toFixed(3)}</p>
                <p className="text-xs text-muted-foreground">g CO2/kWh</p>
              </div>

              {/* Total Emissions Card */}
              <div className="rounded-lg bg-background p-4 space-y-1 relative overflow-hidden">
                {!showTrivial && unoptimizedComparison.total_emissions && (
                  <div className="absolute top-2 right-2 flex items-center gap-0.5 text-[10px] font-medium text-emerald-600 bg-emerald-50 px-1.5 py-0.5 rounded-full border border-emerald-100">
                    {-Math.max(0, ((unoptimizedComparison.total_emissions - (totalEmissions || 0)) / unoptimizedComparison.total_emissions) * 100).toFixed(0)}%
                  </div>
                )}
                <p className="text-xs text-muted-foreground">Total Emissions</p>
                <p className={`text-3xl font-bold ${showTrivial ? "text-orange-600" : "text-primary"}`}>{totalEmissions?.toFixed(2)}</p>
                <p className="text-xs text-muted-foreground">g CO2</p>
              </div>

              {/* SCI Card */}
              <div className="rounded-lg bg-background p-4 space-y-1 relative overflow-hidden">
                {!showTrivial && unoptimizedComparison.sci && (
                  <div className="absolute top-2 right-2 flex items-center gap-0.5 text-[10px] font-medium text-emerald-600 bg-emerald-50 px-1.5 py-0.5 rounded-full border border-emerald-100">
                    {-Math.max(0, ((unoptimizedComparison.sci - (sci || 0)) / unoptimizedComparison.sci) * 100).toFixed(0)}%
                  </div>
                )}
                <p className="text-xs text-muted-foreground">SCI per Unit</p>
                <p className={`text-3xl font-bold ${showTrivial ? "text-orange-600" : "text-primary"}`}>{sci?.toFixed(2)}</p>
                <p className="text-xs text-muted-foreground">g CO2e/unit</p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <div className="flex flex-row items-center justify-between">
            <div>
              <CardTitle>Data Centre Workload Distribution</CardTitle>
              <CardDescription>
                Showing workload from {formatDateTime(rangeStart.toISOString())} to {formatDateTime(rangeEnd.toISOString())}
              </CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <Tabs value={selectedDC} onValueChange={setSelectedDC}>
            <TabsList className="grid w-full grid-cols-5">
              {DATA_CENTERS.map((dc) => (
                <TabsTrigger key={dc.id} value={dc.id} className="text-xs sm:text-sm">DC {dc.id.slice(-1)}</TabsTrigger>
              ))}
            </TabsList>
          </Tabs>

          <div className="flex flex-wrap items-center gap-6 text-sm">
            <div className="flex items-center gap-2">
              <div className="h-3 w-3 rounded bg-gray-400" />
              <span className="text-muted-foreground">Existing</span>
            </div>
            <div className="flex items-center gap-2">
              <div className={`h-3 w-3 rounded ${showTrivial ? "bg-orange-500" : "bg-emerald-500"}`} />
              <span className="text-muted-foreground">{showTrivial ? "Unoptimised" : "Optimised"}</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="h-1 w-4 rounded bg-emerald-500" />
              <span className="text-muted-foreground">Greenness</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="h-1 w-4 rounded bg-blue-400" />
              <span className="text-muted-foreground">Outside-Load</span>
            </div>
          </div>

          {loading ? (
            <div className="flex items-center justify-center h-64"><Loader2 className="h-8 w-8 animate-spin text-muted-foreground" /></div>
          ) : (
            <div className="h-[250px] w-full mt-4">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={workloadData} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
                  <defs>
                    <linearGradient id="colorExisting" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#9ca3af" stopOpacity={0.8} />
                      <stop offset="95%" stopColor="#9ca3af" stopOpacity={0.1} />
                    </linearGradient>
                    <linearGradient id="colorNew" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor={showTrivial ? "#f97316" : "#10b981"} stopOpacity={0.8} />
                      <stop offset="95%" stopColor={showTrivial ? "#f97316" : "#10b981"} stopOpacity={0.1} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} opacity={0.3} />
                  <XAxis dataKey="time" tickFormatter={(time) => formatTime(time)} tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }} minTickGap={30} axisLine={false} tickLine={false} />
                  <YAxis yAxisId="left" domain={[0, maxValue]} tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }} axisLine={false} tickLine={false} width={30} />
                  <YAxis yAxisId="right" orientation="right" hide={true} domain={globalGreennessDomain} />
                  <Tooltip
                    content={({ active, payload, label }) => {
                      if (active && payload && payload.length) {
                        const data = payload[0]?.payload
                        return (
                          <div className="bg-popover text-popover-foreground text-xs rounded-md px-3 py-2 shadow-md border">
                            <p className="font-medium mb-1 border-b pb-1">{formatTime(label)}</p>
                            {data?.greeness != null && <p className="text-emerald-500 font-semibold">Greenness: {Number(data.greeness).toFixed(2)}</p>}
                            {data?.load != null && <p className="text-blue-500 font-semibold">Load: {Number(data.load).toFixed(2)}</p>}
                            {payload.map((entry, index) => {
                              if (entry.value === 0 || entry.dataKey === "greeness" || entry.dataKey === "load") return null
                              return (
                                <div key={index} className="flex justify-between gap-4">
                                  <span className="flex items-center gap-1.5">
                                    <div className="w-2 h-2 rounded-full" style={{ backgroundColor: entry.color }} />
                                    <span className="text-muted-foreground">{entry.dataKey === "newJob" ? (showTrivial ? "Unoptimised" : "Optimised") : "Existing"}</span>
                                  </span>
                                  <span className="font-medium">{Number(entry.value).toFixed(1)} kWh</span>
                                </div>
                              )
                            })}
                          </div>
                        )
                      }
                      return null
                    }}
                  />
                  <Area yAxisId="left" type="monotone" dataKey="existing" stackId="1" stroke="#9ca3af" fill="url(#colorExisting)" isAnimationActive={false} />
                  <Area yAxisId="left" type="monotone" dataKey="newJob" stackId="1" stroke={showTrivial ? "#ea580c" : "#059669"} fill="url(#colorNew)" isAnimationActive={false} />
                  <Line yAxisId="right" type="monotone" dataKey="greeness" stroke="#10b981" strokeWidth={2} dot={false} isAnimationActive={false} />
                  <Line yAxisId="left" type="monotone" dataKey="load" stroke="#3b82f6" strokeWidth={2} dot={false} isAnimationActive={false} />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          )}
        </CardContent>
      </Card>
      <div className="text-sm text-muted-foreground px-1">
        <span className="text-foreground font-medium">Schedule ID:</span> <span className="font-mono">{result.schedule_id}</span>
      </div>
    </div>
  )
}