import { NextRequest, NextResponse } from "next/server"

const BASE_URL = "http://localhost:6969/api/schedules/trivialSchedule"

// ---------------------------------------------------------
// POST /api/schedules/trivialSchedule → proxy to backend POST /api/schedules/trivialSchedule
// Creates an un-optimized schedule (for comparison/testing purposes)
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
    console.error("Error creating trivial schedule:", err)
    return NextResponse.json({ error: "Backend unavailable" }, { status: 500 })
  }
}
