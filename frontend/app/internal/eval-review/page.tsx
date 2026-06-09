"use client";

import React, { useEffect, useState } from "react";
import { CheckCircle2, ChevronDown, ChevronRight, Search, Trash2, Undo2, Upload, X } from "lucide-react";
import { cn } from "@/lib/utils";

const API = process.env.NEXT_PUBLIC_AGENTIC_RAG_API_URL ?? "http://localhost:8000";

type Dataset  = { id: string; name: string; is_benchmark: boolean };
type Question = {
  id: string; section: string | null; question: string; ground_truth: string;
  document_id: string; source_chunk_ids: string[] | null;
  is_approved: boolean; reviewed_by: string | null;
  deleted_at: string | null; created_at: string;
  has_results: boolean;
};
type Tab = "draft" | "approved" | "evaluated" | "archived";
type ChunkContent = { chunk_id: string; document_id: string; text: string; metadata: Record<string, unknown> };
type PanelState = { chunkId: string; question: string; groundTruth: string };

function ChunkPanel({ state, onClose }: { state: PanelState; onClose: () => void }) {
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
      {/* Header */}
      <div className="flex items-start justify-between gap-2 px-4 py-3 border-b border-black/6 shrink-0 bg-gray-50/60">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-0.5">Chunk</p>
          <p className="text-xs font-mono text-gray-500 break-all leading-relaxed">{state.chunkId}</p>
          {data?.metadata?.section && (
            <span className="mt-1.5 inline-block text-xs bg-emerald-50 text-emerald-700 border border-emerald-200 px-2 py-0.5 rounded-full">
              {String(data.metadata.section)}
            </span>
          )}
        </div>
        <button onClick={onClose} className="text-gray-400 hover:text-gray-600 p-1 shrink-0 mt-0.5"><X size={15} /></button>
      </div>

      <div className="flex-1 overflow-y-auto divide-y divide-black/6">
        {/* Chunk content */}
        <div className="px-4 py-4">
          <p className="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-2">Nội dung tài liệu</p>
          {!data && !err && <p className="text-sm text-gray-400 py-4 text-center">Đang tải...</p>}
          {err  && <p className="text-sm text-red-500 py-4 text-center">Không tìm thấy chunk</p>}
          {data && <p className="text-sm text-gray-800 leading-relaxed whitespace-pre-wrap">{data.text}</p>}
        </div>

        {/* Q&A */}
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
  const [datasets,  setDatasets]  = useState<Dataset[]>([]);
  const [datasetId, setDatasetId] = useState<string>("");
  const [questions, setQuestions] = useState<Question[]>([]);
  const [tab,       setTab]       = useState<Tab>("approved");
  const [selected,  setSelected]  = useState<Set<string>>(new Set());
  const [expanded,  setExpanded]  = useState<string | null>(null);
  const [search,    setSearch]    = useState("");
  const [loading,   setLoading]   = useState(false);
  const [panel,     setPanel]     = useState<PanelState | null>(null);
  const [importing, setImporting] = useState(false);
  const [importMsg, setImportMsg] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${API}/internal/datasets`)
      .then((r) => r.json())
      .then((d: Dataset[]) => { setDatasets(d); if (d.length) setDatasetId(d[0].id); })
      .catch(() => {});
  }, []);

  useEffect(() => { if (datasetId) loadQuestions(); }, [datasetId]);

  function loadQuestions() {
    setLoading(true);
    fetch(`${API}/internal/datasets/${datasetId}/questions?include_deleted=true`)
      .then((r) => r.json())
      .then((d: Question[]) => { setQuestions(d); setLoading(false); })
      .catch(() => setLoading(false));
  }

  async function approveOne(id: string) {
    await fetch(`${API}/internal/questions/approve`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question_ids: [id], reviewed_by: "internal" }),
    });
    loadQuestions();
  }

  async function archiveOne(id: string) {
    await fetch(`${API}/internal/questions/archive`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify([id]),
    });
    loadQuestions();
  }

  async function restoreOne(id: string) {
    await fetch(`${API}/internal/questions/restore`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify([id]),
    });
    loadQuestions();
  }

  async function handleBulkApprove() {
    await fetch(`${API}/internal/questions/approve`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question_ids: [...selected], reviewed_by: "internal" }),
    });
    setSelected(new Set()); loadQuestions();
  }

  async function handleBulkArchive() {
    await fetch(`${API}/internal/questions/archive`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify([...selected]),
    });
    setSelected(new Set()); loadQuestions();
  }

  async function handleBulkRestore() {
    await fetch(`${API}/internal/questions/restore`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify([...selected]),
    });
    setSelected(new Set()); loadQuestions();
  }

  async function handleImport() {
    if (!datasetId) return;
    setImporting(true);
    setImportMsg(null);
    try {
      const r = await fetch(`${API}/internal/datasets/${datasetId}/import-excel`, { method: "POST" });
      const d = await r.json();
      setImportMsg(`Đã import ${d.imported} câu hỏi mới`);
      if (d.imported > 0) loadQuestions();
    } catch {
      setImportMsg("Import thất bại");
    } finally {
      setImporting(false);
    }
  }

  const byTab = questions.filter((q) => {
    if (tab === "draft")     return !q.deleted_at && !q.is_approved;
    if (tab === "approved")  return !q.deleted_at && q.is_approved && !q.has_results;
    if (tab === "evaluated") return !q.deleted_at && q.has_results;
    return !!q.deleted_at;
  });

  const filtered = search.trim()
    ? byTab.filter((q) =>
        q.question.toLowerCase().includes(search.toLowerCase()) ||
        q.ground_truth.toLowerCase().includes(search.toLowerCase())
      )
    : byTab;

  const toggleQ   = (id: string) => setSelected((p) => { const n = new Set(p); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const toggleAll = () => setSelected(selected.size === filtered.length ? new Set() : new Set(filtered.map((q) => q.id)));

  const counts = {
    draft:     questions.filter((q) => !q.deleted_at && !q.is_approved).length,
    approved:  questions.filter((q) => !q.deleted_at && q.is_approved && !q.has_results).length,
    evaluated: questions.filter((q) => !q.deleted_at && q.has_results).length,
    archived:  questions.filter((q) => !!q.deleted_at).length,
  };

  const TABS: { key: Tab; label: string; count: number }[] = [
    { key: "draft",     label: "Chưa review",  count: counts.draft },
    { key: "approved",  label: "Đã duyệt",     count: counts.approved },
    { key: "evaluated", label: "Đã đánh giá",  count: counts.evaluated },
    { key: "archived",  label: "Archive",       count: counts.archived },
  ];

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
        <div className="flex items-center gap-2 flex-wrap">
          <select
            value={datasetId}
            onChange={(e) => { setDatasetId(e.target.value); setSelected(new Set()); }}
            className="text-sm border border-black/12 rounded-lg px-3 py-1.5 bg-white focus:outline-none focus:ring-2 focus:ring-emerald-500/40"
          >
            {datasets.map((d) => <option key={d.id} value={d.id}>{d.name}{d.is_benchmark ? " ★" : ""}</option>)}
          </select>
          <button
            onClick={handleImport}
            disabled={importing || !datasetId}
            title="Import câu hỏi pending từ result.xlsx"
            className="flex items-center gap-1.5 text-sm px-3 py-1.5 rounded-lg border border-black/12 bg-white text-gray-600 hover:bg-gray-50 disabled:opacity-40 transition-colors"
          >
            <Upload size={14} />
            {importing ? "Đang import..." : "Import Excel"}
          </button>
          {importMsg && <span className="text-xs text-gray-500">{importMsg}</span>}
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
                "px-3.5 py-1.5 rounded-md text-sm font-medium transition-colors",
                tab === t.key ? "bg-gray-900 text-white" : "text-gray-500 hover:bg-gray-100"
              )}
            >
              {t.label}
              <span className={cn("ml-1.5 text-xs tabular-nums", tab === t.key ? "text-white/70" : "text-gray-400")}>
                {t.count}
              </span>
            </button>
          ))}
        </div>

        <div className="flex items-center gap-2 ml-auto">
          <div className="relative">
            <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Tìm câu hỏi..."
              className="pl-8 pr-3 py-1.5 text-sm border border-black/12 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500/40 w-52"
            />
          </div>

          {selected.size > 0 && tab !== "evaluated" && (
            <div className="flex items-center gap-2">
              <span className="text-xs text-gray-400">Đã chọn {selected.size}</span>
              {tab === "draft" && (
                <button onClick={handleBulkApprove} className="flex items-center gap-1 text-sm px-3 py-1.5 rounded-lg bg-emerald-100 text-emerald-800 hover:bg-emerald-200 transition-colors">
                  <CheckCircle2 size={13} /> Duyệt tất cả
                </button>
              )}
              {tab !== "archived" && (
                <button onClick={handleBulkArchive} className="flex items-center gap-1 text-sm px-3 py-1.5 rounded-lg bg-red-50 text-red-700 hover:bg-red-100 transition-colors">
                  <Trash2 size={13} /> Xóa tất cả
                </button>
              )}
              {tab === "archived" && (
                <button onClick={handleBulkRestore} className="flex items-center gap-1 text-sm px-3 py-1.5 rounded-lg bg-blue-50 text-blue-700 hover:bg-blue-100 transition-colors">
                  <Undo2 size={13} /> Restore tất cả
                </button>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Main: table + side panel */}
      <div className={cn("grid gap-4", panel ? "grid-cols-[1fr_380px]" : "grid-cols-1")}>
        {/* Table */}
        <div className="bg-white rounded-xl border border-black/8 overflow-hidden">
          {loading ? (
            <div className="py-16 text-center text-sm text-gray-400">Đang tải...</div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-black/6 bg-gray-50/60">
                  <th className="w-10 px-4 py-3">
                    <input type="checkbox" checked={selected.size === filtered.length && filtered.length > 0} onChange={toggleAll} className="accent-emerald-600" />
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">Câu hỏi</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">Đáp án chuẩn</th>
                  <th className="px-3 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500 w-48">Ground Truth IDs</th>
                  <th className="w-20 px-3 py-3 text-center text-xs font-semibold uppercase tracking-wider text-gray-500">Action</th>
                  <th className="w-8" />
                </tr>
              </thead>
              <tbody className="divide-y divide-black/5">
                {filtered.length === 0 && (
                  <tr><td colSpan={6} className="py-14 text-center text-sm text-gray-400">Không có câu hỏi</td></tr>
                )}
                {filtered.map((q) => {
                  const isExp = expanded === q.id;
                  const isActiveChunk = panel?.chunkId && q.source_chunk_ids?.includes(panel.chunkId);
                  return (
                    <React.Fragment key={q.id}>
                      <tr className={cn(
                        "hover:bg-gray-50/50 transition-colors",
                        selected.has(q.id) && "bg-emerald-50/50",
                        isActiveChunk && "bg-blue-50/40 ring-1 ring-inset ring-blue-200/60",
                      )}>
                        <td className="px-4 py-3">
                          <input type="checkbox" checked={selected.has(q.id)} onChange={() => toggleQ(q.id)} className="accent-emerald-600" />
                        </td>
                        <td className="px-4 py-3">
                          <p className="text-gray-800 leading-relaxed">{q.question}</p>
                        </td>
                        <td className="px-4 py-3">
                          <p className="text-gray-500 text-xs leading-relaxed">{q.ground_truth}</p>
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
                            {tab === "draft" && (
                              <button onClick={() => approveOne(q.id)} title="Duyệt"
                                className="p-1.5 rounded-lg text-emerald-600 hover:bg-emerald-50 transition-colors">
                                <CheckCircle2 size={16} />
                              </button>
                            )}
                            {tab !== "archived" && tab !== "evaluated" && (
                              <button onClick={() => archiveOne(q.id)} title="Xóa"
                                className="p-1.5 rounded-lg text-red-400 hover:bg-red-50 transition-colors">
                                <Trash2 size={16} />
                              </button>
                            )}
                            {tab === "archived" && (
                              <button onClick={() => restoreOne(q.id)} title="Khôi phục"
                                className="p-1.5 rounded-lg text-blue-500 hover:bg-blue-50 transition-colors">
                                <Undo2 size={16} />
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
                          <td colSpan={6} className="px-8 py-5">
                            <div className="space-y-4 text-sm">
                              {q.section && (
                                <span className="inline-flex items-center text-xs bg-emerald-50 text-emerald-700 border border-emerald-200 px-2.5 py-1 rounded-full">
                                  {q.section}
                                </span>
                              )}
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

        {/* Side panel */}
        {panel && <ChunkPanel state={panel} onClose={() => setPanel(null)} />}
      </div>
    </div>
  );
}
