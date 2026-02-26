import { NextRequest, NextResponse } from "next/server"

const BASE_URL = "http://localhost:6969/api/locations"

export async function GET(request: NextRequest, { params }: { params: Promise<{ location: string }> | { location: string } }) {
  try {
    const resolvedParams = await params;
    const location = resolvedParams.location;
    const url = new URL(`${BASE_URL}/${location}/metrics/forecast_greenness`)
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
    console.error("Error fetching greenness:", err)
    return NextResponse.json({ error: "Backend unavailable" }, { status: 500 })
  }
}
