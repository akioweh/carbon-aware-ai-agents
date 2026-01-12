import { type NextRequest, NextResponse } from "next/server"

export async function POST(request: NextRequest) {
  try {
    const body = await request.json()

    // Mock response based on ScheduleResponse schema
    // Replace this with actual API call to your backend
    const mockResponse = {
      schedule_id: `sched-${Math.random().toString(36).substring(7)}`,
      job_id: body.job_id,
      location: body.data_centre === "No Preference" ? "dc3" : body.data_centre,
      start_time: new Date(Date.now() + 3600000).toISOString(), // 1 hour from now
      end_time: new Date(Date.now() + 3600000 + body.workload_amount * 3600000).toISOString(),
      carbon_intensity: 0.12 + Math.random() * 0.1,
      estimated_emissions_kg: body.workload_amount * (15 + Math.random() * 10),
      sci_per_unit: 1.5 + Math.random() * 1.0,
    }

    return NextResponse.json(mockResponse)
  } catch (error) {
    return NextResponse.json({ error: "Invalid request" }, { status: 400 })
  }
}
