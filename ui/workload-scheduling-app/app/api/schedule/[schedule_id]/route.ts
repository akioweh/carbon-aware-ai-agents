import { NextRequest, NextResponse } from "next/server"

const BASE_URL = "http://localhost:8000/api/schedule"

// ---------------------------------------------------------
// GET /api/schedule/:schedule_id
// ---------------------------------------------------------
export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ schedule_id: string }> }
) {
  const { schedule_id } = await params

  try {
    const backendRes = await fetch(`${BASE_URL}/${schedule_id}`, {
      method: "GET",
    })

    if (!backendRes.ok) {
      throw new Error(`Backend returned ${backendRes.status}`)
    }

    const data = await backendRes.json()
    return NextResponse.json(data, { status: backendRes.status })
  } catch (err) {
    console.error("Error fetching schedule:", err)
    return NextResponse.json({ error: "Backend unavailable" }, { status: 500 })
  }
}

// ---------------------------------------------------------
// DELETE /api/schedule/:schedule_id
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

    if (backendRes.status === 200) {
      return NextResponse.json({ message: "Deleted" })
    }

    const data = await backendRes.json()
    return NextResponse.json(data, { status: backendRes.status })
  } catch (err) {
    console.error("Error deleting schedule:", err)
    return NextResponse.json({ error: "Backend unavailable" }, { status: 500 })
  }
}
