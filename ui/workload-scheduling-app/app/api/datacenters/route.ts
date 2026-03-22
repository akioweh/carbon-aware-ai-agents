import { NextResponse } from "next/server"
import { STATS_API_URL } from "@/app/api/apiConfig";

async function fetchFromStats(path: string, init?: RequestInit): Promise<Response> {
  let lastError: unknown
  let lastResponse: Response | null = null

  try {
    const response = await fetch(`${STATS_API_URL}${path}`, init)

    if (response.ok) {
      return response
    }

    lastResponse = response
    console.warn(`Stats host ${STATS_API_URL} returned ${response.status} for ${path}; trying next host`)
  } catch (err) {
    lastError = err
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
