"use client"

import { useState } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle, CardFooter } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Button } from "@/components/ui/button"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Loader2, Sparkles, AlertCircle } from "lucide-react"

interface SchedulingFormProps {
  onScheduleComplete?: (result: any, unoptimizedResult: any, earliestStart: string, latestFinish: string) => void
}

export function SchedulingForm({ onScheduleComplete }: SchedulingFormProps) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<{ title: string; message: string } | null>(null)
  const [jobType, setJobType] = useState("training")
  const [workloadAmount, setWorkloadAmount] = useState<number | "">("")
  const [preferredDatacenter, setPreferredDatacenter] = useState<string>("none")
  
  // Set default dates
  const today = new Date()
  const tomorrow = new Date(today)
  tomorrow.setDate(tomorrow.getDate() + 1)
  
  // Adjust time to local timezone for the datetime-local input
  const getLocalIsoString = (date: Date) => {
    const tzOffset = date.getTimezoneOffset() * 60000;
    const localDate = new Date(date.getTime() - tzOffset);
    return localDate.toISOString().slice(0, 16);
  };

  const [earliestStart, setEarliestStart] = useState(getLocalIsoString(today))
  const [latestFinish, setLatestFinish] = useState("")

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)

    if (workloadAmount === "" || Number(workloadAmount) <= 0) {
      setError({
        title: "Invalid Input",
        message: "Workload amount must be greater than 0.",
      })
      return
    }

    if (!earliestStart || !latestFinish) {
      setError({
        title: "Invalid Input",
        message: "Please specify both earliest start and latest finish times.",
      })
      return
    }

    setLoading(true)

    // Convert local datetime to UTC ISO string for backend
    const startDate = new Date(earliestStart)
    const endDate = new Date(latestFinish)

    const jobRequest: any = {
      job_type: jobType,
      workload_amount: Number(workloadAmount),
      earliest_start: startDate.toISOString(),
      latest_finish: endDate.toISOString(),
    }
    
    if (preferredDatacenter !== "none") {
      jobRequest.preferred_datacenter = preferredDatacenter
    }

    try {
      // Fetch optimized schedule
      const response = await fetch("/api/schedules", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(jobRequest),
      })

      if (!response.ok) {
        let errorMessage = "An unknown error occurred.";
        let title = "Failed to Schedule";
        try {
          const errorData = await response.json();
          if (errorData.message) errorMessage = errorData.message;
        } catch (_) {}

        if (response.status === 409) {
          title = "Scheduling Conflict";
        } else if (response.status === 422) {
          title = "Validation Error";
        } else if (response.status === 503) {
          title = "Service Unavailable";
          errorMessage = "Cannot connect to the forecasting service. Please try again later.";
        }

        setError({ title, message: errorMessage });
        setLoading(false);
        return;
      }

      const optimizedResult = await response.json()

      // After optimization succeeds, fetch the trivial schedule for comparison
      let trivialResult = null
      try {
        const trivialRes = await fetch(`/api/schedules/${optimizedResult.schedule_id}/trivial`)
        if (trivialRes.ok) {
          trivialResult = await trivialRes.json()
        }
      } catch (err) {
        console.error("Failed to fetch trivial baseline:", err)
      }

      if (onScheduleComplete) {
        onScheduleComplete(optimizedResult, trivialResult, startDate.toISOString(), endDate.toISOString())
      }
    } catch (error) {
      console.error("Error scheduling job:", error)
      setError({
        title: "Connection Error",
        message: "Failed to connect to the scheduling service. Please check your network.",
      })
    } finally {
      setLoading(false)
    }
  }

  return (
    <Card className="w-full max-w-2xl mx-auto shadow-lg border-2">
      <CardHeader className="space-y-1 pb-4">
        <div className="flex items-center gap-2">
          <Sparkles className="h-5 w-5 text-primary" />
          <CardTitle className="text-2xl">Schedule Workload</CardTitle>
        </div>
        <CardDescription className="text-base">
          Define your AI job requirements and let our carbon-aware scheduler find the most eco-friendly placement.
        </CardDescription>
      </CardHeader>
      <form onSubmit={handleSubmit}>
        <CardContent className="space-y-4">
          {error && (
            <Alert variant="destructive" className="mb-6">
              <AlertCircle className="h-4 w-4" />
              <AlertTitle>{error.title}</AlertTitle>
              <AlertDescription>{error.message}</AlertDescription>
            </Alert>
          )}
          
          <div className="grid gap-6 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="jobType" className="text-sm font-medium">Job Type</Label>
              <select
                id="jobType"
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                value={jobType}
                onChange={(e) => setJobType(e.target.value)}
              >
                <option value="training">Model Training</option>
                <option value="inference">Batch Inference</option>
                <option value="data_prep">Data Preparation</option>
              </select>
            </div>
            
            <div className="space-y-2">
              <Label htmlFor="workloadAmount" className="text-sm font-medium">Workload Amount (kWh)</Label>
              <div className="relative">
                <Input
                  id="workloadAmount"
                  type="number"
                  min="0.1"
                  step="0.1"
                  value={workloadAmount}
                  onChange={(e) => setWorkloadAmount(e.target.value === "" ? "" : Number(e.target.value))}
                  required
                  className="pr-12"
                  placeholder="e.g. 100"
                />
                <span className="absolute right-3 top-2.5 text-sm text-muted-foreground">kWh</span>
              </div>
            </div>
          </div>

            <div className="space-y-4 pt-2">
            <h3 className="text-sm font-medium border-b pb-2">Scheduling Window</h3>
            <div className="grid gap-6 sm:grid-cols-2">
              <div className="space-y-2 relative">
                <Label htmlFor="earliestStart" className="text-sm">Earliest Start</Label>
                <Input
                  id="earliestStart"
                  type="datetime-local"
                  value={earliestStart}
                  onChange={(e) => setEarliestStart(e.target.value)}
                  required
                  className="w-full"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="latestFinish" className="text-sm">Latest Finish</Label>
                <Input
                  id="latestFinish"
                  type="datetime-local"
                  value={latestFinish}
                  onChange={(e) => setLatestFinish(e.target.value)}
                  required
                  className="w-full"
                />
              </div>
            </div>
          </div>
          
          <div className="pt-2 pb-2">
            <div className="space-y-2">
              <Label htmlFor="preferredDatacenter" className="text-sm font-medium text-muted-foreground">Preferred Data Center (Optional)</Label>
              <select
                id="preferredDatacenter"
                className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm ring-offset-background file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring focus-visible:ring-offset-1 disabled:cursor-not-allowed disabled:opacity-50"
                value={preferredDatacenter}
                onChange={(e) => setPreferredDatacenter(e.target.value)}
              >
                <option value="none">Let optimizer decide</option>
                <option value="Data-Center-1">Data Centre 1 (us-west-1)</option>
                <option value="Data-Center-2">Data Centre 2 (us-east-1)</option>
                <option value="Data-Center-3">Data Centre 3 (eu-west-1)</option>
                <option value="Data-Center-4">Data Centre 4 (ap-northeast-1)</option>
                <option value="Data-Center-5">Data Centre 5 (sa-east-1)</option>
              </select>
            </div>
          </div>
        </CardContent>
        <CardFooter className="flex flex-col sm:flex-row gap-4 pt-6 bg-muted/20 border-t">
          <Button 
            type="submit" 
            className="w-full sm:w-auto min-w-[200px]" 
            disabled={loading}
            size="lg"
          >
            {loading ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Finding optimal placement...
              </>
            ) : (
              "Schedule Job"
            )}
          </Button>
        </CardFooter>
      </form>
    </Card>
  )
}
