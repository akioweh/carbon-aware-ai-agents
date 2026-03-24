"use client"

import { useRouter } from "next/navigation"
import { PreviousJobs } from "@/components/previous-jobs"
import { PageShell } from "../../components/page-shell"
import { JobSummary } from "@/types/schedule"

export default function ScheduledJobsPage() {
  const router = useRouter()

  const handleSelectJob = (job: JobSummary) => {
    // Navigate to the schedule detail page
    router.push(`/schedule/${job.schedule_id}`)
  }

  return (
    <PageShell>
      <PreviousJobs onSelectJob={handleSelectJob} />
    </PageShell>
  )
}
