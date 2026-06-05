"use client";

import { useEffect, useRef, useState } from "react";
import { AlertCircle, BookOpen, Copy, ExternalLink, Loader2, RefreshCw } from "lucide-react";
import { evalApi } from "@/lib/eval-review-api";
import type { Chunk, Row } from "@/lib/eval-review-types";
import { cn } from "@/lib/utils";

interface Props {
  row: Row | null;
  onSaveGroundTruth: (ids: string) => void;
}

// ── Sort chunks by document order (section + _c001 index) ────────────────────

function sortByDocOrder(chunks: Chunk[]): Chunk[] {
  return [...chunks].sort((a, b) => {
    const srcA = a.chunk_id.split("_").slice(0, 2).join("_");
    const srcB = b.chunk_id.split("_").slice(0, 2).join("_");
    if (srcA !== srcB) return srcA.localeCompare(srcB);
    const num = (id: string) => { const m = id.match(/_c(\d+)$/); return m ? parseInt(m[1], 10) : 0; };
    return num(a.chunk_id) - num(b.chunk_id);
  });
}

// ── Inline doc view (full doc, GT chunks highlighted) ────────────────────────

function DocView({
  chunks,
  highlightIds,
  notFoundIds,
}: {
  chunks: Chunk[];
  highlightIds: Set<string>;
  notFoundIds: string[];
}) {
  const sorted = sortByDocOrder(chunks);

  return (
    <div className="space-y-0">
      {notFoundIds.length > 0 && (
        <div className="mb-3 flex items-start gap-2 rounded-lg border border-danger/25 bg-danger/6 px-3 py-2">
          <AlertCircle className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 text-danger" />
          <div>
            <p className="text-xs font-medium text-danger">Không tìm thấy trong store</p>
            {notFoundIds.map((id) => (
              <code key={id} className="mt-0.5 block font-mono text-[10px] text-danger/70 break-all">
                {id}
              </code>
            ))}
          </div>
        </div>
      )}

      {sorted.map((chunk, idx) => {
        const isHighlight = highlightIds.has(chunk.chunk_id);
        const prevSection = idx > 0 ? sorted[idx - 1].section : null;
        const showSection = chunk.section && chunk.section !== prevSection;

        return (
          <div key={chunk.chunk_id}>
            {showSection && (
              <div className="mb-2 mt-5 flex items-center gap-2 first:mt-0">
                <span className="text-[10px] font-semibold uppercase tracking-widest text-ink/35">
                  {chunk.section}
                </span>
                <div className="flex-1 border-t border-line/60" />
              </div>
            )}

            <div
              data-highlight={isHighlight ? "true" : undefined}
              className={cn(
                "rounded-lg px-3 py-2.5 transition-colors",
                isHighlight
                  ? "my-1 border-l-[3px] border-mint bg-mint/8"
                  : "text-ink/60",
              )}
            >
              <div className="mb-1 flex items-center gap-1.5">
                <code className={cn("font-mono text-[10px]", isHighlight ? "text-mint" : "text-ink/30")}>
                  {chunk.chunk_id}
                </code>
                {isHighlight && (
                  <span className="rounded-full bg-mint/15 px-1.5 py-0.5 text-[10px] font-semibold text-mint">
                    ← ground truth
                  </span>
                )}
              </div>
              <p className={cn(
                "whitespace-pre-wrap text-xs leading-relaxed",
                isHighlight ? "font-semibold text-ink" : "text-ink/60",
              )}>
                {chunk.text}
              </p>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ── Main drawer ───────────────────────────────────────────────────────────────

export function ChunkDrawer({ row, onSaveGroundTruth }: Props) {
  // ── Chunk-list mode state ──
  const [chunks, setChunks] = useState<Chunk[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [copied, setCopied] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  // ── Doc-view mode state ──
  const [docChunks, setDocChunks] = useState<Chunk[]>([]);
  const [notFoundIds, setNotFoundIds] = useState<string[]>([]);

  // ── Shared state ──
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const bodyRef = useRef<HTMLDivElement>(null);

  // Scroll to first highlighted chunk after doc-view loads
  useEffect(() => {
    if (docChunks.length === 0 || loading) return;
    const el = bodyRef.current?.querySelector<HTMLElement>("[data-highlight]");
    if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [docChunks, loading]);

  const gtIds: string[] = (row?.ground_truth_chunk_ids ?? "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  const hasGt = gtIds.length > 0;
  const mode: "doc" | "chunks" = hasGt ? "doc" : "chunks";

  // Sync selected checkboxes
  useEffect(() => {
    if (!row) return;
    setSelected(new Set(gtIds));
    setSaved(false);
  }, [row?.ground_truth_chunk_ids]);

  // Auto-load on row change
  useEffect(() => {
    if (!row) {
      setChunks([]);
      setDocChunks([]);
      setError(null);
      return;
    }

    setError(null);

    if (hasGt) {
      // Doc-view: load full document for each unique doc in GT IDs
      loadDocView(gtIds);
    } else {
      // Chunk-list: load from rag_context or fetch
      loadChunkList(row);
    }
  }, [row?.excel_row, row?.ground_truth_chunk_ids]);

  const loadDocView = async (ids: string[]) => {
    setLoading(true);
    setDocChunks([]);
    setNotFoundIds([]);
    try {
      // Group by unique document (first 2 parts of chunk_id)
      const docMap = new Map<string, string>(); // docPrefix → representativeChunkId
      for (const id of ids) {
        const parts = id.split("_");
        if (parts.length >= 2) {
          const prefix = `${parts[0]}_${parts[1]}`;
          if (!docMap.has(prefix)) docMap.set(prefix, id);
        }
      }

      const allChunks: Chunk[] = [];
      const missing: string[] = [];

      for (const chunkId of docMap.values()) {
        const res = await evalApi.getDocChunks(chunkId);
        if (res.found) {
          allChunks.push(...res.chunks);
        } else {
          // All IDs from this doc are not found
          const prefix = `${chunkId.split("_")[0]}_${chunkId.split("_")[1]}`;
          const missingFromDoc = ids.filter((id) => id.startsWith(prefix));
          missing.push(...missingFromDoc);
        }
      }

      setDocChunks(allChunks);
      setNotFoundIds(missing);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Không thể tải tài liệu");
    } finally {
      setLoading(false);
    }
  };

  const loadChunkList = async (r: Row) => {
    if (r.rag_context) {
      try {
        const parsed = JSON.parse(r.rag_context) as Array<{
          id: string; text: string; score: number; retriever?: string;
        }>;
        if (parsed.length > 0) {
          setChunks(parsed.map((c) => ({
            chunk_id: c.id, text: c.text, score: c.score,
            retriever: c.retriever ?? "", section: "", url: "",
          })));
          return;
        }
      } catch {}
    }
    if (!r.question) return;
    setChunks([]);
    setLoading(true);
    evalApi.getChunks(r.question)
      .then((data) => setChunks(data))
      .catch((e) => setError(e instanceof Error ? e.message : "Không thể fetch chunks"))
      .finally(() => setLoading(false));
  };

  const refetch = () => {
    if (!row) return;
    if (hasGt) loadDocView(gtIds);
    else loadChunkList(row);
  };

  const toggle = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
    setSaved(false);
  };

  const handleSave = () => {
    if (!row) return;
    onSaveGroundTruth([...selected].join(", "));
    setSaved(true);
  };

  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopied(text);
    setTimeout(() => setCopied(null), 1500);
  };

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="fixed right-0 top-0 z-40 flex h-full w-[460px] flex-col border-l border-line bg-white shadow-panel">

      {/* Header */}
      <div className="flex items-start gap-3 border-b border-line bg-paper/50 px-4 py-3">
        <div className="min-w-0 flex-1">
          <p className="mb-1 text-[10px] font-semibold uppercase tracking-widest text-ink/40">
            {mode === "doc" ? "Tài liệu" : "Câu hỏi"}
          </p>
          {row ? (
            <p className="line-clamp-2 text-sm font-medium leading-snug text-ink">
              {mode === "doc"
                ? (docChunks[0]?.section || docChunks[0]?.url || row.question || "—")
                : (row.question ?? "—")}
            </p>
          ) : (
            <p className="text-sm italic text-ink/35">Chọn câu hỏi để xem</p>
          )}
        </div>
        {row && !loading && (
          <button
            onClick={refetch}
            title="Tải lại"
            className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-md text-ink/35 transition hover:bg-mist hover:text-mint"
          >
            <RefreshCw className="h-3.5 w-3.5" />
          </button>
        )}
      </div>

      {/* Mode indicator */}
      {row && (
        <div className="flex items-center gap-2 border-b border-line/60 bg-paper/30 px-4 py-1.5">
          {mode === "doc" ? (
            <>
              <span className="h-2 w-2 rounded-sm border-l-2 border-mint bg-mint/10" />
              <span className="text-[10px] text-ink/50">Ground truth (in đậm)</span>
              <span className="ml-3 h-2 w-2 rounded-sm bg-line/60" />
              <span className="text-[10px] text-ink/50">Chunks khác</span>
            </>
          ) : (
            <>
              <span className="text-[10px] text-ink/50">
                Tích chọn chunk để lưu làm ground truth
              </span>
            </>
          )}
        </div>
      )}

      {/* Body */}
      <div ref={bodyRef} className="flex-1 overflow-y-auto px-4 py-3">
        {!row ? (
          <div className="flex flex-col items-center justify-center py-20 text-center">
            <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-mist">
              <BookOpen className="h-5 w-5 text-mint/60" />
            </div>
            <p className="text-sm text-ink/40">Bấm 👁 để xem chunks của câu hỏi</p>
          </div>
        ) : loading ? (
          <div className="flex flex-col items-center justify-center py-16">
            <Loader2 className="mb-3 h-6 w-6 animate-spin text-mint" />
            <p className="text-sm text-ink/50">
              {mode === "doc" ? "Đang tải tài liệu..." : "Đang tải chunks..."}
            </p>
          </div>
        ) : error ? (
          <div className="flex flex-col items-center justify-center py-16 text-center gap-3">
            <p className="rounded-lg bg-danger/8 px-3 py-2 text-xs text-danger">{error}</p>
            <button onClick={refetch} className="flex h-8 items-center gap-2 rounded-lg border border-line bg-white px-3 text-xs font-medium text-ink/65 transition hover:bg-paper">
              <RefreshCw className="h-3 w-3" /> Thử lại
            </button>
          </div>
        ) : mode === "doc" ? (
          <DocView
            chunks={docChunks}
            highlightIds={new Set(gtIds)}
            notFoundIds={notFoundIds}
          />
        ) : chunks.length === 0 ? (
          <p className="py-16 text-center text-sm text-ink/40">Không có chunks nào</p>
        ) : (
          <div className="space-y-2.5">
            <p className="mb-3 text-[11px] font-semibold uppercase tracking-widest text-ink/40">
              {chunks.length} chunks
            </p>
            {chunks.map((chunk) => {
              const isSelected = selected.has(chunk.chunk_id);
              const pct = Math.min(Math.round(chunk.score * 100), 100);
              let hostname = "";
              try { hostname = chunk.url ? new URL(chunk.url).hostname : ""; } catch {}

              return (
                <div
                  key={chunk.chunk_id}
                  onClick={() => toggle(chunk.chunk_id)}
                  className={cn(
                    "cursor-pointer rounded-xl border p-3 transition-all",
                    isSelected
                      ? "border-mint/40 bg-mint/6 shadow-sm"
                      : "border-line bg-white hover:border-line/80 hover:bg-paper/60",
                  )}
                >
                  <div className="mb-2 flex items-start gap-2">
                    <input type="checkbox" checked={isSelected}
                      onChange={() => toggle(chunk.chunk_id)}
                      onClick={(e) => e.stopPropagation()}
                      className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 cursor-pointer accent-mint"
                    />
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-1">
                        <code className="break-all rounded border border-line/70 bg-paper px-1.5 py-0.5 font-mono text-[10px] text-ink/65">
                          {chunk.chunk_id}
                        </code>
                        <button
                          onClick={(e) => { e.stopPropagation(); handleCopy(chunk.chunk_id); }}
                          className="flex-shrink-0 text-ink/30 transition hover:text-mint" title="Copy ID"
                        >
                          <Copy className="h-3 w-3" />
                        </button>
                        {copied === chunk.chunk_id && (
                          <span className="text-[10px] font-medium text-mint">Copied!</span>
                        )}
                      </div>
                      <div className="mt-1.5 flex items-center gap-2">
                        <div className="h-1 flex-1 overflow-hidden rounded-full bg-line">
                          <div className="h-full rounded-full bg-mint transition-all" style={{ width: `${pct}%` }} />
                        </div>
                        <span className="w-9 flex-shrink-0 text-right font-mono text-[10px] text-ink/45">
                          {chunk.score.toFixed(3)}
                        </span>
                      </div>
                    </div>
                  </div>
                  <p className="ml-5 line-clamp-3 text-xs leading-relaxed text-ink/70">{chunk.text}</p>
                  <div className="ml-5 mt-1.5 flex items-center gap-2">
                    {chunk.section && <span className="truncate text-[10px] text-ink/40">{chunk.section}</span>}
                    {hostname && (
                      <a href={chunk.url} target="_blank" rel="noreferrer"
                        onClick={(e) => e.stopPropagation()}
                        className="flex flex-shrink-0 items-center gap-0.5 text-[10px] text-ink/40 transition hover:text-mint"
                      >
                        <ExternalLink className="h-2.5 w-2.5" />{hostname}
                      </a>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Footer */}
      {row && mode === "chunks" && (
        <div className="border-t border-line bg-paper/40 px-4 py-3">
          <div className="flex items-center justify-between gap-3">
            <p className="min-w-0 text-xs text-ink/50">
              {selected.size > 0 ? (
                <><span className="font-medium text-mint">{selected.size}</span> chunk{selected.size > 1 ? "s" : ""} đã chọn</>
              ) : "Chưa chọn ground truth"}
            </p>
            <button
              onClick={handleSave}
              disabled={selected.size === 0}
              className={cn(
                "flex h-8 flex-shrink-0 items-center gap-1.5 rounded-lg px-3 text-xs font-semibold transition active:scale-95 disabled:cursor-not-allowed disabled:opacity-40",
                saved ? "bg-mint/15 text-mint" : "bg-ink text-white hover:bg-ink/90",
              )}
            >
              {saved ? "✓ Đã lưu" : "Lưu Ground Truth"}
            </button>
          </div>
          {selected.size > 0 && (
            <p className="mt-1.5 truncate font-mono text-[10px] text-ink/35">
              {[...selected].join(", ")}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
