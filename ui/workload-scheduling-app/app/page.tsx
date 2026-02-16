"use client"

import { useState } from "react"
import { SchedulingForm } from "@/components/scheduling-form"
import { ScheduleResult } from "@/components/schedule-result"
import { WorkloadCalendar } from "@/components/workload-calendar"

export default function Home() {
  const [scheduleResult, setScheduleResult] = useState<any>(null)
  const [timeRange, setTimeRange] = useState<{ earliestStart: string; latestFinish: string } | null>(null)
  const [showCalendar, setShowCalendar] = useState(false)

  const handleScheduleComplete = (result: any, earliestStart: string, latestFinish: string) => {
    setScheduleResult(result)
    setTimeRange({ earliestStart, latestFinish })
    setShowCalendar(false)
  }

  const handleBack = () => {
    setScheduleResult(null)
    setTimeRange(null)
  }

  const handleCancel = () => {
    setScheduleResult(null)
    setTimeRange(null)
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-background via-background to-muted/20">
      <div className="container mx-auto px-4 py-8 max-w-6xl">
        {/* Header */}
        <header className="mb-8 text-center">
          <h1 className="text-4xl font-bold tracking-tight mb-2 text-balance">
            Carbon-Aware Workload Scheduler
          </h1>
          <p className="text-muted-foreground text-lg text-balance">
            Optimize your AI workloads for minimal environmental impact
          </p>
        </header>

        {/* Main Content */}
        <main>
          {showCalendar ? (
            <WorkloadCalendar onClose={() => setShowCalendar(false)} scheduleId={scheduleResult?.schedule_id} />
          ) : scheduleResult ? (
            <ScheduleResult
              result={scheduleResult}
              earliestStart={timeRange?.earliestStart}
              latestFinish={timeRange?.latestFinish}
              onBack={handleBack}
              onCancel={handleCancel}
            />
          ) : (
            <SchedulingForm
              onScheduleComplete={handleScheduleComplete}
              onViewCalendar={() => setShowCalendar(true)}
            />
          )}
        </main>

        {/* Footer */}
        <footer className="mt-12 text-center text-sm text-muted-foreground">
          <p>Scheduling AI workloads to minimize carbon emissions across global data centres</p>
        </footer>
      </div>
    </div>
  )
}
