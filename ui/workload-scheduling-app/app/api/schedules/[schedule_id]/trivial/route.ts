import { NextRequest, NextResponse } from "next/server"

const BACKEND_URL = process.env.BACKEND_URL || "http://127.0.0.1:6969"

export async function GET(
  request: NextRequest,
  { params }: { params: { schedule_id: string } }
) {
  try {
    // Next.js 15+ async params
    const { schedule_id } = await params;
    
    // Extract datacenter query parameter if it exists (don't forward next internals)
    const searchParams = request.nextUrl.searchParams
    const datacenter = searchParams.get('datacenter')
    
    const url = `${BACKEND_URL}/api/schedules/${schedule_id}/trivial${datacenter ? `?datacenter=${encodeURIComponent(datacenter)}` : ""}`
    
    console.log(`[API Proxy] GET ${url}`)
    
    const response = await fetch(url)
    
    if (!response.ok) {
      // Pass through the error status
      return NextResponse.json(
        { error: `Backend responded with status: ${response.status}` },
        { status: response.status }
      )
    }
    
    const data = await response.json()
    return NextResponse.json(data)
  } catch (error) {
    console.error("[API Proxy] Error fetching trivial schedule details:", error)
    return NextResponse.json(
      { error: "Failed to fetch trivial schedule details from backend" },
      { status: 500 }
    )
  }
}
