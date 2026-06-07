"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  Bot,
  CheckCircle2,
  Eye,
  Loader2,
  RefreshCw,
  Search,
  Undo2,
  X,
  XCircle,
} from "lucide-react";
import { evalApi } from "@/lib/eval-review-api";
import type { EvalRowStatus, RejectedRow, Row } from "@/lib/eval-review-types";
import { ChunkDrawer } from "@/components/eval-review/ChunkDrawer";
import { StatusBadge } from "@/components/eval-review/StatusBadge";
import { cn } from "@/lib/utils";

// ── Editable cell ─────────────────────────────────────────────────────────────

function EditableCell({
  value,
  onSave,
  multiline = false,
  placeholder = "-",
  mono = false,
}: {
  value: string | null;
  onSave: (v: string) => void;
  multiline?: boolean;
  placeholder?: string;
  mono?: boolean;
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
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              commit();
            }
          }}
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
        <span className="whitespace-pre-wrap break-words">{value}</span>
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
  color: "gray" | "mint" | "blue" | "red";
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
        color === "red" &&
          (active
            ? "border-danger bg-danger text-white"
            : "border-danger/20 bg-danger/5 text-danger/70 hover:bg-danger/10"),
      )}
    >
      <span
        className={cn(
          "h-1.5 w-1.5 rounded-full",
          active ? "bg-current opacity-70" : "",
          !active && color === "gray" && "bg-ink/30",
          !active && color === "mint" && "bg-mint",
          !active && color === "blue" && "bg-blue-500",
          !active && color === "red" && "bg-danger",
        )}
      />
      {label}
      <span className="opacity-70">{count}</span>
    </button>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

type Filter = "all" | "pending" | "approved" | "evaluated" | "deleted";

function parseQuestionId(value: string | null | undefined): number | null {
  if (!value) return null;
  const match = value.trim().match(/\d+/);
  if (!match) return null;
  const parsed = Number.parseInt(match[0], 10);
  return Number.isFinite(parsed) ? parsed : null;
}

export default function EvalReviewPage() {
  const [rows, setRows] = useState<Row[]>([]);
  const [rejectedRows, setRejectedRows] = useState<RejectedRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [backendError, setBackendError] = useState(false);
  const [filter, setFilter] = useState<Filter>("all");
  const [search, setSearch] = useState("");
  const [startId, setStartId] = useState("");
  const [endId, setEndId] = useState("");
  const [selectedRow, setSelectedRow] = useState<Row | null>(null);
  const [savingCell, setSavingCell] = useState<string | null>(null);
  const [rowEvalStatus, setRowEvalStatus] = useState<Record<number, EvalRowStatus>>({});
  const sharedPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const pendingRowsRef = useRef<Set<number>>(new Set());

  const fetchRowsRef = useRef<(() => Promise<void>) | null>(null);

  const fetchRows = useCallback(async () => {
    setLoading(true);
    setBackendError(false);
    try {
      const [activeRows, deletedRows] = await Promise.all([
        evalApi.getRows(true),
        evalApi.getRejectedRows(),
      ]);
      setRows(activeRows);
      setRejectedRows(deletedRows);
    } catch (e) {
      console.error(e);
      setBackendError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchRowsRef.current = fetchRows;
  }, [fetchRows]);

  useEffect(() => {
    fetchRows();
  }, [fetchRows]);

  const startSharedPoll = useCallback((excelRow: number) => {
    pendingRowsRef.current.add(excelRow);
    if (sharedPollRef.current) return;
    sharedPollRef.current = setInterval(async () => {
      if (pendingRowsRef.current.size === 0) {
        clearInterval(sharedPollRef.current!);
        sharedPollRef.current = null;
        return;
      }
      try {
        const allStatus = await evalApi.getActiveEvalStatus();
        setRowEvalStatus((prev) => {
          const next = { ...prev };
          for (const [rowStr, status] of Object.entries(allStatus)) {
            next[Number(rowStr)] = status;
          }
          return next;
        });
        const done: number[] = [];
        for (const row of pendingRowsRef.current) {
          const s = allStatus[String(row)];
          if (!s || s.status === "done" || s.status === "error") {
            done.push(row);
            if (s?.status === "done") fetchRowsRef.current?.();
          }
        }
        done.forEach((r) => pendingRowsRef.current.delete(r));
      } catch { /* ignore */ }
    }, 4000);
  }, []);

  useEffect(() => {
    return () => {
      if (sharedPollRef.current) clearInterval(sharedPollRef.current);
    };
  }, []);

  const applySearchAndRange = useCallback(
    <T extends Pick<Row, "id" | "question">>(sourceRows: T[]) => {
      const q = search.toLowerCase();
      const parsedStart = parseQuestionId(startId);
      const parsedEnd = parseQuestionId(endId);
      const lower =
        parsedStart !== null && parsedEnd !== null
          ? Math.min(parsedStart, parsedEnd)
          : parsedStart;
      const upper =
        parsedStart !== null && parsedEnd !== null
          ? Math.max(parsedStart, parsedEnd)
          : parsedEnd;

      return sourceRows.filter((r) => {
        const rowId = parseQuestionId(r.id);
        if (lower !== null && (rowId === null || rowId < lower)) return false;
        if (upper !== null && (rowId === null || rowId > upper)) return false;
        if (
          q &&
          !r.question?.toLowerCase().includes(q) &&
          !r.id?.toLowerCase().includes(q)
        ) {
          return false;
        }
        return true;
      });
    },
    [search, startId, endId],
  );

  const filtered = useMemo(() => {
    if (filter === "deleted") return applySearchAndRange(rejectedRows);
    return applySearchAndRange(
      rows.filter((r) => filter === "all" || r.display_status === filter),
    );
  }, [applySearchAndRange, rows, rejectedRows, filter]);

  const counts = useMemo(() => {
    let pending = 0;
    let approved = 0;
    let evaluated = 0;
    for (const r of rows) {
      if (r.display_status === "pending") pending++;
      else if (r.display_status === "approved") approved++;
      else if (r.display_status === "evaluated") evaluated++;
    }
    return { pending, approved, evaluated };
  }, [rows]);

  const isDeletedView = filter === "deleted";

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
      startSharedPoll(id);
    } catch (e) {
      setRowEvalStatus((prev) => ({
        ...prev,
        [id]: { status: "error", message: e instanceof Error ? e.message : String(e) },
      }));
    }
  };

  const handleApproveAndEval = async (row: Row) => {
    const id = row.excel_row;
    const approvedRow: Row = {
      ...row,
      review_status: "approved",
      display_status: row.bot_response ? "evaluated" : "approved",
    };
    patchRow(approvedRow);
    if (selectedRow?.excel_row === id) setSelectedRow(approvedRow);
    setRowEvalStatus((prev) => ({
      ...prev,
      [id]: { status: "queued", message: "Đã duyệt, đang chờ đánh giá" },
    }));
    try {
      const res = await evalApi.approveAndEval(id);
      patchRow(res);
      if (selectedRow?.excel_row === id) setSelectedRow(res);
      setRowEvalStatus((prev) => ({ ...prev, [id]: res._eval_status }));
      startSharedPoll(id);
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

  const handleRestoreRejected = async (row: RejectedRow) => {
    await evalApi.restoreRejectedRow(row.reject_row);
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
    <div className="min-h-[100dvh] bg-paper text-ink">
      {/* ── Header ─────────────────────────────────────────────────────── */}
      <header className="sticky top-0 z-30 border-b border-line bg-white/94 backdrop-blur-xl">
        <div className="mx-auto flex max-w-screen-2xl flex-wrap items-center gap-3 px-4 py-3 sm:px-6">
          <Link
            href="/"
            className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg text-ink/45 transition hover:bg-paper hover:text-ink"
            title="Về trang chủ"
          >
            <ArrowLeft className="h-4 w-4" />
          </Link>

          <div className="flex items-center gap-2.5">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-ink text-white shadow-sm">
              <Bot className="h-4 w-4" />
            </div>
            <div>
              <p className="text-base font-semibold leading-none text-ink">
                Eval Review
              </p>
              <p className="mt-1 text-xs text-ink/45">
                Quản lý câu hỏi đánh giá
              </p>
            </div>
          </div>

          <div className="ml-auto flex flex-wrap items-center gap-2">
            <button
              onClick={fetchRows}
              className="flex h-9 items-center gap-1.5 rounded-lg border border-line bg-white px-3 text-sm font-medium text-ink/65 transition hover:bg-paper active:translate-y-px"
            >
              <RefreshCw
                className={cn("h-3.5 w-3.5", loading && "animate-spin")}
              />
              Làm mới
            </button>
          </div>
        </div>
      </header>

      {/* ── Main ───────────────────────────────────────────────────────── */}
      <main className="mx-auto max-w-screen-2xl px-4 py-5 sm:px-6">
        <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_440px]">
          <section className="min-w-0">
            <div className="mb-3 rounded-xl border border-line bg-white/86 px-3 py-3 shadow-sm">
              <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                <div className="flex flex-wrap items-center gap-2">
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
                  <StatPill
                    label="Đã xóa"
                    count={rejectedRows.length}
                    color="red"
                    active={filter === "deleted"}
                    onClick={() => setFilter("deleted")}
                  />
                </div>

                <div className="flex w-full flex-col gap-2 lg:w-auto lg:flex-row lg:items-center">
                  <div className="grid grid-cols-2 gap-2 lg:w-[220px]">
                    <input
                      className="h-10 min-w-0 rounded-lg border border-line bg-white px-3 text-sm placeholder:text-ink/35 focus:outline-none focus:ring-2 focus:ring-mint/40"
                      inputMode="numeric"
                      placeholder="Từ ID"
                      value={startId}
                      onChange={(e) => setStartId(e.target.value)}
                    />
                    <input
                      className="h-10 min-w-0 rounded-lg border border-line bg-white px-3 text-sm placeholder:text-ink/35 focus:outline-none focus:ring-2 focus:ring-mint/40"
                      inputMode="numeric"
                      placeholder="Đến ID"
                      value={endId}
                      onChange={(e) => setEndId(e.target.value)}
                    />
                  </div>

                  <div className="relative w-full lg:w-80">
                    <Search className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink/35" />
                    <input
                      className="h-10 w-full rounded-lg border border-line bg-white pl-9 pr-9 text-sm placeholder:text-ink/35 focus:outline-none focus:ring-2 focus:ring-mint/40"
                      placeholder="Tìm câu hỏi hoặc ID..."
                      value={search}
                      onChange={(e) => setSearch(e.target.value)}
                    />
                    {(search || startId || endId) && (
                      <button
                        title="Xóa bộ lọc"
                        onClick={() => {
                          setSearch("");
                          setStartId("");
                          setEndId("");
                        }}
                        className="absolute right-2 top-1/2 flex h-6 w-6 -translate-y-1/2 items-center justify-center rounded-md text-ink/35 transition hover:bg-paper hover:text-ink/70"
                      >
                        <X className="h-3.5 w-3.5" />
                      </button>
                    )}
                  </div>
                </div>
              </div>

              {!loading && rows.length > 0 && (
                <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-line/70 pt-3 text-xs text-ink/45">
                  <span>
                    Đang hiển thị{" "}
                    <strong className="font-semibold text-ink/70">
                      {filtered.length}
                    </strong>{" "}
                    / {isDeletedView ? rejectedRows.length : rows.length} câu hỏi
                  </span>
                  {savingCell && (
                    <span className="font-medium text-mint">Đang lưu...</span>
                  )}
                </div>
              )}
            </div>

            <div className="overflow-hidden rounded-xl border border-line bg-white shadow-panel">
              <div className="max-h-[calc(100dvh-178px)] overflow-auto">
                <table className="min-w-[920px] w-full border-collapse text-[13px]">
                  <thead className="sticky top-0 z-10">
                    <tr className="border-b border-line bg-paper/95 backdrop-blur">
                  {[
                    ["ID", "w-14 text-center"],
                    ["", "w-14 text-center"],
                    ["Câu hỏi", "w-[29%] min-w-[210px]"],
                    ["Expected Answer", "w-[23%] min-w-[180px]"],
                    ["Ground Truth IDs", "w-[164px]"],
                    ["Trạng thái", "w-[104px] min-w-[104px]"],
                    ["", "sticky right-0 z-20 w-[78px] min-w-[78px] bg-paper text-right shadow-[-12px_0_18px_-20px_rgba(17,24,39,0.45)]"],
                  ].map(([label, cls], headerIndex) => (
                    <th
                      key={`${headerIndex}-${label}`}
                      className={cn(
                        "px-3 py-3 text-left text-[10px] font-semibold uppercase tracking-wide text-ink/45",
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
                    <td colSpan={7} className="py-20 text-center">
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
                      colSpan={7}
                      className="py-20 text-center text-sm text-ink/40"
                    >
                      <RefreshCw className="mx-auto mb-2 h-5 w-5 animate-spin text-mint/60" />
                      Đang tải dữ liệu...
                    </td>
                  </tr>
                ) : filtered.length === 0 ? (
                  <tr>
                    <td
                      colSpan={7}
                      className="py-20 text-center text-sm text-ink/40"
                    >
                      Không có câu hỏi nào khớp
                    </td>
                  </tr>
                ) : (
                  filtered.map((row, idx) => {
                    const deletedRow = isDeletedView ? (row as RejectedRow) : null;
                    const activeRow = isDeletedView ? null : (row as Row);
                    const evalStatus = activeRow ? rowEvalStatus[activeRow.excel_row] : undefined;
                    const evalBusy =
                      evalStatus?.status === "queued" || evalStatus?.status === "running";
                    const isSelected =
                      activeRow !== null && selectedRow?.excel_row === activeRow.excel_row;
                    return (
                      <tr
                        key={isDeletedView ? `deleted-${deletedRow?.reject_row}` : row.excel_row}
                        className={cn(
                          "group border-b border-line/60 transition-colors last:border-0",
                          isSelected
                            ? "bg-mint/8 ring-1 ring-inset ring-mint/25"
                            : activeRow?.display_status === "approved"
                              ? "bg-mint/3 hover:bg-mint/7"
                              : "bg-white hover:bg-paper/65",
                        )}
                      >
                        <td className="px-3 py-4 text-center text-xs font-semibold text-ink/45">
                          {row.id ?? idx + 1}
                        </td>
                        <td className="px-2 py-4 text-center align-top">
                          {!isDeletedView && (
                            <ActionBtn
                              title="Xem chunks"
                              onClick={() => activeRow && setSelectedRow(activeRow)}
                              className={cn(
                                isSelected
                                  ? "border-mint/30 bg-mint/14 text-mint"
                                  : "border-line bg-white text-ink/55 hover:border-line hover:bg-paper hover:text-ink/80",
                              )}
                            >
                              <Eye className="h-4 w-4" />
                            </ActionBtn>
                          )}
                        </td>
                        <td className="px-3 py-4 align-top">
                          {isDeletedView ? (
                            <span className="block whitespace-pre-wrap break-words px-1 py-0.5 text-sm">
                              {row.question}
                            </span>
                          ) : (
                            <EditableCell
                              value={row.question}
                              multiline
                              placeholder="Nhập câu hỏi..."
                              onSave={(v) => activeRow && handleCellSave(activeRow, "question", v)}
                            />
                          )}
                        </td>
                        <td className="px-3 py-4 align-top">
                          {isDeletedView ? (
                            <span className="block whitespace-pre-wrap break-words px-1 py-0.5 text-sm">
                              {row.expected_answer}
                            </span>
                          ) : (
                            <EditableCell
                              value={row.expected_answer}
                              multiline
                              placeholder="Nhập expected answer..."
                              onSave={(v) =>
                                activeRow && handleCellSave(activeRow, "expected_answer", v)
                              }
                            />
                          )}
                        </td>
                        <td className="px-3 py-4 align-top">
                          {isDeletedView ? (
                            <span className="block whitespace-pre-wrap break-words px-1 py-0.5 font-mono text-xs">
                              {row.ground_truth_chunk_ids}
                            </span>
                          ) : (
                            <EditableCell
                              value={row.ground_truth_chunk_ids}
                              mono
                              placeholder="chunk_id, ..."
                              onSave={(v) =>
                                activeRow && handleCellSave(activeRow, "ground_truth_chunk_ids", v)
                              }
                            />
                          )}
                        </td>
                        <td className="px-2 py-4 align-top">
                          {isDeletedView ? (
                            <span className="inline-flex items-center gap-1 rounded-full border border-danger/20 bg-danger/5 px-1.5 py-0.5 text-[10px] font-medium leading-4 text-danger/70 whitespace-nowrap">
                              <span className="h-1 w-1 flex-shrink-0 rounded-full bg-danger" />
                              Đã xóa
                            </span>
                          ) : evalStatus?.status === "error" ? (
                            <span className="inline-flex items-center gap-1 rounded-full border border-danger/20 bg-danger/5 px-1.5 py-0.5 text-[10px] font-medium leading-4 text-danger/70 whitespace-nowrap">
                              <span className="h-1 w-1 flex-shrink-0 rounded-full bg-danger" />
                              Lỗi
                            </span>
                          ) : (
                            <StatusBadge status={activeRow?.display_status ?? "pending"} />
                          )}
                        </td>
                        <td className="sticky right-0 z-[5] bg-white px-2 py-4 align-top shadow-[-12px_0_18px_-20px_rgba(17,24,39,0.45)]">
                          <div className="flex items-center justify-end gap-1">
                            {isDeletedView && deletedRow && (
                              <ActionBtn
                                title="Hoàn lại"
                                onClick={() => handleRestoreRejected(deletedRow)}
                                className="border-blue-200 bg-blue-50 text-blue-700 hover:border-blue-300 hover:bg-blue-100"
                              >
                                <Undo2 className="h-4 w-4" />
                              </ActionBtn>
                            )}
                            {activeRow?.display_status === "pending" && (() => {
                              return (
                                <ActionBtn
                                  title={evalStatus?.message ?? "Duyệt và đưa vào queue đánh giá"}
                                  onClick={() => { if (!evalBusy) handleApproveAndEval(activeRow); }}
                                  className={evalBusy ? "cursor-not-allowed border-mint/20 bg-mint/6 text-mint/45" : "border-mint/25 bg-mint/8 text-mint hover:border-mint/45 hover:bg-mint/14"}
                                >
                                  {evalBusy
                                    ? <Loader2 className="h-4 w-4 animate-spin" />
                                    : <CheckCircle2 className="h-4 w-4" />}
                                </ActionBtn>
                              );
                            })()}
                            {activeRow?.display_status === "approved" && evalBusy && (
                              <ActionBtn
                                title={evalStatus?.message ?? "Đang chờ/chạy đánh giá"}
                                onClick={() => undefined}
                                className="cursor-not-allowed border-mint/20 bg-mint/6 text-mint/45"
                              >
                                <Loader2 className="h-4 w-4 animate-spin" />
                              </ActionBtn>
                            )}
                            {activeRow?.display_status === "evaluated" && (() => {
                              return (
                                <ActionBtn
                                  title={evalBusy ? (evalStatus?.message ?? "Đang xử lý...") : "Đánh giá lại"}
                                  onClick={() => { if (!evalBusy) handleReEval(activeRow); }}
                                  className={evalBusy ? "cursor-not-allowed border-line bg-paper text-ink/30" : "border-line bg-white text-ink/55 hover:border-mint/35 hover:bg-mint/8 hover:text-mint"}
                                >
                                  {evalBusy
                                    ? <Loader2 className="h-4 w-4 animate-spin" />
                                    : <RefreshCw className="h-4 w-4" />}
                                </ActionBtn>
                              );
                            })()}
                            {activeRow !== null && activeRow.display_status !== "evaluated" && !evalBusy && (
                              <ActionBtn
                                title="Reject"
                                onClick={() => handleReject(activeRow)}
                                className="border-danger/20 bg-danger/5 text-danger/70 hover:border-danger/35 hover:bg-danger/10 hover:text-danger"
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
            </div>
          </section>

          <ChunkDrawer
            row={selectedRow}
            onSaveGroundTruth={(ids) =>
              selectedRow
                ? handleCellSave(selectedRow, "ground_truth_chunk_ids", ids)
                : Promise.resolve()
            }
          />
        </div>
      </main>
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
        "flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-md border transition active:translate-y-px",
        className,
      )}
    >
      {children}
    </button>
  );
}
