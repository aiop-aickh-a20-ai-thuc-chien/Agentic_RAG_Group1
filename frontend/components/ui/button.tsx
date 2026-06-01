import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex h-10 items-center justify-center gap-2 rounded-md px-4 text-sm font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mint disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        primary: "bg-ink text-white hover:bg-ink/90 dark:bg-white dark:text-ink dark:hover:bg-white/90",
        secondary:
          "border border-line bg-white text-ink hover:bg-paper dark:border-white/14 dark:bg-slate-900/82 dark:text-slate-50 dark:hover:bg-slate-800",
        ghost: "text-ink hover:bg-white dark:text-slate-50 dark:hover:bg-slate-800",
      },
      size: {
        default: "h-10 px-4",
        icon: "h-10 w-10 px-0",
      },
    },
    defaultVariants: {
      variant: "primary",
      size: "default",
    },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

export function Button({ className, variant, size, ...props }: ButtonProps) {
  return (
    <button className={cn(buttonVariants({ variant, size }), className)} {...props} />
  );
}
