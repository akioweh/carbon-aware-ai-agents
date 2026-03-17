import { NextResponse } from "next/server"

const CANDIDATE_STATS_BASE_URLS = [
  process.env.STATS_API_BASE_URL,
  "http://140.238.79.139:5000",
  "http://localhost:5000",
].filter(Boolean) as string[]

async function fetchFromStats(path: string, init?: RequestInit): Promise<Response> {
  let lastError: unknown
  let lastResponse: Response | null = null

  for (const baseUrl of CANDIDATE_STATS_BASE_URLS) {
    try {
      const response = await fetch(`${baseUrl}${path}`, init)

      if (response.ok) {
        return response
      }

      lastResponse = response
      console.warn(`Stats host ${baseUrl} returned ${response.status} for ${path}; trying next host`)
    } catch (err) {
      lastError = err
    }
  }

  if (lastResponse) {
    return lastResponse
  }

  throw lastError ?? new Error("No stats hosts configured")
}

async function parseBackendBody(response: Response): Promise<unknown> {
  const raw = await response.text()
  if (!raw) return null

  try {
    return JSON.parse(raw)
  } catch {
    return { message: raw }
  }
}

export async function GET() {
  try {
    const backendRes = await fetchFromStats("/datacenters", {
      method: "GET",
      cache: "no-store",
    })

    const data = await parseBackendBody(backendRes)
    return NextResponse.json(data, { status: backendRes.status })
  } catch (err) {
    console.error("Error fetching datacenters from stats:", err)
    return NextResponse.json(
      { error: "Stats backend unavailable" },
      { status: 500 }
    )
  }
}
