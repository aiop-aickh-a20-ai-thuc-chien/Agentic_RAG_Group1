"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion } from "motion/react";
import { Toaster } from "sonner";
import { cn } from "@/lib/utils";
import { CommandPalette } from "./_components/command-palette";

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
      {/* Top bar — kính mờ + bóng tách khỏi nội dung */}
      <header className="border-b border-black/8 bg-white/70 backdrop-blur-md sticky top-0 z-20 shadow-[0_1px_12px_rgba(17,24,39,0.05)]">
        <div className="max-w-7xl mx-auto px-6 h-14 flex items-center gap-8">
          <Link href="/" className="text-sm text-gray-400 hover:text-gray-600 hover:-translate-x-0.5 transition-all mr-2">
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
                  "relative px-4 py-1.5 rounded-md text-sm font-medium transition-colors duration-200 pressable",
                  path === n.href ? "text-white" : "text-gray-600 hover:bg-gray-100"
                )}
              >
                {/* Pill trượt mượt giữa các tab nhờ layoutId chung */}
                {path === n.href && (
                  <motion.span
                    layoutId="nav-pill"
                    className="absolute inset-0 rounded-md bg-emerald-700 shadow-md shadow-emerald-700/25"
                    transition={{ type: "spring", stiffness: 400, damping: 32 }}
                  />
                )}
                <span className="relative z-10">{n.label}</span>
              </Link>
            ))}
          </nav>
          <kbd className="ml-auto hidden md:flex items-center gap-1 text-[11px] text-gray-400 border border-black/10 rounded-md px-1.5 py-0.5 bg-white/60">
            Ctrl K
          </kbd>
        </div>
      </header>

      {/* key theo path để nội dung fade-in mỗi lần chuyển trang */}
      <main key={path} className="max-w-7xl mx-auto px-6 py-8 page-enter">{children}</main>

      <CommandPalette />
      <Toaster richColors position="top-right" closeButton />
    </div>
  );
}
