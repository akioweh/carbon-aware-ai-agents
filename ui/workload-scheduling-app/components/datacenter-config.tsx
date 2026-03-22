"use client"

import { useEffect, useMemo, useState } from "react"
import dynamic from "next/dynamic"
import { ArrowLeft, Globe, RefreshCw, Server } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Separator } from "@/components/ui/separator"
import { Skeleton } from "@/components/ui/skeleton"
import { Switch } from "@/components/ui/switch"

import type { DatacenterMapPoint } from "@/components/datacenter-map"

const DatacenterMap = dynamic(
  () => import("@/components/datacenter-map").then((module) => module.DatacenterMap),
  { ssr: false, loading: () => <Skeleton className="h-full w-full rounded-none" /> }
)

interface DatacenterRecord {
  id: string
  region_id: number
  name: string
  active: boolean
  latitude: number | null
  longitude: number | null
}

interface DataCentreConfigProps {
  onClose: () => void
}

function formatDatacenterId(id: string): string {
  const match = id.match(/Data-Center-(\d+)/i)
  if (!match) return id.replace(/-/g, " ")
  return `Data Center ${match[1]}`
}

function sortConfigDatacenters(data: DatacenterRecord[]): DatacenterRecord[] {
  return [...data].sort((a, b) => {
    const aIsLondon = a.name.trim().toLowerCase() === "london"
    const bIsLondon = b.name.trim().toLowerCase() === "london"
    if (aIsLondon && !bIsLondon) return -1
    if (!aIsLondon && bIsLondon) return 1

    const aNum = Number(a.id.match(/Data-Center-(\d+)/i)?.[1] ?? Number.MAX_SAFE_INTEGER)
    const bNum = Number(b.id.match(/Data-Center-(\d+)/i)?.[1] ?? Number.MAX_SAFE_INTEGER)
    return aNum - bNum
  })
}

async function fetchDataCentres(): Promise<DatacenterRecord[]> {
  const res = await fetch("/api/datacenters", { cache: "no-store" })
  if (!res.ok) {
    throw new Error(`Failed to fetch datacenters (${res.status})`)
  }
  return res.json()
}

async function patchDataCentreActive(id: string, active: boolean): Promise<void> {
  const res = await fetch(`/api/datacenters/${encodeURIComponent(id)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ active }),
  })

  if (!res.ok) {
    throw new Error(`Failed to update datacenter ${id} (${res.status})`)
  }
}

export function DataCentreConfig({ onClose }: DataCentreConfigProps) {
  const [centres, setCentres] = useState<DatacenterRecord[]>([])
  const [initialState, setInitialState] = useState<Record<string, boolean>>({})
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [savedBanner, setSavedBanner] = useState(false)
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await fetchDataCentres()
      const sorted = sortConfigDatacenters(data)
      setCentres(sorted)
      setInitialState(Object.fromEntries(sorted.map((dc) => [dc.id, dc.active])))
      setSelectedId((current) => current ?? sorted[0]?.id ?? null)
    } catch (err) {
      console.error(err)
      setError("Failed to load datacenter configuration from stats API.")
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const handleRefresh = async () => {
    setRefreshing(true)
    await load()
    setRefreshing(false)
  }

  const handleToggle = (id: string, value: boolean) => {
    setCentres((prev) => prev.map((c) => (c.id === id ? { ...c, active: value } : c)))
  }

  const handleSelect = (id: string) => {
    setSelectedId((current) => (current === id ? null : id))
  }

  const hasChanges = useMemo(
    () => centres.some((dc) => initialState[dc.id] !== undefined && initialState[dc.id] !== dc.active),
    [centres, initialState]
  )

  const handleSave = async () => {
    const changed = centres.filter(
      (dc) => initialState[dc.id] !== undefined && initialState[dc.id] !== dc.active
    )

    if (changed.length === 0) {
      return
    }

    setSaving(true)
    setError(null)

    try {
      await Promise.all(changed.map((dc) => patchDataCentreActive(dc.id, dc.active)))
      setInitialState(Object.fromEntries(centres.map((dc) => [dc.id, dc.active])))
      setSavedBanner(true)
      setTimeout(() => {
        setSavedBanner(false)
        onClose()
      }, 250)
    } catch (err) {
      console.error(err)
      setError("Failed to save one or more datacenter updates.")
    } finally {
      setSaving(false)
    }
  }

  const enabledCount = centres.filter((c) => c.active).length
  const mapPoints: DatacenterMapPoint[] = centres
    .filter((dc): dc is DatacenterRecord & { latitude: number; longitude: number } => (
      typeof dc.latitude === "number" && typeof dc.longitude === "number"
    ))
    .map((dc) => ({
      id: dc.id,
      name: dc.name,
      regionId: dc.region_id,
      latitude: dc.latitude,
      longitude: dc.longitude,
      active: dc.active,
    }))

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="sm" onClick={onClose} className="gap-2 -ml-2 bg-transparent">
          <ArrowLeft className="h-4 w-4" />
          Back
        </Button>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[0.95fr_1.25fr] lg:items-start">
        <Card className="overflow-hidden border shadow-md">
          <CardHeader className="px-4 pb-3 pt-4">
            <CardTitle className="flex items-center gap-2 text-base font-semibold">
              <Globe className="h-4 w-4 text-muted-foreground" />
              Data Centre Locations
            </CardTitle>
            <CardDescription className="text-xs">
              Hover a marker for details. Click a marker to highlight the matching data centre.
            </CardDescription>
          </CardHeader>

          <div className="h-[520px] w-full border-t bg-stone-100">
            {loading ? (
              <Skeleton className="h-full w-full rounded-none" />
            ) : mapPoints.length > 0 ? (
              <DatacenterMap centres={mapPoints} selectedId={selectedId} onSelect={handleSelect} />
            ) : (
              <div className="flex h-full items-center justify-center px-6 text-center text-sm text-muted-foreground">
                No coordinates are available for the current datacenter set.
              </div>
            )}
          </div>

          <div className="flex flex-wrap gap-x-4 gap-y-2 border-t px-4 py-3 text-xs text-muted-foreground">
            <span className="flex items-center gap-1.5">
              <span className="h-2.5 w-2.5 rounded-full border border-white bg-slate-900 shadow-sm" />
              Enabled in scheduler
            </span>
            <span className="flex items-center gap-1.5">
              <span className="h-2.5 w-2.5 rounded-full border border-white bg-slate-400 shadow-sm" />
              Disabled in scheduler
            </span>
          </div>
        </Card>

        <Card className="border-2 shadow-lg">
          <CardHeader className="pb-4">
            <div className="flex items-start justify-between gap-4">
              <div>
                <CardTitle className="flex items-center gap-2 text-xl">
                  <Server className="h-5 w-5 text-primary" />
                  Data Centre Configuration
                </CardTitle>
                <CardDescription className="mt-1">
                  Enable or disable data centres used for optimization. Scheduler-visible locations are sourced from stats.
                </CardDescription>
              </div>

              <Button
                variant="outline"
                size="sm"
                onClick={handleRefresh}
                disabled={refreshing || loading}
                className="shrink-0 gap-2 bg-transparent"
              >
                <RefreshCw className={`h-3.5 w-3.5 ${refreshing ? "animate-spin" : ""}`} />
                Refresh
              </Button>
            </div>

            <div className="mt-4 flex flex-wrap gap-3">
              <div className="flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-sm">
                <span className="text-muted-foreground">Enabled:</span>
                <span className="font-medium">{loading ? "-" : enabledCount}</span>
              </div>
              <div className="flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-sm">
                <span className="text-muted-foreground">Total:</span>
                <span className="font-medium">{loading ? "-" : centres.length}</span>
              </div>
            </div>

            {error && <p className="mt-4 text-sm text-destructive">{error}</p>}
          </CardHeader>

          <Separator />

          <CardContent className="pt-0">
            <div className="grid grid-cols-[1fr_auto_auto] items-center gap-4 px-4 py-2.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">
              <span>Data Centre</span>
              <span className="text-center">Region ID</span>
              <span className="text-center w-16">Enabled</span>
            </div>

            <Separator />

            {loading ? (
              <div className="space-y-0">
                {[...Array(5)].map((_, i) => (
                  <div key={i} className="grid grid-cols-[1fr_auto_auto] items-center gap-4 border-b px-4 py-4 last:border-b-0">
                    <div className="space-y-1.5">
                      <Skeleton className="h-4 w-36" />
                      <Skeleton className="h-3 w-24" />
                    </div>
                    <Skeleton className="h-4 w-10" />
                    <Skeleton className="h-5 w-10 rounded-full" />
                  </div>
                ))}
              </div>
            ) : (
              <ul className="divide-y">
                {centres.map((dc) => {
                  const isHighlighted = selectedId === dc.id

                  return (
                    <li
                      key={dc.id}
                      onClick={() => handleSelect(dc.id)}
                      className={`grid cursor-pointer grid-cols-[1fr_auto_auto] items-center gap-4 px-4 py-4 transition-colors ${isHighlighted ? "bg-muted/60" : "hover:bg-muted/30"
                        }`}
                    >
                      <div className="min-w-0">
                        <p className="truncate font-medium text-sm">{formatDatacenterId(dc.id)}</p>
                        <p className="truncate text-xs text-muted-foreground mt-0.5">{dc.name}</p>
                      </div>

                      <div className="flex justify-center">
                        <Badge variant="outline" className="text-xs font-normal tabular-nums">
                          {dc.region_id}
                        </Badge>
                      </div>

                      <div className="flex w-16 justify-center" onClick={(event) => event.stopPropagation()}>
                        <Switch
                          checked={dc.active}
                          onCheckedChange={(value) => handleToggle(dc.id, value)}
                          aria-label={`Toggle ${dc.id}`}
                        />
                      </div>
                    </li>
                  )
                })}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>

      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          {!loading && (
            <>
              {enabledCount} of {centres.length} data centre{enabledCount !== 1 ? "s" : ""} included in optimization.
            </>
          )}
        </p>

        <div className="flex items-center gap-3">
          {!loading && enabledCount === 0 && (
            <span className="text-sm font-medium text-destructive animate-pulse">
              At least one data centre must be active
            </span>
          )}

          {savedBanner && <span className="text-sm text-emerald-600 font-medium">Configuration saved</span>}

          <Button
            onClick={handleSave}
            disabled={saving || loading || !hasChanges || enabledCount === 0}
          >
            {saving ? "Saving..." : "Save Configuration"}
          </Button>
        </div>
      </div>
    </div>
  )
}
