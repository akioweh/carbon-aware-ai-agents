import { NextRequest, NextResponse } from "next/server"
import { SCHEDULER_API_URL } from "@/app/api/apiConfig"

const BASE_URL = `${SCHEDULER_API_URL}/api/schedules`

// ---------------------------------------------------------
// GET /api/schedules → proxy to backend GET /api/schedules
// Supports optional: start_time, end_time, datacenter parameters
// ---------------------------------------------------------
export async function GET(request: NextRequest) {
  try {
    const url = new URL(BASE_URL)

    // Pass through optional query parameters
    const start = request.nextUrl.searchParams.get("start_time")
    const end = request.nextUrl.searchParams.get("end_time")
    const datacenter = request.nextUrl.searchParams.get("datacenter")

    if (start) url.searchParams.set("start_time", start)
    if (end) url.searchParams.set("end_time", end)
    if (datacenter) url.searchParams.set("datacenter", datacenter)

    const backendRes = await fetch(url.toString(), { method: "GET" })

    if (!backendRes.ok) {
      console.error(`Backend returned ${backendRes.status}`)
      return NextResponse.json(
        { error: "Backend unavailable" },
        { status: backendRes.status }
      )
    }

    const data = await backendRes.json()
    return NextResponse.json(data, { status: 200 })
  } catch (err) {
    console.error("Error fetching schedules:", err)
    return NextResponse.json({ error: "Backend unavailable" }, { status: 500 })
  }
}

// ---------------------------------------------------------
// POST /api/schedules → proxy to backend POST /api/schedules
// Creates an optimized schedule
// ---------------------------------------------------------
export async function POST(request: NextRequest) {
  try {
    const body = await request.json()

    const backendRes = await fetch(BASE_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })

    const data = await backendRes.json()
    return NextResponse.json(data, { status: backendRes.status })
  } catch (err) {
    console.error("Error creating schedule:", err)
    return NextResponse.json({ error: "Backend unavailable" }, { status: 500 })
  }
}
