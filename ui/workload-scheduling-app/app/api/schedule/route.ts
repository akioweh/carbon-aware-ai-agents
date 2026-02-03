import { NextRequest, NextResponse } from "next/server"

const BASE_URL = "http://localhost:8000/api/schedule"

// ---------------------------------------------------------
// GET /api/schedule → proxy to FastAPI GET /api/schedule
// ---------------------------------------------------------
export async function GET(request: NextRequest) {
  const url = new URL(BASE_URL)

  const start = request.nextUrl.searchParams.get("start_time")
  const end = request.nextUrl.searchParams.get("end_time")

  if (start) url.searchParams.set("start_time", start)
  if (end) url.searchParams.set("end_time", end)

  try {
    const backendRes = await fetch(url.toString(), {
      method: "GET",
    })

    const data = await backendRes.json()
    return NextResponse.json(data, { status: backendRes.status })
  } catch (err) {
    console.error("Error fetching schedule:", err)
    return NextResponse.json({ error: "Backend unavailable" }, { status: 500 })
  }
}

// ---------------------------------------------------------
// POST /api/schedule → proxy to FastAPI POST /api/schedule
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
