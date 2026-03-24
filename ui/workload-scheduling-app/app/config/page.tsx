"use client"

import { useRouter } from "next/navigation"
import { DataCentreConfig } from "@/components/datacenter-config"
import { PageShell } from "../../components/page-shell"

export default function ConfigPage() {
  const router = useRouter()

  return (
    <PageShell>
      <DataCentreConfig onClose={() => router.back()} />
    </PageShell>
  )
}
