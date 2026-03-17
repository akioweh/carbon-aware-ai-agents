"use client"

import { useState, useEffect } from "react"
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
  const [fetchingGpus, setFetchingGpus] = useState(true)
  const [error, setError] = useState<{ title: string; message: string } | null>(null)

  // Available GPU options from the backend
  const [availableGpus, setAvailableGpus] = useState<string[]>([])

  // Form Fields
  const [jobType, setJobType] = useState("training")
  const [gpuType, setGpuType] = useState("A100_SXM4")
  const [gpuCount, setGpuCount] = useState<number | "">(8)
  const [modelSize, setModelSize] = useState<number | "">(50)
  const [length, setLength] = useState<number | "">(120)
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

  // Fetch available GPUs on mount
  useEffect(() => {
    async function fetchGpus() {
      try {
        const response = await fetch("/api/hardwareSpecs/gpus")
        if (!response.ok) throw new Error("Failed to fetch GPUs")

        const gpus = await response.json()
        setAvailableGpus(gpus)
        if (gpus.length > 0) setGpuType(gpus[0]) // Select first GPU by default
      } catch (err) {
        console.error("Error fetching GPUs:", err)
        setError({
          title: "Setup Error",
          message: "Could not load available GPUs. Please refresh the page.",
        })
      } finally {
        setFetchingGpus(false)
      }
    }
    fetchGpus()
  }, [])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)

    if (!gpuCount || Number(gpuCount) <= 0) {
      setError({
        title: "Invalid Input",
        message: "GPU count must be greater than 0.",
      })
      return
    }
    if (!modelSize || Number(modelSize) <= 0) {
      setError({
        title: "Invalid Input",
        message: "Model size must be greater than 0.",
      })
      return
    }
    if (!length || Number(length) <= 0) {
      setError({
        title: "Invalid Input",
        message: "Length must be greater than 0.",
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
      gpu_type: gpuType,
      gpu_count: Number(gpuCount),
      model_size: Number(modelSize),
      length: Number(length),
      earliest_start: startDate.toISOString(),
      latest_finish: endDate.toISOString(),
    }

    if (preferredDatacenter !== "none") {
      jobRequest.preferred_datacenter = preferredDatacenter
    }

    try {
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
          if (errorData.error) errorMessage = errorData.error;
          else if (errorData.message) errorMessage = errorData.message;
        } catch (_) { }

        if (response.status === 400) title = "Malformed Request";
        else if (response.status === 409) title = "Scheduling Conflict";
        else if (response.status === 422) title = "Validation Error";
        else if (response.status === 503) {
          title = "Service Unavailable";
          errorMessage = "Cannot connect to the scheduling service. Please try again later.";
        }

        setError({ title, message: errorMessage });
        setLoading(false);
        return;
      }

      const optimizedResult = await response.json()

      if (onScheduleComplete) {
        onScheduleComplete(optimizedResult, null, startDate.toISOString(), endDate.toISOString())
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
                <option value="training">Training</option>
                <option value="inference">Inference</option>
                <option value="batch">Batch</option>
              </select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="gpuType" className="text-sm font-medium">GPU Type</Label>
              <select
                id="gpuType"
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                value={gpuType}
                onChange={(e) => setGpuType(e.target.value)}
                disabled={fetchingGpus || availableGpus.length === 0}
                required
              >
                {fetchingGpus ? (
                  <option value="">Loading GPUs...</option>
                ) : availableGpus.length === 0 ? (
                  <option value="">No GPUs Available</option>
                ) : (
                  availableGpus.map(gpu => (
                    <option key={gpu} value={gpu}>{gpu}</option>
                  ))
                )}
              </select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="length" className="text-sm font-medium">Estimated Time (mins)</Label>
              <Input
                id="length"
                type="number"
                min="1"
                value={length}
                onChange={(e) => setLength(e.target.value === "" ? "" : parseInt(e.target.value))}
                required
                placeholder="e.g. 120"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="gpuCount" className="text-sm font-medium">GPU Count</Label>
              <Input
                id="gpuCount"
                type="number"
                min="1"
                value={gpuCount}
                onChange={(e) => setGpuCount(e.target.value === "" ? "" : parseInt(e.target.value))}
                required
                placeholder="e.g. 8"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="modelSize" className="text-sm font-medium">Model VRAM Size (GB)</Label>
              <Input
                id="modelSize"
                type="number"
                min="1"
                value={modelSize}
                onChange={(e) => setModelSize(e.target.value === "" ? "" : parseInt(e.target.value))}
                required
                placeholder="e.g. 26"
              />
            </div>
          </div>

          <div className="space-y-4 pt-4 border-t mt-4">
            <h3 className="text-sm font-medium pb-2">Scheduling Window</h3>
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
                <option value="us-west-1">us-west-1</option>
                <option value="us-east-1">us-east-1</option>
                <option value="eu-west-1">eu-west-1</option>
                <option value="ap-northeast-1">ap-northeast-1</option>
                <option value="sa-east-1">sa-east-1</option>
              </select>
            </div>
          </div>
        </CardContent>
        <CardFooter className="flex flex-col sm:flex-row gap-4 pt-6 bg-muted/20 border-t">
          <Button
            type="submit"
            className="w-full sm:w-auto min-w-[200px]"
            disabled={loading || fetchingGpus || availableGpus.length === 0}
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