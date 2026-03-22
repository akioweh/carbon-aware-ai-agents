import { NextRequest, NextResponse } from "next/server"

const FORECAST_URL = "http://localhost:6969/api/forecast"

export async function GET(request: NextRequest) {
    try {
        const url = new URL(FORECAST_URL)
        request.nextUrl.searchParams.forEach((value, key) => {
            url.searchParams.set(key, value)
        })

        const backendRes = await fetch(url.toString(), { method: "GET" })

        if (!backendRes.ok) {
            return NextResponse.json(
                { error: "Forecast data not found" },
                { status: backendRes.status }
            )
        }

        const data = await backendRes.json()
        return NextResponse.json(data, { status: 200 })
    } catch (err) {
        console.error("Error fetching forecast:", err)
        return NextResponse.json({ error: "Backend unavailable" }, { status: 500 })
    }
}