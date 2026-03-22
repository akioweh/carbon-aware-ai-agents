"use client"

import { useRouter } from "next/navigation"
import { useState, useEffect } from "react"
import { ScheduleResult } from "@/components/schedule-result"
import { PageShell } from "../../../components/page-shell"
import { JobScheduleResponse, ScheduleData } from "@/types/schedule"
import { Loader2 } from "lucide-react"
import { Card, CardContent } from "@/components/ui/card"

export default function SchedulePage({ params }: { params: { schedule_id: string } }) {
  const router = useRouter()
  const [result, setResult] = useState<JobScheduleResponse | null>(null)
  const [unoptimized, setUnoptimized] = useState<ScheduleData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const fetchSchedule = async () => {
      try {
        const res = await fetch(`/api/schedules/${params.schedule_id}`)
        if (!res.ok) throw new Error(`Failed to fetch schedule: ${res.status}`)
        const data = await res.json()
        setResult(data)

        const trivialRes = await fetch(`/api/schedules/${params.schedule_id}/trivial`).catch(() => null)
        if (trivialRes?.ok) {
          const trivialData = await trivialRes.json()
          setUnoptimized(trivialData)
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load schedule")
      } finally {
        setLoading(false)
      }
    }

    fetchSchedule()
  }, [params.schedule_id])

  if (loading) {
    return (
      <PageShell>
        <div className="flex items-center justify-center h-64">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      </PageShell>
    )
  }

  if (error || !result) {
    return (
      <PageShell>
        <Card className="border-2 shadow-lg max-w-2xl mx-auto">
          <CardContent className="p-6">
            <p className="text-red-500">{error || "Schedule not found"}</p>
          </CardContent>
        </Card>
      </PageShell>
    )
  }

  return (
    <PageShell>
      <ScheduleResult
        result={result}
        unoptimizedResult={unoptimized || undefined}
        onBack={() => router.back()}
        onCancel={() => router.push("/scheduled-jobs")}
      />
    </PageShell>
  )
}
