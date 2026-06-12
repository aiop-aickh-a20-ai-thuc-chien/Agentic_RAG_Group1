"use client";

import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Layers, Loader2, Pause, Pencil, Play, RefreshCw, Trash2, X } from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { CountUp, Spotlight } from "../_components/fx";

const API = process.env.NEXT_PUBLIC_AGENTIC_RAG_API_URL ?? "http://localhost:8000";

type Dataset    = { id: string; name: string; is_benchmark: boolean };
type Run        = { id: string; name: string; status: string; total: number; success: number; failed: number; created_at: string };
type Progress   = { run_id: string; status: string; total: number; success: number; failed: number; not_started: number; ragas_done: number };
type DedupStats = { corpus_chunks: number; exact_chunks: number; simhash_chunks: number; embedding_chunks: number };

const DEDUP_LAYERS = [
  { key: "exact_sha256",         label: "L1 Exact",     field: "exact_chunks"    },
  { key: "simhash",              label: "L2 SimHash",   field: "simhash_chunks"  },
  { key: "embedding_similarity", label: "L3 Embedding", field: "embedding_chunks" },
] as const;

const STATUS_LABEL: Record<string, string> = {
  queued:  "Đang chờ",
  running: "Đang chạy",
  paused:  "Tạm dừng",
  done:    "Hoàn thành",
  error:   "Lỗi",
};
const STATUS_CLS: Record<string, string> = {
  queued:  "bg-gray-100 text-gray-500",
  running: "bg-blue-100 text-blue-700",
  paused:  "bg-amber-100 text-amber-700",
  done:    "bg-emerald-100 text-emerald-700",
  error:   "bg-red-100 text-red-700",
};

function fmtDate(s: string) {
  const d = new Date(s);
  return d.toLocaleDateString("vi-VN") + " " + d.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
}

export default function EvalRunPage() {
  const [datasets,   setDatasets]   = useState<Dataset[]>([]);
  const [datasetId,  setDatasetId]  = useState<string>("");
  const [runName,    setRunName]    = useState<string>("");
  const [creating,   setCreating]   = useState(false);
  const [runs,       setRuns]       = useState<Run[]>([]);
  const [activeId,   setActiveId]   = useState<string | null>(null);
  const [progress,   setProgress]   = useState<Progress | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Dedup filter
  const [excludeDedupLayers, setExcludeDedupLayers] = useState<Set<string>>(new Set());
  const [dedupStats,         setDedupStats]         = useState<DedupStats | null>(null);
  // Câu hỏi bị ẩn vì ground-truth nằm trong chunk bị lọc (backend tự loại khi tạo run)
  const [affectedQ,          setAffectedQ]          = useState<{ total: number; affected: number; remaining: number } | null>(null);
  const toggleDedupLayer = (key: string) =>
    setExcludeDedupLayers((prev) => { const n = new Set(prev); n.has(key) ? n.delete(key) : n.add(key); return n; });

  // Rename state
  const [editingId,   setEditingId]   = useState<string | null>(null);
  const [editingName, setEditingName] = useState<string>("");
  const [renaming,    setRenaming]    = useState(false);

  // Delete state
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [deleting,        setDeleting]        = useState(false);

  useEffect(() => {
    fetch(`${API}/internal/datasets`)
      .then((r) => r.json())
      .then((d: Dataset[]) => { setDatasets(d); if (d.length) setDatasetId(d[0].id); })
      .catch(() => {});
    fetch(`${API}/internal/dedup?limit=1`)
      .then((r) => r.json())
      .then((d) => {
        const c = d?.counts;
        if (c) setDedupStats({
          corpus_chunks:    c.corpus_chunks    ?? 0,
          exact_chunks:     c.exact_chunks     ?? 0,
          simhash_chunks:   c.simhash_chunks   ?? 0,
          embedding_chunks: c.embedding_chunks ?? 0,
        });
      })
      .catch(() => {});
  }, []);

  // Preview số câu hỏi sẽ bị ẩn theo dataset + layer đang chọn
  useEffect(() => {
    if (!datasetId) { setAffectedQ(null); return; }
    const layers = [...excludeDedupLayers].join(",");
    fetch(`${API}/internal/datasets/${datasetId}/dedup-affected?layers=${encodeURIComponent(layers)}`)
      .then((r) => r.json())
      .then((d) => setAffectedQ(typeof d?.total === "number" ? d : null))
      .catch(() => setAffectedQ(null));
  }, [datasetId, excludeDedupLayers]);

  useEffect(() => {
    if (!datasetId) return;
    fetch(`${API}/internal/runs?dataset_id=${datasetId}`)
      .then((r) => r.json())
      .then((d: Run[]) => {
        setRuns(d);
        const active = d.find((r) => r.status === "running" || r.status === "queued");
        if (active) setActiveId(active.id);
      })
      .catch(() => {});
  }, [datasetId]);

  useEffect(() => {
    if (pollRef.current) clearInterval(pollRef.current);
    if (!activeId) { setProgress(null); return; }

    const poll = async () => {
      try {
        const r = await fetch(`${API}/internal/runs/${activeId}/progress`);
        const p: Progress = await r.json();
        setProgress(p);
        setRuns((prev) => prev.map((run) =>
          run.id === activeId
            ? { ...run, status: p.status, success: p.success, failed: p.failed, total: p.total }
            : run
        ));
        if (p.status !== "running" && p.status !== "queued") {
          if (pollRef.current) clearInterval(pollRef.current);
        }
      } catch {/* ignore */}
    };

    poll();
    pollRef.current = setInterval(poll, 3000);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [activeId]);

  async function startRun() {
    if (!datasetId || !runName.trim()) return;
    setCreating(true);
    try {
      const r = await fetch(`${API}/internal/runs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          dataset_id: datasetId,
          name: runName.trim(),
          config: excludeDedupLayers.size ? { exclude_dedup_layers: [...excludeDedupLayers] } : {},
        }),
      });
      const d: Run = await r.json();
      setRuns((prev) => [d, ...prev]);
      setActiveId(d.id);
      setRunName("");
      toast.success(`Đã tạo run "${d.name}" — bắt đầu chạy eval`);
    } finally {
      setCreating(false);
    }
  }

  async function pauseRun() {
    if (!activeId) return;
    await fetch(`${API}/internal/runs/${activeId}/pause`, { method: "POST" });
    setProgress((p) => p ? { ...p, status: "paused" } : p);
    setRuns((prev) => prev.map((r) => r.id === activeId ? { ...r, status: "paused" } : r));
  }

  async function resumeRun() {
    if (!activeId) return;
    await fetch(`${API}/internal/runs/${activeId}/resume`, { method: "POST" });
    setProgress((p) => p ? { ...p, status: "running" } : p);
    setRuns((prev) => prev.map((r) => r.id === activeId ? { ...r, status: "running" } : r));
    setActiveId((id) => id);
  }

  function startEdit(run: Run) {
    setEditingId(run.id);
    setEditingName(run.name);
  }

  async function saveRename(id: string) {
    if (!editingName.trim()) return;
    setRenaming(true);
    try {
      await fetch(`${API}/internal/runs/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: editingName.trim() }),
      });
      setRuns((prev) => prev.map((r) => r.id === id ? { ...r, name: editingName.trim() } : r));
      setEditingId(null);
    } finally {
      setRenaming(false);
    }
  }

  async function deleteRun(id: string) {
    setDeleting(true);
    try {
      await fetch(`${API}/internal/runs/${id}`, { method: "DELETE" });
      setRuns((prev) => prev.filter((r) => r.id !== id));
      if (activeId === id) { setActiveId(null); setProgress(null); }
      setConfirmDeleteId(null);
      toast.success("Đã xóa run");
    } finally {
      setDeleting(false);
    }
  }

  const activeRun = runs.find((r) => r.id === activeId);
  const confirmDeleteRun = runs.find((r) => r.id === confirmDeleteId);
  const pct = progress && progress.total > 0
    ? Math.round((progress.success / progress.total) * 100) : 0;
  const failPct = progress && progress.total > 0
    ? Math.round((progress.failed / progress.total) * 100) : 0;
  const ragasPct = progress && progress.success > 0
    ? Math.round((progress.ragas_done / progress.success) * 100) : 0;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-gray-900">Chạy Eval</h1>
        <p className="text-sm text-gray-500 mt-1">Tạo và theo dõi tiến trình đánh giá</p>
      </div>

      {/* Confirm delete dialog — spring vật lý khi mở/đóng */}
      <AnimatePresence>
      {confirmDeleteId && (
        <motion.div
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm">
          <motion.div
            initial={{ opacity: 0, scale: 0.92, y: 12 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: 6 }}
            transition={{ type: "spring", stiffness: 380, damping: 28 }}
            className="bg-white rounded-2xl border border-black/10 shadow-xl w-full max-w-sm mx-4 px-6 py-5 space-y-4">
            <div>
              <p className="text-base font-semibold text-gray-900">Xóa run?</p>
              <p className="text-sm text-gray-500 mt-1">
                Xóa <span className="font-medium text-gray-800">{confirmDeleteRun?.name}</span> sẽ xóa toàn bộ kết quả eval của run này. Không thể hoàn tác.
              </p>
            </div>
            <div className="flex gap-2 justify-end">
              <button onClick={() => setConfirmDeleteId(null)}
                className="px-4 py-1.5 text-sm rounded-lg border border-black/12 text-gray-500 hover:bg-gray-50">
                Huỷ
              </button>
              <button onClick={() => deleteRun(confirmDeleteId)} disabled={deleting}
                className="flex items-center gap-1.5 px-4 py-1.5 text-sm rounded-lg bg-red-600 text-white hover:bg-red-700 disabled:opacity-50 transition-all pressable">
                {deleting && <Loader2 size={13} className="animate-spin" />}
                Xóa
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
      </AnimatePresence>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Config panel */}
        <Spotlight className="bg-white rounded-2xl border border-black/8 p-6 space-y-5">
          <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wider">Cấu hình</h2>
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-gray-500">Dataset</label>
            <select value={datasetId} onChange={(e) => setDatasetId(e.target.value)}
              className="w-full text-sm border border-black/12 rounded-lg px-3 py-2 bg-white focus:outline-none focus:ring-2 focus:ring-emerald-500/40">
              {datasets.map((d) => (
                <option key={d.id} value={d.id}>{d.name}{d.is_benchmark ? " ★" : ""}</option>
              ))}
            </select>
          </div>
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-gray-500">Tên run</label>
            <input value={runName} onChange={(e) => setRunName(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") startRun(); }}
              placeholder="VD: Run tháng 6 v2"
              className="w-full text-sm border border-black/12 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-emerald-500/40"
            />
          </div>
          {/* Dedup filter */}
          <div className="space-y-2.5">
            <div className="flex items-center gap-2">
              <Layers size={13} className="text-gray-400 shrink-0" />
              <span className="text-xs font-medium text-gray-500">Loại bỏ chunk trùng khi retrieval</span>
            </div>
            <div className="grid grid-cols-3 gap-2">
              {DEDUP_LAYERS.map(({ key, label, field }) => {
                const count = dedupStats?.[field];
                const active = excludeDedupLayers.has(key);
                return (
                  <button
                    key={key}
                    type="button"
                    onClick={() => toggleDedupLayer(key)}
                    className={cn(
                      "relative rounded-xl border px-3 py-2.5 text-left transition-all pressable",
                      active
                        ? "border-emerald-600 bg-emerald-50 ring-1 ring-emerald-600/30 shadow-sm"
                        : "border-black/10 bg-white hover:border-black/20 hover:bg-gray-50"
                    )}
                  >
                    <span className={cn(
                      "absolute top-2 right-2 flex h-4 w-4 items-center justify-center rounded-full border text-[10px] transition-colors",
                      active ? "border-emerald-600 bg-emerald-600 text-white" : "border-gray-300 bg-white text-transparent"
                    )}>
                      ✓
                    </span>
                    <p className={cn("text-xs font-semibold", active ? "text-emerald-800" : "text-gray-700")}>{label}</p>
                    <p className={cn("text-[11px] mt-0.5 tabular-nums", active ? "text-emerald-700" : "text-gray-400")}>
                      {count != null ? <>−{count} chunk</> : "—"}
                    </p>
                  </button>
                );
              })}
            </div>
            {(() => {
              const total = dedupStats?.corpus_chunks ?? 0;
              const removed = DEDUP_LAYERS
                .filter((l) => excludeDedupLayers.has(l.key))
                .reduce((s, l) => s + (dedupStats?.[l.field] ?? 0), 0);
              const remaining = Math.max(total - removed, 0);
              const filtering = excludeDedupLayers.size > 0;
              return (
                <div className={cn(
                  "rounded-lg divide-y text-sm tabular-nums border",
                  filtering ? "bg-emerald-50 border-emerald-200 divide-emerald-200/70" : "bg-gray-50 border-black/6 divide-black/6"
                )}>
                  <div className="flex items-center justify-between px-3 py-2">
                    <span className="text-xs text-gray-500">Retrieval trên</span>
                    {dedupStats ? (
                      filtering ? (
                        <span className="text-gray-500">
                          <span className="line-through">{total}</span>
                          {" → "}
                          <span className="font-semibold text-emerald-700">{remaining}</span>
                          <span className="text-xs text-gray-500"> chunk (−{removed})</span>
                        </span>
                      ) : (
                        <span className="font-semibold text-gray-700">{total} <span className="font-normal text-xs text-gray-500">chunk (toàn bộ)</span></span>
                      )
                    ) : (
                      <span className="text-xs text-gray-400">chưa có dữ liệu dedup</span>
                    )}
                  </div>
                  {affectedQ && (
                    <div className="flex items-center justify-between px-3 py-2">
                      <span className="text-xs text-gray-500">Câu hỏi trong run</span>
                      {filtering && affectedQ.affected > 0 ? (
                        <span className="text-gray-500">
                          <span className="line-through">{affectedQ.total}</span>
                          {" → "}
                          <span className="font-semibold text-emerald-700">{affectedQ.remaining}</span>
                          <span className="text-xs text-gray-500"> câu (ẩn {affectedQ.affected} câu có ground-truth bị lọc)</span>
                        </span>
                      ) : (
                        <span className="font-semibold text-gray-700">{affectedQ.total} <span className="font-normal text-xs text-gray-500">câu</span></span>
                      )}
                    </div>
                  )}
                </div>
              );
            })()}
          </div>

          <button onClick={startRun} disabled={creating || !datasetId || !runName.trim()}
            className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-emerald-700 text-white text-sm font-medium hover:bg-emerald-800 hover:shadow-lg hover:shadow-emerald-700/25 disabled:opacity-40 transition-all pressable">
            {creating
              ? <><Loader2 size={15} className="animate-spin" /> Đang tạo...</>
              : <><Play size={15} /> Bắt đầu chạy eval</>}
          </button>
        </Spotlight>

        {/* Progress panel */}
        <Spotlight className="bg-white rounded-2xl border border-black/8 p-6 space-y-5">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wider">Tiến trình</h2>
            {activeId && (
              <button onClick={() => setActiveId((id) => id)}
                className="text-gray-400 hover:text-gray-600 transition-colors" title="Làm mới">
                <RefreshCw size={13} />
              </button>
            )}
          </div>

          {!activeId || !progress ? (
            <div className="py-10 text-center text-sm text-gray-400">
              {runs.find((r) => r.status === "running" || r.status === "queued")
                ? "Đang tải tiến trình..."
                : "Chưa có run nào đang chạy"}
            </div>
          ) : (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-gray-800 truncate">{activeRun?.name}</span>
                <span className={cn("text-xs font-medium px-2 py-0.5 rounded-full shrink-0", STATUS_CLS[progress.status] ?? STATUS_CLS.queued)}>
                  {STATUS_LABEL[progress.status] ?? progress.status}
                </span>
              </div>

              {/* Pipeline progress — sọc chạy khi đang hoạt động */}
              <div>
                <div className="flex justify-between text-xs text-gray-500 mb-1.5">
                  <span>Pipeline: {progress.success} / {progress.total}</span>
                  <span>{pct}%</span>
                </div>
                <div className="h-3 bg-gray-200 ring-1 ring-inset ring-black/5 rounded-full overflow-hidden flex shadow-inner">
                  <div className={cn("h-full bg-gradient-to-r from-emerald-500 to-emerald-400 transition-all duration-500",
                    progress.status === "running" && "progress-active")} style={{ width: `${pct}%` }} />
                  <div className="h-full bg-red-400 transition-all duration-500" style={{ width: `${failPct}%` }} />
                </div>
              </div>

              {/* RAGAS progress */}
              {progress.success > 0 && (
                <div>
                  <div className="flex justify-between text-xs text-gray-500 mb-1.5">
                    <span>RAGAS: {progress.ragas_done} / {progress.success}</span>
                    <span>{ragasPct}%</span>
                  </div>
                  <div className="h-3 bg-gray-200 ring-1 ring-inset ring-black/5 rounded-full overflow-hidden shadow-inner">
                    <div className={cn("h-full bg-gradient-to-r from-violet-500 to-violet-400 transition-all duration-500",
                      progress.status === "running" && ragasPct < 100 && "progress-active")} style={{ width: `${ragasPct}%` }} />
                  </div>
                </div>
              )}

              {/* Counts — số đếm chạy + nháy xanh khi polling cập nhật */}
              <div className="grid grid-cols-3 gap-3 text-center">
                <div className="bg-emerald-50 border border-emerald-100 rounded-lg px-3 py-2 card-lift">
                  <p className="text-lg font-semibold text-emerald-700 tabular-nums">
                    <CountUp value={progress.success} />
                  </p>
                  <p className="text-xs text-emerald-600">Thành công</p>
                </div>
                <div className="bg-red-50 border border-red-100 rounded-lg px-3 py-2 card-lift">
                  <p className="text-lg font-semibold text-red-600 tabular-nums">
                    <CountUp value={progress.failed} />
                  </p>
                  <p className="text-xs text-red-500">Lỗi</p>
                </div>
                <div className="bg-gray-50 border border-gray-100 rounded-lg px-3 py-2 card-lift">
                  <p className="text-lg font-semibold text-gray-600 tabular-nums">
                    <CountUp value={progress.not_started} />
                  </p>
                  <p className="text-xs text-gray-400">Còn lại</p>
                </div>
              </div>

              {/* Controls */}
              {(progress.status === "running" || progress.status === "queued") && (
                <button onClick={pauseRun}
                  className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg border border-amber-300 text-amber-700 text-sm hover:bg-amber-50 transition-colors">
                  <Pause size={14} /> Tạm dừng
                </button>
              )}
              {progress.status === "paused" && (
                <button onClick={resumeRun}
                  className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg border border-emerald-300 text-emerald-700 text-sm hover:bg-emerald-50 transition-colors">
                  <Play size={14} /> Tiếp tục
                </button>
              )}
            </div>
          )}
        </Spotlight>
      </div>

      {/* Run history */}
      <div className="bg-white rounded-2xl border border-black/8 overflow-hidden">
        <div className="px-5 py-4 border-b border-black/6">
          <h2 className="text-sm font-semibold text-gray-700">Lịch sử run</h2>
        </div>
        {runs.length === 0 ? (
          <div className="py-14 text-center text-sm text-gray-400">Chưa có run nào</div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-black/6 bg-gray-50/60 text-xs font-semibold uppercase tracking-wider text-gray-500">
                <th className="px-5 py-3 text-left">Tên run</th>
                <th className="px-3 py-3 text-center w-28">Trạng thái</th>
                <th className="px-3 py-3 text-right w-28">Tiến độ</th>
                <th className="px-3 py-3 text-right w-28">Lỗi</th>
                <th className="px-5 py-3 text-right w-40">Thời gian</th>
                <th className="px-3 py-3 w-32" />
              </tr>
            </thead>
            <tbody className="divide-y divide-black/5">
              {runs.map((run) => (
                <tr key={run.id}
                  className={cn("hover:bg-gray-50/50 transition-colors cursor-pointer", activeId === run.id && "bg-blue-50/40")}
                  onClick={() => { if (editingId !== run.id) setActiveId(run.id); }}>

                  {/* Name — inline edit */}
                  <td className="px-5 py-3 font-medium text-gray-800" onClick={(e) => e.stopPropagation()}>
                    {editingId === run.id ? (
                      <form onSubmit={(e) => { e.preventDefault(); saveRename(run.id); }}
                        className="flex items-center gap-1.5">
                        <input
                          autoFocus
                          value={editingName}
                          onChange={(e) => setEditingName(e.target.value)}
                          className="text-sm border border-emerald-300 rounded-lg px-2 py-1 w-48 focus:outline-none focus:ring-2 focus:ring-emerald-500/40"
                        />
                        <button type="submit" disabled={renaming}
                          className="text-xs px-2 py-1 rounded-lg bg-emerald-700 text-white hover:bg-emerald-800 disabled:opacity-50">
                          {renaming ? <Loader2 size={12} className="animate-spin" /> : "Lưu"}
                        </button>
                        <button type="button" onClick={() => setEditingId(null)}
                          className="text-gray-400 hover:text-gray-600 p-1">
                          <X size={13} />
                        </button>
                      </form>
                    ) : (
                      <div className="flex items-center gap-2 group/name">
                        <span>{run.name}</span>
                        <button
                          onClick={() => startEdit(run)}
                          className="opacity-0 group-hover/name:opacity-100 text-gray-400 hover:text-gray-600 transition-opacity p-0.5"
                          title="Đổi tên">
                          <Pencil size={12} />
                        </button>
                      </div>
                    )}
                  </td>

                  <td className="px-3 py-3 text-center">
                    <span className={cn("text-xs font-medium px-2 py-0.5 rounded-full", STATUS_CLS[run.status] ?? STATUS_CLS.queued)}>
                      {STATUS_LABEL[run.status] ?? run.status}
                    </span>
                  </td>
                  <td className="px-3 py-3 text-right text-gray-600 tabular-nums">{run.success} / {run.total}</td>
                  <td className="px-3 py-3 text-right tabular-nums">
                    <span className={cn(run.failed > 0 ? "text-red-600" : "text-gray-400")}>{run.failed}</span>
                  </td>
                  <td className="px-5 py-3 text-right text-xs text-gray-400">{fmtDate(run.created_at)}</td>

                  {/* Actions */}
                  <td className="px-3 py-3 text-right" onClick={(e) => e.stopPropagation()}>
                    <div className="flex items-center justify-end gap-2">
                      <a href="/internal/eval-results"
                        className="text-xs text-emerald-700 hover:underline whitespace-nowrap">
                        Xem kết quả →
                      </a>
                      <button
                        onClick={() => setConfirmDeleteId(run.id)}
                        className="p-1 text-gray-300 hover:text-red-500 transition-colors"
                        title="Xóa run">
                        <Trash2 size={13} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
