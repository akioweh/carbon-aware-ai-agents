import { NextRequest, NextResponse } from "next/server"
import { SCHEDULER_API_URL } from "@/app/api/apiConfig"

export async function GET(request: NextRequest) {
    try {
        const url = new URL(`${SCHEDULER_API_URL}/api/forecast`)
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