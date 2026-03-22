"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { Globe, History, ClipboardList } from "lucide-react"
import { cn } from "@/utils/utils"

const TAB_LINKS = [
  {
    href: "/",
    label: "Scheduling Form",
    icon: ClipboardList,
    isActive: (pathname: string) => pathname === "/",
  },
  {
    href: "/workload-calendar",
    label: "Global Workload",
    icon: Globe,
    isActive: (pathname: string) => pathname.startsWith("/workload-calendar"),
  },
  {
    href: "/scheduled-jobs",
    label: "Scheduled Jobs",
    icon: History,
    isActive: (pathname: string) => pathname.startsWith("/scheduled-jobs"),
  },
]

export function TopNavTabs() {
  const pathname = usePathname()

  return (
    <nav aria-label="Primary navigation" className="mb-4 w-full max-w-2xl mx-auto">
      <div className="bg-muted text-muted-foreground inline-flex h-10 w-full items-center justify-center rounded-lg p-[3px]">
        {TAB_LINKS.map((tab) => {
          const Icon = tab.icon
          const active = tab.isActive(pathname)

          return (
            <Link
              key={tab.href}
              href={tab.href}
              className={cn(
                "inline-flex h-full flex-1 items-center justify-center gap-1.5 rounded-md border border-transparent px-2 py-1 text-sm font-medium whitespace-nowrap transition-[color,box-shadow]",
                "focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:outline-none focus-visible:ring-[3px]",
                active
                  ? "bg-background text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              )}
              aria-current={active ? "page" : undefined}
            >
              <Icon className="h-4 w-4" />
              <span className="truncate">{tab.label}</span>
            </Link>
          )
        })}
      </div>
    </nav>
  )
}
