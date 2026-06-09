"use client";

import React, { useEffect, useRef, useState } from "react";
import { ChevronDown, ChevronRight, Loader2, Plus, X } from "lucide-react";
import { cn } from "@/lib/utils";

const API = process.env.NEXT_PUBLIC_AGENTIC_RAG_API_URL ?? "http://localhost:8000";

type Dataset = { id: string; name: string; is_benchmark: boolean };
type Run     = { id: string; name: string; status: string; total: number; success: number; failed: number; created_at: string };
type Result  = {
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

function fmt(v: number | null, digits = 2) {
  if (v === null || v === undefined) return "—";
  return (v * 100).toFixed(digits) + "%";
}
function fmtRaw(v: number | null, digits = 2) {
  if (v === null || v === undefined) return "—";
  return v.toFixed(digits);
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
  const [results,   setResults]   = useState<Result[]>([]);
  const [questions, setQuestions] = useState<Record<string, Question>>({});
  const [loading,   setLoading]   = useState(false);
  const [expanded,  setExpanded]  = useState<string | null>(null);
  const [newDataset, setNewDataset] = useState(false);
  const [newDatasetName, setNewDatasetName] = useState("");
  const [newRun, setNewRun] = useState(false);
  const [newRunName, setNewRunName] = useState("");
  const [creating, setCreating] = useState(false);

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
    // Also load questions for this dataset
    fetch(`${API}/internal/datasets/${datasetId}/questions?include_deleted=true`)
      .then((r) => r.json())
      .then((d: Question[]) => {
        const map: Record<string, Question> = {};
        d.forEach((q) => { map[q.id] = q; });
        setQuestions(map);
      })
      .catch(() => {});
  }, [datasetId]);

  useEffect(() => {
    if (!runId) { setResults([]); return; }
    setLoading(true);
    fetch(`${API}/internal/runs/${runId}/results`)
      .then((r) => r.json())
      .then((d: Result[]) => { setResults(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, [runId]);

  const selectedRun = runs.find((r) => r.id === runId);

  // Aggregate metrics
  const agg = results.reduce(
    (acc, r) => ({
      recall:   acc.recall   + (r.recall_at_5 ?? 0),
      mrr:      acc.mrr      + (r.mrr_at_5 ?? 0),
      citation: acc.citation + (r.citation_chunk_match ?? 0),
      guardrail:acc.guardrail+ (r.guardrail_pass ? 1 : 0),
      faith:    acc.faith    + (r.ragas_faithfulness ?? 0),
      rel:      acc.rel      + (r.ragas_answer_relevancy ?? 0),
      ctxP:     acc.ctxP    + (r.ragas_context_precision ?? 0),
      ctxR:     acc.ctxR    + (r.ragas_context_recall ?? 0),
      n:        acc.n + 1,
      nGuard:   acc.nGuard   + (r.guardrail_pass === null ? 0 : 1),
      nRagas:   acc.nRagas   + (r.ragas_faithfulness === null ? 0 : 1),
    }),
    { recall: 0, mrr: 0, citation: 0, guardrail: 0, faith: 0, rel: 0, ctxP: 0, ctxR: 0, n: 0, nGuard: 0, nRagas: 0 }
  );
  const n = agg.n || 1;

  // Merge: evaluated + chưa đánh giá
  const evaluatedIds = new Set(results.map((r) => r.question_id));
  const unevaluated  = Object.values(questions).filter((q) => !evaluatedIds.has(q.id) && q.is_approved);
  const allRows: { result: Result | null; question: Question | null }[] = [
    ...results.map((r) => ({ result: r, question: questions[r.question_id] ?? null })),
    ...unevaluated.map((q) => ({ result: null, question: q })),
  ];

  const SUMMARY = [
    { label: "Recall@5",     v: agg.recall / n },
    { label: "MRR@5",        v: agg.mrr / n },
    { label: "Citation",     v: agg.citation / n },
    { label: "Faithfulness", v: agg.nRagas ? agg.faith / agg.nRagas : null },
    { label: "Relevancy",    v: agg.nRagas ? agg.rel / agg.nRagas : null },
    { label: "Ctx Precision",v: agg.nRagas ? agg.ctxP / agg.nRagas : null },
    { label: "Ctx Recall",   v: agg.nRagas ? agg.ctxR / agg.nRagas : null },
  ];

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">Eval Results</h1>
          <p className="text-sm text-gray-500 mt-1">Kết quả đánh giá theo từng run</p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          {/* Dataset selector + create */}
          <div className="flex items-center gap-1">
            <select
              value={datasetId}
              onChange={(e) => { setDatasetId(e.target.value); setRunId(""); setResults([]); }}
              className="text-sm border border-black/12 rounded-lg px-3 py-1.5 bg-white focus:outline-none focus:ring-2 focus:ring-emerald-500/40"
            >
              {datasets.map((d) => <option key={d.id} value={d.id}>{d.name}{d.is_benchmark ? " ★" : ""}</option>)}
            </select>
            <button
              onClick={() => { setNewDataset((v) => !v); setNewRun(false); }}
              title="Tạo dataset mới"
              className="p-1.5 rounded-lg border border-black/12 bg-white text-gray-500 hover:bg-gray-50 transition-colors"
            >
              {newDataset ? <X size={14} /> : <Plus size={14} />}
            </button>
          </div>

          {/* Run selector + create */}
          <div className="flex items-center gap-1">
            <select
              value={runId}
              onChange={(e) => setRunId(e.target.value)}
              className="text-sm border border-black/12 rounded-lg px-3 py-1.5 bg-white focus:outline-none focus:ring-2 focus:ring-emerald-500/40 max-w-xs"
            >
              {runs.length === 0 && <option value="">Chưa có run nào</option>}
              {runs.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
            </select>
            <button
              onClick={() => { setNewRun((v) => !v); setNewDataset(false); }}
              title="Tạo run mới"
              disabled={!datasetId}
              className="p-1.5 rounded-lg border border-black/12 bg-white text-gray-500 hover:bg-gray-50 transition-colors disabled:opacity-40"
            >
              {newRun ? <X size={14} /> : <Plus size={14} />}
            </button>
          </div>
        </div>
      </div>

      {/* Inline: tạo dataset */}
      {newDataset && (
        <form
          className="flex items-center gap-2 bg-white border border-black/8 rounded-xl px-4 py-3"
          onSubmit={async (e) => {
            e.preventDefault();
            if (!newDatasetName.trim()) return;
            setCreating(true);
            const r = await fetch(`${API}/internal/datasets`, {
              method: "POST", headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ name: newDatasetName.trim(), is_benchmark: false }),
            });
            const d: Dataset = await r.json();
            setDatasets((prev) => [d, ...prev]);
            setDatasetId(d.id);
            setNewDatasetName(""); setNewDataset(false); setCreating(false);
          }}
        >
          <span className="text-sm text-gray-500 shrink-0">Tên dataset:</span>
          <input
            autoFocus value={newDatasetName} onChange={(e) => setNewDatasetName(e.target.value)}
            placeholder="VD: Benchmark v2"
            className="flex-1 text-sm border border-black/12 rounded-lg px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-emerald-500/40"
          />
          <button type="submit" disabled={creating || !newDatasetName.trim()}
            className="px-3 py-1.5 text-sm rounded-lg bg-emerald-700 text-white hover:bg-emerald-800 disabled:opacity-40 transition-colors">
            {creating ? <Loader2 size={14} className="animate-spin" /> : "Tạo"}
          </button>
        </form>
      )}

      {/* Inline: tạo run */}
      {newRun && (
        <form
          className="flex items-center gap-2 bg-white border border-black/8 rounded-xl px-4 py-3"
          onSubmit={async (e) => {
            e.preventDefault();
            if (!newRunName.trim() || !datasetId) return;
            setCreating(true);
            const r = await fetch(`${API}/internal/runs`, {
              method: "POST", headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ dataset_id: datasetId, name: newRunName.trim() }),
            });
            const d: Run = await r.json();
            setRuns((prev) => [d, ...prev]);
            setRunId(d.id);
            setNewRunName(""); setNewRun(false); setCreating(false);
          }}
        >
          <span className="text-sm text-gray-500 shrink-0">Tên run:</span>
          <input
            autoFocus value={newRunName} onChange={(e) => setNewRunName(e.target.value)}
            placeholder="VD: Run tháng 6"
            className="flex-1 text-sm border border-black/12 rounded-lg px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-emerald-500/40"
          />
          <button type="submit" disabled={creating || !newRunName.trim()}
            className="px-3 py-1.5 text-sm rounded-lg bg-emerald-700 text-white hover:bg-emerald-800 disabled:opacity-40 transition-colors">
            {creating ? <Loader2 size={14} className="animate-spin" /> : "Tạo & chạy eval"}
          </button>
        </form>
      )}

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
            <span>{results.length} câu có kết quả</span>
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
          <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
            <div
              className="h-full bg-emerald-500 rounded-full transition-all"
              style={{ width: `${(selectedRun.success / selectedRun.total) * 100}%` }}
            />
          </div>
        </div>
      )}

      {/* Aggregate metrics */}
      {results.length > 0 && (
        <div className="grid grid-cols-4 sm:grid-cols-7 gap-3">
          {SUMMARY.map((s) => (
            <div key={s.label} className="bg-white rounded-xl border border-black/8 px-4 py-3 text-center">
              <p className="text-xs text-gray-400 mb-1">{s.label}</p>
              <p className={cn(
                "text-lg font-semibold tabular-nums",
                s.v === null ? "text-gray-300" :
                s.v >= 0.7 ? "text-emerald-700" :
                s.v >= 0.4 ? "text-amber-700" : "text-red-600"
              )}>
                {s.v === null ? "—" : fmt(s.v, 0)}
              </p>
            </div>
          ))}
        </div>
      )}

      {/* Results table */}
      <div className="bg-white rounded-xl border border-black/8 overflow-hidden">
        {loading ? (
          <div className="py-16 flex items-center justify-center gap-2 text-sm text-gray-400">
            <Loader2 size={15} className="animate-spin" /> Đang tải kết quả...
          </div>
        ) : results.length === 0 ? (
          <div className="py-16 text-center text-sm text-gray-400">
            {runId ? "Chưa có kết quả nào" : "Chọn dataset và run để xem kết quả"}
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-black/6 bg-gray-50/60 text-xs font-semibold uppercase tracking-wider text-gray-500">
                <th className="px-4 py-3 text-left">Câu hỏi</th>
                <th className="px-3 py-3 text-center w-20">Recall</th>
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
              {allRows.length === 0 && (
                <tr><td colSpan={9} className="py-14 text-center text-sm text-gray-400">Chưa có dữ liệu</td></tr>
              )}
              {allRows.map(({ result: r, question: q }) => {
                const rowKey = r ? r.id : (q?.id ?? "unknown");
                const isExp  = expanded === rowKey;
                const pending = r === null;
                return (
                  <React.Fragment key={rowKey}>
                    <tr className={cn("hover:bg-gray-50/50 transition-colors", pending && "bg-gray-50/30")}>
                      <td className="px-4 py-2.5 max-w-xs">
                        <div className="flex items-center gap-2">
                          <p className="text-gray-800 line-clamp-1 text-sm flex-1">{q?.question ?? r?.question_id ?? "—"}</p>
                          {pending && (
                            <span className="text-xs text-gray-400 bg-gray-100 border border-gray-200 px-1.5 py-0.5 rounded-full shrink-0 whitespace-nowrap">Chưa đánh giá</span>
                          )}
                        </div>
                        {q?.section && (
                          <span className="text-xs text-gray-400 bg-gray-100 px-1.5 py-0.5 rounded mt-0.5 inline-block truncate max-w-[200px]">
                            {q.section}
                          </span>
                        )}
                      </td>
                      <MetricCell v={r?.recall_at_5 ?? null} />
                      <MetricCell v={r?.mrr_at_5 ?? null} />
                      <MetricCell v={r?.citation_chunk_match ?? null} />
                      <MetricCell v={r?.ragas_faithfulness ?? null} />
                      <MetricCell v={r?.ragas_answer_relevancy ?? null} />
                      <MetricCell v={r?.ragas_context_precision ?? null} />
                      <MetricCell v={r?.ragas_context_recall ?? null} />
                      <td className="px-2 py-2.5">
                        <button onClick={() => setExpanded(isExp ? null : rowKey)} className="text-gray-400 hover:text-gray-600 p-1 transition-colors">
                          {isExp ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                        </button>
                      </td>
                    </tr>

                    {isExp && (
                      <tr className="bg-gray-50/40">
                        <td colSpan={9} className="px-6 py-5">
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

                            {pending && (
                              <p className="text-sm text-gray-400 italic">Câu hỏi này chưa được đánh giá trong run hiện tại.</p>
                            )}

                            {r?.bot_response && (
                              <div>
                                <p className="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-1.5">Bot response</p>
                                <div className="bg-white border border-black/8 rounded-lg px-4 py-3 text-gray-700 leading-relaxed max-h-40 overflow-y-auto">
                                  {r.bot_response}
                                </div>
                              </div>
                            )}

                            {r && (
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
                                      ["Recall@5",           fmt(r.recall_at_5)],
                                      ["MRR@5",              fmt(r.mrr_at_5)],
                                      ["Citation match",     fmt(r.citation_chunk_match)],
                                      ["RAGAS Faithfulness", fmt(r.ragas_faithfulness)],
                                      ["RAGAS Relevancy",    fmt(r.ragas_answer_relevancy)],
                                      ["RAGAS Ctx Precision",fmt(r.ragas_context_precision)],
                                      ["RAGAS Ctx Recall",   fmt(r.ragas_context_recall)],
                                    ].map(([k, v]) => (
                                      <div key={k} className="flex items-center justify-between text-xs">
                                        <span className="text-gray-500">{k}</span>
                                        <span className="font-mono text-gray-700">{v}</span>
                                      </div>
                                    ))}
                                  </div>
                                </div>
                              </div>
                            )}

                            {r?.trace_url && (
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
        )}
      </div>
    </div>
  );
}
