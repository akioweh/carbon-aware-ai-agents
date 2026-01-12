"use client"

import { useState } from "react"
import { SchedulingForm } from "@/components/scheduling-form"
import { ScheduleResult } from "@/components/schedule-result"
import { Leaf } from "lucide-react"

export default function Home() {
  const [scheduleResult, setScheduleResult] = useState<any>(null)

  const handleScheduleComplete = (result: any) => {
    setScheduleResult(result)
  }

  const handleBack = () => {
    setScheduleResult(null)
  }

  return (
    <div className="min-h-screen bg-background">
      <div className="container mx-auto px-4 py-8 md:py-16">
        <div className="mx-auto max-w-2xl">
          {/* Header */}
          <div className="mb-8 text-center">
            <div className="mb-4 flex justify-center">
              <div className="inline-flex items-center gap-2 rounded-full bg-primary/10 px-4 py-2 text-sm font-medium text-primary">
                <Leaf className="h-4 w-4" />
                Eco-Optimized Scheduling
              </div>
            </div>
            <h1 className="mb-3 text-4xl font-bold tracking-tight text-foreground md:text-5xl text-balance">
              {scheduleResult ? "Schedule Confirmed" : "Schedule Your Workload"}
            </h1>
            <p className="text-lg text-muted-foreground text-balance">
              {scheduleResult
                ? "Your task has been scheduled for optimal environmental efficiency"
                : "Optimize your computational tasks for minimal environmental impact across our global data center network"}
            </p>
          </div>

          {scheduleResult ? (
            <ScheduleResult result={scheduleResult} onBack={handleBack} />
          ) : (
            <>
              <SchedulingForm onScheduleComplete={handleScheduleComplete} />

              {/* Footer Info */}
              <div className="mt-8 text-center">
                <p className="text-sm text-muted-foreground">
                  Our algorithm prioritizes renewable energy availability and carbon-neutral operations
                </p>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
