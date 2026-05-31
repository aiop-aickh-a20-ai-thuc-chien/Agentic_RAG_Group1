import * as React from "react";
import { cn } from "@/lib/utils";

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {}

export function Input({ className, ...props }: InputProps) {
  return (
    <input
      className={cn(
        "h-10 w-full rounded-md border border-line bg-white px-3 text-sm text-ink outline-none transition placeholder:text-ink/40 focus:border-mint focus:ring-2 focus:ring-mint/15 dark:border-white/14 dark:bg-slate-900/80 dark:text-slate-50 dark:placeholder:text-slate-300",
        className,
      )}
      {...props}
    />
  );
}
