"use client";

import React, { useEffect, useMemo, useState } from "react";
import { ChevronDown, ChevronRight, ChevronLeft, Loader2, TrendingDown, TrendingUp } from "lucide-react";
import {
  CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { cn } from "@/lib/utils";

const API = process.env.NEXT_PUBLIC_AGENTIC_RAG_API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const DETAIL_PAGE_SIZE = 50;

type Dataset = { id: string; name: string; is_benchmark: boolean };
type RunSummary = {
  run_id: string; name: string; config: Record<string, unknown>;
  total_questions: number;
  avg_recall: number | null; avg_mrr: number | null;
  avg_citation: number | null; guardrail_rate: number | null;
  has_ragas: boolean;
  avg_ragas_faithfulness: number | null; avg_ragas_relevancy: number | null;
  external: boolean;
  source_dataset_name: string | null;
  coverage: number;
  coverage_total: number;
};
type Result = {
  id: string; question_id: string; run_id: string;
  rag_context: string | null; bot_response: string | null;
  bot_citations: unknown; trace_url: string | null;
  retrieved_top5_ids: string[] | null; ground_truth_rank: number | null;
  recall_at_5: number | null; mrr_at_5: number | null;
  citation_chunk_match: number | null; guardrail_pass: boolean | null;
  ragas_faithfulness: number | null; ragas_answer_relevancy: number | null;
  ragas_context_precision: number | null; ragas_context_recall: number | null;
  ran_at: string;
};
type Question = { id: string; question: string; ground_truth: string; section: string | null; source_chunk_ids: string[] | null; is_approved: boolean };
type PairedRow = { questionId: string; a: Result | null; b: Result | null };

function fmtPct(v: number | null, digits = 2) {
  if (v === null || v === undefined) return "—";
  return (v * 100).toFixed(digits) + "%";
}

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

// Per-question side-by-side metric cell — A / B, winner highlighted.
function CmpCell({ a, b, good = 0.7, bad = 0.4 }: { a: number | null; b: number | null; good?: number; bad?: number }) {
  const aWins = a !== null && (b === null || a > b + 0.005);
  const bWins = b !== null && (a === null || b > a + 0.005);
  const cls = (v: number | null, wins: boolean) => {
    if (v === null) return "text-gray-300";
    const base = v >= good ? "bg-emerald-50 text-emerald-700" : v >= bad ? "bg-amber-50 text-amber-700" : "bg-red-50 text-red-700";
    return cn(base, wins && "ring-1 ring-current font-semibold");
  };
  return (
    <td className="px-2 py-2.5 text-center">
      <div className="flex items-center justify-center gap-1">
        <span className={cn("text-xs font-mono px-1.5 py-0.5 rounded", cls(a, aWins))}>{a === null ? "—" : fmtPct(a)}</span>
        <span className="text-[9px] text-gray-300">/</span>
        <span className={cn("text-xs font-mono px-1.5 py-0.5 rounded", cls(b, bWins))}>{b === null ? "—" : fmtPct(b)}</span>
      </div>
    </td>
  );
}

function ResultDetail({ r, label, accent }: { r: Result | null; label: string; accent: "blue" | "violet" }) {
  const ring    = accent === "blue" ? "border-blue-100 bg-blue-50/20" : "border-violet-100 bg-violet-50/20";
  const heading = accent === "blue" ? "text-blue-700" : "text-violet-700";
  if (!r) return (
    <div className={cn("rounded-xl border p-4 flex items-center justify-center text-sm text-gray-400 min-h-[100px]", ring)}>
      Run này không có kết quả cho câu hỏi
    </div>
  );
  return (
    <div className={cn("rounded-xl border p-4 space-y-3 text-sm", ring)}>
      <p className={cn("text-xs font-bold uppercase tracking-wider", heading)}>{label}</p>
      {r.bot_response && (
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-1">Bot response</p>
          <div className="bg-white border border-black/8 rounded-lg px-3 py-2 text-gray-700 leading-relaxed max-h-36 overflow-y-auto text-xs">
            {r.bot_response}
          </div>
        </div>
      )}
      {r.retrieved_top5_ids && r.retrieved_top5_ids.length > 0 && (
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-1">
            Retrieved Top-5 {r.ground_truth_rank !== null && `· GT rank #${r.ground_truth_rank}`}
          </p>
          <div className="space-y-0.5">
            {r.retrieved_top5_ids.map((id, i) => (
              <div key={id} className="flex items-center gap-1.5">
                <span className="text-[10px] text-gray-400 w-3 text-right">{i + 1}.</span>
                <span className="text-[10px] font-mono bg-gray-100 px-1.5 py-0.5 rounded text-gray-600 truncate">{id}</span>
              </div>
            ))}
          </div>
        </div>
      )}
      <div>
        <p className="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-1">Metrics</p>
        <div className="grid grid-cols-2 gap-x-4 gap-y-0.5">
          {[
            ["Recall@5",     fmtPct(r.recall_at_5)],
            ["MRR@5",        fmtPct(r.mrr_at_5)],
            ["Citation",     fmtPct(r.citation_chunk_match)],
            ["Faithfulness", fmtPct(r.ragas_faithfulness)],
            ["Relevancy",    fmtPct(r.ragas_answer_relevancy)],
            ["Ctx Prec",     fmtPct(r.ragas_context_precision)],
            ["Ctx Recall",   fmtPct(r.ragas_context_recall)],
          ].map(([k, v]) => (
            <div key={k} className="flex items-center justify-between text-xs">
              <span className="text-gray-400">{k}</span>
              <span className="font-mono text-gray-700">{v}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// So sánh config A vs B — highlight key khác nhau (giải thích vì sao điểm đổi).
function ConfigDiff({ a, b, nameA, nameB }: {
  a: Record<string, unknown>; b: Record<string, unknown>; nameA: string; nameB: string;
}) {
  const keys = Array.from(new Set([...Object.keys(a || {}), ...Object.keys(b || {})]));
  if (keys.length === 0) return (
    <div className="bg-white rounded-xl border border-black/8 px-5 py-3 text-xs text-gray-400">
      Hai run này chưa lưu config (tạo trước khi bật snapshot config).
    </div>
  );
  const str = (v: unknown) => (v === undefined || v === null ? "—" : String(v));
  return (
    <div className="bg-white rounded-xl border border-black/8 overflow-hidden">
      <div className="px-5 py-2 border-b border-black/6 bg-gray-50/60 text-xs font-semibold uppercase tracking-wider text-gray-500">
        So sánh config
      </div>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-xs text-gray-400 border-b border-black/5">
            <th className="px-5 py-2 text-left font-medium">Tham số</th>
            <th className="px-3 py-2 text-left font-medium"><span className="inline-flex items-center gap-1.5"><span className="w-2 h-2 rounded-full bg-blue-500" />{nameA}</span></th>
            <th className="px-3 py-2 text-left font-medium"><span className="inline-flex items-center gap-1.5"><span className="w-2 h-2 rounded-full bg-violet-500" />{nameB}</span></th>
          </tr>
        </thead>
        <tbody className="divide-y divide-black/5">
          {keys.map((k) => {
            const va = str(a?.[k]); const vb = str(b?.[k]);
            const diff = va !== vb;
            return (
              <tr key={k} className={cn(diff && "bg-amber-50/50")}>
                <td className="px-5 py-1.5 text-xs text-gray-500 font-mono">{k}</td>
                <td className={cn("px-3 py-1.5 text-xs font-mono", diff ? "text-amber-700 font-semibold" : "text-gray-700")}>{va}</td>
                <td className={cn("px-3 py-1.5 text-xs font-mono", diff ? "text-amber-700 font-semibold" : "text-gray-700")}>{vb}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ── Chart xu hướng metric qua các run (cũ → mới) ─────────────────────────────
const TREND_LINES = [
  { key: "recall",       label: "Recall@5",     color: "#059669" },
  { key: "mrr",          label: "MRR@5",        color: "#2563eb" },
  { key: "citation",     label: "Citation",     color: "#7c3aed" },
  { key: "guardrail",    label: "Guardrail",    color: "#6b7280" },
  { key: "faithfulness", label: "Faithfulness", color: "#d97706" },
  { key: "relevancy",    label: "Relevancy",    color: "#e11d48" },
] as const;

function TrendChart({ runs }: Readonly<{ runs: RunSummary[] }>) {
  const data = runs.map((r) => ({
    name: r.name,
    recall: r.avg_recall,
    mrr: r.avg_mrr,
    citation: r.avg_citation,
    guardrail: r.guardrail_rate,
    faithfulness: r.has_ragas ? r.avg_ragas_faithfulness : null,
    relevancy: r.has_ragas ? r.avg_ragas_relevancy : null,
  }));
  return (
    <div className="bg-white rounded-xl border border-black/8 overflow-hidden">
      <div className="px-5 py-3 border-b border-black/6 bg-gray-50/60">
        <p className="text-xs font-semibold uppercase tracking-wider text-gray-500">
          Xu hướng metric qua các version
        </p>
      </div>
      <div className="px-3 pt-4 pb-2 h-72">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 4, right: 24, bottom: 0, left: -16 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,0.06)" />
            <XAxis dataKey="name" tick={{ fontSize: 11, fill: "#9ca3af" }} tickLine={false} axisLine={{ stroke: "rgba(0,0,0,0.1)" }} />
            <YAxis domain={[0, 1]} tick={{ fontSize: 11, fill: "#9ca3af" }} tickLine={false} axisLine={false}
              tickFormatter={(v: number) => `${Math.round(v * 100)}%`} />
            <Tooltip
              formatter={(v) => (typeof v === "number" ? `${(v * 100).toFixed(1)}%` : String(v ?? "—"))}
              contentStyle={{ fontSize: 12, borderRadius: 10, border: "1px solid rgba(0,0,0,0.08)", boxShadow: "0 8px 24px rgba(17,24,39,0.08)" }}
            />
            <Legend wrapperStyle={{ fontSize: 12 }} iconType="plainline" />
            {TREND_LINES.map((l) => (
              <Line
                key={l.key} type="monotone" dataKey={l.key} name={l.label}
                stroke={l.color} strokeWidth={2} connectNulls
                dot={{ r: 3, strokeWidth: 0, fill: l.color }}
                activeDot={{ r: 5 }}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

export default function EvalComparePage() {
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [datasetId, setDatasetId] = useState<string>("");
  const [runs, setRuns]           = useState<RunSummary[]>([]);
  const [loading, setLoading]     = useState(false);

  // Detailed per-question comparison
  const [detailA, setDetailA]   = useState<string>("");
  const [detailB, setDetailB]   = useState<string>("");
  const [resA, setResA]         = useState<Result[]>([]);
  const [resB, setResB]         = useState<Result[]>([]);
  const [questions, setQuestions] = useState<Record<string, Question>>({});
  const [detailLoading, setDetailLoading] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [detailPage, setDetailPage] = useState(0);

  useEffect(() => {
    fetch(`${API}/internal/datasets`).then((r) => r.json()).then((d: Dataset[]) => {
      setDatasets(d);
      if (d.length) setDatasetId(d[0].id);
    });
  }, []);

  useEffect(() => {
    if (!datasetId) return;
    setLoading(true);
    setDetailA(""); setDetailB(""); setResA([]); setResB([]); setExpanded(null); setDetailPage(0);
    fetch(`${API}/internal/compare?dataset_id=${datasetId}`)
      .then((r) => r.json())
      .then((d: RunSummary[]) => { setRuns(d); setLoading(false); })
      .catch(() => setLoading(false));
    fetch(`${API}/internal/datasets/${datasetId}/questions?include_deleted=true`)
      .then((r) => r.json())
      .then((d: Question[]) => {
        const map: Record<string, Question> = {};
        d.forEach((q) => { map[q.id] = q; });
        setQuestions(map);
      })
      .catch(() => {});
  }, [datasetId]);

  // Load full results when run A selected
  useEffect(() => {
    if (!detailA) { setResA([]); return; }
    fetch(`${API}/internal/runs/${detailA}/results?limit=5000&offset=0`)
      .then((r) => r.json()).then((d: Result[]) => setResA(d)).catch(() => setResA([]));
  }, [detailA]);

  // Load full results when run B selected
  useEffect(() => {
    if (!detailB) { setResB([]); return; }
    setDetailLoading(true);
    fetch(`${API}/internal/runs/${detailB}/results?limit=5000&offset=0`)
      .then((r) => r.json()).then((d: Result[]) => { setResB(d); setDetailLoading(false); })
      .catch(() => { setResB([]); setDetailLoading(false); });
  }, [detailB]);

  // Reset page/expand when either run changes
  useEffect(() => { setExpanded(null); setDetailPage(0); }, [detailA, detailB]);

  const pairedRows = useMemo<PairedRow[]>(() => {
    if (!detailA || !detailB) return [];
    // Filter về câu thuộc dataset hiện tại — khi run kế thừa có 1000 câu,
    // chỉ giữ 100 câu trong dataset B để so sánh không bị nhiễu.
    const qbIds = new Set(Object.keys(questions));
    const filterByDataset = qbIds.size > 0;
    const filteredA = filterByDataset ? resA.filter((r) => qbIds.has(r.question_id)) : resA;
    const filteredB = filterByDataset ? resB.filter((r) => qbIds.has(r.question_id)) : resB;

    const mapB = new Map(filteredB.map((r) => [r.question_id, r]));
    const seen = new Set<string>();
    const rows: PairedRow[] = [];
    for (const r of filteredA) {
      seen.add(r.question_id);
      rows.push({ questionId: r.question_id, a: r, b: mapB.get(r.question_id) ?? null });
    }
    for (const r of filteredB) {
      if (!seen.has(r.question_id)) rows.push({ questionId: r.question_id, a: null, b: r });
    }
    return rows;
  }, [detailA, detailB, resA, resB, questions]);

  const pageRows = pairedRows.slice(detailPage * DETAIL_PAGE_SIZE, (detailPage + 1) * DETAIL_PAGE_SIZE);
  const hasMore  = (detailPage + 1) * DETAIL_PAGE_SIZE < pairedRows.length;

  const runA = runs.find((r) => r.run_id === detailA);
  const runB = runs.find((r) => r.run_id === detailB);

  // Sắp xếp cũ → mới để tính delta so với version trước
  // TrendChart chỉ dùng native run — inherited run không thuộc "tiến trình" dataset này
  const nativeRuns  = runs.filter((r) => !r.external);
  const ordered     = [...nativeRuns].reverse();
  const inheritedRuns = runs.filter((r) => r.external);

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
              {/* Run kế thừa từ dataset khác — hiển thị phân cách + badge coverage */}
              {inheritedRuns.length > 0 && (
                <tr>
                  <td colSpan={8} className="px-4 py-2 bg-gray-50/80 border-t border-dashed border-black/10">
                    <span className="text-[11px] font-semibold uppercase tracking-wider text-gray-400">
                      Run kế thừa từ dataset khác — điểm tính trên {runs[0]?.coverage_total ?? "?"} câu chung
                    </span>
                  </td>
                </tr>
              )}
              {inheritedRuns.map((run) => (
                <tr key={run.run_id} className="hover:bg-blue-50/20 transition-colors opacity-75">
                  <td className="px-4 py-4">
                    <p className="font-medium text-gray-600">{run.name}</p>
                    <div className="flex items-center gap-1.5 mt-0.5 flex-wrap">
                      <span className="inline-flex items-center gap-1 text-[11px] bg-blue-50 text-blue-700 border border-blue-200 px-1.5 py-0.5 rounded-full">
                        kế thừa
                      </span>
                      {run.source_dataset_name && (
                        <span className="text-[11px] text-gray-400">{run.source_dataset_name}</span>
                      )}
                      <span className="text-[11px] text-gray-400 tabular-nums">
                        · {run.coverage}/{run.coverage_total} câu
                      </span>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-center">
                    <span className="text-gray-400 tabular-nums">{run.coverage.toLocaleString()}</span>
                  </td>
                  <MetricCell v={run.avg_recall} />
                  <MetricCell v={run.avg_mrr} />
                  <MetricCell v={run.avg_citation} />
                  <MetricCell v={run.guardrail_rate} />
                  <MetricCell v={run.has_ragas ? run.avg_ragas_faithfulness : null} />
                  <MetricCell v={run.has_ragas ? run.avg_ragas_relevancy : null} />
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Chart xu hướng — chỉ hiện khi có >= 2 run để so */}
      {!loading && runs.length > 1 && <TrendChart runs={ordered} />}

      {/* Best version highlight — chỉ trong native run */}
      {nativeRuns.length > 1 && (() => {
        const best = [...nativeRuns].sort((a, b) => (b.avg_recall ?? 0) - (a.avg_recall ?? 0))[0];
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

      {/* ── So sánh chi tiết theo câu ───────────────────────────────── */}
      {!loading && runs.length > 0 && (
        <div className="space-y-4 pt-2">
          <div className="border-t border-black/8 pt-6">
            <h2 className="text-lg font-semibold text-gray-900">So sánh chi tiết theo câu</h2>
            <p className="text-sm text-gray-500 mt-0.5">Chọn 2 run để xem kết quả từng câu — run kế thừa tự lọc về câu của dataset này</p>
          </div>

          {/* Run selectors */}
          <div className="flex items-center gap-3 flex-wrap">
            <div className="flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full bg-blue-500 shrink-0" />
              <select
                value={detailA}
                onChange={(e) => setDetailA(e.target.value)}
                className="text-sm border border-blue-300 rounded-lg px-3 py-1.5 bg-blue-50/40 focus:outline-none focus:ring-2 focus:ring-blue-500/40 max-w-[240px]"
              >
                <option value="">— Chọn Run A —</option>
                {runs.filter((r) => r.run_id !== detailB).map((r) => (
                  <option key={r.run_id} value={r.run_id}>
                    {r.external ? `[kế thừa] ${r.name}` : r.name}
                  </option>
                ))}
              </select>
            </div>
            <span className="text-gray-300 font-light text-lg">vs</span>
            <div className="flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full bg-violet-500 shrink-0" />
              <select
                value={detailB}
                onChange={(e) => setDetailB(e.target.value)}
                className="text-sm border border-violet-300 rounded-lg px-3 py-1.5 bg-violet-50/40 focus:outline-none focus:ring-2 focus:ring-violet-500/40 max-w-[240px]"
              >
                <option value="">— Chọn Run B —</option>
                {runs.filter((r) => r.run_id !== detailA).map((r) => (
                  <option key={r.run_id} value={r.run_id}>
                    {r.external ? `[kế thừa] ${r.name}` : r.name}
                  </option>
                ))}
              </select>
            </div>
            {detailLoading && <Loader2 size={15} className="animate-spin text-violet-500" />}
            {!detailLoading && pairedRows.length > 0 && (
              <span className="text-xs text-gray-400 ml-auto">{pairedRows.length} câu so sánh</span>
            )}
          </div>

          {/* Aggregate compare strip */}
          {runA && runB && (
            <div className="bg-white rounded-xl border border-black/8 overflow-hidden">
              <div className="px-5 py-2.5 border-b border-black/6 bg-gray-50/60">
                <div className="grid grid-cols-7 text-xs font-semibold uppercase tracking-wider text-gray-500">
                  <div className="col-span-3">Run</div>
                  <div className="text-center">Recall</div>
                  <div className="text-center">MRR</div>
                  <div className="text-center">Citation</div>
                  <div className="text-center">Guardrail</div>
                </div>
              </div>
              {[
                { run: runA, dot: "bg-blue-500" },
                { run: runB, dot: "bg-violet-500" },
              ].map(({ run, dot }) => (
                <div key={run.run_id} className="px-5 py-2.5 border-b border-black/5 last:border-0">
                  <div className="grid grid-cols-7 items-center">
                    <div className="col-span-3 flex items-center gap-1.5">
                      <span className={cn("w-2 h-2 rounded-full shrink-0", dot)} />
                      <span className="text-xs font-medium text-gray-700 truncate">{run.name}</span>
                    </div>
                    {[run.avg_recall, run.avg_mrr, run.avg_citation, run.guardrail_rate].map((v, idx) => (
                      <div key={idx} className="text-center">
                        <span className={cn("text-xs font-mono", v == null ? "text-gray-300" : "text-gray-700")}>
                          {v == null ? "—" : v.toFixed(2)}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Config diff A vs B */}
          {runA && runB && (
            <ConfigDiff
              a={runA.config} b={runB.config}
              nameA={runA.name} nameB={runB.name}
            />
          )}

          {/* Per-question table */}
          {!detailA || !detailB ? (
            <div className="bg-white rounded-xl border border-black/8 py-14 text-center text-sm text-gray-400">
              Chọn cả Run A và Run B để bắt đầu so sánh
            </div>
          ) : detailLoading ? (
            <div className="bg-white rounded-xl border border-black/8 py-14 flex items-center justify-center gap-2 text-sm text-gray-400">
              <Loader2 size={15} className="animate-spin" /> Đang tải dữ liệu so sánh...
            </div>
          ) : pairedRows.length === 0 ? (
            <div className="bg-white rounded-xl border border-black/8 py-14 text-center text-sm text-gray-400">Không có câu hỏi chung</div>
          ) : (
            <div className="bg-white rounded-xl border border-black/8 overflow-hidden">
              <div className="px-5 py-2 border-b border-black/6 bg-gray-50/60 flex items-center gap-4 flex-wrap">
                <div className="flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-full bg-blue-500" />
                  <span className="text-xs text-gray-600">{runA?.name}</span>
                </div>
                <span className="text-gray-300 text-xs">/</span>
                <div className="flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-full bg-violet-500" />
                  <span className="text-xs text-gray-600">{runB?.name}</span>
                </div>
                <span className="text-xs text-gray-400 ml-1">— giá trị tốt hơn được in đậm + viền</span>
              </div>
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-black/6 bg-gray-50/40 text-xs font-semibold uppercase tracking-wider text-gray-500">
                    <th className="px-4 py-3 text-left">Câu hỏi</th>
                    <th className="px-2 py-3 text-center">Recall</th>
                    <th className="px-2 py-3 text-center">MRR</th>
                    <th className="px-2 py-3 text-center">Citation</th>
                    <th className="px-2 py-3 text-center">Faith</th>
                    <th className="px-2 py-3 text-center">Relevancy</th>
                    <th className="px-2 py-3 text-center">Ctx P</th>
                    <th className="px-2 py-3 text-center">Ctx R</th>
                    <th className="w-8" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-black/5">
                  {pageRows.map(({ questionId, a, b }) => {
                    const q = questions[questionId] ?? null;
                    const isExp = expanded === questionId;
                    return (
                      <React.Fragment key={questionId}>
                        <tr className="hover:bg-gray-50/40 transition-colors">
                          <td className="px-4 py-2.5 max-w-xs">
                            <p className="text-gray-800 line-clamp-1 text-sm">{q?.question ?? questionId}</p>
                            {q?.section && <span className="text-xs text-gray-400 bg-gray-100 px-1.5 py-0.5 rounded mt-0.5 inline-block truncate max-w-[200px]">{q.section}</span>}
                          </td>
                          <CmpCell a={a?.recall_at_5 ?? null}             b={b?.recall_at_5 ?? null} />
                          <CmpCell a={a?.mrr_at_5 ?? null}                b={b?.mrr_at_5 ?? null} />
                          <CmpCell a={a?.citation_chunk_match ?? null}    b={b?.citation_chunk_match ?? null} />
                          <CmpCell a={a?.ragas_faithfulness ?? null}      b={b?.ragas_faithfulness ?? null} />
                          <CmpCell a={a?.ragas_answer_relevancy ?? null}  b={b?.ragas_answer_relevancy ?? null} />
                          <CmpCell a={a?.ragas_context_precision ?? null} b={b?.ragas_context_precision ?? null} />
                          <CmpCell a={a?.ragas_context_recall ?? null}    b={b?.ragas_context_recall ?? null} />
                          <td className="px-2 py-2.5">
                            <button onClick={() => setExpanded(isExp ? null : questionId)} className="text-gray-400 hover:text-gray-600 p-1 transition-colors">
                              {isExp ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                            </button>
                          </td>
                        </tr>

                        {isExp && (
                          <tr className="bg-gray-50/30">
                            <td colSpan={9} className="px-6 py-5">
                              <div className="space-y-4">
                                {/* Shared context */}
                                <div className="grid grid-cols-2 gap-5 text-sm">
                                  <div>
                                    <p className="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-1">Câu hỏi</p>
                                    <p className="text-gray-800 leading-relaxed">{q?.question ?? "—"}</p>
                                  </div>
                                  <div>
                                    <p className="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-1">Đáp án chuẩn</p>
                                    <p className="text-gray-600 leading-relaxed">{q?.ground_truth ?? "—"}</p>
                                    {q?.source_chunk_ids && q.source_chunk_ids.length > 0 && (
                                      <div className="mt-2 flex flex-wrap gap-1">
                                        {q.source_chunk_ids.map((id) => (
                                          <span key={id} className="text-xs font-mono bg-emerald-50 text-emerald-700 border border-emerald-200 px-2 py-0.5 rounded">{id}</span>
                                        ))}
                                      </div>
                                    )}
                                  </div>
                                </div>

                                {/* Side-by-side A vs B */}
                                <div className="grid grid-cols-2 gap-4">
                                  <ResultDetail r={a} label={runA?.name ?? "Run A"} accent="blue" />
                                  <ResultDetail r={b} label={runB?.name ?? "Run B"} accent="violet" />
                                </div>
                              </div>
                            </td>
                          </tr>
                        )}
                      </React.Fragment>
                    );
                  })}
                </tbody>
              </table>
              <div className="flex items-center justify-between px-5 py-3 border-t border-black/6 bg-gray-50/40">
                <span className="text-xs text-gray-500">Trang {detailPage + 1} · {pageRows.length} câu / tổng {pairedRows.length}</span>
                <div className="flex items-center gap-2">
                  <button disabled={detailPage === 0} onClick={() => { setDetailPage((p) => p - 1); setExpanded(null); }} className="text-xs px-3 py-1.5 rounded-lg border border-black/10 bg-white hover:bg-gray-50 disabled:opacity-40 flex items-center gap-1"><ChevronLeft size={13} /> Trước</button>
                  <button disabled={!hasMore} onClick={() => { setDetailPage((p) => p + 1); setExpanded(null); }} className="text-xs px-3 py-1.5 rounded-lg border border-black/10 bg-white hover:bg-gray-50 disabled:opacity-40 flex items-center gap-1">Sau <ChevronRight size={13} /></button>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
