"use client";

import React, { useEffect, useState } from "react";
import { CheckCircle2, ChevronRight, Layers, Loader2, Plus, Search, Trash2, X } from "lucide-react";
import { cn } from "@/lib/utils";

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

type Dataset  = { id: string; name: string; description: string | null; is_benchmark: boolean; is_multihop?: boolean; created_at: string };
type Question = {
  id: string; question: string; ground_truth: string; section: string | null;
  document_id: string; source_chunk_ids: string[] | null;
  is_approved: boolean; deleted_at: string | null; global_seq: number;
};

export default function DatasetsPage() {
  const [datasets,    setDatasets]    = useState<Dataset[]>([]);
  const [activeId,    setActiveId]    = useState<string | null>(null);
  const [questions,   setQuestions]   = useState<Question[]>([]);
  const [qLoading,    setQLoading]    = useState(false);

  // Create dataset form
  const [showCreate,  setShowCreate]  = useState(false);
  const [newName,     setNewName]     = useState("");
  const [newDesc,     setNewDesc]     = useState("");
  const [isBenchmark, setIsBenchmark] = useState(true);
  const [isMultihop, setIsMultihop] = useState(false);
  const [creating,    setCreating]    = useState(false);

  // Import from approved pool
  const [showImport,  setShowImport]  = useState(false);
  const [pool,        setPool]        = useState<Question[]>([]);
  const [poolLoading, setPoolLoading] = useState(false);
  const [srcSelected, setSrcSelected] = useState<Set<string>>(new Set());
  const [srcSearch,   setSrcSearch]   = useState("");
  const [importing,   setImporting]   = useState(false);
  const [importSource, setImportSource] = useState<string>(""); // "" = tất cả câu đã duyệt; còn lại = id dataset nguồn
  // Lọc dedup: ẩn câu có ground-truth nằm trong chunk bị flag ở layer được chọn
  const [hideDedupLayers, setHideDedupLayers] = useState<Set<string>>(new Set());
  const [flaggedByLayer,  setFlaggedByLayer]  = useState<FlaggedMap>({});
  const toggleHideLayer = (key: string) =>
    setHideDedupLayers((prev) => { const n = new Set(prev); n.has(key) ? n.delete(key) : n.add(key); return n; });

  // Delete dataset confirm
  const [confirmDelete, setConfirmDelete] = useState<Dataset | null>(null);
  const [deleting,      setDeleting]      = useState(false);

  // Search within active dataset
  const [search, setSearch] = useState("");

  useEffect(() => { loadDatasets(); }, []);

  // Khi đổi layer ẩn: bỏ chọn những câu vừa bị ẩn để không import nhầm
  useEffect(() => {
    const hidden = collectFlaggedChunkIds(hideDedupLayers, flaggedByLayer);
    if (hidden.size === 0) return;
    setSrcSelected((prev) => {
      const next = new Set(prev);
      for (const q of pool)
        if ((q.source_chunk_ids ?? []).some((cid) => hidden.has(cid))) next.delete(q.id);
      return next;
    });
  }, [hideDedupLayers, flaggedByLayer, pool]);

  function loadDatasets() {
    fetch(`${API}/internal/datasets`)
      .then((r) => r.json())
      .then((d: Dataset[]) => setDatasets(d))
      .catch(() => {});
  }

  function loadQuestions(id: string) {
    setQLoading(true);
    setQuestions([]);
    fetch(`${API}/internal/datasets/${id}/questions?include_deleted=false`)
      .then((r) => r.json())
      .then((d: Question[]) => { setQuestions(d); setQLoading(false); })
      .catch(() => setQLoading(false));
  }

  function selectDataset(id: string) {
    setActiveId(id);
    setShowImport(false);
    setSearch("");
    loadQuestions(id);
  }

  async function deleteDataset(id: string) {
    setDeleting(true);
    await fetch(`${API}/internal/datasets/${id}`, { method: "DELETE" });
    setDatasets((prev) => prev.filter((d) => d.id !== id));
    if (activeId === id) { setActiveId(null); setQuestions([]); }
    setConfirmDelete(null); setDeleting(false);
  }

  async function createDataset(e: React.FormEvent) {
    e.preventDefault();
    if (!newName.trim()) return;
    setCreating(true);
    const r = await fetch(`${API}/internal/datasets`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: newName.trim(), description: newDesc.trim() || null, is_benchmark: isBenchmark, is_multihop: isMultihop }),
    });
    const d: Dataset = await r.json();
    setDatasets((prev) => [d, ...prev]);
    setNewName(""); setNewDesc(""); setCreating(false); setShowCreate(false);
    selectDataset(d.id);
  }

  // Xóa câu khỏi dataset (không xóa khỏi kho)
  async function removeQuestion(qid: string) {
    if (!activeId) return;
    await fetch(`${API}/internal/datasets/${activeId}/questions/remove`, {
      method: "DELETE", headers: { "Content-Type": "application/json" },
      body: JSON.stringify([qid]),
    });
    setQuestions((prev) => prev.filter((q) => q.id !== qid));
  }

  // Load pool theo nguồn: "" = toàn bộ kho approved, hoặc id 1 dataset nguồn.
  // Luôn bỏ qua câu đã có trong dataset đang mở + chỉ lấy câu approved.
  function loadPool(source: string) {
    if (!activeId) return;
    setSrcSelected(new Set());
    setPoolLoading(true);
    const url = source
      ? `${API}/internal/datasets/${source}/questions?include_deleted=false`
      : `${API}/internal/questions?include_deleted=false`;
    fetch(url)
      .then((r) => r.json())
      .then((all: Question[]) => {
        const alreadyIn = new Set(questions.map((q) => q.id));
        setPool(all.filter((q) => q.is_approved && !alreadyIn.has(q.id)));
        setPoolLoading(false);
      })
      .catch(() => setPoolLoading(false));
  }

  // Mở panel import — mặc định lấy từ toàn bộ kho câu đã duyệt
  function openImport() {
    if (!activeId) return;
    setSrcSearch("");
    setImportSource("");
    setHideDedupLayers(new Set());
    setShowImport(true);
    loadPool("");
    fetch(`${API}/internal/dedup/flagged-chunk-ids`)
      .then((r) => r.json())
      .then((d: FlaggedMap) => setFlaggedByLayer(d && typeof d === "object" ? d : {}))
      .catch(() => setFlaggedByLayer({}));
  }

  function changeSource(source: string) {
    setImportSource(source);
    loadPool(source);
  }

  async function doImport() {
    if (!activeId || srcSelected.size === 0) return;
    setImporting(true);
    await fetch(`${API}/internal/datasets/${activeId}/questions/add`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(Array.from(srcSelected)),
    });
    setImporting(false);
    setShowImport(false);
    loadQuestions(activeId);
  }

  const activeDataset = datasets.find((d) => d.id === activeId);
  const filtered = search.trim()
    ? questions.filter((q) => q.question.toLowerCase().includes(search.toLowerCase()) || q.ground_truth.toLowerCase().includes(search.toLowerCase()))
    : questions;

  // Tập chunk_id bị flag ở các layer đang chọn để ẩn
  const hiddenChunkIds = collectFlaggedChunkIds(hideDedupLayers, flaggedByLayer);
  const isHiddenByDedup = (q: Question) =>
    hiddenChunkIds.size > 0 && (q.source_chunk_ids ?? []).some((cid) => hiddenChunkIds.has(cid));

  // pool sau khi ẩn câu trùng → rồi mới áp search
  const poolAfterDedup = pool.filter((q) => !isHiddenByDedup(q));
  const hiddenCount = pool.length - poolAfterDedup.length;
  const poolFiltered = srcSearch.trim()
    ? poolAfterDedup.filter((q) => q.question.toLowerCase().includes(srcSearch.toLowerCase()) || q.ground_truth.toLowerCase().includes(srcSearch.toLowerCase()))
    : poolAfterDedup;

  const poolCountLabel = (() => {
    if (poolLoading) return "Đang tải...";
    if (hiddenCount > 0)
      return `${poolAfterDedup.length} câu hiển thị · ẩn ${hiddenCount} câu trùng (tổng ${pool.length})`;
    return `${pool.length} câu approved chưa có trong dataset này`;
  })();

  return (
    <div className="space-y-5">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">Datasets</h1>
          <p className="text-sm text-gray-500 mt-1">Tạo và quản lý bộ câu hỏi benchmark</p>
        </div>
        <button
          onClick={() => { setShowCreate((v) => !v); setShowImport(false); }}
          className="flex items-center gap-1.5 text-sm px-4 py-2 rounded-lg bg-emerald-700 text-white hover:bg-emerald-800 transition-colors"
        >
          {showCreate ? <X size={14} /> : <Plus size={14} />}
          Tạo dataset
        </button>
      </div>

      {/* Confirm delete dialog */}
      {confirmDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm">
          <div className="bg-white rounded-2xl border border-black/10 shadow-xl w-full max-w-sm mx-4 px-6 py-5 space-y-4">
            <div>
              <p className="text-base font-semibold text-gray-900">Xóa dataset?</p>
              <p className="text-sm text-gray-500 mt-1">
                Bạn có chắc muốn xóa <span className="font-medium text-gray-800">{confirmDelete.name}</span>?
                Câu hỏi sẽ không bị xóa khỏi kho.
              </p>
            </div>
            <div className="flex gap-2 justify-end">
              <button onClick={() => setConfirmDelete(null)}
                className="px-4 py-1.5 text-sm rounded-lg border border-black/12 text-gray-500 hover:bg-gray-50">
                Huỷ
              </button>
              <button onClick={() => deleteDataset(confirmDelete.id)} disabled={deleting}
                className="flex items-center gap-1.5 px-4 py-1.5 text-sm rounded-lg bg-red-600 text-white hover:bg-red-700 disabled:opacity-50 transition-colors">
                {deleting && <Loader2 size={13} className="animate-spin" />}
                Xóa
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Create form */}
      {showCreate && (
        <form onSubmit={createDataset} className="bg-white rounded-xl border border-black/8 px-5 py-4 space-y-3">
          <p className="text-sm font-medium text-gray-700">Dataset mới</p>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-gray-400 mb-1 block">Tên *</label>
              <input
                autoFocus value={newName} onChange={(e) => setNewName(e.target.value)}
                placeholder="VD: Benchmark v2 – Tháng 6"
                className="w-full text-sm border border-black/12 rounded-lg px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-emerald-500/40"
              />
            </div>
            <div>
              <label className="text-xs text-gray-400 mb-1 block">Mô tả</label>
              <input
                value={newDesc} onChange={(e) => setNewDesc(e.target.value)}
                placeholder="Tuỳ chọn"
                className="w-full text-sm border border-black/12 rounded-lg px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-emerald-500/40"
              />
            </div>
          </div>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <label className="flex items-center gap-2 text-sm text-gray-600 cursor-pointer">
                <input type="checkbox" checked={isBenchmark} onChange={(e) => setIsBenchmark(e.target.checked)} className="accent-emerald-600" />
                Đánh dấu là benchmark ★
              </label>
              <label className="flex items-center gap-2 text-sm text-gray-600 cursor-pointer">
                <input type="checkbox" checked={isMultihop} onChange={(e) => setIsMultihop(e.target.checked)} className="accent-teal-600" />
                Multi-hop (coverage@5)
              </label>
            </div>
            <div className="flex gap-2">
              <button type="button" onClick={() => setShowCreate(false)} className="px-3 py-1.5 text-sm rounded-lg border border-black/12 text-gray-500 hover:bg-gray-50">Huỷ</button>
              <button type="submit" disabled={creating || !newName.trim()} className="px-4 py-1.5 text-sm rounded-lg bg-emerald-700 text-white hover:bg-emerald-800 disabled:opacity-40 flex items-center gap-1.5">
                {creating && <Loader2 size={13} className="animate-spin" />} Tạo
              </button>
            </div>
          </div>
        </form>
      )}

      {/* Main layout */}
      <div className="grid grid-cols-[260px_1fr] gap-4 items-start">
        {/* Dataset list */}
        <div className="bg-white rounded-xl border border-black/8 overflow-hidden">
          <div className="px-4 py-2.5 border-b border-black/6 bg-gray-50/60">
            <p className="text-xs font-semibold uppercase tracking-wider text-gray-500">Bộ dữ liệu</p>
          </div>
          {datasets.length === 0 && (
            <p className="text-sm text-gray-400 p-4 text-center">Chưa có dataset nào</p>
          )}
          {datasets.map((d) => (
            <div
              key={d.id}
              className={cn(
                "group flex items-center border-b border-black/5 last:border-0 hover:bg-gray-50 row-hover",
                activeId === d.id && "bg-emerald-50 hover:bg-emerald-50"
              )}
            >
              <div
                role="button" tabIndex={0}
                onClick={() => selectDataset(d.id)}
                onKeyDown={(e) => e.key === "Enter" && selectDataset(d.id)}
                className="flex-1 min-w-0 px-4 py-3 cursor-pointer"
              >
                <div className="flex items-center gap-1">
                  <span className="text-sm font-medium text-gray-800 truncate flex-1">
                    {d.name}
                    {d.is_benchmark && <span className="ml-1 text-amber-500">★</span>}
                    {d.is_multihop && <span className="ml-1 text-[10px] font-semibold text-teal-700 bg-teal-50 border border-teal-200 px-1.5 py-0.5 rounded-full align-middle">multi-hop</span>}
                  </span>
                  {activeId === d.id && <ChevronRight size={13} className="text-emerald-600 shrink-0" />}
                </div>
              </div>
              <button
                onClick={() => setConfirmDelete(d)}
                className="p-2 mr-2 text-gray-300 hover:text-red-500 transition-colors shrink-0 opacity-0 group-hover:opacity-100"
                title="Xóa dataset"
              >
                <Trash2 size={13} />
              </button>
            </div>
          ))}
        </div>

        {/* Question panel */}
        {!activeId ? (
          <div className="bg-white rounded-xl border border-black/8 h-48 flex items-center justify-center text-sm text-gray-400">
            ← Chọn dataset để xem câu hỏi
          </div>
        ) : (
          <div className="space-y-3">
            {/* Toolbar */}
            <div className="flex items-center gap-2 flex-wrap">
              <div className="relative flex-1 min-w-48">
                <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400" />
                <input
                  value={search} onChange={(e) => setSearch(e.target.value)}
                  placeholder="Tìm câu hỏi..."
                  className="w-full pl-8 pr-3 py-1.5 text-sm border border-black/12 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500/40"
                />
              </div>
              <button
                onClick={openImport}
                className="flex items-center gap-1.5 text-sm px-3 py-1.5 rounded-lg border border-emerald-200 text-emerald-700 bg-emerald-50 hover:bg-emerald-100 transition-colors"
              >
                <Plus size={13} /> Thêm từ câu đã duyệt
              </button>
            </div>

            {/* Import panel */}
            {showImport && (
              <div className="bg-white rounded-xl border border-black/8 px-5 py-4 space-y-3">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-gray-700">Thêm câu vào dataset</p>
                    <p className="text-xs text-gray-400 mt-0.5">{poolCountLabel}</p>
                  </div>
                  <button onClick={() => setShowImport(false)} className="text-gray-400 hover:text-gray-600"><X size={15} /></button>
                </div>

                {/* Chọn nguồn: toàn bộ kho hay kế thừa từ 1 dataset có sẵn */}
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-xs text-gray-400 shrink-0">Lấy từ:</span>
                  <select
                    value={importSource}
                    onChange={(e) => changeSource(e.target.value)}
                    className="text-sm border border-black/12 rounded-lg px-3 py-1.5 bg-white focus:outline-none focus:ring-2 focus:ring-emerald-500/40 max-w-[280px]"
                  >
                    <option value="">Tất cả câu đã duyệt</option>
                    {datasets.filter((d) => d.id !== activeId).map((d) => (
                      <option key={d.id} value={d.id}>{d.name}{d.is_benchmark ? " ★" : ""}</option>
                    ))}
                  </select>
                </div>

                {/* Lọc dedup: ẩn câu có ground-truth nằm trong chunk bị flag */}
                <div className="flex items-center gap-2 flex-wrap rounded-lg bg-gray-50 border border-black/6 px-3 py-2">
                  <Layers size={13} className="text-gray-400 shrink-0" />
                  <span className="text-xs text-gray-500 shrink-0">Ẩn câu trùng:</span>
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
                    <span className="text-xs text-amber-700 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded-full ml-auto">
                      đã ẩn {hiddenCount} câu
                    </span>
                  )}
                </div>

                <div className="flex items-center gap-2">
                  <div className="relative flex-1">
                    <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400" />
                    <input
                      value={srcSearch} onChange={(e) => setSrcSearch(e.target.value)}
                      placeholder="Tìm câu hỏi..."
                      className="w-full pl-8 pr-3 py-1.5 text-sm border border-black/12 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500/40"
                    />
                  </div>
                  <button
                    onClick={() => {
                      const ids = poolFiltered.map((q) => q.id);
                      setSrcSelected(srcSelected.size === ids.length ? new Set() : new Set(ids));
                    }}
                    className="text-xs text-emerald-700 hover:underline whitespace-nowrap"
                  >
                    {srcSelected.size === poolFiltered.length && poolFiltered.length > 0 ? "Bỏ chọn tất cả" : "Chọn tất cả"}
                  </button>
                </div>

                <div className="max-h-64 overflow-y-auto border border-black/6 rounded-lg divide-y divide-black/5">
                  {poolLoading ? (
                    <div className="py-8 flex items-center justify-center gap-2 text-sm text-gray-400">
                      <Loader2 size={14} className="animate-spin" /> Đang tải...
                    </div>
                  ) : poolFiltered.length === 0 ? (
                    <p className="text-sm text-gray-400 p-6 text-center">
                      {pool.length === 0 ? "Không có câu đã duyệt nào ngoài dataset này" : "Không tìm thấy câu nào"}
                    </p>
                  ) : poolFiltered.map((q) => (
                    <label key={q.id} className={cn("flex items-start gap-3 px-3 py-2.5 cursor-pointer hover:bg-gray-50 transition-colors", srcSelected.has(q.id) && "bg-emerald-50/60")}>
                      <input type="checkbox" className="accent-emerald-600 mt-0.5 shrink-0"
                        checked={srcSelected.has(q.id)}
                        onChange={() => setSrcSelected((prev) => { const n = new Set(prev); n.has(q.id) ? n.delete(q.id) : n.add(q.id); return n; })}
                      />
                      <span className="text-xs text-gray-400 tabular-nums mt-0.5 shrink-0 w-8 text-right">{q.global_seq}.</span>
                      <div className="min-w-0 flex-1">
                        <p className="text-sm text-gray-800 line-clamp-1">{q.question}</p>
                        <p className="text-xs text-gray-400 line-clamp-1 mt-0.5">{q.ground_truth}</p>
                      </div>
                    </label>
                  ))}
                </div>

                <div className="flex items-center justify-between pt-1">
                  <span className="text-xs text-gray-400">Đã chọn <strong className="text-gray-700">{srcSelected.size}</strong> / {poolFiltered.length} câu</span>
                  <button
                    onClick={doImport}
                    disabled={importing || srcSelected.size === 0}
                    className="flex items-center gap-1.5 text-sm px-4 py-1.5 rounded-lg bg-emerald-700 text-white hover:bg-emerald-800 disabled:opacity-40 transition-colors"
                  >
                    {importing && <Loader2 size={13} className="animate-spin" />}
                    Thêm {srcSelected.size > 0 ? `${srcSelected.size} câu` : ""}
                  </button>
                </div>
              </div>
            )}

            {/* Questions table */}
            <div className="bg-white rounded-xl border border-black/8 overflow-hidden">
              <div className="px-4 py-2.5 border-b border-black/6 bg-gray-50/60 flex items-center justify-between">
                <p className="text-xs font-semibold uppercase tracking-wider text-gray-500">
                  {activeDataset?.name} — {filtered.length} câu hỏi
                </p>
                <div className="flex items-center gap-1.5">
                  {activeDataset?.is_multihop && <span className="text-xs text-teal-700 bg-teal-50 border border-teal-200 px-2 py-0.5 rounded-full">Multi-hop · coverage@5</span>}
                  {activeDataset?.is_benchmark && <span className="text-xs text-amber-600 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded-full">Benchmark ★</span>}
                </div>
              </div>
              {qLoading ? (
                <div className="py-12 flex items-center justify-center gap-2 text-sm text-gray-400">
                  <Loader2 size={14} className="animate-spin" /> Đang tải...
                </div>
              ) : (
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-black/6 text-xs font-semibold uppercase tracking-wider text-gray-500">
                      <th className="px-3 py-3 text-right w-10">#</th>
                      <th className="px-4 py-3 text-left">Câu hỏi</th>
                      <th className="px-4 py-3 text-left">Đáp án chuẩn</th>
                      <th className="px-3 py-3 text-center w-24">Trạng thái</th>
                      <th className="w-10" />
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-black/5">
                    {filtered.length === 0 && (
                      <tr><td colSpan={5} className="py-12 text-center text-sm text-gray-400">
                        Chưa có câu hỏi nào · Nhấn "Thêm từ câu đã duyệt" để thêm
                      </td></tr>
                    )}
                    {filtered.map((q) => (
                      <tr key={q.id} className="hover:bg-gray-50/50 transition-colors">
                        <td className="px-3 py-3 text-right">
                          <span className="text-xs text-gray-400 tabular-nums">{q.global_seq}</span>
                        </td>
                        <td className="px-4 py-3">
                          <p className="text-gray-800 leading-relaxed line-clamp-2">{q.question}</p>
                          {q.section && (
                            <span className="text-xs text-gray-400 bg-gray-100 px-1.5 py-0.5 rounded-full mt-1 inline-block">{q.section}</span>
                          )}
                        </td>
                        <td className="px-4 py-3">
                          <p className="text-gray-500 text-xs leading-relaxed line-clamp-2">{q.ground_truth}</p>
                        </td>
                        <td className="px-3 py-3 text-center">
                          <span className="inline-flex items-center gap-1 text-xs text-emerald-700 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded-full">
                            <CheckCircle2 size={11} /> Approved
                          </span>
                        </td>
                        <td className="px-3 py-3 text-center">
                          <button onClick={() => removeQuestion(q.id)} title="Xóa khỏi dataset (không xóa câu hỏi)"
                            className="p-1 text-gray-300 hover:text-red-500 transition-colors">
                            <Trash2 size={14} />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
