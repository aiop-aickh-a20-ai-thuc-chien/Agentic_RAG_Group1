import { cn } from "@/lib/utils";
import type { DisplayStatus } from "@/lib/eval-review-types";

const CONFIGS: Record<
  DisplayStatus,
  { dot: string; badge: string; label: string }
> = {
  pending: {
    dot: "bg-ink/30",
    badge: "border-line bg-paper text-ink/55",
    label: "Chưa duyệt",
  },
  approved: {
    dot: "bg-mint",
    badge: "border-mint/30 bg-mint/8 text-mint",
    label: "Đã duyệt",
  },
  evaluated: {
    dot: "bg-blue-500",
    badge: "border-blue-200 bg-blue-50 text-blue-700",
    label: "Đã đánh giá",
  },
};

export function StatusBadge({ status }: { status: DisplayStatus }) {
  const { dot, badge, label } = CONFIGS[status];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium",
        badge,
      )}
    >
      <span className={cn("h-1.5 w-1.5 rounded-full flex-shrink-0", dot)} />
      {label}
    </span>
  );
}
