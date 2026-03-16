"use client"

import { useEffect, useMemo, useState } from "react"

export interface ActiveDatacenter {
  id: string
  name: string
  region_id: number
}

interface DatacenterApiRecord extends ActiveDatacenter {
  active: boolean
}

function getDatacenterOrder(id: string): number {
  const match = id.match(/Data-Center-(\d+)/i)
  if (!match) return Number.MAX_SAFE_INTEGER
  return Number(match[1])
}

function formatDatacenterId(id: string): string {
  const match = id.match(/Data-Center-(\d+)/i)
  if (!match) return id.replace(/-/g, " ")
  return `Data Center ${match[1]}`
}

const FALLBACK_DATACENTERS: ActiveDatacenter[] = [
  { id: "Data-Center-1", name: "London", region_id: 13 },
  { id: "Data-Center-2", name: "North Scotland", region_id: 1 },
  { id: "Data-Center-3", name: "South Scotland", region_id: 2 },
  { id: "Data-Center-4", name: "North West England", region_id: 3 },
  { id: "Data-Center-5", name: "North East England", region_id: 4 },
]

export function useActiveDatacenters() {
  const [datacenters, setDatacenters] = useState<ActiveDatacenter[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const load = async () => {
      try {
        const response = await fetch("/api/datacenters", { cache: "no-store" })
        if (!response.ok) {
          setDatacenters(FALLBACK_DATACENTERS)
          return
        }

        const data = (await response.json()) as DatacenterApiRecord[]
        const active = data
          .filter((dc) => dc.active)
          .sort((a, b) => getDatacenterOrder(a.id) - getDatacenterOrder(b.id))
          .map((dc) => ({ id: dc.id, name: dc.name, region_id: dc.region_id }))

        setDatacenters(active.length > 0 ? active : FALLBACK_DATACENTERS)
      } catch (error) {
        console.error("Failed to load active datacenters:", error)
        setDatacenters(FALLBACK_DATACENTERS)
      } finally {
        setLoading(false)
      }
    }

    load()
  }, [])

  const options = useMemo(
    () => datacenters.map((dc) => ({ value: dc.id, label: `${formatDatacenterId(dc.id)} (${dc.name})` })),
    [datacenters]
  )

  return { datacenters, options, loading }
}
