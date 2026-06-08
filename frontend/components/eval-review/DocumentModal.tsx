"use client";

import { useEffect, useRef } from "react";
import { X, FileText } from "lucide-react";
import type { Chunk } from "@/lib/eval-review-types";
import { cn } from "@/lib/utils";

interface Props {
  chunks: Chunk[];
  highlightId: string;
  onClose: () => void;
}

function sortByDocOrder(chunks: Chunk[]): Chunk[] {
  return [...chunks].sort((a, b) => {
    const srcA = a.chunk_id.split("_").slice(0, 2).join("_");
    const srcB = b.chunk_id.split("_").slice(0, 2).join("_");
    if (srcA !== srcB) return srcA.localeCompare(srcB);
    const num = (id: string) => {
      const m = id.match(/_c(\d+)$/);
      return m ? parseInt(m[1], 10) : 0;
    };
    return num(a.chunk_id) - num(b.chunk_id);
  });
}

export function DocumentModal({ chunks, highlightId, onClose }: Props) {
  const highlightRef = useRef<HTMLDivElement>(null);
  const sorted = sortByDocOrder(chunks);
  const highlight = chunks.find((c) => c.chunk_id === highlightId);

  useEffect(() => {
    const el = highlightRef.current;
    if (el) {
      setTimeout(
        () => el.scrollIntoView({ behavior: "smooth", block: "center" }),
        80,
      );
    }
  }, [highlightId]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  const docUrl = highlight?.url || sorted[0]?.url || "";
  let hostname = "";
  try {
    hostname = docUrl ? new URL(docUrl).hostname : "";
  } catch {}

  return (
    <div className="fixed inset-0 z-50 flex items-stretch bg-ink/50 backdrop-blur-sm">
      <div className="absolute inset-0" onClick={onClose} />

      <div className="relative z-10 mx-auto my-6 flex w-full max-w-3xl flex-col overflow-hidden rounded-2xl border border-line bg-white shadow-panel">
        {/* Header */}
        <div className="flex items-center gap-3 border-b border-line bg-paper/60 px-6 py-3">
          <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg bg-mint/10">
            <FileText className="h-4 w-4 text-mint" />
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-semibold text-ink">
              {highlight?.section
                ? `${highlight.section}`
                : hostname || "Tài liệu"}
            </p>
            {hostname && (
              <p className="truncate text-[11px] text-ink/45">{docUrl}</p>
            )}
          </div>
          <div className="flex items-center gap-2">
            <span className="rounded-full border border-mint/30 bg-mint/8 px-2.5 py-0.5 text-[11px] font-medium text-mint">
              {sorted.length} chunk{sorted.length !== 1 ? "s" : ""}
            </span>
            <button
              onClick={onClose}
              className="flex h-8 w-8 items-center justify-center rounded-lg text-ink/40 transition hover:bg-mist hover:text-ink"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        {/* Legend */}
        <div className="flex items-center gap-2 border-b border-line/60 bg-paper/30 px-6 py-2">
          <span className="h-3 w-3 rounded-sm border-l-2 border-mint bg-mint/10" />
          <span className="text-[11px] text-ink/50">Chunk đang xem (in đậm)</span>
          <span className="ml-4 h-3 w-3 rounded-sm bg-line/60" />
          <span className="text-[11px] text-ink/50">Chunks khác</span>
        </div>

        {/* Scrollable body */}
        <div className="flex-1 overflow-y-auto px-8 py-6">
          <div className="space-y-0">
            {sorted.map((chunk, idx) => {
              const isHighlight = chunk.chunk_id === highlightId;
              const prevSection =
                idx > 0 ? sorted[idx - 1].section : null;
              const showSection =
                chunk.section && chunk.section !== prevSection;

              return (
                <div key={chunk.chunk_id}>
                  {showSection && (
                    <div className="mb-3 mt-6 first:mt-0 flex items-center gap-3">
                      <span className="text-[11px] font-semibold uppercase tracking-widest text-ink/35">
                        {chunk.section}
                      </span>
                      <div className="flex-1 border-t border-line/60" />
                    </div>
                  )}

                  <div
                    ref={isHighlight ? highlightRef : undefined}
                    className={cn(
                      "rounded-lg px-4 py-3 transition-colors",
                      isHighlight
                        ? "border-l-[3px] border-mint bg-mint/8 my-1"
                        : "text-ink/65",
                    )}
                  >
                    <div className="mb-1.5 flex items-center gap-2">
                      <code
                        className={cn(
                          "font-mono text-[10px]",
                          isHighlight ? "text-mint" : "text-ink/30",
                        )}
                      >
                        {chunk.chunk_id}
                      </code>
                      {isHighlight && (
                        <span className="rounded-full bg-mint/15 px-1.5 py-0.5 text-[10px] font-semibold text-mint">
                          ← đang xem
                        </span>
                      )}
                    </div>

                    <p
                      className={cn(
                        "whitespace-pre-wrap leading-relaxed",
                        isHighlight
                          ? "text-sm font-semibold text-ink"
                          : "text-sm text-ink/60",
                      )}
                    >
                      {chunk.text}
                    </p>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
