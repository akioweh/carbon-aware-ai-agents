import { NextResponse } from "next/server"

const BASE_URL = "http://localhost:6969/api/schedules/summary"

export async function GET() {
  try {
    const backendRes = await fetch(BASE_URL, { method: "GET" })

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
    console.error("Error fetching schedule summaries:", err)
    return NextResponse.json({ error: "Backend unavailable" }, { status: 500 })
  }
}
