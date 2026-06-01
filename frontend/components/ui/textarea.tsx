import * as React from "react";
import { cn } from "@/lib/utils";

export interface TextareaProps
  extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {}

export function Textarea({ className, ...props }: TextareaProps) {
  return (
    <textarea
      className={cn(
        "min-h-24 w-full resize-none rounded-md border border-line bg-white px-3 py-2 text-sm text-ink outline-none transition placeholder:text-ink/40 focus:border-mint focus:ring-2 focus:ring-mint/15 dark:border-white/14 dark:bg-slate-900/80 dark:text-slate-50 dark:placeholder:text-slate-300",
        className,
      )}
      {...props}
    />
  );
}
