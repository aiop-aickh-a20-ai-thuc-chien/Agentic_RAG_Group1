"use client";

/**
 * Command palette Ctrl+K — nhảy nhanh giữa các trang internal, tìm dataset/run.
 * Data fetch lười: chỉ gọi API khi mở palette lần đầu.
 */

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Command } from "cmdk";
import {
  BarChart3, Database, GitCompare, ListChecks, Play, ShieldCheck, Sparkles,
} from "lucide-react";

const API = process.env.NEXT_PUBLIC_AGENTIC_RAG_API_URL ?? "http://localhost:8000";

const PAGES = [
  { href: "/internal/dedup-review", label: "Dedup",        icon: ShieldCheck },
  { href: "/internal/autodata",     label: "Tạo câu hỏi",  icon: Sparkles },
  { href: "/internal/eval-review",  label: "Review",       icon: ListChecks },
  { href: "/internal/datasets",     label: "Datasets",     icon: Database },
  { href: "/internal/eval-run",     label: "Chạy Eval",    icon: Play },
  { href: "/internal/eval-results", label: "Eval Results", icon: BarChart3 },
  { href: "/internal/eval-compare", label: "So sánh",      icon: GitCompare },
];

type Dataset = { id: string; name: string };
type Run     = { id: string; name: string; status: string };

export function CommandPalette() {
  const router = useRouter();
  const [open, setOpen]         = useState(false);
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [runs, setRuns]         = useState<Run[]>([]);
  const [loaded, setLoaded]     = useState(false);

  // Ctrl+K / Cmd+K mở, Esc đóng (cmdk tự xử lý Esc qua onOpenChange của dialog)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "k" && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        setOpen((v) => !v);
      }
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  // Fetch lười khi mở lần đầu
  useEffect(() => {
    if (!open || loaded) return;
    setLoaded(true);
    fetch(`${API}/internal/datasets`)
      .then((r) => r.json())
      .then((d: Dataset[]) => setDatasets(Array.isArray(d) ? d : []))
      .catch(() => {});
    fetch(`${API}/internal/runs`)
      .then((r) => r.json())
      .then((d: Run[]) => setRuns(Array.isArray(d) ? d.slice(0, 20) : []))
      .catch(() => {});
  }, [open, loaded]);

  const go = (href: string) => {
    setOpen(false);
    router.push(href);
  };

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center pt-[18vh] bg-black/25 backdrop-blur-sm"
      onClick={() => setOpen(false)}
    >
      <div onClick={(e) => e.stopPropagation()} className="w-full max-w-lg mx-4 page-enter">
        <Command
          label="Command palette"
          className="bg-white rounded-2xl border border-black/10 shadow-2xl overflow-hidden"
        >
          <Command.Input
            autoFocus
            placeholder="Tìm trang, dataset, run..."
            className="w-full px-5 py-3.5 text-sm border-b border-black/8 focus:outline-none placeholder:text-gray-400"
          />
          <Command.List className="max-h-80 overflow-y-auto p-2">
            <Command.Empty className="py-8 text-center text-sm text-gray-400">
              Không tìm thấy kết quả
            </Command.Empty>

            <Command.Group heading="Trang" className="text-[11px] uppercase tracking-wider text-gray-400 px-2 [&_[cmdk-group-items]]:mt-1">
              {PAGES.map((p) => (
                <Command.Item
                  key={p.href}
                  value={`page ${p.label}`}
                  onSelect={() => go(p.href)}
                  className="flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm text-gray-700 cursor-pointer data-[selected=true]:bg-emerald-50 data-[selected=true]:text-emerald-800"
                >
                  <p.icon size={15} className="text-gray-400" />
                  {p.label}
                </Command.Item>
              ))}
            </Command.Group>

            {datasets.length > 0 && (
              <Command.Group heading="Datasets" className="text-[11px] uppercase tracking-wider text-gray-400 px-2 mt-2 [&_[cmdk-group-items]]:mt-1">
                {datasets.map((d) => (
                  <Command.Item
                    key={d.id}
                    value={`dataset ${d.name}`}
                    onSelect={() => go("/internal/datasets")}
                    className="flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm text-gray-700 cursor-pointer data-[selected=true]:bg-emerald-50 data-[selected=true]:text-emerald-800"
                  >
                    <Database size={15} className="text-gray-400" />
                    {d.name}
                  </Command.Item>
                ))}
              </Command.Group>
            )}

            {runs.length > 0 && (
              <Command.Group heading="Eval Runs" className="text-[11px] uppercase tracking-wider text-gray-400 px-2 mt-2 [&_[cmdk-group-items]]:mt-1">
                {runs.map((r) => (
                  <Command.Item
                    key={r.id}
                    value={`run ${r.name}`}
                    onSelect={() => go("/internal/eval-results")}
                    className="flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm text-gray-700 cursor-pointer data-[selected=true]:bg-emerald-50 data-[selected=true]:text-emerald-800"
                  >
                    <Play size={15} className="text-gray-400" />
                    <span className="flex-1 truncate">{r.name}</span>
                    <span className="text-[11px] text-gray-400">{r.status}</span>
                  </Command.Item>
                ))}
              </Command.Group>
            )}
          </Command.List>
        </Command>
      </div>
    </div>
  );
}
