"use client"

import { Calendar } from "@/components/ui/calendar"

import type React from "react"

import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { CalendarDays, Clock, Loader2, Server } from "lucide-react"

const datacenters = [
  { id: "dc1", name: "Data Centre 1", location: "Portland, OR" },
  { id: "dc2", name: "Data Centre 2", location: "Ashburn, VA" },
  { id: "dc3", name: "Data Centre 3", location: "Frankfurt, DE" },
  { id: "dc4", name: "Data Centre 4", location: "Singapore, SG" },
  { id: "dc5", name: "Data Centre 5", location: "São Paulo, BR" },
]

const jobTypes = [
  { value: "training", label: "Training", description: "Model training workloads" },
  { value: "inference", label: "Inference", description: "Model inference tasks" },
  { value: "batch", label: "Batch", description: "Batch processing jobs" },
]

interface SchedulingFormProps {
  onScheduleComplete?: (result: any, earliestStart: string, latestFinish: string) => void
  onViewCalendar?: () => void
}

export function SchedulingForm({ onScheduleComplete, onViewCalendar }: SchedulingFormProps) {
  const [workload, setWorkload] = useState("")
  const [datacenter, setDatacenter] = useState("")
  const [jobType, setJobType] = useState("")
  const [earliestStart, setEarliestStart] = useState("")
  const [latestFinish, setLatestFinish] = useState("")
  const [isSubmitting, setIsSubmitting] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setIsSubmitting(true)

    const jobRequest = { 
      job_type: jobType, 
      workload_amount: Number.parseFloat(workload), 
      earliest_start: new Date(earliestStart).toISOString(), 
      latest_finish: new Date(latestFinish).toISOString(), 
    }

    console.log("[v0] Submitting job request:", jobRequest)

    try {
      const response = await fetch("/api/schedule", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(jobRequest),
      })

      if (!response.ok) {
        throw new Error("Failed to schedule job")
      }

      const result = await response.json()
      console.log("[v0] Schedule result:", result)

      if (onScheduleComplete) {
        onScheduleComplete(result, earliestStart, latestFinish)
      }
    } catch (error) {
      console.error("[v0] Error scheduling job:", error)
      alert("Failed to schedule job. Please try again.")
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <Card className="border-2 shadow-lg">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Server className="h-5 w-5 text-primary" />
          Task Configuration
        </CardTitle>
        <CardDescription>Configure your computational workload and scheduling preferences</CardDescription>
        {onViewCalendar && (
          <Button 
            variant="outline" 
            size="sm" 
            onClick={onViewCalendar}
            className="mt-2 gap-2 bg-transparent"
          >
            <CalendarDays className="h-4 w-4" />
            View Workload Calendar
          </Button>
        )}
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-6">
          {/* Workload Amount */}
          <div className="space-y-2">
            <Label htmlFor="workload" className="text-sm font-medium">
              Workload Amount
            </Label>
            <div className="relative">
              <Input
                id="workload"
                type="number"
                step="0.01"
                min="0"
                placeholder="e.g., 1.5"
                value={workload}
                onChange={(e) => setWorkload(e.target.value)}
                required
                className="pr-20"
              />
              <span className="absolute right-3 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">Units</span>
            </div>
            <p className="text-xs text-muted-foreground">Computational power required to complete the job</p>
          </div>

          <div className="grid gap-6 sm:grid-cols-2">
            {/* Data Center Preference */}
            <div className="space-y-2">
              <Label htmlFor="datacenter" className="text-sm font-medium">
                Data Center Preference
              </Label>
              <Select value={datacenter} onValueChange={setDatacenter} required>
                <SelectTrigger id="datacenter">
                  <SelectValue placeholder="Select a data center" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">
                    <span className="font-medium">No Preference</span>
                    <span className="ml-2 text-xs text-muted-foreground">(Recommended)</span>
                  </SelectItem>
                  {datacenters.map((dc) => (
                    <SelectItem key={dc.id} value={dc.id}>
                      <span className="font-medium">{dc.name}</span>
                      <span className="ml-2 text-xs text-muted-foreground">{dc.location}</span>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">
                Select &quot;No Preference&quot; for optimal environmental impact
              </p>
            </div>

            <div className="space-y-2">
              <Label htmlFor="job-type" className="text-sm font-medium">
                Job Type
              </Label>
              <Select value={jobType} onValueChange={setJobType} required>
                <SelectTrigger id="job-type">
                  <SelectValue placeholder="Select job type" />
                </SelectTrigger>
                <SelectContent>
                  {jobTypes.map((type) => (
                    <SelectItem key={type.value} value={type.value}>
                      <span className="font-medium">{type.label}</span>
                      <span className="ml-2 text-xs text-muted-foreground">{type.description}</span>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">Type of AI workload to process</p>
            </div>
          </div>

          {/* Time Constraints */}
          <div className="grid gap-6 sm:grid-cols-2">
            {/* Earliest Start */}
            <div className="space-y-2">
              <Label htmlFor="earliest-start" className="text-sm font-medium flex items-center gap-1.5">
                <Clock className="h-3.5 w-3.5" />
                Earliest Start
              </Label>
              <Input
                id="earliest-start"
                type="datetime-local"
                value={earliestStart}
                onChange={(e) => setEarliestStart(e.target.value)}
                required
              />
            </div>

            {/* Latest Finish */}
            <div className="space-y-2">
              <Label htmlFor="latest-finish" className="text-sm font-medium flex items-center gap-1.5">
                <Calendar className="h-3.5 w-3.5" />
                Latest Finish
              </Label>
              <Input
                id="latest-finish"
                type="datetime-local"
                value={latestFinish}
                onChange={(e) => setLatestFinish(e.target.value)}
                required
              />
            </div>
          </div>

          {/* Submit Button */}
          <Button type="submit" className="w-full" size="lg" disabled={isSubmitting}>
            {isSubmitting ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Scheduling...
              </>
            ) : (
              "Schedule Task"
            )}
          </Button>
        </form>
      </CardContent>
    </Card>
  )
}
