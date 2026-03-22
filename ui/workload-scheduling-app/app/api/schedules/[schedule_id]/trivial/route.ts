import { NextRequest, NextResponse } from "next/server"
import { SCHEDULER_API_URL } from "@/app/api/apiConfig"

const BASE_URL = `${SCHEDULER_API_URL}/api/schedules`

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ schedule_id: string }> }
) {
  const { schedule_id } = await params

  try {
    const url = new URL(`${BASE_URL}/${schedule_id}/trivial`)

    const datacenter = request.nextUrl.searchParams.get("datacenter")
    if (datacenter) url.searchParams.set("datacenter", datacenter)

    const backendRes = await fetch(url.toString(), { method: "GET" })

    if (!backendRes.ok) {
      console.error(`Backend returned ${backendRes.status}`)
      return NextResponse.json(
        { error: "Trivial schedule not found" },
        { status: backendRes.status }
      )
    }

    const data = await backendRes.json()
    return NextResponse.json(data, { status: 200 })
  } catch (err) {
    console.error("Error fetching trivial schedule:", err)
    return NextResponse.json({ error: "Backend unavailable" }, { status: 500 })
  }
}
