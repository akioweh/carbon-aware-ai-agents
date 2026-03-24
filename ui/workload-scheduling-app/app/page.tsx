"use client"

import { useRouter } from "next/navigation"
import { SchedulingForm } from "@/components/scheduling-form"
import { PageShell } from "../components/page-shell"

export default function Home() {
  const router = useRouter()

  const handleScheduleComplete = (result: any) => {
    router.push(`/schedule/${result.schedule_id}`)
  }

  return (
    <PageShell>
      <SchedulingForm
        onScheduleComplete={handleScheduleComplete}
        onConfigure={() => router.push("/config")}
      />
    </PageShell>
  )
}
