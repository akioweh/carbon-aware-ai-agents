import { TopNavTabs } from "@/components/top-nav-tabs"

interface PageShellProps {
  children: React.ReactNode
}

export function PageShell({ children }: PageShellProps) {
  return (
    <div className="min-h-screen bg-gradient-to-br from-background via-background to-muted/20">
      <div className="container mx-auto px-4 py-8 w-full max-w-screen-2xl">
        <header className="mb-8 text-center">
          <h1 className="text-4xl font-bold tracking-tight mb-2 text-balance">
            Carbon-Aware Workload Scheduler
          </h1>
          <p className="text-muted-foreground text-lg text-balance">
            Optimize your AI workloads for minimal environmental impact
          </p>
        </header>

        <main>
          <TopNavTabs />
          {children}
        </main>

        <footer className="mt-12 text-center text-sm text-muted-foreground">
          <p>Scheduling AI workloads to minimize carbon emissions across global data centres</p>
        </footer>
      </div>
    </div>
  )
}
