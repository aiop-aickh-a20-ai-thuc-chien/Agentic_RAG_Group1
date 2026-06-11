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
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
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

type SourceDebugView = "ingestion" | "quality";

type KnowledgeQualityFindingKind = "exact_duplicate" | "near_duplicate" | "conflict";
type KnowledgeQualitySeverity = "info" | "warning" | "critical";

type KnowledgeQualityFact = {
  fact_id: string;
  chunk_id: string;
  entity: string;
  attribute: string;
  value: string;
  normalized_value?: string | null;
  unit?: string | null;
  span?: string | null;
  start?: number | null;
  end?: number | null;
  metadata: Record<string, unknown>;
};

type KnowledgeQualityFinding = {
  finding_id: string;
  kind: KnowledgeQualityFindingKind;
  severity: KnowledgeQualitySeverity;
  status: string;
  chunk_ids: string[];
  fact_ids: string[];
  summary: string;
  suggested_action?: string | null;
  confidence?: number | null;
  metadata: Record<string, unknown>;
};

type KnowledgeQualityReport = {
  facts: KnowledgeQualityFact[];
  findings: KnowledgeQualityFinding[];
  metadata: Record<string, unknown>;
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
const SOURCE_DEBUG_CACHE_PREFIX = "agentic-rag:source-debug:";
const SOURCE_QUALITY_CACHE_PREFIX = "agentic-rag:source-quality:";
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
  const [quality, setQuality] = useState<KnowledgeQualityReport | null>(null);
  const [activeView, setActiveView] = useState<SourceDebugView>("ingestion");
  const [error, setError] = useState("");
  const [qualityError, setQualityError] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isQualityLoading, setIsQualityLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function loadDebug() {
      if (!documentId) return;

      const cachedDebug = readCachedSourceDebug(documentId);
      if (cachedDebug) {
        setDebug(cachedDebug);
        setIsLoading(false);
      } else {
        setIsLoading(true);
      }
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
        writeCachedSourceDebug(documentId, payload);
        if (!cancelled) {
          setDebug(payload);
        }
      } catch (loadError) {
        if (!cancelled && !readCachedSourceDebug(documentId)) {
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

  useEffect(() => {
    let cancelled = false;

    async function loadQuality() {
      if (!documentId) return;

      const cachedQuality = readCachedKnowledgeQuality(documentId);
      if (cachedQuality) {
        setQuality(cachedQuality);
        setIsQualityLoading(false);
      } else {
        setIsQualityLoading(true);
      }
      setQualityError("");

      try {
        const response = await fetch(
          `${API_URL}/sources/${encodeURIComponent(documentId)}/quality`,
          { cache: "no-store" },
        );
        if (!response.ok) {
          throw new Error(`Không lấy được báo cáo quality: ${response.status}`);
        }
        const payload = (await response.json()) as KnowledgeQualityReport;
        writeCachedKnowledgeQuality(documentId, payload);
        if (!cancelled) {
          setQuality(payload);
        }
      } catch (loadError) {
        if (!cancelled && !readCachedKnowledgeQuality(documentId)) {
          setQualityError(sourceErrorMessage(loadError));
          setQuality(null);
        }
      } finally {
        if (!cancelled) {
          setIsQualityLoading(false);
        }
      }
    }

    void loadQuality();

    return () => {
      cancelled = true;
    };
  }, [documentId]);

  const title = debug?.name ?? "Debug ingestion";
  const sourceType = debug?.source_type ?? "";
  const chunkInputType = debug?.chunk_input_type ?? "";
  const labels = debugLabelsForSource(sourceType, chunkInputType);
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
  const debugViews: Array<{ id: SourceDebugView; label: string }> = [
    { id: "ingestion", label: "Ingestion" },
    { id: "quality", label: "Quality" },
  ];

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
          <div className="mt-4 grid max-w-sm grid-cols-2 gap-1 rounded-md bg-paper/70 p-1 dark:bg-slate-900/76">
            {debugViews.map((view) => (
              <button
                className={cn(
                  "h-9 rounded px-3 text-sm font-medium transition",
                  activeView === view.id
                    ? "bg-white text-mint shadow-sm dark:bg-slate-800 dark:text-emerald-200"
                    : "text-ink/58 hover:bg-white/70 dark:text-slate-300 dark:hover:bg-slate-800/70",
                )}
                key={view.id}
                onClick={() => setActiveView(view.id)}
                type="button"
              >
                {view.label}
              </button>
            ))}
          </div>
        </header>

        {isLoading ? (
          <StateCard icon={Loader2} text="Đang tải source debug..." spin />
        ) : error ? (
          <StateCard icon={ShieldAlert} text={error} tone="danger" />
        ) : debug && activeView === "quality" ? (
          <QualityReportView
            error={qualityError}
            isLoading={isQualityLoading}
            report={quality}
          />
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

function QualityReportView({
  error,
  isLoading,
  report,
}: {
  error: string;
  isLoading: boolean;
  report: KnowledgeQualityReport | null;
}) {
  if (isLoading) {
    return <StateCard icon={Loader2} text="Đang tải báo cáo quality..." spin />;
  }

  if (error) {
    return <StateCard icon={ShieldAlert} text={error} tone="danger" />;
  }

  if (!report) {
    return <StateCard icon={ShieldAlert} text="Chưa có báo cáo quality cho source này." />;
  }

  const duplicateFindings = report.findings.filter((finding) =>
    finding.kind === "exact_duplicate" || finding.kind === "near_duplicate",
  );
  const conflictFindings = report.findings.filter((finding) => finding.kind === "conflict");

  return (
    <section className="grid min-h-0 flex-1 gap-4 overflow-hidden xl:grid-cols-[320px_minmax(0,1fr)_minmax(0,1fr)]">
      <DebugColumn
        description="Tổng quan fact extraction và metadata của quality run"
        icon={FileText}
        title="Quality summary"
      >
        <QualitySummary report={report} />
      </DebugColumn>

      <DebugColumn
        description="Các fact bị trùng chính xác hoặc gần giống"
        icon={Layers3}
        title="Duplicates"
      >
        <QualityFindingList
          emptyText="Không phát hiện duplicate trong source này."
          findings={duplicateFindings}
        />
      </DebugColumn>

      <DebugColumn
        description="Các fact có giá trị mâu thuẫn cần kiểm tra"
        icon={ShieldAlert}
        title="Conflicts"
      >
        <QualityFindingList
          emptyText="Không phát hiện conflict trong source này."
          findings={conflictFindings}
        />
      </DebugColumn>
    </section>
  );
}

function QualitySummary({ report }: { report: KnowledgeQualityReport }) {
  const criticalCount = report.findings.filter((finding) => finding.severity === "critical").length;
  const warningCount = report.findings.filter((finding) => finding.severity === "warning").length;
  const metadataEntries = Object.entries(report.metadata);

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-2">
        <Metric label="Facts" value={String(report.facts.length)} />
        <Metric label="Findings" value={String(report.findings.length)} />
        <Metric label="Critical" value={String(criticalCount)} />
        <Metric label="Warning" value={String(warningCount)} />
      </div>

      {!report.findings.length ? (
        <EmptyBlock text="Không phát hiện duplicate hoặc conflict. Vẫn nên kiểm tra sample fact nếu source quan trọng." />
      ) : null}

      <QualityFactList facts={report.facts} />

      {metadataEntries.length ? (
        <details className="rounded-md border border-line bg-white/70 dark:border-white/14 dark:bg-slate-950/42">
          <summary className="cursor-pointer px-3 py-2 text-xs font-semibold text-ink/62 dark:text-slate-300">
            Quality metadata ({metadataEntries.length})
          </summary>
          <div className="max-h-48 space-y-2 overflow-y-auto border-t border-line p-3 dark:border-white/14">
            {metadataEntries.map(([key, value]) => (
              <DebugField key={key} label={key} value={formatDebugValue(value)} />
            ))}
          </div>
        </details>
      ) : null}
    </div>
  );
}

function QualityFactList({ facts }: { facts: KnowledgeQualityFact[] }) {
  if (!facts.length) {
    return <EmptyBlock text="Endpoint chưa trả về fact nào cho source này." />;
  }

  return (
    <div className="rounded-md border border-line bg-white/70 dark:border-white/14 dark:bg-slate-950/42">
      <div className="border-b border-line px-3 py-2 text-xs font-semibold text-ink/62 dark:border-white/14 dark:text-slate-300">
        Facts extracted
      </div>
      <div className="max-h-72 space-y-2 overflow-y-auto p-3">
        {facts.map((fact) => (
          <article
            className="min-w-0 rounded-md border border-line bg-paper/70 p-3 dark:border-white/14 dark:bg-slate-900/70"
            key={fact.fact_id}
          >
            <p className="break-words text-sm font-semibold leading-5 [overflow-wrap:anywhere]">
              {fact.entity || "-"} · {fact.attribute || "-"}
            </p>
            <p className="mt-1 break-words text-xs leading-5 text-ink/70 [overflow-wrap:anywhere] dark:text-slate-200">
              {fact.value || "-"}
              {fact.unit ? ` ${fact.unit}` : ""}
            </p>
            {fact.normalized_value ? (
              <p className="mt-1 break-words text-[11px] text-ink/48 [overflow-wrap:anywhere] dark:text-slate-400">
                normalized: {fact.normalized_value}
              </p>
            ) : null}
            <div className="mt-2 flex flex-wrap gap-1.5">
              <Badge>{fact.chunk_id}</Badge>
              <Badge>{formatFactSpan(fact)}</Badge>
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}

function QualityFindingList({
  emptyText,
  findings,
}: {
  emptyText: string;
  findings: KnowledgeQualityFinding[];
}) {
  if (!findings.length) {
    return <EmptyBlock text={emptyText} />;
  }

  return (
    <div className="space-y-3">
      {findings
        .slice()
        .sort((left, right) => findingSeverityRank(right) - findingSeverityRank(left))
        .map((finding) => (
          <QualityFindingCard finding={finding} key={finding.finding_id} />
        ))}
    </div>
  );
}

function QualityFindingCard({ finding }: { finding: KnowledgeQualityFinding }) {
  const metadataEntries = Object.entries(finding.metadata);

  return (
    <article className="min-w-0 overflow-hidden rounded-md border border-line bg-white/70 p-4 dark:border-white/14 dark:bg-slate-950/42">
      <div className="mb-3 flex min-w-0 flex-wrap items-center gap-2">
        <span
          className={cn(
            "rounded-full px-2 py-1 text-xs font-semibold",
            severityBadgeClass(finding.severity),
          )}
        >
          {severityLabel(finding.severity)}
        </span>
        <span className="rounded-full border border-line bg-paper/70 px-2 py-1 text-xs font-medium text-ink/62 dark:border-white/14 dark:bg-slate-900 dark:text-slate-300">
          {findingKindLabel(finding.kind)}
        </span>
        {finding.status ? <Badge>{finding.status}</Badge> : null}
      </div>

      <p className="break-words text-sm font-semibold leading-6 [overflow-wrap:anywhere]">
        {finding.summary || "Finding chưa có summary."}
      </p>
      {finding.suggested_action ? (
        <p className="mt-2 break-words text-xs leading-5 text-ink/62 [overflow-wrap:anywhere] dark:text-slate-300">
          {finding.suggested_action}
        </p>
      ) : null}

      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        <DebugField label="Confidence" value={formatConfidence(finding.confidence)} />
        <DebugField label="Finding ID" value={finding.finding_id} />
      </div>

      <QualityIdChips ids={finding.chunk_ids} label="Chunks" />
      <QualityIdChips ids={finding.fact_ids} label="Facts" />

      {metadataEntries.length ? (
        <details className="mt-3 rounded-md border border-line bg-paper/70 dark:border-white/14 dark:bg-slate-900/70">
          <summary className="cursor-pointer px-3 py-2 text-xs font-semibold text-ink/62 dark:text-slate-300">
            Metadata ({metadataEntries.length})
          </summary>
          <div className="max-h-40 space-y-2 overflow-y-auto border-t border-line p-3 dark:border-white/14">
            {metadataEntries.map(([key, value]) => (
              <DebugField key={key} label={key} value={formatDebugValue(value)} />
            ))}
          </div>
        </details>
      ) : null}
    </article>
  );
}

function QualityIdChips({ ids, label }: { ids: string[]; label: string }) {
  if (!ids.length) return null;

  return (
    <div className="mt-3">
      <p className="mb-1 text-[11px] font-semibold uppercase text-ink/42 dark:text-slate-400">
        {label}
      </p>
      <div className="flex flex-wrap gap-1.5">
        {ids.map((id) => (
          <span
            className="max-w-full break-words rounded-full border border-line bg-paper/70 px-2 py-1 text-[11px] text-ink/62 [overflow-wrap:anywhere] dark:border-white/14 dark:bg-slate-900 dark:text-slate-300"
            key={id}
          >
            {id}
          </span>
        ))}
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

function SectionBadge({ metadata }: { metadata: Record<string, unknown> }) {
  const sectionPath = metadata.section_path;
  if (Array.isArray(sectionPath) && sectionPath.length > 0) {
    return (
      <Badge className="max-w-[200px] truncate" title={sectionPath.join(" > ")}>
        {sectionPath.join(" > ")}
      </Badge>
    );
  }
  return <Badge>{metadataValue(metadata, "section") ?? "main"}</Badge>;
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
        <SectionBadge metadata={result.chunk.metadata} />
      </div>
      <div className="break-words text-sm [overflow-wrap:anywhere]">
        <ReactMarkdown
          components={{
            h1: ({ children }) => (
              <h1 className="mb-1 mt-2 text-sm font-bold text-ink dark:text-slate-100">
                {children}
              </h1>
            ),
            h2: ({ children }) => (
              <h2 className="mb-1 mt-2 text-sm font-semibold text-ink dark:text-slate-100">
                {children}
              </h2>
            ),
            h3: ({ children }) => (
              <h3 className="mb-0.5 mt-1 text-xs font-semibold text-ink/80 dark:text-slate-200">
                {children}
              </h3>
            ),
            p: ({ children }) => (
              <p className="leading-6 text-ink/72 dark:text-slate-200">{children}</p>
            ),
            ul: ({ children }) => (
              <ul className="ml-3 list-disc text-ink/72 dark:text-slate-200">{children}</ul>
            ),
            ol: ({ children }) => (
              <ol className="ml-3 list-decimal text-ink/72 dark:text-slate-200">{children}</ol>
            ),
            li: ({ children }) => <li className="leading-6">{children}</li>,
          }}
          remarkPlugins={[remarkGfm]}
        >
          {result.chunk.text}
        </ReactMarkdown>
      </div>
      <ChunkMetadata metadata={result.chunk.metadata} />
    </article>
  );
}

function renderLinePieces(
  text: string,
  contentStart: number,
  lineEnd: number,
  highlights: ChunkHighlight[],
  lineIdx: number,
): ReactNode[] {
  const pieces: ReactNode[] = [];
  let cursor = contentStart;
  for (const h of highlights) {
    if (h.start >= lineEnd || h.end <= contentStart) continue;
    const hStart = Math.max(h.start, contentStart);
    const hEnd = Math.min(h.end, lineEnd);
    if (hStart > cursor) {
      pieces.push(<span key={`gap-${lineIdx}-${cursor}`}>{text.slice(cursor, hStart)}</span>);
    }
    if (hEnd > hStart) {
      pieces.push(
        <mark
          className={cn("rounded px-0.5 text-inherit", h.style.text)}
          key={`${h.key}-l${lineIdx}`}
          title={`Chunk ${h.rank}: ${h.chunkId}`}
        >
          {text.slice(hStart, hEnd)}
        </mark>,
      );
      cursor = hEnd;
    }
  }
  if (cursor < lineEnd) {
    pieces.push(<span key={`tail-${lineIdx}-${cursor}`}>{text.slice(cursor, lineEnd)}</span>);
  }
  return pieces;
}

function MarkdownPieces({
  highlights,
  text,
}: {
  highlights: ChunkHighlight[];
  text: string;
}) {
  const lines = text.split("\n");
  const elements: ReactNode[] = [];
  let charPos = 0;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const lineStart = charPos;
    const lineEnd = charPos + line.length;
    charPos += line.length + 1;

    if (line.trim() === "") {
      elements.push(<div className="h-3" key={`blank-${i}`} />);
      continue;
    }

    const headingMatch = /^(#{1,6})\s+/.exec(line);
    const isBullet = /^[-*+]\s/.test(line);
    const contentStart = headingMatch
      ? lineStart + headingMatch[0].length
      : isBullet
        ? lineStart + 2
        : lineStart;
    const pieces = renderLinePieces(text, contentStart, lineEnd, highlights, i);

    if (headingMatch) {
      const level = headingMatch[1].length;
      const cls =
        level === 1
          ? "mt-3 text-sm font-bold text-ink dark:text-slate-100"
          : level === 2
            ? "mt-2 text-xs font-semibold text-ink dark:text-slate-100"
            : "mt-1 text-xs font-medium text-ink/80 dark:text-slate-200";
      elements.push(
        <div className={cls} key={i}>
          {pieces}
        </div>,
      );
    } else if (isBullet) {
      elements.push(
        <div className="flex gap-1.5 leading-6" key={i}>
          <span className="shrink-0 text-xs text-ink/40 dark:text-slate-500">•</span>
          <span className="text-xs text-ink/72 dark:text-slate-200">{pieces}</span>
        </div>,
      );
    } else {
      elements.push(
        <div className="text-xs leading-6 text-ink/72 dark:text-slate-200" key={i}>
          {pieces}
        </div>,
      );
    }
  }

  return <div className="break-words [overflow-wrap:anywhere]">{elements}</div>;
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
        <div className="rounded-md border border-line bg-white/70 p-4 [overflow-wrap:anywhere] dark:border-white/14 dark:bg-slate-950/40">
          <ReactMarkdown
            components={{
              h1: ({ children }) => (
                <h1 className="mb-2 mt-3 text-sm font-bold text-ink dark:text-slate-100">
                  {children}
                </h1>
              ),
              h2: ({ children }) => (
                <h2 className="mb-1 mt-2 text-xs font-semibold text-ink dark:text-slate-100">
                  {children}
                </h2>
              ),
              h3: ({ children }) => (
                <h3 className="mb-1 mt-1 text-xs font-medium text-ink/80 dark:text-slate-200">
                  {children}
                </h3>
              ),
              p: ({ children }) => (
                <p className="text-xs leading-6 text-ink/72 dark:text-slate-200">{children}</p>
              ),
              ul: ({ children }) => (
                <ul className="ml-3 list-disc text-xs text-ink/72 dark:text-slate-200">
                  {children}
                </ul>
              ),
              li: ({ children }) => <li className="leading-6">{children}</li>,
            }}
            remarkPlugins={[remarkGfm]}
          >
            {text}
          </ReactMarkdown>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="rounded-md border border-line bg-white/70 p-3 text-xs leading-5 text-ink/58 dark:border-white/14 dark:bg-slate-950/40 dark:text-slate-300">
        Đã map {mappedHighlights.length}/{highlights.length} chunk lên đầu vào chunking
        {unmappedCount ? `, ${unmappedCount} chunk không tìm thấy range.` : "."}
      </div>
      <div className="rounded-md border border-line bg-white/70 p-4 [overflow-wrap:anywhere] dark:border-white/14 dark:bg-slate-950/40">
        <MarkdownPieces highlights={mappedHighlights} text={text} />
      </div>
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

function stripChunkHeadingPrefix(text: string): string {
  const m = /^#{1,6} [^\n]+\n\n/.exec(text);
  return m ? text.slice(m[0].length) : text;
}

function buildChunkHighlights(chunkInput: string, chunks: SourceChunk[]): ChunkHighlight[] {
  const normalizedChunkInput = normalizeForRange(chunkInput);
  let normalizedCursor = 0;

  return chunks.map((result, index) => {
    const style = CHUNK_HIGHLIGHT_STYLES[index % CHUNK_HIGHLIGHT_STYLES.length];

    // Fast path: use stored character offsets when available (new chunks)
    const rangeValue = result.chunk.metadata?.chunk_input_range;
    if (
      Array.isArray(rangeValue) &&
      typeof rangeValue[0] === "number" &&
      typeof rangeValue[1] === "number"
    ) {
      const start = rangeValue[0] as number;
      const end = rangeValue[1] as number;
      return {
        chunkId: result.chunk.chunk_id,
        end,
        key: chunkKey(result, index),
        mapped: start >= 0 && end > start && end <= chunkInput.length,
        rank: result.rank,
        start,
        style,
      };
    }

    // Fallback: text search for chunks without chunk_input_range (old ingested data)
    const chunkTextForMapping =
      typeof result.chunk.metadata?.raw_text === "string" && result.chunk.metadata.raw_text.trim()
        ? result.chunk.metadata.raw_text
        : stripChunkHeadingPrefix(result.chunk.text);
    const normalizedChunk = normalizeForRange(chunkTextForMapping).text.trim();
    let start = -1;
    let end = -1;

    if (normalizedChunk) {
      const afterCursor = normalizedChunkInput.text.indexOf(normalizedChunk, normalizedCursor);
      const foundAt =
        afterCursor >= 0 ? afterCursor : normalizedChunkInput.text.indexOf(normalizedChunk);
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
  const chunkInputType = debug.chunk_input_type;

  if (sourceType === "url" && chunkInputType === "markdown_cleaned") {
    return "URL này dùng parsed HTML sections làm đầu vào chunking; cột giữa đang hiển thị đúng nội dung trước khi tách chunk.";
  }
  if (sourceType === "url" && chunkInputType === "parsed_sections") {
    return "URL này được upload bằng chunker cũ. Nạp lại URL để dùng markdown-aware chunking mới.";
  }
  if (sourceType === "pdf") {
    return "PDF này dùng Markdown parse làm đầu vào chunking; section trong metadata là heading gần nhất trong Markdown.";
  }
  return null;
}

function debugLabelsForSource(sourceType: string, chunkInputType = "") {
  const normalizedType = sourceType.toLowerCase();
  const isNewUrlChunking = chunkInputType === "markdown_cleaned";
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
      chunkInputTitle: isNewUrlChunking ? "Cleaned Markdown" : "Parsed HTML sections",
      chunkInputDescription: isNewUrlChunking
        ? "Markdown đã lọc boilerplate, đầu vào cho chunk_markdown_by_sections"
        : "Nội dung HTML đã clean và chia section trước khi chunk",
      chunksDescription: isNewUrlChunking
        ? "Chunks theo heading structure (section_path)"
        : "Các đoạn được tách từ parsed HTML sections",
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

function findingKindLabel(kind: KnowledgeQualityFindingKind): string {
  if (kind === "exact_duplicate") return "Exact duplicate";
  if (kind === "near_duplicate") return "Near duplicate";
  return "Conflict";
}

function severityLabel(severity: KnowledgeQualitySeverity): string {
  if (severity === "critical") return "Critical";
  if (severity === "warning") return "Warning";
  return "Info";
}

function severityBadgeClass(severity: KnowledgeQualitySeverity): string {
  if (severity === "critical") {
    return "bg-danger/12 text-danger dark:bg-red-300/14 dark:text-red-200";
  }
  if (severity === "warning") {
    return "bg-amber-100 text-amber-800 dark:bg-amber-300/18 dark:text-amber-100";
  }
  return "bg-mint/10 text-mint dark:bg-emerald-300/12 dark:text-emerald-200";
}

function findingSeverityRank(finding: KnowledgeQualityFinding): number {
  if (finding.severity === "critical") return 3;
  if (finding.severity === "warning") return 2;
  return 1;
}

function formatConfidence(value?: number | null): string {
  if (typeof value !== "number" || Number.isNaN(value)) return "-";
  const percent = value <= 1 ? value * 100 : value;
  return `${Math.round(percent)}%`;
}

function formatFactSpan(fact: KnowledgeQualityFact): string {
  if (fact.span) return fact.span;
  if (typeof fact.start === "number" && typeof fact.end === "number") {
    return `${fact.start}-${fact.end}`;
  }
  return "no span";
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

function readCachedSourceDebug(documentId: string): SourceDebugResponse | null {
  if (typeof window === "undefined" || !documentId) return null;

  try {
    const raw = window.sessionStorage.getItem(sourceDebugCacheKey(documentId));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as SourceDebugResponse;
    if (parsed.document_id !== documentId || !Array.isArray(parsed.chunks)) {
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

function writeCachedSourceDebug(documentId: string, debug: SourceDebugResponse) {
  if (typeof window === "undefined" || !documentId) return;

  try {
    window.sessionStorage.setItem(sourceDebugCacheKey(documentId), JSON.stringify(debug));
  } catch {
    // Large debug payloads can exceed sessionStorage quota; the page still works without cache.
  }
}

function sourceDebugCacheKey(documentId: string): string {
  return `${SOURCE_DEBUG_CACHE_PREFIX}${documentId}`;
}

function readCachedKnowledgeQuality(documentId: string): KnowledgeQualityReport | null {
  if (typeof window === "undefined" || !documentId) return null;

  try {
    const raw = window.sessionStorage.getItem(sourceQualityCacheKey(documentId));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as KnowledgeQualityReport;
    if (!Array.isArray(parsed.facts) || !Array.isArray(parsed.findings)) {
      return null;
    }
    return {
      facts: parsed.facts,
      findings: parsed.findings,
      metadata:
        parsed.metadata && typeof parsed.metadata === "object" && !Array.isArray(parsed.metadata)
          ? parsed.metadata
          : {},
    };
  } catch {
    return null;
  }
}

function writeCachedKnowledgeQuality(documentId: string, report: KnowledgeQualityReport) {
  if (typeof window === "undefined" || !documentId) return;

  try {
    window.sessionStorage.setItem(sourceQualityCacheKey(documentId), JSON.stringify(report));
  } catch {
    // Large reports can exceed sessionStorage quota; the page still works without cache.
  }
}

function sourceQualityCacheKey(documentId: string): string {
  return `${SOURCE_QUALITY_CACHE_PREFIX}${documentId}`;
}

function sourceErrorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  return "Không thể tải source debug.";
}
