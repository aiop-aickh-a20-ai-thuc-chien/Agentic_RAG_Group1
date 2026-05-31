import * as React from "react";
import { cn } from "@/lib/utils";

export function Badge({
  className,
  ...props
}: React.HTMLAttributes<HTMLSpanElement>) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border border-line bg-white px-2.5 py-1 text-xs font-medium text-ink dark:border-white/14 dark:bg-slate-900/82 dark:text-slate-50",
        className,
      )}
      {...props}
    />
  );
}
