"use client"

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { CalendarCheck, MapPin, Leaf, Clock, ArrowLeft } from "lucide-react"

interface ScheduleResultProps {
  result: {
    schedule_id: string
    job_id: string
    location: string
    start_time: string
    end_time: string
    carbon_intensity?: number
    estimated_emissions_kg?: number
    sci_per_unit?: number
  }
  onBack?: () => void
}

export function ScheduleResult({ result, onBack }: ScheduleResultProps) {
  const formatDateTime = (isoString: string) => {
    return new Date(isoString).toLocaleString("en-US", {
      dateStyle: "medium",
      timeStyle: "short",
    })
  }

  const calculateDuration = (start: string, end: string) => {
    const startTime = new Date(start).getTime()
    const endTime = new Date(end).getTime()
    const hours = Math.round(((endTime - startTime) / (1000 * 60 * 60)) * 10) / 10
    return hours
  }

  return (
    <div className="space-y-6">
      {/* Back Button */}
      {onBack && (
        <Button variant="ghost" onClick={onBack} className="gap-2">
          <ArrowLeft className="h-4 w-4" />
          Schedule Another Job
        </Button>
      )}

      {/* Success Header */}
      <div className="text-center space-y-2">
        <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-primary/10 mb-4">
          <CalendarCheck className="h-8 w-8 text-primary" />
        </div>
        <h2 className="text-3xl font-bold text-foreground">Schedule Created!</h2>
        <p className="text-muted-foreground">Your job has been optimized for minimal environmental impact</p>
      </div>

      {/* Schedule Details */}
      <Card className="border-2">
        <CardHeader>
          <CardTitle>Schedule Details</CardTitle>
          <CardDescription>Job ID: {result.job_id}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Basic Info */}
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <MapPin className="h-4 w-4" />
                <span>Data Center</span>
              </div>
              <p className="text-lg font-semibold">{result.location}</p>
            </div>

            <div className="space-y-2">
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Clock className="h-4 w-4" />
                <span>Duration</span>
              </div>
              <p className="text-lg font-semibold">{calculateDuration(result.start_time, result.end_time)} hours</p>
            </div>
          </div>

          {/* Timing */}
          <div className="space-y-3 p-4 bg-muted/50 rounded-lg">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-sm text-muted-foreground mb-1">Start Time</p>
                <p className="font-medium">{formatDateTime(result.start_time)}</p>
              </div>
              <Badge variant="secondary">Scheduled</Badge>
            </div>
            <div className="border-l-2 border-border ml-2 pl-4 py-2">
              <p className="text-xs text-muted-foreground">Running...</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground mb-1">End Time</p>
              <p className="font-medium">{formatDateTime(result.end_time)}</p>
            </div>
          </div>

          {/* Environmental Impact */}
          {(result.carbon_intensity !== undefined ||
            result.estimated_emissions_kg !== undefined ||
            result.sci_per_unit !== undefined) && (
            <div className="space-y-4">
              <div className="flex items-center gap-2">
                <Leaf className="h-5 w-5 text-primary" />
                <h3 className="font-semibold">Environmental Impact</h3>
              </div>

              <div className="grid gap-4 sm:grid-cols-3">
                {result.carbon_intensity !== undefined && (
                  <div className="p-4 bg-primary/5 rounded-lg space-y-1">
                    <p className="text-xs text-muted-foreground">Carbon Intensity</p>
                    <p className="text-2xl font-bold text-primary">{result.carbon_intensity.toFixed(3)}</p>
                    <p className="text-xs text-muted-foreground">kg CO₂/kWh</p>
                  </div>
                )}

                {result.estimated_emissions_kg !== undefined && (
                  <div className="p-4 bg-primary/5 rounded-lg space-y-1">
                    <p className="text-xs text-muted-foreground">Total Emissions</p>
                    <p className="text-2xl font-bold text-primary">{result.estimated_emissions_kg.toFixed(2)}</p>
                    <p className="text-xs text-muted-foreground">kg CO₂</p>
                  </div>
                )}

                {result.sci_per_unit !== undefined && (
                  <div className="p-4 bg-primary/5 rounded-lg space-y-1">
                    <p className="text-xs text-muted-foreground">SCI per Unit</p>
                    <p className="text-2xl font-bold text-primary">{result.sci_per_unit.toFixed(2)}</p>
                    <p className="text-xs text-muted-foreground">kg CO₂e/unit</p>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Schedule ID */}
          <div className="pt-4 border-t">
            <p className="text-xs text-muted-foreground">Schedule ID</p>
            <p className="font-mono text-sm mt-1">{result.schedule_id}</p>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
