"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import {
  ArrowLeft,
  ExternalLink,
  FileText,
  Layers3,
  Loader2,
  PanelTop,
  ShieldAlert,
  type LucideIcon,
} from "lucide-react";
import type { ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

type SourceChunk = {
  chunk: {
    chunk_id: string;
    text: string;
    metadata: Record<string, unknown>;
  };
  score: number;
  rank: number;
  retriever: string;
};

type SourceDebugResponse = {
  provider: string;
  document_id: string;
  name: string;
  source_type: string;
  source: string;
  metadata: Record<string, unknown>;
  markdown: string;
  chunk_input: string;
  chunk_input_type: string;
  total_chunks: number;
  chunks: SourceChunk[];
};

type ChunkHighlightStyle = {
  badge: string;
  border: string;
  dot: string;
  text: string;
};

type ChunkHighlight = {
  chunkId: string;
  end: number;
  key: string;
  mapped: boolean;
  rank: number;
  start: number;
  style: ChunkHighlightStyle;
};

const API_URL =
  process.env.NEXT_PUBLIC_AGENTIC_RAG_API_URL ?? "http://127.0.0.1:8000";
const CHUNK_HIGHLIGHT_STYLES: ChunkHighlightStyle[] = [
  {
    badge: "bg-amber-100 text-amber-800 dark:bg-amber-300/18 dark:text-amber-100",
    border: "border-l-amber-400 dark:border-l-amber-300",
    dot: "bg-amber-400 dark:bg-amber-300",
    text: "bg-amber-200/70 ring-1 ring-amber-300/70 dark:bg-amber-300/24 dark:ring-amber-300/28",
  },
  {
    badge: "bg-sky-100 text-sky-800 dark:bg-sky-300/18 dark:text-sky-100",
    border: "border-l-sky-400 dark:border-l-sky-300",
    dot: "bg-sky-400 dark:bg-sky-300",
    text: "bg-sky-200/70 ring-1 ring-sky-300/70 dark:bg-sky-300/24 dark:ring-sky-300/28",
  },
  {
    badge: "bg-emerald-100 text-emerald-800 dark:bg-emerald-300/18 dark:text-emerald-100",
    border: "border-l-emerald-400 dark:border-l-emerald-300",
    dot: "bg-emerald-400 dark:bg-emerald-300",
    text: "bg-emerald-200/70 ring-1 ring-emerald-300/70 dark:bg-emerald-300/24 dark:ring-emerald-300/28",
  },
  {
    badge: "bg-fuchsia-100 text-fuchsia-800 dark:bg-fuchsia-300/18 dark:text-fuchsia-100",
    border: "border-l-fuchsia-400 dark:border-l-fuchsia-300",
    dot: "bg-fuchsia-400 dark:bg-fuchsia-300",
    text: "bg-fuchsia-200/70 ring-1 ring-fuchsia-300/70 dark:bg-fuchsia-300/24 dark:ring-fuchsia-300/28",
  },
  {
    badge: "bg-lime-100 text-lime-800 dark:bg-lime-300/18 dark:text-lime-100",
    border: "border-l-lime-400 dark:border-l-lime-300",
    dot: "bg-lime-400 dark:bg-lime-300",
    text: "bg-lime-200/70 ring-1 ring-lime-300/70 dark:bg-lime-300/24 dark:ring-lime-300/28",
  },
  {
    badge: "bg-rose-100 text-rose-800 dark:bg-rose-300/18 dark:text-rose-100",
    border: "border-l-rose-400 dark:border-l-rose-300",
    dot: "bg-rose-400 dark:bg-rose-300",
    text: "bg-rose-200/70 ring-1 ring-rose-300/70 dark:bg-rose-300/24 dark:ring-rose-300/28",
  },
];

export default function SourceDebugPage() {
  const params = useParams();
  const rawDocumentId = params?.documentId;
  const documentId = Array.isArray(rawDocumentId)
    ? rawDocumentId[0]
    : rawDocumentId ?? "";
  const [debug, setDebug] = useState<SourceDebugResponse | null>(null);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function loadDebug() {
      if (!documentId) return;
      setIsLoading(true);
      setError("");

      try {
        const response = await fetch(
          `${API_URL}/sources/${encodeURIComponent(documentId)}/debug`,
          { cache: "no-store" },
        );
        if (!response.ok) {
          throw new Error(`Không lấy được debug source: ${response.status}`);
        }
        const payload = (await response.json()) as SourceDebugResponse;
        if (!cancelled) {
          setDebug(payload);
        }
      } catch (loadError) {
        if (!cancelled) {
          setError(sourceErrorMessage(loadError));
          setDebug(null);
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    }

    void loadDebug();

    return () => {
      cancelled = true;
    };
  }, [documentId]);

  const title = debug?.name ?? "Debug ingestion";
  const sourceType = debug?.source_type ?? "";
  const labels = debugLabelsForSource(sourceType);
  const chunkingNotice = debug ? chunkingNoticeForDebug(debug) : null;
  const chunkInput = debug ? debug.chunk_input || debug.markdown : "";
  const chunkHighlights = useMemo(
    () => (debug ? buildChunkHighlights(chunkInput, debug.chunks) : []),
    [debug, chunkInput],
  );
  const chunkHighlightsByKey = useMemo(
    () => new Map(chunkHighlights.map((highlight) => [highlight.key, highlight])),
    [chunkHighlights],
  );

  return (
    <main className="h-screen overflow-hidden bg-mist px-4 py-5 text-ink dark:bg-slate-950 dark:text-slate-100 sm:px-6">
      <div className="mx-auto flex h-full min-h-0 max-w-[1600px] flex-col gap-4">
        <header className="shrink-0 rounded-lg border border-line/80 bg-white/90 px-4 py-4 shadow-panel backdrop-blur-xl dark:border-white/14 dark:bg-slate-950/90 sm:px-5">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
            <div className="min-w-0">
              <Link
                className="mb-3 inline-flex items-center gap-2 text-sm font-medium text-mint transition hover:text-mint/72 dark:text-emerald-200"
                href="/citation-chat"
              >
                <ArrowLeft className="h-4 w-4" aria-hidden="true" />
                Trở về chat
              </Link>
              <div className="min-w-0">
                <p className="text-xs font-semibold uppercase text-ink/46 dark:text-slate-400">
                  Source debug
                </p>
                <h1 className="mt-1 truncate text-2xl font-semibold tracking-normal sm:text-3xl">
                  {title}
                </h1>
              </div>
            </div>
            {debug ? (
              <div className="grid gap-2 sm:grid-cols-3 lg:w-[520px]">
                <Metric label="Loại" value={sourceType || "-"} />
                <Metric label="Provider" value={debug.provider} />
                <Metric label="Chunks" value={String(debug.total_chunks)} />
              </div>
            ) : null}
          </div>
        </header>

        {isLoading ? (
          <StateCard icon={Loader2} text="Đang tải source debug..." spin />
        ) : error ? (
          <StateCard icon={ShieldAlert} text={error} tone="danger" />
        ) : debug ? (
          <section className="grid min-h-0 flex-1 gap-4 overflow-hidden xl:grid-cols-[1.1fr_1fr_1fr]">
            <DebugColumn
              description={labels.originalDescription}
              icon={PanelTop}
              title={labels.originalTitle}
            >
              <OriginalSource debug={debug} documentId={documentId} />
            </DebugColumn>

            <DebugColumn
              description={labels.chunkInputDescription}
              icon={FileText}
              title={labels.chunkInputTitle}
            >
              {chunkingNotice ? <DebugNotice text={chunkingNotice} /> : null}
              {chunkInput.trim() ? (
                <HighlightedChunkInput highlights={chunkHighlights} text={chunkInput} />
              ) : (
                <EmptyBlock text="Source này chưa có đầu vào chunking được lưu." />
              )}
            </DebugColumn>

            <DebugColumn
              description={labels.chunksDescription}
              icon={Layers3}
              title="Chunks"
            >
              {chunkingNotice ? <DebugNotice text={chunkingNotice} /> : null}
              <ChunksList
                chunks={debug.chunks}
                highlightsByKey={chunkHighlightsByKey}
                totalChunks={debug.total_chunks}
              />
            </DebugColumn>
          </section>
        ) : null}
      </div>
    </main>
  );
}

function OriginalSource({
  debug,
  documentId,
}: {
  debug: SourceDebugResponse;
  documentId: string;
}) {
  const sourceType = debug.source_type.toLowerCase();
  const originalUrl = useMemo(() => {
    if (sourceType === "pdf") {
      return `${API_URL}/sources/${encodeURIComponent(documentId)}/raw`;
    }
    if (isHttpUrl(debug.source)) {
      return debug.source;
    }
    return "";
  }, [debug.source, documentId, sourceType]);

  if (originalUrl) {
    const labels = debugLabelsForSource(sourceType);
    return (
      <div className="flex h-full min-h-0 flex-1 flex-col gap-3">
        <div className="flex min-w-0 items-center justify-between gap-3 rounded-md border border-line bg-white/70 p-3 dark:border-white/14 dark:bg-slate-950/40">
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold" title={debug.source}>
              {sourceType === "pdf" ? debug.name : debug.source}
            </p>
            <p className="mt-1 text-xs text-ink/50 dark:text-slate-400">
              {labels.originalHint}
            </p>
          </div>
          <a
            className="inline-flex h-9 shrink-0 items-center gap-2 rounded-md border border-line bg-white px-3 text-sm font-medium text-mint transition hover:bg-paper dark:border-white/14 dark:bg-slate-900 dark:text-emerald-200 dark:hover:bg-slate-800"
            href={originalUrl}
            rel="noreferrer"
            target="_blank"
          >
            <ExternalLink className="h-4 w-4" aria-hidden="true" />
            Mở
          </a>
        </div>
        <iframe
          className="min-h-0 flex-1 rounded-md border border-line bg-white dark:border-white/14"
          src={originalUrl}
          title={`Nguồn gốc ${debug.name}`}
        />
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <DebugField label="Tên" value={debug.name} />
      <DebugField label="Loại" value={debug.source_type} />
      <DebugField label="Nguồn" value={debug.source} />
      <div className="rounded-md border border-line bg-white/70 p-3 dark:border-white/14 dark:bg-slate-950/40">
        <p className="mb-2 text-xs font-semibold text-ink/62 dark:text-slate-300">
          Metadata
        </p>
        <div className="space-y-2">
          {Object.entries(debug.metadata).map(([key, value]) => (
            <DebugField key={key} label={key} value={formatDebugValue(value)} />
          ))}
        </div>
      </div>
    </div>
  );
}

function ChunksList({
  chunks,
  highlightsByKey,
  totalChunks,
}: {
  chunks: SourceChunk[];
  highlightsByKey: Map<string, ChunkHighlight>;
  totalChunks: number;
}) {
  if (!chunks.length) {
    return <EmptyBlock text="Source này chưa có chunk." />;
  }

  return (
    <div className="space-y-3">
      <div className="rounded-md border border-line bg-white/70 p-3 text-sm text-ink/62 dark:border-white/14 dark:bg-slate-950/40 dark:text-slate-300">
        {totalChunks} chunk đã tạo
      </div>
      {chunks.map((result, index) => (
        <ChunkCard
          highlight={highlightsByKey.get(chunkKey(result, index))}
          index={index}
          key={chunkKey(result, index)}
          result={result}
        />
      ))}
    </div>
  );
}

function ChunkCard({
  highlight,
  index,
  result,
}: {
  highlight: ChunkHighlight | undefined;
  index: number;
  result: SourceChunk;
}) {
  const fallbackStyle = CHUNK_HIGHLIGHT_STYLES[index % CHUNK_HIGHLIGHT_STYLES.length];
  const style = highlight?.style ?? fallbackStyle;

  return (
    <article
      className={cn(
        "min-w-0 overflow-hidden rounded-md border border-line border-l-4 bg-white/70 p-4 dark:border-white/14 dark:bg-slate-950/40",
        style.border,
      )}
    >
      <div className="mb-3 flex min-w-0 items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <span
              className={cn(
                "inline-flex items-center gap-1.5 rounded-full px-2 py-1 text-xs font-semibold",
                style.badge,
              )}
            >
              <span className={cn("h-2 w-2 rounded-full", style.dot)} />
              Chunk {result.rank}
            </span>
            {highlight?.mapped ? (
              <span className="text-[11px] font-medium text-ink/46 dark:text-slate-400">
                map {highlight.start}-{highlight.end}
              </span>
            ) : (
              <span className="text-[11px] font-medium text-danger dark:text-red-200">
                không map được
              </span>
            )}
          </div>
          <p className="mt-1 break-words text-xs text-ink/46 [overflow-wrap:anywhere] dark:text-slate-400">
            {result.chunk.chunk_id}
          </p>
        </div>
        <Badge>{metadataValue(result.chunk.metadata, "section") ?? "main"}</Badge>
      </div>
      <p className="break-words text-sm leading-6 text-ink/72 [overflow-wrap:anywhere] dark:text-slate-200">
        {result.chunk.text}
      </p>
      <ChunkMetadata metadata={result.chunk.metadata} />
    </article>
  );
}

function HighlightedChunkInput({
  highlights,
  text,
}: {
  highlights: ChunkHighlight[];
  text: string;
}) {
  const mappedHighlights = highlights
    .filter((highlight) => highlight.mapped)
    .sort((left, right) => left.start - right.start || left.rank - right.rank);
  const unmappedCount = highlights.length - mappedHighlights.length;

  if (!mappedHighlights.length) {
    return (
      <div className="space-y-3">
        <DebugNotice text="Chưa map được chunk nào lên đầu vào này. Thường là source cũ hoặc thiếu artifact debug khi upload." />
        <pre className="whitespace-pre-wrap break-words rounded-md border border-line bg-white/70 p-4 text-xs leading-6 text-ink/72 [overflow-wrap:anywhere] dark:border-white/14 dark:bg-slate-950/40 dark:text-slate-200">
          {text}
        </pre>
      </div>
    );
  }

  const pieces: ReactNode[] = [];
  let cursor = 0;
  for (const highlight of mappedHighlights) {
    const start = Math.max(highlight.start, cursor);
    const end = Math.max(highlight.end, start);
    if (start > cursor) {
      pieces.push(
        <span key={`text-${cursor}-${start}`}>{text.slice(cursor, start)}</span>,
      );
    }
    if (end > cursor) {
      pieces.push(
        <mark
          className={cn("rounded px-0.5 text-inherit", highlight.style.text)}
          key={highlight.key}
          title={`Chunk ${highlight.rank}: ${highlight.chunkId}`}
        >
          {text.slice(start, end)}
        </mark>,
      );
      cursor = end;
    }
  }
  if (cursor < text.length) {
    pieces.push(<span key={`text-${cursor}-end`}>{text.slice(cursor)}</span>);
  }

  return (
    <div className="space-y-3">
      <div className="rounded-md border border-line bg-white/70 p-3 text-xs leading-5 text-ink/58 dark:border-white/14 dark:bg-slate-950/40 dark:text-slate-300">
        Đã map {mappedHighlights.length}/{highlights.length} chunk lên đầu vào chunking
        {unmappedCount ? `, ${unmappedCount} chunk không tìm thấy range.` : "."}
      </div>
      <pre className="whitespace-pre-wrap break-words rounded-md border border-line bg-white/70 p-4 text-xs leading-6 text-ink/72 [overflow-wrap:anywhere] dark:border-white/14 dark:bg-slate-950/40 dark:text-slate-200">
        {pieces}
      </pre>
    </div>
  );
}

function ChunkMetadata({ metadata }: { metadata: Record<string, unknown> }) {
  const entries = Object.entries(metadata);
  if (!entries.length) return null;

  return (
    <details
      className="mt-4 rounded-md border border-line bg-paper/70 dark:border-white/14 dark:bg-slate-900/70"
      open
    >
      <summary className="cursor-pointer px-3 py-2 text-xs font-semibold text-ink/62 dark:text-slate-300">
        Metadata ({entries.length})
      </summary>
      <div className="max-h-48 space-y-2 overflow-y-auto border-t border-line p-3 dark:border-white/14">
        {entries.map(([key, value]) => (
          <DebugField key={key} label={key} value={formatDebugValue(value)} />
        ))}
      </div>
    </details>
  );
}

function DebugColumn({
  children,
  description,
  icon: Icon,
  title,
}: {
  children: ReactNode;
  description: string;
  icon: LucideIcon;
  title: string;
}) {
  return (
    <article className="flex min-h-0 min-w-0 flex-col overflow-hidden rounded-lg border border-line/80 bg-white/90 shadow-panel backdrop-blur-xl dark:border-white/14 dark:bg-slate-950/90">
      <div className="shrink-0 border-b border-line px-4 py-4 dark:border-white/14">
        <div className="flex items-center gap-3">
          <div className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-mint/25 bg-mint/10 text-mint dark:border-emerald-300/24 dark:bg-emerald-300/12 dark:text-emerald-200">
            <Icon className="h-4 w-4" aria-hidden="true" />
          </div>
          <div>
            <h2 className="text-base font-semibold">{title}</h2>
            <p className="mt-1 text-xs text-ink/50 dark:text-slate-400">
              {description}
            </p>
          </div>
        </div>
      </div>
      <div className="flex min-h-0 flex-1 flex-col overflow-y-auto p-4">{children}</div>
    </article>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 rounded-md border border-line bg-white/70 px-3 py-2 dark:border-white/14 dark:bg-slate-950/42">
      <p className="text-xs text-ink/50 dark:text-slate-400">{label}</p>
      <p className="mt-1 truncate text-base font-semibold" title={value}>
        {value}
      </p>
    </div>
  );
}

function StateCard({
  icon: Icon,
  spin = false,
  text,
  tone = "normal",
}: {
  icon: LucideIcon;
  spin?: boolean;
  text: string;
  tone?: "normal" | "danger";
}) {
  return (
    <div
      className={cn(
        "flex items-center gap-3 rounded-lg border bg-white/90 p-5 shadow-panel dark:bg-slate-950/90",
        tone === "danger"
          ? "border-danger/30 text-danger dark:text-red-200"
          : "border-line/80 text-ink/70 dark:border-white/14 dark:text-slate-200",
      )}
    >
      <Icon className={cn("h-5 w-5", spin && "animate-spin")} aria-hidden="true" />
      <span className="text-sm font-medium">{text}</span>
    </div>
  );
}

function DebugField({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 rounded-md border border-line bg-white/70 px-3 py-2 dark:border-white/14 dark:bg-slate-950/42">
      <p className="text-[11px] font-semibold uppercase text-ink/42 dark:text-slate-400">
        {label}
      </p>
      <p className="mt-1 break-words text-xs leading-5 text-ink/70 [overflow-wrap:anywhere] dark:text-slate-200">
        {value || "-"}
      </p>
    </div>
  );
}

function EmptyBlock({ text }: { text: string }) {
  return (
    <div className="rounded-md border border-dashed border-line bg-white/70 p-4 text-sm text-ink/58 dark:border-white/14 dark:bg-slate-950/40 dark:text-slate-300">
      {text}
    </div>
  );
}

function DebugNotice({ text }: { text: string }) {
  return (
    <div className="mb-3 rounded-md border border-mint/25 bg-mint/8 p-3 text-xs leading-5 text-ink/64 dark:border-emerald-300/24 dark:bg-emerald-300/10 dark:text-emerald-100">
      {text}
    </div>
  );
}

function isHttpUrl(value: string) {
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:";
  } catch {
    return false;
  }
}

function buildChunkHighlights(chunkInput: string, chunks: SourceChunk[]): ChunkHighlight[] {
  const normalizedChunkInput = normalizeForRange(chunkInput);
  let normalizedCursor = 0;

  return chunks.map((result, index) => {
    const style = CHUNK_HIGHLIGHT_STYLES[index % CHUNK_HIGHLIGHT_STYLES.length];
    const normalizedChunk = normalizeForRange(result.chunk.text).text.trim();
    let start = -1;
    let end = -1;

    if (normalizedChunk) {
      const afterCursor = normalizedChunkInput.text.indexOf(normalizedChunk, normalizedCursor);
      const foundAt = afterCursor >= 0
        ? afterCursor
        : normalizedChunkInput.text.indexOf(normalizedChunk);
      if (foundAt >= 0) {
        const normalizedEnd = foundAt + normalizedChunk.length - 1;
        start = normalizedChunkInput.map[foundAt] ?? -1;
        end = (normalizedChunkInput.map[normalizedEnd] ?? start) + 1;
        normalizedCursor = foundAt + normalizedChunk.length;
      }
    }

    return {
      chunkId: result.chunk.chunk_id,
      end,
      key: chunkKey(result, index),
      mapped: start >= 0 && end > start,
      rank: result.rank,
      start,
      style,
    };
  });
}

function chunkKey(result: SourceChunk, index: number): string {
  return `${result.chunk.chunk_id}-${result.rank}-${index}`;
}

function normalizeForRange(value: string): { map: number[]; text: string } {
  let normalized = "";
  const map: number[] = [];
  let previousWasWhitespace = false;

  for (let index = 0; index < value.length; index += 1) {
    const char = value[index];
    if (/\s/.test(char)) {
      if (normalized && !previousWasWhitespace) {
        normalized += " ";
        map.push(index);
      }
      previousWasWhitespace = true;
      continue;
    }

    normalized += char;
    map.push(index);
    previousWasWhitespace = false;
  }

  if (normalized.endsWith(" ")) {
    normalized = normalized.slice(0, -1);
    map.pop();
  }

  return { map, text: normalized };
}

function chunkingNoticeForDebug(debug: SourceDebugResponse): string | null {
  const firstChunk = debug.chunks[0]?.chunk;
  if (!firstChunk) return null;

  const sourceType = debug.source_type.toLowerCase();
  const method = metadataValue(firstChunk.metadata, "chunking_method");
  const hasMarkdownSectionPath = Array.isArray(firstChunk.metadata.section_path);
  if (sourceType === "url" && method === "deterministic-character-overlap") {
    return "URL này dùng parsed HTML sections làm đầu vào chunking; cột giữa đang hiển thị đúng nội dung trước khi tách chunk.";
  }
  if (sourceType === "url" && hasMarkdownSectionPath) {
    return "URL này được upload bằng logic tạm thời: chunk từ Markdown parse. Nạp lại URL để dùng parsed HTML sections.";
  }
  if (sourceType === "pdf") {
    return "PDF này dùng Markdown parse làm đầu vào chunking; section trong metadata là heading gần nhất trong Markdown.";
  }
  return null;
}

function debugLabelsForSource(sourceType: string) {
  const normalizedType = sourceType.toLowerCase();
  if (normalizedType === "pdf") {
    return {
      originalTitle: "PDF gốc",
      originalDescription: "File PDF trước khi parse",
      originalHint: "PDF gốc được lưu local để đối chiếu với Markdown.",
      chunkInputTitle: "Markdown parse",
      chunkInputDescription: "Markdown được parse từ PDF và dùng làm đầu vào chunking",
      chunksDescription: "Các đoạn được tách từ Markdown PDF",
    };
  }
  if (normalizedType === "url") {
    return {
      originalTitle: "Trang web gốc",
      originalDescription: "Trang chính thức trước khi extract",
      originalHint: "Nếu trang gốc chặn nhúng, dùng nút mở trực tiếp.",
      chunkInputTitle: "Parsed HTML sections",
      chunkInputDescription: "Nội dung HTML đã clean và chia section trước khi chunk",
      chunksDescription: "Các đoạn được tách từ parsed HTML sections",
    };
  }
  if (normalizedType === "text") {
    return {
      originalTitle: "Văn bản gốc",
      originalDescription: "Nội dung người dùng nhập",
      originalHint: "Văn bản gốc được lưu như Markdown đầu vào.",
      chunkInputTitle: "Văn bản đã lưu",
      chunkInputDescription: "Nội dung text được dùng trực tiếp làm đầu vào chunking",
      chunksDescription: "Các đoạn được tách từ văn bản",
    };
  }
  return {
    originalTitle: "Gốc",
    originalDescription: "Nội dung đầu vào trước khi parse",
    originalHint: "Nguồn gốc dùng để đối chiếu với Markdown.",
    chunkInputTitle: "Đầu vào chunking",
    chunkInputDescription: "Nội dung được đưa vào bước tách chunk",
    chunksDescription: "Các đoạn được đưa vào retrieval",
  };
}

function metadataValue(metadata: Record<string, unknown>, key: string): string | null {
  const value = metadata[key];
  if (typeof value === "string" && value.trim()) return value;
  if (typeof value === "number") return String(value);
  return null;
}

function formatDebugValue(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return JSON.stringify(value);
}

function sourceErrorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  return "Không thể tải source debug.";
}
