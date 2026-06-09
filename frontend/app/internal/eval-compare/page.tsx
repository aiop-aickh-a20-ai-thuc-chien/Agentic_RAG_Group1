"use client";

import { useEffect, useState } from "react";
import { TrendingDown, TrendingUp } from "lucide-react";
import { cn } from "@/lib/utils";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Dataset = { id: string; name: string; is_benchmark: boolean };
type RunSummary = {
  run_id: string; name: string; config: Record<string, unknown>;
  total_questions: number;
  avg_recall: number | null; avg_mrr: number | null;
  avg_citation: number | null; guardrail_rate: number | null;
  has_ragas: boolean;
  avg_ragas_faithfulness: number | null; avg_ragas_relevancy: number | null;
};

function Delta({ curr, prev }: { curr: number | null; prev: number | null }) {
  if (curr == null || prev == null) return null;
  const diff = curr - prev;
  if (Math.abs(diff) < 0.001) return null;
  const positive = diff > 0;
  return (
    <span className={cn("inline-flex items-center gap-0.5 text-xs ml-1", positive ? "text-emerald-600" : "text-red-500")}>
      {positive ? <TrendingUp size={11} /> : <TrendingDown size={11} />}
      {positive ? "+" : ""}{(diff * 100).toFixed(1)}%
    </span>
  );
}

function MetricCell({ v, prev }: { v: number | null; prev?: number | null }) {
  if (v == null) return <td className="px-4 py-3 text-center text-gray-300 text-sm">—</td>;
  const pct = Math.round(v * 100);
  return (
    <td className="px-4 py-3 text-center">
      <span className={cn("font-semibold tabular-nums text-sm", pct >= 80 ? "text-emerald-700" : pct >= 60 ? "text-amber-600" : "text-red-600")}>
        {(v).toFixed(2)}
      </span>
      {prev !== undefined && <Delta curr={v} prev={prev} />}
    </td>
  );
}

export default function EvalComparePage() {
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [datasetId, setDatasetId] = useState<string>("");
  const [runs, setRuns]           = useState<RunSummary[]>([]);
  const [loading, setLoading]     = useState(false);

  useEffect(() => {
    fetch(`${API}/internal/datasets`).then((r) => r.json()).then((d: Dataset[]) => {
      setDatasets(d);
      if (d.length) setDatasetId(d[0].id);
    });
  }, []);

  useEffect(() => {
    if (!datasetId) return;
    setLoading(true);
    fetch(`${API}/internal/compare?dataset_id=${datasetId}`)
      .then((r) => r.json())
      .then((d: RunSummary[]) => { setRuns(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, [datasetId]);

  // Sắp xếp cũ → mới để tính delta so với version trước
  const ordered = [...runs].reverse();

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">So sánh versions</h1>
          <p className="text-sm text-gray-500 mt-1">Điểm trung bình theo từng eval run</p>
        </div>
        <select
          value={datasetId}
          onChange={(e) => setDatasetId(e.target.value)}
          className="text-sm border border-black/12 rounded-lg px-3 py-1.5 bg-white focus:outline-none focus:ring-2 focus:ring-emerald-500/40"
        >
          {datasets.map((d) => <option key={d.id} value={d.id}>{d.name}{d.is_benchmark ? " ★" : ""}</option>)}
        </select>
      </div>

      {loading && (
        <div className="flex items-center justify-center py-16 text-gray-400 gap-2">
          <span className="animate-spin">⟳</span> Đang tải...
        </div>
      )}

      {!loading && runs.length === 0 && (
        <div className="bg-white rounded-xl border border-black/8 py-16 text-center text-sm text-gray-400">
          Chưa có eval run nào cho dataset này
        </div>
      )}

      {!loading && runs.length > 0 && (
        <div className="bg-white rounded-xl border border-black/8 overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-black/6 bg-gray-50/60">
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">Version</th>
                <th className="px-4 py-3 text-center text-xs font-semibold uppercase tracking-wider text-gray-500 w-24">Câu chạy</th>
                <th className="px-4 py-3 text-center text-xs font-semibold uppercase tracking-wider text-gray-500 w-28">Recall@5</th>
                <th className="px-4 py-3 text-center text-xs font-semibold uppercase tracking-wider text-gray-500 w-28">MRR@5</th>
                <th className="px-4 py-3 text-center text-xs font-semibold uppercase tracking-wider text-gray-500 w-28">Citation</th>
                <th className="px-4 py-3 text-center text-xs font-semibold uppercase tracking-wider text-gray-500 w-28">Guardrail</th>
                <th className="px-4 py-3 text-center text-xs font-semibold uppercase tracking-wider text-gray-500 w-28">Faithfulness</th>
                <th className="px-4 py-3 text-center text-xs font-semibold uppercase tracking-wider text-gray-500 w-28">Relevancy</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-black/5">
              {ordered.map((run, i) => {
                const prev = i > 0 ? ordered[i - 1] : null;
                return (
                  <tr key={run.run_id} className="hover:bg-gray-50/40 transition-colors">
                    <td className="px-4 py-4">
                      <p className="font-medium text-gray-800">{run.name}</p>
                      {Object.keys(run.config).length > 0 && (
                        <p className="text-xs text-gray-400 mt-0.5 font-mono">
                          {Object.entries(run.config).map(([k, v]) => `${k}=${v}`).join(" · ")}
                        </p>
                      )}
                    </td>
                    <td className="px-4 py-3 text-center">
                      <span className="text-gray-600 tabular-nums">{run.total_questions.toLocaleString()}</span>
                    </td>
                    <MetricCell v={run.avg_recall}    prev={prev?.avg_recall} />
                    <MetricCell v={run.avg_mrr}       prev={prev?.avg_mrr} />
                    <MetricCell v={run.avg_citation}  prev={prev?.avg_citation} />
                    <MetricCell v={run.guardrail_rate} prev={prev?.guardrail_rate} />
                    <MetricCell v={run.has_ragas ? run.avg_ragas_faithfulness : null} prev={prev?.has_ragas ? prev.avg_ragas_faithfulness : null} />
                    <MetricCell v={run.has_ragas ? run.avg_ragas_relevancy : null}    prev={prev?.has_ragas ? prev.avg_ragas_relevancy : null} />
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Best version highlight */}
      {runs.length > 1 && (() => {
        const best = [...runs].sort((a, b) => (b.avg_recall ?? 0) - (a.avg_recall ?? 0))[0];
        return (
          <div className="bg-emerald-50 border border-emerald-200 rounded-xl px-5 py-3 flex items-center gap-3">
            <TrendingUp size={18} className="text-emerald-600 shrink-0" />
            <p className="text-sm text-emerald-800">
              <span className="font-semibold">{best.name}</span> có Recall@5 cao nhất
              {best.avg_recall != null && <> — <span className="font-mono">{best.avg_recall.toFixed(2)}</span></>}
            </p>
          </div>
        );
      })()}
    </div>
  );
}
