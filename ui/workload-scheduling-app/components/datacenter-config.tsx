"use client"

import { useEffect, useMemo, useState } from "react"
import { ArrowLeft, RefreshCw, Server } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Separator } from "@/components/ui/separator"
import { Skeleton } from "@/components/ui/skeleton"
import { Switch } from "@/components/ui/switch"

interface DatacenterRecord {
  id: string
  region_id: number
  name: string
  active: boolean
}

interface DataCentreConfigProps {
  onClose: () => void
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

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await fetchDataCentres()
      setCentres(data)
      setInitialState(Object.fromEntries(data.map((dc) => [dc.id, dc.active])))
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

  return (
    <div className="space-y-6 max-w-3xl mx-auto">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="sm" onClick={onClose} className="gap-2 -ml-2 bg-transparent">
          <ArrowLeft className="h-4 w-4" />
          Back
        </Button>
      </div>

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
                <div key={i} className="grid grid-cols-[1fr_auto_auto] items-center gap-4 px-4 py-4 border-b last:border-b-0">
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
              {centres.map((dc) => (
                <li
                  key={dc.id}
                  className="grid grid-cols-[1fr_auto_auto] items-center gap-4 px-4 py-4 transition-colors hover:bg-muted/30"
                >
                  <div className="min-w-0">
                    <p className="truncate font-medium text-sm">{dc.id}</p>
                    <p className="truncate text-xs text-muted-foreground mt-0.5">
                      {dc.name}
                    </p>
                  </div>

                  <div className="flex justify-center">
                    <Badge variant="outline" className="text-xs font-normal tabular-nums">
                      {dc.region_id}
                    </Badge>
                  </div>

                  <div className="flex w-16 justify-center">
                    <Switch
                      checked={dc.active}
                      onCheckedChange={(v) => handleToggle(dc.id, v)}
                      aria-label={`Toggle ${dc.id}`}
                    />
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          {!loading && (
            <>
              {enabledCount} of {centres.length} data centre{enabledCount !== 1 ? "s" : ""} included in optimization.
            </>
          )}
        </p>

        <div className="flex items-center gap-3">
          {savedBanner && <span className="text-sm text-emerald-600 font-medium">Configuration saved</span>}
          <Button onClick={handleSave} disabled={saving || loading || !hasChanges}>
            {saving ? "Saving..." : "Save Configuration"}
          </Button>
        </div>
      </div>
    </div>
  )
}
