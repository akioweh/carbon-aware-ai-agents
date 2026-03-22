import { NextRequest, NextResponse } from "next/server"
import { SCHEDULER_API_URL } from "@/app/api/apiConfig"

const BASE_URL = `${SCHEDULER_API_URL}/api/hardwareSpecs/gpus`

// ---------------------------------------------------------
// GET /api/hardwareSpecs/gpus
// Gets available GPU specs
// ---------------------------------------------------------
export async function GET(_request: NextRequest) {
    try {
        const backendRes = await fetch(BASE_URL, {
            method: "GET",
        })

        if (!backendRes.ok) {
            console.error(`Backend returned ${backendRes.status}`)
            return NextResponse.json(
                { error: "Failed to fetch GPU specs" },
                { status: backendRes.status }
            )
        }

        const data = await backendRes.json()
        return NextResponse.json(data, { status: 200 })
    } catch (err) {
        console.error("Error fetching GPU specs:", err)
        return NextResponse.json({ error: "Backend unavailable" }, { status: 503 })
    }
}