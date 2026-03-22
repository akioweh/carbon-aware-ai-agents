import { NextResponse } from 'next/server';
import { STATS_API_HOST } from '@/app/api/apiConfig'
export async function GET() {
    try {
        const response = await fetch(`${STATS_API_HOST}/predictionWindow`, {
            cache: 'no-store'
        });

        if (!response.ok) {
            return NextResponse.json({ error: 'Backend responded with error' }, { status: response.status });
        }

        const data = await response.json();
        return NextResponse.json(data);
    } catch (error) {
        console.error("Proxy error:", error);
        return NextResponse.json({ error: 'Failed to connect to backend' }, { status: 500 });
    }
}
