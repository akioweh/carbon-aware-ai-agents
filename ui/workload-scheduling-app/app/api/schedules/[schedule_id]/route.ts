import { NextRequest, NextResponse } from "next/server"
import { SCHEDULER_API_URL } from "@/app/api/apiConfig"

const BASE_URL = `${SCHEDULER_API_URL}/api/schedules`

// ---------------------------------------------------------
// GET /api/schedules/:schedule_id
// Retrieves a specific schedule by ID
// Supports optional: datacenter parameter
// ---------------------------------------------------------
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ schedule_id: string }> }
) {
  const { schedule_id } = await params

  try {
    const url = new URL(`${BASE_URL}/${schedule_id}`)

    // Pass through optional datacenter parameter
    const datacenter = request.nextUrl.searchParams.get("datacenter")
    if (datacenter) url.searchParams.set("datacenter", datacenter)

    const backendRes = await fetch(url.toString(), { method: "GET" })

    if (!backendRes.ok) {
      console.error(`Backend returned ${backendRes.status}`)
      return NextResponse.json(
        { error: "Schedule not found" },
        { status: backendRes.status }
      )
    }

    const data = await backendRes.json()
    return NextResponse.json(data, { status: 200 })
  } catch (err) {
    console.error("Error fetching schedule:", err)
    return NextResponse.json({ error: "Backend unavailable" }, { status: 500 })
  }
}

// ---------------------------------------------------------
// DELETE /api/schedules/:schedule_id
// Deletes a specific schedule by ID
// ---------------------------------------------------------
export async function DELETE(
  _request: NextRequest,
  { params }: { params: Promise<{ schedule_id: string }> }
) {
  const { schedule_id } = await params

  try {
    const backendRes = await fetch(`${BASE_URL}/${schedule_id}`, {
      method: "DELETE",
    })

    if (backendRes.status === 204 || backendRes.status === 200) {
      return NextResponse.json({ message: "Deleted" }, { status: 200 })
    }

    const data = await backendRes.json()
    return NextResponse.json(data, { status: backendRes.status })
  } catch (err) {
    console.error("Error deleting schedule:", err)
    return NextResponse.json({ error: "Backend unavailable" }, { status: 500 })
  }
}
