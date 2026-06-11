"use client";

/**
 * FX components dùng chung cho các trang internal eval.
 * Nguyên tắc: animation ghi thẳng vào DOM qua ref (không setState mỗi frame),
 * tôn trọng prefers-reduced-motion.
 */

import { useEffect, useRef } from "react";
import { cn } from "@/lib/utils";

// ── CountUp: số đếm chạy từ giá trị cũ → mới, nhấp nháy khi đổi ──────────────
export function CountUp({
  value,
  format,
  className,
  flash = true,
}: Readonly<{
  value: number;
  format?: (v: number) => string;
  className?: string;
  flash?: boolean;
}>) {
  const ref = useRef<HTMLSpanElement>(null);
  const prevRef = useRef<number | null>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const fmt = (v: number) => (format ? format(v) : String(Math.round(v)));
    const from = prevRef.current ?? 0;
    const to = value;
    const isFirst = prevRef.current === null;
    prevRef.current = value;

    const reduce = globalThis.window?.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce || from === to) {
      el.textContent = fmt(to);
      return;
    }

    const dur = 600;
    const t0 = performance.now();
    let raf = 0;
    const tick = (t: number) => {
      const p = Math.min(1, (t - t0) / dur);
      const eased = 1 - Math.pow(1 - p, 3); // ease-out cubic
      el.textContent = fmt(from + (to - from) * eased);
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);

    // Nhấp nháy nền khi giá trị THAY ĐỔI (không nháy lần mount đầu)
    if (flash && !isFirst) {
      el.classList.remove("value-flash");
      void el.offsetWidth; // ép restart animation
      el.classList.add("value-flash");
    }
    return () => cancelAnimationFrame(raf);
  }, [value, format, flash]);

  return <span ref={ref} className={cn("inline-block", className)} />;
}

// ── Skeleton: khung xương shimmer khi loading ─────────────────────────────────
export function Skeleton({ className }: Readonly<{ className?: string }>) {
  return <div className={cn("skeleton", className)} />;
}

/** Skeleton dạng bảng: header + N hàng, dùng cho mọi bảng đang tải */
export function TableSkeleton({ rows = 6 }: Readonly<{ rows?: number }>) {
  return (
    <div className="px-5 py-4 space-y-3">
      <div className="flex gap-4">
        <Skeleton className="h-3 w-1/3" />
        <Skeleton className="h-3 w-16" />
        <Skeleton className="h-3 w-16" />
        <Skeleton className="h-3 w-20 ml-auto" />
      </div>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="flex items-center gap-4">
          <Skeleton className={cn("h-4", i % 2 ? "w-2/5" : "w-1/2")} />
          <Skeleton className="h-4 w-14" />
          <Skeleton className="h-4 w-14" />
          <Skeleton className="h-4 w-24 ml-auto" />
        </div>
      ))}
    </div>
  );
}

// ── Spotlight: quầng sáng theo con trỏ trên card (Tầng 2) ────────────────────
export function Spotlight({
  children,
  className,
}: Readonly<{ children: React.ReactNode; className?: string }>) {
  const ref = useRef<HTMLDivElement>(null);
  return (
    <div
      ref={ref}
      className={cn("spotlight", className)}
      onMouseMove={(e) => {
        const el = ref.current;
        if (!el) return;
        const r = el.getBoundingClientRect();
        el.style.setProperty("--spot-x", `${e.clientX - r.left}px`);
        el.style.setProperty("--spot-y", `${e.clientY - r.top}px`);
      }}
    >
      {children}
    </div>
  );
}
