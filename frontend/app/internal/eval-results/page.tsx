"use client";

import React, { useEffect, useState, useCallback } from "react";
import { motion } from "motion/react";
import { ChevronDown, ChevronRight, ChevronLeft } from "lucide-react";
import { cn } from "@/lib/utils";
import { CountUp, TableSkeleton } from "../_components/fx";

const API = process.env.NEXT_PUBLIC_AGENTIC_RAG_API_URL ?? "http://localhost:8000";
const PAGE_SIZE = 50;

type Dataset  = { id: string; name: string; is_benchmark: boolean };
type Run      = { id: string; name: string; status: string; total: number; success: number; failed: number; created_at: string };
type Metrics  = {
  total: number;
  recall: number | null; coverage_at_5: number | null; mrr: number | null; citation: number | null; guardrail: number | null;
  faithfulness: number | null; relevancy: number | null; ctx_precision: number | null; ctx_recall: number | null;
};
type Result   = {
  id: string; question_id: string; run_id: string;
  rag_context: string | null; bot_response: string | null;
  bot_citations: unknown; trace_url: string | null;
  retrieved_top5_ids: string[] | null; ground_truth_rank: number | null;
  recall_at_5: number | null; coverage_at_5: number | null; mrr_at_5: number | null;
  citation_chunk_match: number | null; guardrail_pass: boolean | null;
  ragas_faithfulness: number | null; ragas_answer_relevancy: number | null;
  ragas_context_precision: number | null; ragas_context_recall: number | null;
  ran_at: string;
};
type Question = { id: string; question: string; ground_truth: string; section: string | null; source_chunk_ids: string[] | null; is_approved: boolean };

function fmt(v: number | null, digits = 2) {
  if (v === null || v === undefined) return "—";
  return (v * 100).toFixed(digits) + "%";
}

function MetricCell({ v, good = 0.7, bad = 0.4 }: { v: number | null; good?: number; bad?: number }) {
  if (v === null || v === undefined) return <td className="px-3 py-2.5 text-center text-xs text-gray-300">—</td>;
  const color = v >= good ? "text-emerald-700 bg-emerald-50" : v >= bad ? "text-amber-700 bg-amber-50" : "text-red-700 bg-red-50";
  return (
    <td className="px-3 py-2.5 text-center">
      <span className={cn("text-xs font-mono px-1.5 py-0.5 rounded", color)}>{fmt(v)}</span>
    </td>
  );
}

export default function EvalResultsPage() {
  const [datasets,  setDatasets]  = useState<Dataset[]>([]);
  const [datasetId, setDatasetId] = useState<string>("");
  const [runs,      setRuns]      = useState<Run[]>([]);
  const [runId,     setRunId]     = useState<string>("");
  const [metrics,   setMetrics]   = useState<Metrics | null>(null);
  const [results,   setResults]   = useState<Result[]>([]);
  const [questions, setQuestions] = useState<Record<string, Question>>({});
  const [page,      setPage]      = useState(0);
  const [hasMore,   setHasMore]   = useState(false);
  const [loading,   setLoading]   = useState(false);
  const [expanded,  setExpanded]  = useState<string | null>(null);

  useEffect(() => {
    fetch(`${API}/internal/datasets`)
      .then((r) => r.json())
      .then((d: Dataset[]) => { setDatasets(d); if (d.length) setDatasetId(d[0].id); })
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!datasetId) return;
    fetch(`${API}/internal/runs?dataset_id=${datasetId}`)
      .then((r) => r.json())
      .then((d: Run[]) => { setRuns(d); if (d.length) setRunId(d[0].id); else setRunId(""); })
      .catch(() => {});
    fetch(`${API}/internal/datasets/${datasetId}/questions?include_deleted=true`)
      .then((r) => r.json())
      .then((d: Question[]) => {
        const map: Record<string, Question> = {};
        d.forEach((q) => { map[q.id] = q; });
        setQuestions(map);
      })
      .catch(() => {});
  }, [datasetId]);

  const loadPage = useCallback((rid: string, p: number) => {
    setLoading(true);
    fetch(`${API}/internal/runs/${rid}/results?limit=${PAGE_SIZE}&offset=${p * PAGE_SIZE}`)
      .then((r) => r.json())
      .then((d: Result[]) => {
        setResults(d);
        setHasMore(d.length === PAGE_SIZE);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!runId) { setResults([]); setMetrics(null); setPage(0); return; }
    setPage(0);
    setExpanded(null);
    // Load metrics (fast, aggregated)
    fetch(`${API}/internal/runs/${runId}/metrics`)
      .then((r) => r.json())
      .then((d: Metrics) => setMetrics(d))
      .catch(() => {});
    // Load first page of results
    loadPage(runId, 0);
  }, [runId, loadPage]);

  useEffect(() => {
    if (!runId) return;
    loadPage(runId, page);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page]);

  const selectedRun = runs.find((r) => r.id === runId);

  const SUMMARY = metrics ? [
    { label: "Recall@5",      v: metrics.recall },
    { label: "Coverage@5",    v: metrics.coverage_at_5 },
    { label: "MRR@5",         v: metrics.mrr },
    { label: "Citation",      v: metrics.citation },
    { label: "Faithfulness",  v: metrics.faithfulness },
    { label: "Relevancy",     v: metrics.relevancy },
    { label: "Ctx Precision", v: metrics.ctx_precision },
    { label: "Ctx Recall",    v: metrics.ctx_recall },
  ] : [];

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">Eval Results</h1>
          <p className="text-sm text-gray-500 mt-1">Kết quả đánh giá theo từng run</p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <select
            value={datasetId}
            onChange={(e) => { setDatasetId(e.target.value); setRunId(""); setResults([]); setMetrics(null); }}
            className="text-sm border border-black/12 rounded-lg px-3 py-1.5 bg-white focus:outline-none focus:ring-2 focus:ring-emerald-500/40"
          >
            {datasets.map((d) => <option key={d.id} value={d.id}>{d.name}{d.is_benchmark ? " ★" : ""}</option>)}
          </select>
          <select
            value={runId}
            onChange={(e) => setRunId(e.target.value)}
            className="text-sm border border-black/12 rounded-lg px-3 py-1.5 bg-white focus:outline-none focus:ring-2 focus:ring-emerald-500/40 max-w-xs"
          >
            {runs.length === 0 && <option value="">Chưa có run nào</option>}
            {runs.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
          </select>
        </div>
      </div>

      {/* Run summary bar */}
      {selectedRun && (
        <div className="bg-white rounded-xl border border-black/8 px-5 py-3 flex items-center gap-5 flex-wrap">
          <div className="flex items-center gap-2">
            <span className={cn(
              "text-xs font-medium px-2 py-0.5 rounded-full",
              selectedRun.status === "done" ? "bg-emerald-100 text-emerald-700" :
              selectedRun.status === "running" ? "bg-blue-100 text-blue-700" : "bg-gray-100 text-gray-500"
            )}>
              {selectedRun.status}
            </span>
            <span className="text-sm text-gray-600">{selectedRun.name}</span>
          </div>
          <div className="flex items-center gap-4 text-sm text-gray-500 ml-auto">
            <span>{metrics?.total ?? "…"} câu có kết quả</span>
            <span className="text-gray-300">|</span>
            <span>Total: {selectedRun.total}</span>
          </div>
        </div>
      )}

      {/* Progress bar */}
      {selectedRun && selectedRun.total > 0 && (
        <div className="bg-white rounded-xl border border-black/8 px-5 py-3">
          <div className="flex justify-between text-xs text-gray-500 mb-1.5">
            <span>Tiến độ</span>
            <span>{selectedRun.success}/{selectedRun.total}</span>
          </div>
          <div className="h-2 bg-gray-100 rounded-full overflow-hidden shadow-inner">
            <div
              className={cn(
                "h-full bg-gradient-to-r from-emerald-500 to-emerald-400 rounded-full transition-all",
                selectedRun.status === "running" && "progress-active"
              )}
              style={{ width: `${(selectedRun.success / selectedRun.total) * 100}%` }}
            />
          </div>
        </div>
      )}

      {/* Aggregate metrics — xuất hiện so le + số đếm chạy */}
      {SUMMARY.length > 0 && (
        <div key={runId} className="grid grid-cols-4 sm:grid-cols-7 gap-3">
          {SUMMARY.map((s, i) => (
            <motion.div
              key={s.label}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.4, delay: i * 0.05, ease: [0.16, 1, 0.3, 1] }}
              className="bg-white rounded-xl border border-black/8 px-4 py-3 text-center card-lift"
            >
              <p className="text-xs text-gray-400 mb-1">{s.label}</p>
              <p className={cn(
                "text-lg font-semibold tabular-nums",
                s.v === null ? "text-gray-300" :
                s.v >= 0.7 ? "text-emerald-700" :
                s.v >= 0.4 ? "text-amber-700" : "text-red-600"
              )}>
                {s.v === null ? "—" : <CountUp value={s.v} format={(v) => (v * 100).toFixed(0) + "%"} flash={false} />}
              </p>
            </motion.div>
          ))}
        </div>
      )}

      {/* Results table */}
      <div className="bg-white rounded-xl border border-black/8 overflow-hidden">
        {loading ? (
          <TableSkeleton rows={8} />
        ) : results.length === 0 ? (
          <div className="py-16 text-center text-sm text-gray-400">
            {runId ? "Chưa có kết quả nào" : "Chọn dataset và run để xem kết quả"}
          </div>
        ) : (
          <>
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-black/6 bg-gray-50/60 text-xs font-semibold uppercase tracking-wider text-gray-500">
                  <th className="px-4 py-3 text-left">Câu hỏi</th>
                  <th className="px-3 py-3 text-center w-20">Recall</th>
                  <th className="px-3 py-3 text-center w-20 text-teal-600" title="Lấy ĐỦ tất cả chunk GT trong top-5 — metric multi-hop">Cover</th>
                  <th className="px-3 py-3 text-center w-20">MRR</th>
                  <th className="px-3 py-3 text-center w-20">Citation</th>
                  <th className="px-3 py-3 text-center w-20">Faith</th>
                  <th className="px-3 py-3 text-center w-20">Rel</th>
                  <th className="px-3 py-3 text-center w-20">Ctx P</th>
                  <th className="px-3 py-3 text-center w-20">Ctx R</th>
                  <th className="w-8" />
                </tr>
              </thead>
              <tbody className="divide-y divide-black/5">
                {results.map((r) => {
                  const q      = questions[r.question_id] ?? null;
                  const rowKey = r.id;
                  const isExp  = expanded === rowKey;
                  return (
                    <React.Fragment key={rowKey}>
                      <tr className="hover:bg-gray-50/50 transition-colors">
                        <td className="px-4 py-2.5 max-w-xs">
                          <p className="text-gray-800 line-clamp-1 text-sm">{q?.question ?? r.question_id}</p>
                          {q?.section && (
                            <span className="text-xs text-gray-400 bg-gray-100 px-1.5 py-0.5 rounded mt-0.5 inline-block truncate max-w-[200px]">
                              {q.section}
                            </span>
                          )}
                        </td>
                        <MetricCell v={r.recall_at_5} />
                        <MetricCell v={r.coverage_at_5} />
                        <MetricCell v={r.mrr_at_5} />
                        <MetricCell v={r.citation_chunk_match} />
                        <MetricCell v={r.ragas_faithfulness} />
                        <MetricCell v={r.ragas_answer_relevancy} />
                        <MetricCell v={r.ragas_context_precision} />
                        <MetricCell v={r.ragas_context_recall} />
                        <td className="px-2 py-2.5">
                          <button onClick={() => setExpanded(isExp ? null : rowKey)} className="text-gray-400 hover:text-gray-600 p-1 transition-colors">
                            {isExp ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                          </button>
                        </td>
                      </tr>

                      {isExp && (
                        <tr className="bg-gray-50/40">
                          <td colSpan={10} className="px-6 py-5">
                            <div className="space-y-4 text-sm">
                              <div className="grid grid-cols-2 gap-5">
                                <div>
                                  <p className="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-1.5">Câu hỏi</p>
                                  <p className="text-gray-800 leading-relaxed">{q?.question ?? "—"}</p>
                                </div>
                                <div>
                                  <p className="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-1.5">Đáp án chuẩn</p>
                                  <p className="text-gray-600 leading-relaxed mb-2">{q?.ground_truth ?? "—"}</p>
                                  {q?.source_chunk_ids && q.source_chunk_ids.length > 0 && (
                                    <div>
                                      <p className="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-1.5">Ground truth chunks</p>
                                      <div className="flex flex-wrap gap-1.5">
                                        {q.source_chunk_ids.map((id) => (
                                          <span key={id} className="text-xs font-mono bg-emerald-50 text-emerald-700 border border-emerald-200 px-2 py-0.5 rounded">{id}</span>
                                        ))}
                                      </div>
                                    </div>
                                  )}
                                </div>
                              </div>

                              {r.bot_response && (
                                <div>
                                  <p className="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-1.5">Bot response</p>
                                  <div className="bg-white border border-black/8 rounded-lg px-4 py-3 text-gray-700 leading-relaxed max-h-40 overflow-y-auto">
                                    {r.bot_response}
                                  </div>
                                </div>
                              )}

                              <div className="grid grid-cols-2 gap-5">
                                {r.retrieved_top5_ids && r.retrieved_top5_ids.length > 0 && (
                                  <div>
                                    <p className="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-1.5">
                                      Retrieved Top-5 {r.ground_truth_rank !== null && `(GT rank: #${r.ground_truth_rank})`}
                                    </p>
                                    <div className="space-y-1">
                                      {r.retrieved_top5_ids.map((id, i) => (
                                        <div key={id} className="flex items-center gap-2">
                                          <span className="text-xs text-gray-400 w-4 text-right">{i + 1}.</span>
                                          <span className="text-xs font-mono bg-gray-100 px-2 py-0.5 rounded text-gray-600 truncate flex-1">{id}</span>
                                        </div>
                                      ))}
                                    </div>
                                  </div>
                                )}
                                <div>
                                  <p className="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-1.5">Detailed Metrics</p>
                                  <div className="space-y-1">
                                    {[
                                      ["Recall@5",            fmt(r.recall_at_5)],
                                      ["Coverage@5",          fmt(r.coverage_at_5)],
                                      ["MRR@5",               fmt(r.mrr_at_5)],
                                      ["Citation match",      fmt(r.citation_chunk_match)],
                                      ["RAGAS Faithfulness",  fmt(r.ragas_faithfulness)],
                                      ["RAGAS Relevancy",     fmt(r.ragas_answer_relevancy)],
                                      ["RAGAS Ctx Precision", fmt(r.ragas_context_precision)],
                                      ["RAGAS Ctx Recall",    fmt(r.ragas_context_recall)],
                                    ].map(([k, v]) => (
                                      <div key={k} className="flex items-center justify-between text-xs">
                                        <span className="text-gray-500">{k}</span>
                                        <span className="font-mono text-gray-700">{v}</span>
                                      </div>
                                    ))}
                                  </div>
                                </div>
                              </div>

                              {r.trace_url && (
                                <a href={r.trace_url} target="_blank" rel="noreferrer" className="text-xs text-blue-600 hover:underline">
                                  Xem trace →
                                </a>
                              )}
                            </div>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                })}
              </tbody>
            </table>

            {/* Pagination */}
            <div className="flex items-center justify-between px-5 py-3 border-t border-black/6 bg-gray-50/40">
              <span className="text-xs text-gray-500">
                Trang {page + 1} · hiển thị {results.length} câu
              </span>
              <div className="flex items-center gap-2">
                <button
                  disabled={page === 0}
                  onClick={() => setPage((p) => p - 1)}
                  className="text-xs px-3 py-1.5 rounded-lg border border-black/10 bg-white hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1"
                >
                  <ChevronLeft size={13} /> Trước
                </button>
                <button
                  disabled={!hasMore}
                  onClick={() => setPage((p) => p + 1)}
                  className="text-xs px-3 py-1.5 rounded-lg border border-black/10 bg-white hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1"
                >
                  Sau <ChevronRight size={13} />
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
