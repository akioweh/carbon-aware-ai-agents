"use client"

import { useState, useEffect, useRef } from "react"
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
import { Area, Line, ComposedChart, CartesianGrid, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine } from "recharts"
import { JobScheduleResponse, ScheduleData, ScheduleBlock } from "../types/schedule"

interface WorkloadInterval {
  time: string
  existing: number
  newJob: number
  greenness?: number
}

interface ScheduleResultProps {
  result: JobScheduleResponse
  unoptimizedResult?: ScheduleData
  // User's input time range
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

// Map location strings to DC IDs
function locationToDcId(location: string): string | undefined {
  const dc = DATA_CENTERS.find(d => d.backendLocation === location)
  return dc?.id
}

// At the top of ScheduleResult.tsx, outside the component
function convertBlocksToWorkload(blocks: any[], start: Date, end: Date, newScheduleId?: string, greennessData?: any[]) {
  const intervalMs = 5 * 60 * 1000
  const intervals: WorkloadInterval[] = []

  for (let t = start.getTime(); t <= end.getTime(); t += intervalMs) {
    const timestamp = new Date(t)
    const intervalStart = t
    const intervalEnd = t + intervalMs

    // Consider a block part of this interval if it overlaps the interval window
    // (We match exact timestamp since blocks are exactly 5 mins long)
    const matching = blocks.filter(b => {
      if (!b || !b.timestamp) return false
      const blockTime = new Date(b.timestamp).getTime()
      // Give a little leeway for parsing inconsistencies
      return Math.abs(blockTime - intervalStart) < 60000
    })

    const existing = matching
      .filter(b => b.schedule_id !== newScheduleId)
      .reduce((sum, b) => sum + (typeof b.additional_load === 'number' ? b.additional_load : 0), 0)

    const newJob = matching
      .filter(b => b.schedule_id === newScheduleId)
      .reduce((sum, b) => sum + (typeof b.additional_load === 'number' ? b.additional_load : 0), 0)

    let currentGreenness = undefined;
    if (greennessData && greennessData.length > 0) {
      const pastPoints = greennessData.filter(g => new Date(g.timestamp).getTime() <= t);
      if (pastPoints.length > 0) {
        currentGreenness = pastPoints[pastPoints.length - 1].value;
      } else {
        currentGreenness = greennessData[0].value;
      }
    }

    intervals.push({
      time: timestamp.toISOString(),
      existing,
      newJob,
      greenness: currentGreenness
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

export function ScheduleResult({ result, unoptimizedResult, earliestStart, latestFinish, onBack, onCancel }: ScheduleResultProps) {
  const [selectedDC, setSelectedDC] = useState(DATA_CENTERS[0].id)
  const [workloadData, setWorkloadData] = useState<WorkloadInterval[]>([])
  const [loading, setLoading] = useState(false)
  const [cancelling, setCancelling] = useState(false)
  const [allBlocks, setAllBlocks] = useState<any[]>([])
  const [greennessCache, setGreennessCache] = useState<Record<string, any[]>>({})
  const [showTrivial, setShowTrivial] = useState(false)
  const scrollContainerRef = useRef<HTMLDivElement>(null)

  const [fetchedOptData, setFetchedOptData] = useState<any>(null)
  const [fetchedUnoptData, setFetchedUnoptData] = useState<ScheduleData | null>(null)

  // Use fetched data if we have it (since POST might only return an ID now), otherwise fallback to props
  const optData = fetchedOptData || result

  // Use unoptimizedResult prop, or fetched data
  let unoptData = fetchedUnoptData || unoptimizedResult || null

  // Clean up if it's an error object or if the array of blocks is totally empty
  if (unoptData && (('error' in unoptData) || (unoptData.scheduled_blocks && unoptData.scheduled_blocks.length === 0))) {
    // Only clean up if it's explicitly an error or if we have blocks and they are empty
    // If blocks are undefined (like from summary), keep it!
    if ('error' in unoptData || (unoptData.scheduled_blocks && unoptData.scheduled_blocks.length === 0)) {
      unoptData = null;
    }
  }

  // Get impact values
  const activeImpact = showTrivial && unoptData ? unoptData.impact : optData.impact
  const carbonIntensity = activeImpact?.carbon_intensity
  const totalEmissions = activeImpact?.total_emissions
  const sci = activeImpact?.sci

  // Get unoptimized comparison values for savings calculation
  const optEmissions = optData.impact?.total_emissions
  const unoptEmissions = unoptData?.impact?.total_emissions
  const emissionsSavings = optEmissions && unoptEmissions && unoptEmissions > optEmissions
    ? ((unoptEmissions - optEmissions) / unoptEmissions) * 100
    : 0

  // Fallback for unoptimizedComparison that the UI below expects
  const unoptimizedComparison = {
    carbon_intensity: unoptData?.impact?.carbon_intensity,
    total_emissions: unoptData?.impact?.total_emissions,
    sci: unoptData?.impact?.sci,
  }

  const getTimeRange = (blocks?: any[]) => {
    // We try to find the full bounds of the specific job's actual scheduled blocks.
    // If the backend didn't supply them in `result.scheduled_blocks` (e.g. to save bandwidth on POST),
    // they should be inside the `allBlocks` state, or passed in via the `blocks` parameter during the initial fetch.
    const jobBlocksFromState = allBlocks.filter(b => b.schedule_id === result.schedule_id);
    const trivialBlocksFromState = allBlocks.filter(b => b.schedule_id === `${result.schedule_id}_trivial`);

    const optBlocks = blocks ? blocks.filter(b => b.schedule_id === result.schedule_id) : (jobBlocksFromState.length > 0 ? jobBlocksFromState : (result.scheduled_blocks || []));
    const unoptBlocks = blocks ? blocks.filter(b => b.schedule_id === `${result.schedule_id}_trivial`) : (trivialBlocksFromState.length > 0 ? trivialBlocksFromState : (unoptData?.scheduled_blocks || []));
    const allRelevantBlocks = [...optBlocks, ...unoptBlocks];

    if (allRelevantBlocks.length > 0) {
      const timestamps = allRelevantBlocks.map((b: any) => new Date(b.timestamp).getTime())
      return {
        // Add 15 minutes padding to start and 20 minutes padding to end
        start: new Date(Math.min(...timestamps) - 15 * 60 * 1000),
        end: new Date(Math.max(...timestamps) + 20 * 60 * 1000)
      }
    }

    // If the user's explicit requested time window is available, use that as the fallback bounding box!
    if (earliestStart && latestFinish) {
      return {
        start: new Date(new Date(earliestStart).getTime() - 15 * 60 * 1000),
        end: new Date(new Date(latestFinish).getTime() + 15 * 60 * 1000)
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

  // Fetch: (1) the specific job's blocks and trivial blocks, (2) windowed existing blocks, then combine
  useEffect(() => {
    const loadBlocks = async () => {
      setLoading(true)
      try {
        let newJobBlocks: any[] = [];
        let unoptJobBlocks: any[] = [];

        // Fetch specific schedule details and its trivial baseline
        const [scheduleRes, trivialRes, ...greennessRes] = await Promise.all([
          fetch(`/api/schedules/${result.schedule_id}`),
          fetch(`/api/schedules/${result.schedule_id}/trivial`).catch(() => null),
          ...DATA_CENTERS.map(dc => fetch(`/api/locations/${dc.backendLocation}/greenness`).then(res => res.ok ? res.json() : null).catch(() => null))
        ])

        const newGreenness: Record<string, any[]> = {}
        DATA_CENTERS.forEach((dc, i) => {
          if (greennessRes[i] && greennessRes[i].data) {
            newGreenness[dc.id] = greennessRes[i].data
          } else {
            newGreenness[dc.id] = []
          }
        })
        setGreennessCache(newGreenness)

        if (!scheduleRes.ok) {
          throw new Error(`Failed to fetch schedule: ${scheduleRes.status}`)
        }

        const scheduleData = await scheduleRes.json()
        setFetchedOptData(scheduleData)
        newJobBlocks = Array.isArray(scheduleData.scheduled_blocks)
          ? scheduleData.scheduled_blocks
          : []

        if (trivialRes && trivialRes.ok) {
          const trivialData = await trivialRes.json();
          if (trivialData && Array.isArray(trivialData.scheduled_blocks)) {
            unoptJobBlocks = trivialData.scheduled_blocks;
            setFetchedUnoptData(trivialData);
          }
        }

        // Get the time range to limit the background workload fetch
        const { start, end } = getTimeRange([...newJobBlocks, ...unoptJobBlocks])

        // Fetch blocks in the time window to get existing workload
        const startQuery = `start_time=${encodeURIComponent(start.toISOString())}`
        const endQuery = `end_time=${encodeURIComponent(end.toISOString())}`
        const allRes = await fetch(`/api/schedules?${startQuery}&${endQuery}`)

        if (!allRes.ok) {
          throw new Error(`Failed to fetch window schedules: ${allRes.status}`)
        }
        const allData = await allRes.json()
        const allBlocksRaw = Array.isArray(allData) ? allData : []

        // Combine: mark new job blocks and include all blocks
        const combined = allBlocksRaw.map((b: any) => ({
          ...b,
        }))

        // Add new job blocks if not already included
        let combinedWithNewJob = [...combined]
        for (const block of newJobBlocks) {
          if (!combinedWithNewJob.find((b: any) =>
            b.timestamp === block.timestamp &&
            b.schedule_id === block.schedule_id
          )) {
            combinedWithNewJob.push(block)
          }
        }

        if (unoptJobBlocks.length > 0) {
          for (const block of unoptJobBlocks) {
            // Attach a suffix to distinguish trivial blocks from actual blocks since they share the same ID
            const trivialBlock = { ...block, schedule_id: `${block.schedule_id}_trivial` }
            if (!combinedWithNewJob.find((b: any) =>
              b.timestamp === trivialBlock.timestamp &&
              b.schedule_id === trivialBlock.schedule_id
            )) {
              combinedWithNewJob.push(trivialBlock)
            }
          }
        }

        setAllBlocks(combinedWithNewJob)

        // Auto-select a data center that actually has workload if current selected DC has none
        if (newJobBlocks.length > 0) {
          const hasLoadOnCurrentDc = newJobBlocks.some((b: any) => locationToDcId(b.location) === selectedDC);
          if (!hasLoadOnCurrentDc) {
            const firstActiveDc = locationToDcId(newJobBlocks[0].location);
            if (firstActiveDc) {
              setSelectedDC(firstActiveDc);
            }
          }
        }
      } catch (err) {
        console.error("Failed to load blocks", err)
        setAllBlocks([])
      } finally {
        setLoading(false)
      }
    }

    loadBlocks()
  }, [result.schedule_id])

  // Update workload data when data center changes (uses cached allBlocks)
  useEffect(() => {
    // Get the dynamic bounds of whatever is loaded so far!
    const { start, end } = getTimeRange()

    // Filter blocks by selected DC using backend location name
    const dcBlocks = allBlocks.filter(
      (b: any) => locationToDcId(b.location) === selectedDC
    )

    // Use schedule_id to identify new job blocks
    const newJobScheduleId = showTrivial && unoptData ? `${unoptData.schedule_id}_trivial` : result.schedule_id

    // Filter out blocks that belong to the "other" variant of this job
    const otherVariantScheduleId = showTrivial && unoptData ? result.schedule_id : `${unoptData?.schedule_id}_trivial`
    const realBlocks = dcBlocks.filter((b: any) => b.schedule_id !== otherVariantScheduleId)

    // Convert blocks → workload intervals for chart
    const intervals = convertBlocksToWorkload(realBlocks, start, end, newJobScheduleId, greennessCache[selectedDC])

    // Fill empty arrays with 0s so Recharts doesn't look completely blank when there's no data
    if (intervals.length > 0 && intervals.every(i => i.existing === 0 && i.newJob === 0)) {
      // This just makes sure Recharts has something to draw at baseline
    }

    setWorkloadData(intervals)
  }, [selectedDC, allBlocks, result.schedule_id, showTrivial, unoptData, greennessCache])

  const handleCancel = async () => {
    setCancelling(true)
    try {
      const response = await fetch(`/api/schedules/${result.schedule_id}`, {
        method: "DELETE",
      })

      if (response.ok) {
        onCancel?.()
      } else {
        onCancel?.()
      }
    } catch (error) {
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

  // Fixed Y-axis: all data centers have capacity of 50
  const maxValue = 50
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
              <AlertDialogAction onClick={handleCancel} className="bg-destructive text-white hover:bg-destructive/90">
                Cancel Job
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </div>

      {/* Impact Overview (Consolidated) */}
      {(carbonIntensity !== undefined || totalEmissions !== undefined || sci !== undefined) && (
        <Card className={`border-2 ${showTrivial ? "border-orange-200 bg-orange-50/50" : "border-primary/20 bg-primary/5"}`}>
          <CardHeader className="pb-2">
            <div className="flex flex-row items-center justify-between">
              <div className="flex items-center gap-2">
                {showTrivial ? (
                  <TrendingDown className="h-5 w-5 text-orange-600" />
                ) : (
                  <Leaf className="h-5 w-5 text-primary" />
                )}
                <CardTitle>Environmental Impact</CardTitle>
              </div>

              {unoptData && (
                <div className="flex items-center gap-2 text-sm bg-background p-1 rounded-md border">
                  <Button
                    variant={!showTrivial ? "default" : "ghost"}
                    size="sm"
                    className="h-8"
                    onClick={() => setShowTrivial(false)}
                  >
                    Optimised
                  </Button>
                  <Button
                    variant={showTrivial ? "default" : "ghost"}
                    size="sm"
                    className="h-8"
                    onClick={() => setShowTrivial(true)}
                  >
                    Unoptimised
                  </Button>
                </div>
              )}
            </div>
            <CardDescription className="mb-2">
              {showTrivial
                ? "Estimated carbon footprint for the unoptimised baseline schedule"
                : "Estimated carbon footprint for this scheduled job"}
            </CardDescription>
          </CardHeader>
          <CardContent className="pt-0">
            <div className="grid gap-4 sm:grid-cols-3">
              {carbonIntensity !== undefined && (
                <div className="rounded-lg bg-background p-4 space-y-1 relative overflow-hidden">
                  <p className="text-xs text-muted-foreground">Carbon Intensity</p>
                  <p className={`text-3xl font-bold ${showTrivial ? "text-orange-600" : "text-primary"}`}>{carbonIntensity.toFixed(3)}</p>
                  <p className="text-xs text-muted-foreground">kg CO2/kWh</p>
                  {!showTrivial && unoptimizedComparison.carbon_intensity && unoptimizedComparison.carbon_intensity > carbonIntensity && (
                    <div className="absolute top-2 right-2 bg-emerald-100 text-emerald-700 text-[10px] font-bold px-1.5 py-0.5 rounded">
                      -{(((unoptimizedComparison.carbon_intensity - carbonIntensity) / unoptimizedComparison.carbon_intensity) * 100).toFixed(0)}%
                    </div>
                  )}
                </div>
              )}

              {totalEmissions !== undefined && (
                <div className="rounded-lg bg-background p-4 space-y-1 relative overflow-hidden">
                  <p className="text-xs text-muted-foreground">Total Emissions</p>
                  <p className={`text-3xl font-bold ${showTrivial ? "text-orange-600" : "text-primary"}`}>{totalEmissions.toFixed(2)}</p>
                  <p className="text-xs text-muted-foreground">kg CO2</p>
                  {!showTrivial && unoptimizedComparison.total_emissions && unoptimizedComparison.total_emissions > totalEmissions && (
                    <div className="absolute top-2 right-2 bg-emerald-100 text-emerald-700 text-[10px] font-bold px-1.5 py-0.5 rounded">
                      -{(((unoptimizedComparison.total_emissions - totalEmissions) / unoptimizedComparison.total_emissions) * 100).toFixed(0)}%
                    </div>
                  )}
                </div>
              )}

              {sci !== undefined && (
                <div className="rounded-lg bg-background p-4 space-y-1 relative overflow-hidden">
                  <p className="text-xs text-muted-foreground">SCI per Unit</p>
                  <p className={`text-3xl font-bold ${showTrivial ? "text-orange-600" : "text-primary"}`}>{sci.toFixed(2)}</p>
                  <p className="text-xs text-muted-foreground">kg CO2e/unit</p>
                  {!showTrivial && unoptimizedComparison.sci && unoptimizedComparison.sci > sci && (
                    <div className="absolute top-2 right-2 bg-emerald-100 text-emerald-700 text-[10px] font-bold px-1.5 py-0.5 rounded">
                      -{(((unoptimizedComparison.sci - sci) / unoptimizedComparison.sci) * 100).toFixed(0)}%
                    </div>
                  )}
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Data Center Workload View */}
      <Card>
        <CardHeader>
          <div className="flex flex-row items-center justify-between">
            <div>
              <CardTitle>Data Centre Workload Distribution</CardTitle>
              <CardDescription>
                Showing workload from {formatDateTime(rangeStart.toISOString())} to {formatDateTime(rangeEnd.toISOString())}
              </CardDescription>
            </div>
            {unoptData && (
              <div className="text-right">
                <span className="text-xs text-muted-foreground block">Currently viewing:</span>
                <span className={`text-sm font-semibold ${showTrivial ? "text-orange-600" : "text-primary"}`}>
                  {showTrivial ? "Unoptimised Baseline" : "Optimised Schedule"}
                </span>
              </div>
            )}
          </div>
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
              <div className={`h-3 w-3 rounded ${showTrivial ? "bg-orange-500" : "bg-emerald-500"}`} />
              <span className="text-muted-foreground">{showTrivial ? "Unoptimised Job" : "Optimised Job"}</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="h-0.5 w-4 bg-emerald-500" />
              <span className="text-muted-foreground">Energy Greenness</span>
            </div>
          </div>

          {/* Area Chart using Recharts */}
          {loading ? (
            <div className="flex items-center justify-center h-64">
              <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
          ) : (
            <div className="h-[250px] w-full mt-4">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart
                  data={workloadData}
                  margin={{ top: 10, right: 30, left: 0, bottom: 0 }}
                >
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
                  <XAxis
                    dataKey="time"
                    tickFormatter={(time) => formatTime(time)}
                    tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }}
                    minTickGap={30}
                    axisLine={false}
                    tickLine={false}
                  />
                  <YAxis
                    yAxisId="left"
                    domain={[0, maxValue]}
                    tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }}
                    axisLine={false}
                    tickLine={false}
                    width={30}
                    tickFormatter={(val) => Math.floor(val).toString()}
                  />
                  <YAxis
                    yAxisId="right"
                    orientation="right"
                    domain={['auto', 'auto']}
                    hide={true}
                  />
                  <Tooltip
                    content={({ active, payload, label }) => {
                      if (active && payload && payload.length) {
                        return (
                          <div className="bg-popover text-popover-foreground text-xs rounded-md px-3 py-2 shadow-md border">
                            <p className="font-medium mb-1 border-b pb-1">{formatTime(label)}</p>
                            <div className="space-y-1">
                              {payload.map((entry, index) => {
                                if (entry.dataKey === "greenness") {
                                  return (
                                    <div key={`item-${index}`} className="flex justify-between gap-4 mt-1 pt-1 border-t">
                                      <span className="text-emerald-600 font-medium">Carbon Intensity</span>
                                      <span className="font-medium text-emerald-600">{Number(entry.value).toFixed(3)}</span>
                                    </div>
                                  )
                                }
                                const isNew = entry.dataKey === "newJob";
                                if (entry.value === 0) return null;
                                return (
                                  <div key={`item-${index}`} className="flex justify-between gap-4">
                                    <span className="flex items-center gap-1.5">
                                      <div
                                        className="w-2 h-2 rounded-full"
                                        style={{ backgroundColor: entry.color }}
                                      />
                                      <span className="text-muted-foreground capitalize">
                                        {isNew ? (showTrivial ? "Unoptimised" : "Optimised") : "Existing"}
                                      </span>
                                    </span>
                                    <span className="font-medium">{Number(entry.value).toFixed(1)} kWh</span>
                                  </div>
                                );
                              })}
                            </div>
                          </div>
                        );
                      }
                      return null;
                    }}
                  />
                  {workloadData.filter(d => new Date(d.time).getHours() === 0 && new Date(d.time).getMinutes() === 0).map((d, i) => (
                    <ReferenceLine
                      key={`midnight-${i}`}
                      yAxisId="left"
                      x={d.time}
                      stroke="#94a3b8"
                      strokeDasharray="4 4"
                      strokeWidth={1}
                      label={{ position: "insideTopLeft", value: new Date(d.time).toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" }), fill: "#64748b", fontSize: 11, offset: 10 }}
                    />
                  ))}
                  <Area
                    yAxisId="left"
                    type="monotone"
                    dataKey="existing"
                    stackId="1"
                    stroke="#9ca3af"
                    fill="url(#colorExisting)"
                    isAnimationActive={true}
                    animationDuration={300}
                  />
                  <Area
                    yAxisId="left"
                    type="monotone"
                    dataKey="newJob"
                    stackId="1"
                    stroke={showTrivial ? "#ea580c" : "#059669"}
                    fill="url(#colorNew)"
                    isAnimationActive={true}
                    animationDuration={300}
                  />
                  <Line
                    yAxisId="right"
                    type="stepAfter"
                    dataKey="greenness"
                    stroke="#10b981"
                    strokeWidth={1.5}
                    dot={false}
                    isAnimationActive={true}
                    animationDuration={300}
                  />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Schedule Info Footer */}
      <div className="flex flex-wrap items-center justify-between gap-4 text-sm text-muted-foreground px-1">
        <div>
          <span className="text-foreground font-medium">Schedule ID:</span>{" "}
          <span className="font-mono">{result.schedule_id}</span>
        </div>
      </div>
    </div>
  )
}
