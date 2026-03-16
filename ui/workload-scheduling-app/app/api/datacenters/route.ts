import { NextResponse } from "next/server"

const CANDIDATE_STATS_BASE_URLS = [
  process.env.STATS_API_BASE_URL,
  "http://140.238.79.139:5000",
  "http://localhost:5000",
].filter(Boolean) as string[]

async function fetchFromStats(path: string, init?: RequestInit): Promise<Response> {
  let lastError: unknown

  for (const baseUrl of CANDIDATE_STATS_BASE_URLS) {
    try {
      return await fetch(`${baseUrl}${path}`, init)
    } catch (err) {
      lastError = err
    }
  }

  throw lastError ?? new Error("No stats hosts configured")
}

export async function GET() {
  try {
    const backendRes = await fetchFromStats("/datacenters", {
      method: "GET",
      cache: "no-store",
    })

    const data = await backendRes.json()
    return NextResponse.json(data, { status: backendRes.status })
  } catch (err) {
    console.error("Error fetching datacenters from stats:", err)
    return NextResponse.json(
      { error: "Stats backend unavailable" },
      { status: 500 }
    )
  }
}
