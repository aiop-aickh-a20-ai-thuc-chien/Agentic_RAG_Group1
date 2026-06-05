"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  Bot,
  CheckCircle2,
  Eye,
  Loader2,
  RefreshCw,
  Search,
  XCircle,
  Zap,
} from "lucide-react";
import { evalApi } from "@/lib/eval-review-api";
import type { EvalRowStatus, Row } from "@/lib/eval-review-types";
import { ChunkDrawer } from "@/components/eval-review/ChunkDrawer";
import { RunEvalModal } from "@/components/eval-review/RunEvalModal";
import { StatusBadge } from "@/components/eval-review/StatusBadge";
import { cn } from "@/lib/utils";

// ── Editable cell ─────────────────────────────────────────────────────────────

function EditableCell({
  value,
  onSave,
  multiline = false,
  placeholder = "—",
  mono = false,
  fullText = false,
}: {
  value: string | null;
  onSave: (v: string) => void;
  multiline?: boolean;
  placeholder?: string;
  mono?: boolean;
  fullText?: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value ?? "");

  const commit = () => {
    onSave(draft);
    setEditing(false);
  };

  if (editing) {
    const base =
      "w-full rounded border border-mint/60 bg-white text-sm focus:outline-none focus:ring-2 focus:ring-mint/40";
    if (multiline) {
      return (
        <textarea
          className={cn(base, "resize-none p-1.5")}
          rows={3}
          value={draft}
          autoFocus
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commit}
        />
      );
    }
    return (
      <input
        className={cn(base, "px-2 py-1", mono && "font-mono text-xs")}
        value={draft}
        autoFocus
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => e.key === "Enter" && commit()}
      />
    );
  }

  return (
    <span
      title={value ?? ""}
      className={cn(
        "block cursor-text rounded px-1 py-0.5 text-sm transition-colors hover:bg-mist/70",
        mono && "font-mono text-xs",
        !value && "italic text-ink/30",
      )}
      onClick={() => {
        setDraft(value ?? "");
        setEditing(true);
      }}
    >
      {value ? (
        <span className={fullText ? undefined : "line-clamp-2"}>{value}</span>
      ) : (
        placeholder
      )}
    </span>
  );
}

// ── Stat pill ─────────────────────────────────────────────────────────────────

function StatPill({
  label,
  count,
  color,
  active,
  onClick,
}: {
  label: string;
  count: number;
  color: "gray" | "mint" | "blue";
  active?: boolean;
  onClick?: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium transition",
        color === "gray" &&
          (active
            ? "border-ink/30 bg-ink text-white"
            : "border-line bg-white text-ink/60 hover:bg-paper"),
        color === "mint" &&
          (active
            ? "border-mint bg-mint text-white"
            : "border-mint/25 bg-mint/8 text-mint hover:bg-mint/15"),
        color === "blue" &&
          (active
            ? "border-blue-500 bg-blue-600 text-white"
            : "border-blue-200 bg-blue-50 text-blue-700 hover:bg-blue-100"),
      )}
    >
      <span
        className={cn(
          "h-1.5 w-1.5 rounded-full",
          active ? "bg-current opacity-70" : "",
          !active && color === "gray" && "bg-ink/30",
          !active && color === "mint" && "bg-mint",
          !active && color === "blue" && "bg-blue-500",
        )}
      />
      {label}
      <span className="opacity-70">{count}</span>
    </button>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

type Filter = "all" | "pending" | "approved" | "evaluated";

export default function EvalReviewPage() {
  const [rows, setRows] = useState<Row[]>([]);
  const [loading, setLoading] = useState(true);
  const [backendError, setBackendError] = useState(false);
  const [filter, setFilter] = useState<Filter>("all");
  const [search, setSearch] = useState("");
  const [selectedRow, setSelectedRow] = useState<Row | null>(null);
  const [showRunModal, setShowRunModal] = useState(false);
  const [savingCell, setSavingCell] = useState<string | null>(null);
  const [rowEvalStatus, setRowEvalStatus] = useState<Record<number, EvalRowStatus>>({});
  const pollRefs = useRef<Record<number, ReturnType<typeof setInterval>>>({});

  const fetchRows = useCallback(async () => {
    setLoading(true);
    setBackendError(false);
    try {
      setRows(await evalApi.getRows());
    } catch (e) {
      console.error(e);
      setBackendError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchRows();
  }, [fetchRows]);

  const filtered = rows.filter((r) => {
    if (filter !== "all" && r.display_status !== filter) return false;
    if (search && !r.question?.toLowerCase().includes(search.toLowerCase()))
      return false;
    return true;
  });

  const counts = {
    pending: rows.filter((r) => r.display_status === "pending").length,
    approved: rows.filter((r) => r.display_status === "approved").length,
    evaluated: rows.filter((r) => r.display_status === "evaluated").length,
  };
  const approvedPending = rows.filter(
    (r) => r.display_status === "approved",
  ).length;

  const patchRow = (updated: Row) =>
    setRows((prev) =>
      prev.map((r) => (r.excel_row === updated.excel_row ? updated : r)),
    );

  const handleReEval = async (row: Row) => {
    const id = row.excel_row;
    try {
      const res = await evalApi.reEval(id);
      patchRow(res);
      if (selectedRow?.excel_row === id) setSelectedRow(res);
      setRowEvalStatus((prev) => ({ ...prev, [id]: res._eval_status }));
      const interval = setInterval(async () => {
        try {
          const s = await evalApi.getRowEvalStatus(id);
          setRowEvalStatus((prev) => ({ ...prev, [id]: s }));
          if (s.status === "done" || s.status === "error") {
            clearInterval(pollRefs.current[id]);
            delete pollRefs.current[id];
            if (s.status === "done") fetchRows();
          }
        } catch { /* ignore */ }
      }, 2500);
      pollRefs.current[id] = interval;
    } catch (e) {
      setRowEvalStatus((prev) => ({
        ...prev,
        [id]: { status: "error", message: e instanceof Error ? e.message : String(e) },
      }));
    }
  };

  const handleApproveAndEval = async (row: Row) => {
    const id = row.excel_row;
    try {
      const res = await evalApi.approveAndEval(id);
      patchRow(res);
      if (selectedRow?.excel_row === id) setSelectedRow(res);
      setRowEvalStatus((prev) => ({ ...prev, [id]: res._eval_status }));

      // Poll until done or error
      const interval = setInterval(async () => {
        try {
          const s = await evalApi.getRowEvalStatus(id);
          setRowEvalStatus((prev) => ({ ...prev, [id]: s }));
          if (s.status === "done" || s.status === "error") {
            clearInterval(pollRefs.current[id]);
            delete pollRefs.current[id];
            if (s.status === "done") fetchRows();
          }
        } catch { /* ignore poll errors */ }
      }, 2500);
      pollRefs.current[id] = interval;
    } catch (e) {
      setRowEvalStatus((prev) => ({
        ...prev,
        [id]: { status: "error", message: e instanceof Error ? e.message : String(e) },
      }));
    }
  };

  const handleReject = async (row: Row) => {
    await evalApi.rejectRow(row.excel_row);
    if (selectedRow?.excel_row === row.excel_row) setSelectedRow(null);
    await fetchRows();
  };

  const handleCellSave = async (
    row: Row,
    field: keyof Row,
    value: string,
  ) => {
    const key = `${row.excel_row}-${field}`;
    setSavingCell(key);
    try {
      const updated = await evalApi.updateRow(row.excel_row, {
        [field]: value,
      } as Partial<Row>);
      patchRow(updated);
      if (selectedRow?.excel_row === row.excel_row) setSelectedRow(updated);
    } finally {
      setSavingCell(null);
    }
  };

  return (
    <div className="min-h-screen bg-paper">
      {/* ── Header ─────────────────────────────────────────────────────── */}
      <header className="sticky top-0 z-30 border-b border-line bg-white/92 backdrop-blur-xl">
        <div className="mx-auto flex max-w-screen-2xl items-center gap-4 px-6 py-3">
          <Link
            href="/"
            className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-md text-ink/40 transition hover:bg-paper hover:text-ink"
            title="Về trang chủ"
          >
            <ArrowLeft className="h-4 w-4" />
          </Link>

          <div className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-ink text-white shadow-sm">
              <Bot className="h-4 w-4" />
            </div>
            <div>
              <p className="text-sm font-semibold leading-none text-ink">
                Eval Review
              </p>
              <p className="mt-0.5 text-[11px] text-ink/45">
                Quản lý câu hỏi đánh giá
              </p>
            </div>
          </div>

          <div className="ml-5 flex items-center gap-1.5">
            <StatPill
              label="Tất cả"
              count={rows.length}
              color="gray"
              active={filter === "all"}
              onClick={() => setFilter("all")}
            />
            <StatPill
              label="Chưa duyệt"
              count={counts.pending}
              color="gray"
              active={filter === "pending"}
              onClick={() => setFilter("pending")}
            />
            <StatPill
              label="Đã duyệt"
              count={counts.approved}
              color="mint"
              active={filter === "approved"}
              onClick={() => setFilter("approved")}
            />
            <StatPill
              label="Đã đánh giá"
              count={counts.evaluated}
              color="blue"
              active={filter === "evaluated"}
              onClick={() => setFilter("evaluated")}
            />
          </div>

          <div className="ml-auto flex items-center gap-2">
            <button
              onClick={fetchRows}
              className="flex h-9 items-center gap-1.5 rounded-lg border border-line bg-white px-3 text-sm font-medium text-ink/65 transition hover:bg-paper active:scale-95"
            >
              <RefreshCw
                className={cn("h-3.5 w-3.5", loading && "animate-spin")}
              />
              Làm mới
            </button>
            <button
              disabled={approvedPending === 0}
              onClick={() => setShowRunModal(true)}
              className="flex h-9 items-center gap-2 rounded-lg bg-mint px-4 text-sm font-semibold text-white shadow-sm transition hover:bg-mint/90 active:scale-95 disabled:cursor-not-allowed disabled:opacity-40"
            >
              <Zap className="h-3.5 w-3.5" />
              Run Evaluate + RAGAS
              {approvedPending > 0 && (
                <span className="rounded-full bg-white/20 px-1.5 py-0.5 text-xs">
                  {approvedPending}
                </span>
              )}
            </button>
          </div>
        </div>
      </header>

      {/* ── Main ───────────────────────────────────────────────────────── */}
      <main className="mx-auto max-w-screen-2xl px-6 py-6">
        <div className="mb-4 flex items-center justify-end">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink/35" />
            <input
              className="h-9 w-72 rounded-lg border border-line bg-white pl-9 pr-3 text-sm placeholder:text-ink/35 focus:outline-none focus:ring-2 focus:ring-mint/40"
              placeholder="Tìm câu hỏi..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
        </div>

        <div className="mr-[468px]">
          <div className="overflow-hidden rounded-xl border border-line bg-white shadow-panel">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="border-b border-line bg-paper/70">
                  {[
                    ["#", "w-8 text-center"],
                    ["Câu hỏi", "min-w-[260px]"],
                    ["Expected Answer", "min-w-[200px]"],
                    ["Ground Truth IDs", "w-44"],
                    ["Trạng thái", "w-28"],
                    ["", "w-20 text-right"],
                  ].map(([label, cls]) => (
                    <th
                      key={label}
                      className={cn(
                        "px-4 py-2.5 text-left text-[11px] font-semibold uppercase tracking-wide text-ink/45",
                        cls,
                      )}
                    >
                      {label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {backendError ? (
                  <tr>
                    <td colSpan={6} className="py-20 text-center">
                      <p className="mb-1 text-sm font-medium text-danger">
                        Không kết nối được backend
                      </p>
                      <p className="mb-4 text-xs text-ink/45">
                        Kiểm tra server đang chạy trên port 8000
                      </p>
                      <button
                        onClick={fetchRows}
                        className="mx-auto flex h-8 items-center gap-2 rounded-lg border border-line bg-white px-3 text-xs font-medium text-ink/65 transition hover:bg-paper"
                      >
                        <RefreshCw className="h-3.5 w-3.5" />
                        Thử lại
                      </button>
                    </td>
                  </tr>
                ) : loading && rows.length === 0 ? (
                  <tr>
                    <td
                      colSpan={6}
                      className="py-20 text-center text-sm text-ink/40"
                    >
                      <RefreshCw className="mx-auto mb-2 h-5 w-5 animate-spin text-mint/60" />
                      Đang tải dữ liệu...
                    </td>
                  </tr>
                ) : filtered.length === 0 ? (
                  <tr>
                    <td
                      colSpan={6}
                      className="py-20 text-center text-sm text-ink/40"
                    >
                      Không có câu hỏi nào khớp
                    </td>
                  </tr>
                ) : (
                  filtered.map((row, idx) => {
                    const isSelected =
                      selectedRow?.excel_row === row.excel_row;
                    return (
                      <tr
                        key={row.excel_row}
                        className={cn(
                          "group border-b border-line/50 transition-colors last:border-0",
                          isSelected
                            ? "bg-mint/6 ring-1 ring-inset ring-mint/20"
                            : row.display_status === "approved"
                              ? "bg-mint/3 hover:bg-mint/6"
                              : "bg-white hover:bg-paper/70",
                        )}
                      >
                        <td className="px-4 py-3 text-center text-xs text-ink/35">
                          {idx + 1}
                        </td>
                        <td className="px-4 py-3">
                          <EditableCell
                            value={row.question}
                            multiline
                            fullText
                            placeholder="Nhập câu hỏi..."
                            onSave={(v) => handleCellSave(row, "question", v)}
                          />
                        </td>
                        <td className="px-4 py-3">
                          <EditableCell
                            value={row.expected_answer}
                            multiline
                            fullText
                            placeholder="Nhập expected answer..."
                            onSave={(v) =>
                              handleCellSave(row, "expected_answer", v)
                            }
                          />
                        </td>
                        <td className="px-4 py-3">
                          <EditableCell
                            value={row.ground_truth_chunk_ids}
                            mono
                            placeholder="chunk_id, ..."
                            onSave={(v) =>
                              handleCellSave(row, "ground_truth_chunk_ids", v)
                            }
                          />
                        </td>
                        <td className="px-4 py-3">
                          <StatusBadge status={row.display_status} />
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex items-center justify-end gap-0.5">
                            {row.display_status === "pending" && (() => {
                              const es = rowEvalStatus[row.excel_row];
                              const busy = es?.status === "queued" || es?.status === "running";
                              return (
                                <ActionBtn
                                  title={es?.message ?? "Approve & Evaluate"}
                                  onClick={() => { if (!busy) handleApproveAndEval(row); }}
                                  className={busy ? "cursor-not-allowed text-mint/40" : "text-mint hover:bg-mint/10"}
                                >
                                  {busy
                                    ? <Loader2 className="h-4 w-4 animate-spin" />
                                    : <CheckCircle2 className="h-4 w-4" />}
                                </ActionBtn>
                              );
                            })()}
                            <ActionBtn
                              title="Xem chunks"
                              onClick={() => setSelectedRow(row)}
                              className={cn(
                                isSelected
                                  ? "bg-mint/15 text-mint"
                                  : "text-ink/40 hover:bg-paper hover:text-ink/70",
                              )}
                            >
                              <Eye className="h-4 w-4" />
                            </ActionBtn>
                            {row.display_status === "evaluated" && (() => {
                              const es = rowEvalStatus[row.excel_row];
                              const busy = es?.status === "queued" || es?.status === "running";
                              return (
                                <ActionBtn
                                  title={busy ? (es?.message ?? "Đang xử lý...") : "Đánh giá lại"}
                                  onClick={() => { if (!busy) handleReEval(row); }}
                                  className={busy ? "cursor-not-allowed text-ink/30" : "text-ink/40 hover:bg-paper hover:text-mint"}
                                >
                                  {busy
                                    ? <Loader2 className="h-4 w-4 animate-spin" />
                                    : <RefreshCw className="h-4 w-4" />}
                                </ActionBtn>
                              );
                            })()}
                            {row.display_status !== "evaluated" && (
                              <ActionBtn
                                title="Reject"
                                onClick={() => handleReject(row)}
                                className="text-ink/30 hover:bg-danger/8 hover:text-danger"
                              >
                                <XCircle className="h-4 w-4" />
                              </ActionBtn>
                            )}
                          </div>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>

          {!loading && rows.length > 0 && (
            <p className="mt-2.5 text-right text-xs text-ink/35">
              {filtered.length} / {rows.length} câu hỏi
              {savingCell && (
                <span className="ml-3 text-mint">Đang lưu...</span>
              )}
            </p>
          )}
        </div>
      </main>

      <ChunkDrawer
        row={selectedRow}
        onSaveGroundTruth={(ids) =>
          selectedRow
            ? handleCellSave(selectedRow, "ground_truth_chunk_ids", ids)
            : Promise.resolve()
        }
      />

      {showRunModal && (
        <RunEvalModal
          approvedCount={approvedPending}
          onClose={() => {
            setShowRunModal(false);
            fetchRows();
          }}
        />
      )}
    </div>
  );
}

function ActionBtn({
  children,
  title,
  onClick,
  className,
}: {
  children: React.ReactNode;
  title: string;
  onClick: () => void;
  className?: string;
}) {
  return (
    <button
      title={title}
      onClick={onClick}
      className={cn(
        "flex h-7 w-7 items-center justify-center rounded-md transition active:scale-90",
        className,
      )}
    >
      {children}
    </button>
  );
}
