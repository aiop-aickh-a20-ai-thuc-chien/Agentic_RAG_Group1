"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/internal/autodata",     label: "Tạo câu hỏi" },
  { href: "/internal/eval-review",  label: "Review" },
  { href: "/internal/datasets",     label: "Datasets" },
  { href: "/internal/eval-run",     label: "Chạy Eval" },
  { href: "/internal/eval-results", label: "Eval Results" },
  { href: "/internal/eval-compare", label: "So sánh" },
];

export default function InternalLayout({ children }: { children: React.ReactNode }) {
  const path = usePathname();

  return (
    <div className="min-h-screen" style={{ background: "var(--bg)" }}>
      {/* Top bar */}
      <header className="border-b border-black/8 bg-white/60 backdrop-blur-sm sticky top-0 z-20">
        <div className="max-w-7xl mx-auto px-6 h-14 flex items-center gap-8">
          <Link href="/" className="text-sm text-gray-400 hover:text-gray-600 transition-colors mr-2">
            ← App
          </Link>
          <span className="text-xs font-semibold uppercase tracking-widest text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded">
            Internal
          </span>
          <nav className="flex items-center gap-1 ml-2">
            {NAV.map((n) => (
              <Link
                key={n.href}
                href={n.href}
                className={cn(
                  "px-4 py-1.5 rounded-md text-sm font-medium transition-colors",
                  path === n.href
                    ? "bg-emerald-700 text-white"
                    : "text-gray-600 hover:bg-gray-100"
                )}
              >
                {n.label}
              </Link>
            ))}
          </nav>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-8">{children}</main>
    </div>
  );
}
