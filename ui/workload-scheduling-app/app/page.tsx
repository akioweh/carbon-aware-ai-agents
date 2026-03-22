"use client"

import { useState } from "react"
import { SchedulingForm } from "@/components/scheduling-form"
import { ScheduleResult } from "@/components/schedule-result"
import { WorkloadCalendar } from "@/components/workload-calendar"
import { PreviousJobs } from "@/components/previous-jobs"
import { DataCentreConfig } from "@/components/datacenter-config"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { History, Globe } from "lucide-react"

export default function Home() {
  const [scheduleResult, setScheduleResult] = useState<any>(null)
  const [unoptimizedResult, setUnoptimizedResult] = useState<any>(null)
  const [timeRange, setTimeRange] = useState<{ earliestStart: string; latestFinish: string } | null>(null)
  const [showConfig, setShowConfig] = useState(false)
  const [source, setSource] = useState<"form" | "history">("form")
  const [activeTab, setActiveTab] = useState<"form" | "workload" | "history">("form")

  const handleScheduleComplete = (result: any, unoptimizedResult: any, earliestStart: string, latestFinish: string) => {
    setScheduleResult(result)
    setUnoptimizedResult(unoptimizedResult)
    setTimeRange({ earliestStart, latestFinish })
    setShowConfig(false)
    setSource("form")
    setActiveTab("form")
  }

  const handleBack = () => {
    setScheduleResult(null)
    setUnoptimizedResult(null)
    setTimeRange(null)
    if (source === "history") setActiveTab("history")
  }

  const handleCancel = () => {
    setScheduleResult(null)
    setUnoptimizedResult(null)
    setTimeRange(null)
    if (source === "history") setActiveTab("history")
  }

  const handleSelectJob = (job: any) => {
    // Check if the backend gave us unoptimizedResult via job.unoptimizedResult (from summary)
    const unopt = job.unoptimizedResult || null;

    setScheduleResult(job)
    setUnoptimizedResult(unopt) // Pass it directly
    setTimeRange({ earliestStart: job.start_time, latestFinish: job.end_time })
    setShowConfig(false)
    setSource("history")
    setActiveTab("history")
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-background via-background to-muted/20">
      <div className="container mx-auto px-4 py-8 w-full max-w-screen-2xl">
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
          <Tabs value={activeTab} onValueChange={(value) => setActiveTab(value as "form" | "workload" | "history")}>
            <TabsList className="mb-4 grid w-full grid-cols-3 max-w-2xl mx-auto h-10">
              <TabsTrigger value="form">Scheduling Form</TabsTrigger>
              <TabsTrigger value="workload" className="gap-2">
                <Globe className="h-4 w-4" />
                View Global Workload
              </TabsTrigger>
              <TabsTrigger value="history" className="gap-2">
                <History className="h-4 w-4" />
                View Scheduled Jobs
              </TabsTrigger>
            </TabsList>

            <TabsContent value="form">
              {showConfig ? (
                <DataCentreConfig onClose={() => setShowConfig(false)} />
              ) : scheduleResult && source === "form" ? (
                <ScheduleResult
                  result={scheduleResult}
                  unoptimizedResult={unoptimizedResult}
                  earliestStart={timeRange?.earliestStart}
                  latestFinish={timeRange?.latestFinish}
                  onBack={handleBack}
                  onCancel={handleCancel}
                />
              ) : (
                <SchedulingForm
                  onScheduleComplete={handleScheduleComplete}
                  onConfigure={() => setShowConfig(true)}
                />
              )}
            </TabsContent>

            <TabsContent value="workload">
              <WorkloadCalendar scheduleId={scheduleResult?.schedule_id} />
            </TabsContent>

            <TabsContent value="history">
              {scheduleResult && source === "history" ? (
                <ScheduleResult
                  result={scheduleResult}
                  unoptimizedResult={unoptimizedResult}
                  earliestStart={timeRange?.earliestStart}
                  latestFinish={timeRange?.latestFinish}
                  onBack={handleBack}
                  onCancel={handleCancel}
                />
              ) : (
                <PreviousJobs onSelectJob={handleSelectJob} />
              )}
            </TabsContent>
          </Tabs>
        </main>

        {/* Footer */}
        <footer className="mt-12 text-center text-sm text-muted-foreground">
          <p>Scheduling AI workloads to minimize carbon emissions across global data centres</p>
        </footer>
      </div>
    </div>
  )
}
