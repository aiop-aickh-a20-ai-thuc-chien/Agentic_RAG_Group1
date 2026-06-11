"use client";

import Link from "next/link";
import {
  ArrowRight,
  Bot,
  Check,
  ClipboardList,
  FileCheck2,
  FlaskConical,
  LockKeyhole,
  Moon,
  Sparkles,
  Sun,
  UserRound,
  type LucideIcon,
} from "lucide-react";
import { useState } from "react";
import { KnowledgeScene } from "@/components/knowledge-scene";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type Theme = "light" | "dark";

const highlights = [
  "Trả lời bằng tiếng Việt",
  "Có trích dẫn từ tài liệu",
  "Từ chối khi không đủ nguồn",
];

export default function ToolLauncherPage() {
  const [theme, setTheme] = useState<Theme>("light");
  const isDark = theme === "dark";

  return (
    <main
      className={cn(
        "relative min-h-[100dvh] overflow-hidden transition-colors",
        isDark
          ? "dark bg-[#0b1220] text-white"
          : "bg-[linear-gradient(135deg,#fbfcf8,#edf7f1_52%,#f7f8f2)] text-ink",
      )}
    >
      <KnowledgeScene />
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_74%_18%,rgba(15,143,114,0.16),transparent_28rem)] dark:bg-[radial-gradient(circle_at_76%_18%,rgba(52,211,153,0.20),transparent_30rem)]" />

      <section className="relative z-10 mx-auto flex min-h-[100dvh] max-w-7xl flex-col px-4 py-4 sm:px-6 lg:px-8">
        <header className="flex items-center justify-between rounded-lg border border-line/80 bg-white/82 px-4 py-3 shadow-panel backdrop-blur-xl dark:border-white/14 dark:bg-slate-950/88">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-lg bg-ink text-white shadow-lift dark:bg-white dark:text-ink">
              <Bot className="h-5 w-5" aria-hidden="true" />
            </div>
            <div>
              <h1 className="text-lg font-semibold tracking-normal">Agentic RAG</h1>
              <p className="text-sm text-ink/58 dark:text-slate-200">
                Chọn công cụ để bắt đầu
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              className="inline-flex h-10 items-center gap-2 rounded-md border border-line bg-white px-3 text-sm font-medium transition hover:bg-paper dark:border-white/14 dark:bg-white/10 dark:text-white dark:hover:bg-white/16"
              onClick={() => setTheme(isDark ? "light" : "dark")}
              type="button"
            >
              {isDark ? (
                <Sun className="h-4 w-4" aria-hidden="true" />
              ) : (
                <Moon className="h-4 w-4" aria-hidden="true" />
              )}
              {isDark ? "Sáng" : "Tối"}
            </button>
            <Button>
              <UserRound className="h-4 w-4" aria-hidden="true" />
              Đăng nhập
            </Button>
          </div>
        </header>

        <div className="grid flex-1 items-center gap-8 py-10 lg:grid-cols-[minmax(0,0.95fr)_minmax(420px,1fr)] lg:py-14">
          <section>
            <Badge className="border-mint/24 bg-mint/8 text-mint dark:border-emerald-300/28 dark:bg-emerald-300/12 dark:text-emerald-200">
              <Sparkles className="mr-1 h-3.5 w-3.5" aria-hidden="true" />
              Workspace RAG
            </Badge>
            <h2 className="mt-5 max-w-4xl text-5xl font-semibold leading-tight tracking-normal md:text-7xl">
              Một nơi để làm việc với tài liệu.
            </h2>
            <p className="mt-5 max-w-2xl text-base leading-7 text-ink/62 dark:text-slate-200">
              Chọn trải nghiệm cần dùng, mở vào đúng không gian làm việc, rồi hỏi
              tài liệu như một sản phẩm thật.
            </p>
          </section>

          <section className="rounded-xl border border-line/80 bg-white/88 p-3 shadow-panel backdrop-blur-xl dark:border-white/14 dark:bg-slate-950/88">
            <Link
              className="group block rounded-lg border border-mint/26 bg-[linear-gradient(135deg,rgba(15,143,114,0.10),rgba(255,255,255,0.86))] p-5 transition hover:-translate-y-0.5 hover:border-mint hover:shadow-lift dark:border-emerald-300/24 dark:bg-[linear-gradient(135deg,rgba(52,211,153,0.14),rgba(15,23,42,0.88))] dark:hover:border-emerald-300/60"
              href="/citation-chat"
            >
              <div className="flex items-start justify-between gap-4">
                <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-ink text-white dark:bg-emerald-300 dark:text-ink">
                  <FileCheck2 className="h-6 w-6" aria-hidden="true" />
                </div>
                <ArrowRight className="h-5 w-5 text-ink/46 transition group-hover:translate-x-1 dark:text-slate-300" aria-hidden="true" />
              </div>

              <div className="mt-8">
                <p className="text-sm font-semibold text-mint dark:text-emerald-200">
                  Công cụ đang có
                </p>
                <h3 className="mt-2 text-3xl font-semibold tracking-normal">
                  Hỏi đáp có trích dẫn
                </h3>
                <p className="mt-3 max-w-2xl text-sm leading-6 text-ink/60 dark:text-slate-200">
                  Tải tài liệu, đặt câu hỏi, nhận câu trả lời kèm nguồn kiểm chứng
                  giống phong cách NotebookLM.
                </p>
              </div>

              <div className="mt-8 grid gap-2 sm:grid-cols-3">
                {highlights.map((item) => (
                  <div
                    className="rounded-md border border-line bg-white/76 px-3 py-2 text-sm dark:border-white/14 dark:bg-white/10 dark:text-slate-100"
                    key={item}
                  >
                    <Check className="mb-2 h-4 w-4 text-mint dark:text-emerald-300" aria-hidden="true" />
                    {item}
                  </div>
                ))}
              </div>
            </Link>

            <div className="mt-3 grid gap-3 sm:grid-cols-3">
              <Link
                href="/internal/eval-review"
                className="group rounded-lg border border-line/80 bg-white/64 p-4 text-sm transition hover:-translate-y-0.5 hover:border-mint/40 hover:bg-white hover:shadow-sm dark:border-white/14 dark:bg-slate-900/76"
              >
                <ClipboardList className="mb-3 h-4 w-4 text-mint dark:text-emerald-300" aria-hidden="true" />
                <p className="font-medium text-ink dark:text-slate-100">Eval Review</p>
                <p className="mt-1 text-xs text-ink/56 dark:text-slate-200">
                  Duyệt & đánh giá câu hỏi
                </p>
              </Link>
              <Link
                href="/internal/autodata"
                className="group rounded-lg border border-line/80 bg-white/64 p-4 text-sm transition hover:-translate-y-0.5 hover:border-mint/40 hover:bg-white hover:shadow-sm dark:border-white/14 dark:bg-slate-900/76"
              >
                <FlaskConical className="mb-3 h-4 w-4 text-mint dark:text-emerald-300" aria-hidden="true" />
                <p className="font-medium text-ink dark:text-slate-100">AutoData</p>
                <p className="mt-1 text-xs text-ink/56 dark:text-slate-200">
                  Tự sinh câu hỏi từ tài liệu
                </p>
              </Link>
              <ComingSoon icon={LockKeyhole} label="Quản lý hồ sơ" />
            </div>
          </section>
        </div>
      </section>
    </main>
  );
}

function ComingSoon({
  icon: Icon,
  label,
}: {
  icon: LucideIcon;
  label: string;
}) {
  return (
    <div className="rounded-lg border border-line/80 bg-white/64 p-4 text-sm text-ink/56 dark:border-white/14 dark:bg-slate-900/76 dark:text-slate-200">
      <Icon className="mb-3 h-4 w-4" aria-hidden="true" />
      <p className="font-medium">{label}</p>
      <p className="mt-1 text-xs">Sẽ mở rộng sau</p>
    </div>
  );
}
