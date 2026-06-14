"use client";

import React, { useEffect, useState } from "react";
import { motion } from "motion/react";
import { Archive, CheckCircle2, ChevronDown, ChevronRight, Clock, Layers, Search, Trash2, Undo2, X } from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { TableSkeleton } from "../_components/fx";

const API = process.env.NEXT_PUBLIC_AGENTIC_RAG_API_URL ?? "http://localhost:8000";

const DEDUP_LAYERS = [
  { key: "exact_sha256",         label: "L1 Exact"     },
  { key: "simhash",              label: "L2 SimHash"   },
  { key: "embedding_similarity", label: "L3 Embedding" },
] as const;
type FlaggedMap = Record<string, string[]>;

// Gom mọi chunk_id bị flag ở các layer đang chọn thành 1 Set
function collectFlaggedChunkIds(layers: Set<string>, flaggedByLayer: FlaggedMap): Set<string> {
  const out = new Set<string>();
  for (const layer of layers)
    for (const cid of flaggedByLayer[layer] ?? []) out.add(cid);
  return out;
}

type Dataset  = { id: string; name: string; is_benchmark: boolean };
type Question = {
  id: string; dataset_id: string | null; section: string | null;
  question: string; ground_truth: string;
  document_id: string; source_chunk_ids: string[] | null;
  is_approved: boolean; reviewed_by: string | null;
  deleted_at: string | null; created_at: string;
  has_results: boolean;
  eval_count: number;
};
type HistoryEntry = {
  run_id: string; run_name: string; dataset_name: string | null;
  ran_at: string;
  recall_at_5: number | null; mrr_at_5: number | null;
  citation_chunk_match: number | null; guardrail_pass: boolean | null;
  ragas_faithfulness: number | null; ragas_answer_relevancy: number | null;
  eval_error: string | null;
};
type Tab = "pending" | "approved" | "archived";
type ChunkContent = { chunk_id: string; document_id: string; text: string; metadata: Record<string, unknown> };
type PanelState = { chunkId: string; question: string; groundTruth: string };

function fmtPct(v: number | null) {
  if (v === null || v === undefined) return "—";
  return (v * 100).toFixed(1) + "%";
}

function HistoryOverlay({ questionId, questionText, onClose }: Readonly<{
  questionId: string; questionText: string; onClose: () => void;
}>) {
  const [entries, setEntries] = useState<HistoryEntry[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    fetch(`${API}/internal/questions/${questionId}/history`)
      .then((r) => r.json())
      .then((d: HistoryEntry[]) => { setEntries(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, [questionId]);

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-end p-4 pointer-events-none">
      <div className="pointer-events-auto w-[520px] max-h-[70vh] flex flex-col bg-white rounded-2xl border border-black/10 shadow-2xl shadow-black/10 overflow-hidden">
        {/* Header */}
        <div className="flex items-start justify-between gap-3 px-5 py-4 border-b border-black/6 bg-gray-50/60 shrink-0">
          <div className="min-w-0">
            <div className="flex items-center gap-2 mb-0.5">
              <Clock size={13} className="text-gray-400 shrink-0" />
              <p className="text-xs font-semibold uppercase tracking-wider text-gray-500">Lịch sử đánh giá</p>
            </div>
            <p className="text-sm text-gray-700 line-clamp-2 leading-relaxed">{questionText}</p>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 p-1 shrink-0 mt-0.5 transition-colors"><X size={15} /></button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto divide-y divide-black/5">
          {loading && (
            <div className="py-10 text-center text-sm text-gray-400">Đang tải...</div>
          )}
          {!loading && entries.length === 0 && (
            <div className="py-10 text-center text-sm text-gray-400">Chưa có lần đánh giá nào</div>
          )}
          {entries.map((e, i) => (
            <div key={`${e.run_id}-${i}`} className="px-5 py-3.5 hover:bg-gray-50/50 transition-colors">
              <div className="flex items-start justify-between gap-3 mb-2">
                <div>
                  <p className="text-sm font-medium text-gray-800">{e.run_name}</p>
                  {e.dataset_name && (
                    <p className="text-xs text-gray-400">{e.dataset_name}</p>
                  )}
                </div>
                <span className="text-[11px] text-gray-400 tabular-nums shrink-0 mt-0.5">
                  {new Date(e.ran_at).toLocaleDateString("vi-VN")}
                </span>
              </div>
              {e.eval_error ? (
                <p className="text-xs text-red-500 bg-red-50 px-2 py-1 rounded">{e.eval_error}</p>
              ) : (
                <div className="grid grid-cols-5 gap-1">
                  {[
                    ["Recall", fmtPct(e.recall_at_5)],
                    ["MRR",    fmtPct(e.mrr_at_5)],
                    ["Cite",   fmtPct(e.citation_chunk_match)],
                    ["Faith",  fmtPct(e.ragas_faithfulness)],
                    ["Relev",  fmtPct(e.ragas_answer_relevancy)],
                  ].map(([k, v]) => (
                    <div key={k} className="text-center bg-gray-50 rounded-lg px-1.5 py-1.5">
                      <p className="text-[10px] text-gray-400 mb-0.5">{k}</p>
                      <p className={cn("text-xs font-mono font-semibold", v === "—" ? "text-gray-300" : "text-gray-700")}>{v}</p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>

        <div className="px-5 py-2.5 border-t border-black/6 bg-gray-50/40 shrink-0">
          <p className="text-[11px] text-gray-400">{entries.length} lần đánh giá</p>
        </div>
      </div>
    </div>
  );
}

function ChunkPanel({ state, onClose }: Readonly<{ state: PanelState; onClose: () => void }>) {
  const [data, setData] = useState<ChunkContent | null>(null);
  const [err,  setErr]  = useState(false);

  useEffect(() => {
    setData(null); setErr(false);
    fetch(`${API}/internal/chunks/${encodeURIComponent(state.chunkId)}`)
      .then((r) => { if (!r.ok) { throw new Error("not found"); } return r.json(); })
      .then(setData)
      .catch(() => setErr(true));
  }, [state.chunkId]);

  return (
    <aside className="flex flex-col bg-white rounded-xl border border-black/8 overflow-hidden sticky top-20 max-h-[calc(100vh-6rem)]">
      <div className="flex items-start justify-between gap-2 px-4 py-3 border-b border-black/6 shrink-0 bg-gray-50/60">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-0.5">Chunk</p>
          <p className="text-xs font-mono text-gray-500 break-all leading-relaxed">{state.chunkId}</p>
          {typeof data?.metadata?.section === "string" && data.metadata.section && (
            <span className="mt-1.5 inline-block text-xs bg-emerald-50 text-emerald-700 border border-emerald-200 px-2 py-0.5 rounded-full">
              {data.metadata.section}
            </span>
          )}
        </div>
        <button onClick={onClose} className="text-gray-400 hover:text-gray-600 p-1 shrink-0 mt-0.5"><X size={15} /></button>
      </div>
      <div className="flex-1 overflow-y-auto divide-y divide-black/6">
        <div className="px-4 py-4">
          <p className="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-2">Nội dung tài liệu</p>
          {!data && !err && <p className="text-sm text-gray-400 py-4 text-center">Đang tải...</p>}
          {err  && <p className="text-sm text-red-500 py-4 text-center">Không tìm thấy chunk</p>}
          {data && <p className="text-sm text-gray-800 leading-relaxed whitespace-pre-wrap">{data.text}</p>}
        </div>
        <div className="px-4 py-4 space-y-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-1.5">Câu hỏi</p>
            <p className="text-sm text-gray-800 leading-relaxed">{state.question}</p>
          </div>
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-1.5">Đáp án chuẩn</p>
            <p className="text-sm text-gray-700 leading-relaxed">{state.groundTruth}</p>
          </div>
        </div>
      </div>
    </aside>
  );
}

export default function EvalReviewPage() {
  const [datasets,       setDatasets]       = useState<Dataset[]>([]);
  const [questions,      setQuestions]      = useState<Question[]>([]);
  const [tab,            setTab]            = useState<Tab>("pending");
  const [selected,       setSelected]       = useState<Set<string>>(new Set());
  const [expanded,       setExpanded]       = useState<string | null>(null);
  const [search,         setSearch]         = useState("");
  const [loading,        setLoading]        = useState(false);
  const [panel,          setPanel]          = useState<PanelState | null>(null);
  const [historyPanel,   setHistoryPanel]   = useState<{ id: string; question: string } | null>(null);
  const [editing,        setEditing]        = useState<{ id: string; question: string; groundTruth: string } | null>(null);
  // Lọc dedup: ẩn câu sinh từ chunk bị flag ở layer được chọn
  const [hideDedupLayers, setHideDedupLayers] = useState<Set<string>>(new Set());
  const [flaggedByLayer,  setFlaggedByLayer]  = useState<FlaggedMap>({});
  const toggleHideLayer = (key: string) =>
    setHideDedupLayers((prev) => { const n = new Set(prev); n.has(key) ? n.delete(key) : n.add(key); return n; });

  useEffect(() => {
    fetch(`${API}/internal/datasets`)
      .then((r) => r.json())
      .then((d: Dataset[]) => setDatasets(d))
      .catch(() => {});
    fetch(`${API}/internal/dedup/flagged-chunk-ids`)
      .then((r) => r.json())
      .then((d: FlaggedMap) => setFlaggedByLayer(d && typeof d === "object" ? d : {}))
      .catch(() => {});
    loadQuestions();
  }, []);

  // Khi đổi layer ẩn: bỏ chọn những câu vừa bị ẩn để không thao tác nhầm
  useEffect(() => {
    const hidden = collectFlaggedChunkIds(hideDedupLayers, flaggedByLayer);
    if (hidden.size === 0) return;
    setSelected((prev) => {
      const next = new Set(prev);
      for (const q of questions)
        if ((q.source_chunk_ids ?? []).some((cid) => hidden.has(cid))) next.delete(q.id);
      return next;
    });
  }, [hideDedupLayers, flaggedByLayer, questions]);

  function loadQuestions() {
    setLoading(true);
    fetch(`${API}/internal/questions?include_deleted=true`)
      .then((r) => r.json())
      .then((d: Question[]) => { setQuestions(d); setLoading(false); })
      .catch(() => setLoading(false));
  }

  function patchLocal(ids: string[], changes: Partial<Question>) {
    setQuestions((prev) => prev.map((q) => ids.includes(q.id) ? { ...q, ...changes } : q));
  }

  async function approveOne(id: string) {
    await fetch(`${API}/internal/questions/approve`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question_ids: [id], reviewed_by: "internal" }),
    });
    patchLocal([id], { is_approved: true });
  }

  async function archiveOne(id: string) {
    await fetch(`${API}/internal/questions/archive`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify([id]),
    });
    patchLocal([id], { deleted_at: new Date().toISOString() });
  }

  async function restoreOne(id: string) {
    await fetch(`${API}/internal/questions/restore`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify([id]),
    });
    patchLocal([id], { deleted_at: null });
  }

  async function handleBulkApprove() {
    const ids = [...selected];
    await fetch(`${API}/internal/questions/approve`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question_ids: ids, reviewed_by: "internal" }),
    });
    patchLocal(ids, { is_approved: true });
    setSelected(new Set());
    toast.success(`Đã duyệt ${ids.length} câu`);
  }

  async function handleBulkArchive() {
    const ids = [...selected];
    await fetch(`${API}/internal/questions/archive`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(ids),
    });
    patchLocal(ids, { deleted_at: new Date().toISOString() });
    setSelected(new Set());
    toast(`Đã loại bỏ ${ids.length} câu`, { description: "Khôi phục được ở tab Loại bỏ." });
  }

  async function handleBulkRestore() {
    const ids = [...selected];
    await fetch(`${API}/internal/questions/restore`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(ids),
    });
    patchLocal(ids, { deleted_at: null });
    setSelected(new Set());
    toast.success(`Đã khôi phục ${ids.length} câu`);
  }

  // Xóa cứng — BE chỉ xóa câu chưa có kết quả eval; câu đã chạy bị skip (giữ lịch sử).
  async function deleteForever(ids: string[]) {
    const res = await fetch(`${API}/internal/questions`, {
      method: "DELETE", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(ids),
    });
    const d = await res.json().catch(() => ({ deleted: 0, skipped: [] as string[] }));
    const skipped: string[] = d.skipped ?? [];
    const deletedIds = new Set(ids.filter((id) => !skipped.includes(id)));
    setQuestions((prev) => prev.filter((q) => !deletedIds.has(q.id)));
    setSelected(new Set());
    if (deletedIds.size > 0) toast.success(`Đã xóa vĩnh viễn ${deletedIds.size} câu`);
    if (skipped.length > 0) {
      toast.warning(`${skipped.length} câu đã có kết quả eval nên không xóa cứng được`, {
        description: "Dùng Loại bỏ để ẩn — lịch sử eval được giữ nguyên.",
      });
    }
  }

  function deleteForeverOne(id: string) {
    if (confirm("Xóa vĩnh viễn câu này? Không khôi phục được.")) deleteForever([id]);
  }

  function handleBulkDeleteForever() {
    if (confirm(`Xóa vĩnh viễn ${selected.size} câu đã chọn? Không khôi phục được.`)) {
      deleteForever([...selected]);
    }
  }

  async function saveEdit() {
    if (!editing) return;
    await fetch(`${API}/internal/questions/${editing.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: editing.question, ground_truth: editing.groundTruth }),
    });
    patchLocal([editing.id], { question: editing.question, ground_truth: editing.groundTruth });
    setEditing(null);
  }

  // Tập chunk_id bị flag ở các layer đang chọn để ẩn
  const hiddenChunkIds = collectFlaggedChunkIds(hideDedupLayers, flaggedByLayer);
  const isHiddenByDedup = (q: Question) =>
    hiddenChunkIds.size > 0 && (q.source_chunk_ids ?? []).some((cid) => hiddenChunkIds.has(cid));

  const byTab = questions.filter((q) => {
    if (isHiddenByDedup(q)) return false;
    if (tab === "pending")  return !q.deleted_at && !q.is_approved;
    if (tab === "approved") return !q.deleted_at && q.is_approved;
    return !!q.deleted_at;
  });

  const hiddenCount = questions.filter(isHiddenByDedup).length;

  const filtered = search.trim()
    ? byTab.filter((q) =>
        q.question.toLowerCase().includes(search.toLowerCase()) ||
        q.ground_truth.toLowerCase().includes(search.toLowerCase())
      )
    : byTab;

  const toggleQ   = (id: string) => setSelected((p) => { const n = new Set(p); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const toggleAll = () => setSelected(selected.size === filtered.length ? new Set() : new Set(filtered.map((q) => q.id)));

  const visible = questions.filter((q) => !isHiddenByDedup(q));
  const counts = {
    pending:  visible.filter((q) => !q.deleted_at && !q.is_approved).length,
    approved: visible.filter((q) => !q.deleted_at && q.is_approved).length,
    archived: visible.filter((q) => !!q.deleted_at).length,
  };

  const TABS: { key: Tab; label: string; count: number; active: string; hover: string }[] = [
    { key: "pending",  label: "Chưa review", count: counts.pending,  active: "bg-amber-500 text-white",   hover: "text-amber-600 hover:bg-amber-50" },
    { key: "approved", label: "Đã duyệt",    count: counts.approved, active: "bg-blue-600 text-white",    hover: "text-blue-600 hover:bg-blue-50" },
    { key: "archived", label: "Loại bỏ",     count: counts.archived, active: "bg-gray-500 text-white",    hover: "text-gray-500 hover:bg-gray-100" },
  ];

  const datasetMap  = Object.fromEntries(datasets.map((d) => [d.id, d.name]));
  const globalIndex = Object.fromEntries(questions.map((q, i) => [q.id, i + 1]));

  const openPanel = (chunkId: string, q: Question) =>
    setPanel({ chunkId, question: q.question, groundTruth: q.ground_truth });

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">Review</h1>
          <p className="text-sm text-gray-500 mt-1">Duyệt câu hỏi trước khi đưa vào eval</p>
        </div>
      </div>

      {/* Tabs + search + bulk */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="flex gap-1">
          {TABS.map((t) => (
            <button
              key={t.key}
              onClick={() => { setTab(t.key); setSelected(new Set()); setExpanded(null); }}
              className={cn(
                "relative px-3.5 py-1.5 rounded-md text-sm font-medium transition-colors duration-200 pressable",
                tab === t.key ? "text-white" : cn(t.hover, "hover:-translate-y-px")
              )}
            >
              {/* Pill trượt mượt giữa các tab — đổi màu theo tab đích */}
              {tab === t.key && (
                <motion.span
                  layoutId="review-tab-pill"
                  className={cn("absolute inset-0 rounded-md shadow-md", t.active)}
                  transition={{ type: "spring", stiffness: 400, damping: 32 }}
                />
              )}
              <span className="relative z-10">{t.label}</span>
              <span className={cn("relative z-10 ml-1.5 text-xs tabular-nums", tab === t.key ? "text-white/70" : "text-gray-400")}>
                {t.count}
              </span>
            </button>
          ))}
        </div>

        <div className="flex items-center gap-2 ml-auto">
          {/* Lọc dedup: ẩn câu sinh từ chunk bị flag */}
          <div className="flex items-center gap-1.5">
            <Layers size={13} className="text-gray-400 shrink-0" />
            <span className="text-xs text-gray-400 shrink-0 mr-0.5">Ẩn trùng:</span>
            {DEDUP_LAYERS.map(({ key, label }) => {
              const active = hideDedupLayers.has(key);
              const flaggedCount = (flaggedByLayer[key] ?? []).length;
              return (
                <button
                  key={key}
                  type="button"
                  onClick={() => toggleHideLayer(key)}
                  className={cn(
                    "text-xs px-2.5 py-1 rounded-full border transition-all pressable",
                    active
                      ? "border-emerald-600 bg-emerald-600 text-white"
                      : "border-black/12 bg-white text-gray-600 hover:border-emerald-300 hover:bg-emerald-50"
                  )}
                  title={`${flaggedCount} chunk bị flag ở ${label}`}
                >
                  {label}
                </button>
              );
            })}
            {hiddenCount > 0 && (
              <span className="text-xs text-amber-700 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded-full whitespace-nowrap">
                đã ẩn {hiddenCount}
              </span>
            )}
          </div>

          <div className="relative">
            <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Tìm câu hỏi..."
              className="pl-8 pr-3 py-1.5 text-sm border border-black/12 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500/40 w-52"
            />
          </div>

          {selected.size > 0 && (
            <div className="flex items-center gap-2">
              <span className="text-xs text-gray-400">Đã chọn {selected.size}</span>
              {tab === "pending" && (
                <button onClick={handleBulkApprove} className="flex items-center gap-1 text-sm px-3 py-1.5 rounded-lg bg-emerald-100 text-emerald-800 hover:bg-emerald-200 transition-colors">
                  <CheckCircle2 size={13} /> Duyệt câu chọn
                </button>
              )}
              {tab === "archived" && (
                <button onClick={handleBulkRestore} className="flex items-center gap-1 text-sm px-3 py-1.5 rounded-lg bg-blue-50 text-blue-700 hover:bg-blue-100 transition-colors">
                  <Undo2 size={13} /> Khôi phục
                </button>
              )}
              {/* Nút 1 — Loại bỏ (mềm) */}
              {tab !== "archived" && (
                <button onClick={handleBulkArchive} className="flex items-center gap-1 text-sm px-3 py-1.5 rounded-lg bg-amber-50 text-amber-700 hover:bg-amber-100 transition-colors">
                  <Archive size={13} /> Loại bỏ
                </button>
              )}
              {/* Nút 2 — Xóa vĩnh viễn (cứng); câu đã có kết quả sẽ bị BE skip */}
              <button onClick={handleBulkDeleteForever} className="flex items-center gap-1 text-sm px-3 py-1.5 rounded-lg bg-red-600 text-white hover:bg-red-700 transition-colors">
                <Trash2 size={13} /> Xóa vĩnh viễn
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Main: table + side panel */}
      <div className={cn("grid gap-4", panel ? "grid-cols-[1fr_380px]" : "grid-cols-1")}>
        <div className="bg-white rounded-xl border border-black/8 overflow-hidden">
          {loading ? (
            <TableSkeleton rows={8} />
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-black/6 bg-gray-50/60">
                  <th className="w-10 px-4 py-3">
                    <input type="checkbox" checked={selected.size === filtered.length && filtered.length > 0} onChange={toggleAll} className="accent-emerald-600" />
                  </th>
                  <th className="px-3 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500 w-12">#</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">Câu hỏi</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">Đáp án chuẩn</th>
                  <th className="px-3 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500 w-48">Ground Truth IDs</th>
                  <th className="w-20 px-3 py-3 text-center text-xs font-semibold uppercase tracking-wider text-gray-500">Action</th>
                  <th className="w-8" />
                </tr>
              </thead>
              <tbody className="divide-y divide-black/5">
                {filtered.length === 0 && (
                  <tr><td colSpan={7} className="py-14 text-center text-sm text-gray-400">Không có câu hỏi</td></tr>
                )}
                {filtered.map((q) => {
                  const isExp         = expanded === q.id;
                  const isEditing     = editing?.id === q.id;
                  const isActiveChunk = panel?.chunkId && q.source_chunk_ids?.includes(panel.chunkId);
                  return (
                    <React.Fragment key={q.id}>
                      <tr className={cn(
                        "hover:bg-gray-50/50 transition-colors",
                        selected.has(q.id) && "bg-emerald-50/50",
                        isActiveChunk && "bg-blue-50/40 ring-1 ring-inset ring-blue-200/60",
                        isEditing && "bg-amber-50/60 ring-1 ring-inset ring-amber-200/60",
                      )}>
                        <td className="px-4 py-3">
                          <input type="checkbox" checked={selected.has(q.id)} onChange={() => toggleQ(q.id)} className="accent-emerald-600" />
                        </td>
                        <td className="px-3 py-3">
                          <span className="text-xs text-gray-400 tabular-nums">{globalIndex[q.id]}</span>
                        </td>
                        <td className="px-4 py-3">
                          {isEditing
                            ? <textarea autoFocus rows={3} value={editing.question}
                                onChange={(e) => setEditing({ ...editing, question: e.target.value })}
                                onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); saveEdit(); } if (e.key === "Escape") setEditing(null); }}
                                className="w-full text-xs border border-amber-300 rounded-lg px-2 py-1.5 focus:outline-none focus:ring-2 focus:ring-amber-400/40 resize-none" />
                            : <button type="button" disabled={tab === "archived"}
                                onClick={() => setEditing({ id: q.id, question: q.question, groundTruth: q.ground_truth })}
                                className="text-left text-xs text-gray-800 leading-relaxed w-full cursor-text hover:bg-amber-50/60 rounded px-1 -mx-1 transition-colors disabled:cursor-default disabled:hover:bg-transparent line-clamp-3">
                                {q.question}
                              </button>}
                        </td>
                        <td className="px-4 py-3">
                          {isEditing
                            ? <textarea rows={3} value={editing.groundTruth}
                                onChange={(e) => setEditing({ ...editing, groundTruth: e.target.value })}
                                onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); saveEdit(); } if (e.key === "Escape") setEditing(null); }}
                                className="w-full text-xs border border-amber-300 rounded-lg px-2 py-1.5 focus:outline-none focus:ring-2 focus:ring-amber-400/40 resize-none" />
                            : <button type="button" disabled={tab === "archived"}
                                onClick={() => setEditing({ id: q.id, question: q.question, groundTruth: q.ground_truth })}
                                className="text-left text-gray-500 text-xs leading-relaxed w-full cursor-text hover:bg-amber-50/60 rounded px-1 -mx-1 transition-colors disabled:cursor-default disabled:hover:bg-transparent">
                                {q.ground_truth}
                              </button>}
                        </td>
                        <td className="px-3 py-3">
                          {q.source_chunk_ids && q.source_chunk_ids.length > 0 ? (
                            <div className="flex flex-col gap-1">
                              {q.source_chunk_ids.map((id) => (
                                <button
                                  key={id}
                                  onClick={() => openPanel(id, q)}
                                  className={cn(
                                    "text-left text-xs font-mono px-1.5 py-0.5 rounded border transition-colors truncate max-w-[170px]",
                                    panel?.chunkId === id
                                      ? "bg-blue-600 text-white border-blue-600"
                                      : "bg-blue-50 text-blue-700 border-blue-200 hover:bg-blue-100"
                                  )}
                                  title={id}
                                >
                                  {id}
                                </button>
                              ))}
                            </div>
                          ) : (
                            <span className="text-xs text-gray-300">—</span>
                          )}
                        </td>
                        <td className="px-3 py-3">
                          <div className="flex items-center justify-center gap-1">
                            {tab === "pending" && (
                              <button onClick={() => approveOne(q.id)} title="Duyệt"
                                className="p-1.5 rounded-lg text-emerald-600 hover:bg-emerald-50 hover:scale-110 transition-all pressable">
                                <CheckCircle2 size={16} />
                              </button>
                            )}
                            {tab === "archived" && (
                              <button onClick={() => restoreOne(q.id)} title="Khôi phục"
                                className="p-1.5 rounded-lg text-blue-500 hover:bg-blue-50 hover:scale-110 transition-all pressable">
                                <Undo2 size={16} />
                              </button>
                            )}
                            {/* Nút 1 — Loại bỏ (mềm, khôi phục được) */}
                            {tab !== "archived" && (
                              <button onClick={() => archiveOne(q.id)} title="Loại bỏ (vào thùng rác, khôi phục được)"
                                className="p-1.5 rounded-lg text-amber-500 hover:bg-amber-50 hover:scale-110 transition-all pressable">
                                <Archive size={16} />
                              </button>
                            )}
                            {/* Nút 2 — Xóa vĩnh viễn (cứng); câu đã có kết quả eval thì khóa */}
                            {q.has_results ? (
                              <button disabled title="Đã có kết quả eval — không xóa cứng được, chỉ loại bỏ"
                                className="p-1.5 rounded-lg text-gray-300 cursor-not-allowed">
                                <Trash2 size={16} />
                              </button>
                            ) : (
                              <button onClick={() => deleteForeverOne(q.id)} title="Xóa vĩnh viễn (không khôi phục được)"
                                className="p-1.5 rounded-lg text-red-600 hover:bg-red-50 hover:scale-110 transition-all pressable">
                                <Trash2 size={16} />
                              </button>
                            )}
                            {/* Badge lịch sử eval — chỉ hiện khi có ≥1 lần chạy */}
                            {q.eval_count > 0 && (
                              <button
                                onClick={() => setHistoryPanel({ id: q.id, question: q.question })}
                                title={`Xem lịch sử ${q.eval_count} lần đánh giá`}
                                className="relative p-1.5 rounded-lg text-indigo-500 hover:bg-indigo-50 hover:scale-110 transition-all pressable"
                              >
                                <Clock size={15} />
                                <span className="absolute -top-1 -right-1 min-w-[14px] h-[14px] flex items-center justify-center text-[9px] font-bold bg-indigo-500 text-white rounded-full px-0.5 leading-none">
                                  {q.eval_count}
                                </span>
                              </button>
                            )}
                          </div>
                        </td>
                        <td className="px-2 py-3">
                          <button onClick={() => setExpanded(isExp ? null : q.id)} className="text-gray-400 hover:text-gray-600 p-1 transition-colors">
                            {isExp ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                          </button>
                        </td>
                      </tr>

                      {isExp && (
                        <tr className="bg-gray-50/40">
                          <td colSpan={7} className="px-8 py-5">
                            <div className="space-y-4 text-sm">
                              <div className="flex items-center gap-2 flex-wrap">
                                {q.section && (
                                  <span className="inline-flex items-center text-xs bg-emerald-50 text-emerald-700 border border-emerald-200 px-2.5 py-1 rounded-full">
                                    {q.section}
                                  </span>
                                )}
                                {q.dataset_id && datasetMap[q.dataset_id] && (
                                  <span className="inline-flex items-center text-xs bg-gray-100 text-gray-500 px-2.5 py-1 rounded-full">
                                    {datasetMap[q.dataset_id]}
                                  </span>
                                )}
                              </div>
                              <div className="grid grid-cols-2 gap-6">
                                <div>
                                  <p className="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-2">Câu hỏi đầy đủ</p>
                                  <p className="text-gray-800 leading-relaxed">{q.question}</p>
                                </div>
                                <div>
                                  <p className="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-2">Đáp án chuẩn</p>
                                  <p className="text-gray-700 leading-relaxed">{q.ground_truth}</p>
                                </div>
                              </div>
                              <div className="flex items-center gap-4 text-xs text-gray-400 pt-1 border-t border-black/6">
                                <span>Doc: <span className="font-mono text-gray-500">{q.document_id}</span></span>
                                {q.reviewed_by && <span>Reviewed by: {q.reviewed_by}</span>}
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
          )}
        </div>

        {panel && <ChunkPanel state={panel} onClose={() => setPanel(null)} />}
      </div>

      {/* Overlay lịch sử eval theo câu — float góc dưới phải */}
      {historyPanel && (
        <HistoryOverlay
          questionId={historyPanel.id}
          questionText={historyPanel.question}
          onClose={() => setHistoryPanel(null)}
        />
      )}
    </div>
  );
}
