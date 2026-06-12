"use client";

import { useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  ArrowRight,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  DatabaseZap,
  FileText,
  Loader2,
  RefreshCw,
  Search,
  ShieldCheck,
} from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

const API = process.env.NEXT_PUBLIC_AGENTIC_RAG_API_URL ?? "http://localhost:8000";
// Fetch tất cả pairs rồi group client-side — Neon trả về 2 k rows < 50 ms.
const FETCH_LIMIT = 2000;
const GROUP_PAGE_SIZE = 25;

type DedupChunk = {
  chunk_id: string;
  document_id: string | null;
  document_name: string | null;
  source_type: string | null;
  source: string | null;
  page: unknown;
  section: unknown;
  text: string;
};

type DedupItem = {
  id: string;
  status: string;
  review_status: string;
  layer: string;
  score: unknown;
  distance: unknown;
  reason: unknown;
  group_id: unknown;
  canonical: DedupChunk | null;
  duplicate: DedupChunk;
};

type DedupGroup = {
  id: string;
  duplicate: DedupChunk;
  topLayer: string;
  pairs: DedupItem[];
};

type DedupCounts = {
  pairs: number;
  unique_candidates: number;
  exact: number;
  simhash: number;
  embedding: number;
  exact_chunks: number;
  simhash_chunks: number;
  embedding_chunks: number;
  corpus_chunks: number;
  corpus_documents: number;
};

type DedupResponse = {
  provider: string;
  total: number;
  limit: number;
  offset: number;
  counts: DedupCounts;
  items: DedupItem[];
};

const LAYER_ORDER: Record<string, number> = {
  exact_sha256: 0,
  simhash: 1,
  embedding_similarity: 2,
};

const LAYER_META: Record<string, { label: string; badge: string; dot: string }> = {
  exact_sha256: {
    label: "Exact",
    badge: "border-rose-200 bg-rose-50 text-rose-700",
    dot: "bg-rose-500",
  },
  simhash: {
    label: "SimHash",
    badge: "border-amber-200 bg-amber-50 text-amber-700",
    dot: "bg-amber-500",
  },
  embedding_similarity: {
    label: "Embedding",
    badge: "border-sky-200 bg-sky-50 text-sky-700",
    dot: "bg-sky-500",
  },
};

const SOURCE_TYPES = [
  { value: "", label: "Mọi nguồn" },
  { value: "pdf", label: "PDF" },
  { value: "url", label: "URL" },
  { value: "text", label: "Text" },
];

function layerRank(layer: string): number {
  return LAYER_ORDER[layer] ?? 99;
}

function groupItems(items: DedupItem[]): DedupGroup[] {
  const map = new Map<string, DedupGroup>();
  for (const item of items) {
    const key = item.duplicate.chunk_id;
    const existing = map.get(key);
    if (existing) {
      existing.pairs.push(item);
      if (layerRank(item.layer) < layerRank(existing.topLayer)) {
        existing.topLayer = item.layer;
      }
    } else {
      map.set(key, { id: key, duplicate: item.duplicate, topLayer: item.layer, pairs: [item] });
    }
  }
  return Array.from(map.values()).sort((a, b) => {
    const ld = layerRank(a.topLayer) - layerRank(b.topLayer);
    if (ld !== 0) return ld;
    return b.pairs.length - a.pairs.length;
  });
}

export default function DedupReviewPage() {
  const [data, setData] = useState<DedupResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [rebuilding, setRebuilding] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [layer, setLayer] = useState("");
  const [sourceType, setSourceType] = useState("");
  const [query, setQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set());
  const [groupOffset, setGroupOffset] = useState(0);

  // Đọc ?layer= từ URL khi mở (deep-link từ trang Tạo câu hỏi)
  useEffect(() => {
    if (globalThis.window === undefined) return;
    const fromUrl = new URLSearchParams(globalThis.location.search).get("layer");
    if (fromUrl) setLayer(fromUrl);
  }, []);

  useEffect(() => {
    const handle = setTimeout(() => setDebouncedQuery(query.trim()), 350);
    return () => clearTimeout(handle);
  }, [query]);

  useEffect(() => {
    const params = new URLSearchParams();
    params.set("limit", String(FETCH_LIMIT));
    params.set("offset", "0");
    if (layer) params.set("layer", layer);
    if (sourceType) params.set("source_type", sourceType);
    if (debouncedQuery) params.set("q", debouncedQuery);

    setLoading(true);
    setError(null);
    fetch(`${API}/internal/dedup?${params.toString()}`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((payload: DedupResponse) => {
        setData(payload);
        setExpandedGroups(new Set());
        setGroupOffset(0);
      })
      .catch((error_: Error) => setError(error_.message))
      .finally(() => setLoading(false));
  }, [layer, sourceType, debouncedQuery, refreshKey]);

  const counts = data?.counts;
  const total = data?.total ?? 0;
  const items = useMemo(() => data?.items ?? [], [data]);
  const groups = useMemo(() => groupItems(items), [items]);

  const displayedGroups = groups.slice(groupOffset, groupOffset + GROUP_PAGE_SIZE);
  const groupTotal = groups.length;
  const groupPageStart = groupTotal === 0 ? 0 : groupOffset + 1;
  const groupPageEnd = Math.min(groupOffset + GROUP_PAGE_SIZE, groupTotal);
  const truncated = total > items.length;

  const setLayerFilter = (value: string) => {
    setLayer((current) => (current === value ? "" : value));
    setGroupOffset(0);
  };

  const toggleGroup = (id: string) => {
    setExpandedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const rebuildIndex = async () => {
    if (rebuilding) return;
    const confirmed = globalThis.confirm(
      "Quét lại toàn bộ chunk từ S3 để dựng lại chỉ mục? Mất vài phút.",
    );
    if (!confirmed) return;
    setRebuilding(true);
    try {
      const response = await fetch(`${API}/internal/dedup/rebuild`, { method: "POST" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const payload = await response.json();
      toast.success(
        `Đã dựng lại chỉ mục: ${payload.candidate_rows} cặp từ ${payload.chunk_count} chunks.`,
      );
      setGroupOffset(0);
      setRefreshKey((v) => v + 1);
    } catch (error_) {
      toast.error(`Dựng lại chỉ mục thất bại: ${(error_ as Error).message}`);
    } finally {
      setRebuilding(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">Dedup</h1>
          <p className="text-sm text-gray-500 mt-1">
            Rà soát các chunk nghi trùng lặp — chỉ đánh dấu, không xóa dữ liệu.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={rebuildIndex}
            disabled={rebuilding}
            title="Đọc lại toàn bộ chunk từ S3 và dựng lại chỉ mục — chỉ cần khi dữ liệu lệch."
            className="inline-flex items-center gap-2 rounded-md border border-black/10 bg-white px-3 py-2 text-sm text-gray-600 hover:bg-gray-50 disabled:opacity-50 pressable"
          >
            {rebuilding ? <Loader2 size={14} className="animate-spin" /> : <DatabaseZap size={14} />}
            {rebuilding ? "Đang quét S3..." : "Quét lại từ S3"}
          </button>
          <button
            onClick={() => setRefreshKey((v) => v + 1)}
            disabled={loading}
            className="inline-flex items-center gap-2 rounded-md border border-black/10 bg-white px-3 py-2 text-sm text-gray-600 hover:bg-gray-50 disabled:opacity-50 pressable"
          >
            <RefreshCw size={14} className={cn(loading && "animate-spin")} />
            Làm mới
          </button>
        </div>
      </div>

      {/* Stats — 2 hàng: tổng quan corpus | breakdown theo layer */}
      <div className="space-y-2">
        {/* Hàng 1: corpus overview */}
        <div className="flex flex-wrap items-stretch divide-x divide-black/6 rounded-lg border border-black/8 bg-white">
          <StatCell
            label="Tổng tài liệu"
            value={counts?.corpus_documents ?? 0}
          />
          <StatCell
            label="Tổng chunk"
            value={counts?.corpus_chunks ?? 0}
          />
          <StatCell
            label="Chunk bị trùng"
            value={counts?.unique_candidates ?? 0}
            sub={`${counts?.pairs ?? 0} cặp`}
            active={layer === ""}
            onClick={() => setLayerFilter("")}
          />
        </div>
        {/* Hàng 2: breakdown per layer — số chunk trùng (số cặp) */}
        <div className="flex flex-wrap items-stretch divide-x divide-black/6 rounded-lg border border-black/8 bg-white">
          <StatCell
            label="Layer 1 · Exact"
            value={counts?.exact_chunks ?? 0}
            sub={`${counts?.exact ?? 0} cặp`}
            dot="bg-rose-500"
            active={layer === "exact_sha256"}
            onClick={() => setLayerFilter("exact_sha256")}
          />
          <StatCell
            label="Layer 2 · SimHash"
            value={counts?.simhash_chunks ?? 0}
            sub={`${counts?.simhash ?? 0} cặp`}
            dot="bg-amber-500"
            active={layer === "simhash"}
            onClick={() => setLayerFilter("simhash")}
          />
          <StatCell
            label="Layer 3 · Embedding"
            value={counts?.embedding_chunks ?? 0}
            sub={`${counts?.embedding ?? 0} cặp`}
            dot="bg-sky-500"
            active={layer === "embedding_similarity"}
            onClick={() => setLayerFilter("embedding_similarity")}
          />
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <div className="relative min-w-[240px] flex-1">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setGroupOffset(0);
            }}
            placeholder="Tìm theo tên tài liệu, chunk id, nội dung..."
            className="w-full rounded-md border border-black/10 bg-white py-2 pl-9 pr-3 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500/30"
          />
        </div>
        <select
          value={sourceType}
          onChange={(e) => {
            setSourceType(e.target.value);
            setGroupOffset(0);
          }}
          className="rounded-md border border-black/10 bg-white px-3 py-2 text-sm text-gray-600 focus:outline-none focus:ring-2 focus:ring-emerald-500/30"
        >
          {SOURCE_TYPES.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </div>

      {truncated && !loading && (
        <div className="flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-4 py-2.5 text-xs text-amber-700">
          <AlertCircle size={13} />
          Đang hiển thị {items.length.toLocaleString()}/{total.toLocaleString()} cặp đầu tiên. Dùng bộ lọc để thu hẹp kết quả.
        </div>
      )}

      {loading && (
        <div className="flex h-44 items-center justify-center gap-2 rounded-lg border border-black/8 bg-white text-sm text-gray-400">
          <Loader2 size={16} className="animate-spin" />
          Đang tải...
        </div>
      )}

      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          <AlertCircle size={16} />
          Không tải được dữ liệu: {error}
        </div>
      )}

      {!loading && !error && groups.length === 0 && (
        <div className="flex h-44 flex-col items-center justify-center gap-1 rounded-lg border border-black/8 bg-white text-sm text-gray-400">
          <p>Không có chunk trùng nào khớp bộ lọc.</p>
          {total === 0 && (counts?.pairs ?? 0) === 0 && (
            <p className="text-xs">
              Nếu vừa chạy backfill mà chưa thấy dữ liệu, bấm &quot;Quét lại từ S3&quot;.
            </p>
          )}
        </div>
      )}

      {!loading && !error && displayedGroups.length > 0 && (
        <div className="space-y-3">
          <div className="overflow-hidden rounded-lg border border-black/8 bg-white divide-y divide-black/6">
            {displayedGroups.map((group) => (
              <GroupRow
                key={group.id}
                group={group}
                expanded={expandedGroups.has(group.id)}
                onToggle={() => toggleGroup(group.id)}
              />
            ))}
          </div>

          <div className="flex items-center justify-between gap-3">
            <p className="text-xs text-gray-500 tabular-nums">
              {groupPageStart}–{groupPageEnd} / {groupTotal} chunk · {total.toLocaleString()} cặp
            </p>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setGroupOffset(Math.max(groupOffset - GROUP_PAGE_SIZE, 0))}
                disabled={groupOffset === 0}
                className="inline-flex items-center gap-1 rounded-md border border-black/10 bg-white px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-50 disabled:opacity-40 pressable"
              >
                <ChevronLeft size={14} />
                Trước
              </button>
              <button
                onClick={() => setGroupOffset(groupOffset + GROUP_PAGE_SIZE)}
                disabled={groupPageEnd >= groupTotal}
                className="inline-flex items-center gap-1 rounded-md border border-black/10 bg-white px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-50 disabled:opacity-40 pressable"
              >
                Sau
                <ChevronRight size={14} />
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function StatCell({
  label,
  value,
  sub,
  dot,
  active = false,
  onClick,
}: Readonly<{
  label: string;
  value: number;
  sub?: string;
  dot?: string;
  active?: boolean;
  onClick?: () => void;
}>) {
  const Tag = onClick ? "button" : "div";
  return (
    <Tag
      onClick={onClick}
      className={cn(
        "flex min-w-[140px] flex-1 items-center gap-3 px-4 py-3 text-left",
        onClick && "cursor-pointer transition-colors hover:bg-gray-50",
        active && onClick && "bg-emerald-50/60",
      )}
    >
      {dot && <span className={cn("h-2 w-2 shrink-0 rounded-full", dot)} />}
      <div>
        <p className="text-lg font-semibold leading-tight text-gray-900 tabular-nums">{value}</p>
        <p className="text-[11px] text-gray-500">{label}</p>
        {sub && <p className="text-[10px] text-gray-400 tabular-nums">{sub}</p>}
      </div>
    </Tag>
  );
}

function GroupRow({
  group,
  expanded,
  onToggle,
}: Readonly<{
  group: DedupGroup;
  expanded: boolean;
  onToggle: () => void;
}>) {
  const meta = LAYER_META[group.topLayer];
  const matchCount = group.pairs.length;

  return (
    <div>
      <button
        onClick={onToggle}
        className="grid w-full grid-cols-[auto_auto_1fr_auto_auto_auto] items-center gap-3 px-4 py-2.5 text-left transition-colors hover:bg-gray-50/70"
      >
        <span
          className={cn(
            "inline-flex shrink-0 rounded-full border px-2 py-0.5 text-[11px] font-medium",
            meta?.badge ?? "border-gray-200 bg-gray-50 text-gray-600",
          )}
        >
          {meta?.label ?? group.topLayer}
        </span>
        <FileText size={13} className="shrink-0 text-amber-600" />
        <span
          className="min-w-0 truncate text-sm font-medium text-gray-800"
          title={docLabel(group.duplicate)}
        >
          {docLabel(group.duplicate)}
        </span>
        <ArrowRight size={13} className="shrink-0 text-gray-300" />
        <span className="shrink-0 whitespace-nowrap text-sm text-gray-500">
          {matchCount} tài liệu trùng
        </span>
        <ChevronDown
          size={14}
          className={cn("shrink-0 text-gray-400 transition-transform", expanded && "rotate-180")}
        />
      </button>

      {expanded && (
        <div className="divide-y divide-black/5 border-t border-black/6 bg-gray-50/40">
          {group.pairs.map((pair) => (
            <PairSubRow key={pair.id} pair={pair} />
          ))}
        </div>
      )}
    </div>
  );
}

function PairSubRow({ pair }: Readonly<{ pair: DedupItem }>) {
  const [open, setOpen] = useState(false);
  const meta = LAYER_META[pair.layer];

  return (
    <div>
      <button
        onClick={() => setOpen((v) => !v)}
        className="grid w-full grid-cols-[auto_auto_1fr_auto_auto] items-center gap-3 px-6 py-2 text-left transition-colors hover:bg-gray-50"
      >
        <span
          className={cn(
            "inline-flex shrink-0 rounded-full border px-1.5 py-0.5 text-[10px] font-medium",
            meta?.badge ?? "border-gray-200 bg-gray-50 text-gray-600",
          )}
        >
          {meta?.label ?? pair.layer}
        </span>
        <ShieldCheck size={12} className="shrink-0 text-emerald-600" />
        <span
          className="min-w-0 truncate text-sm text-gray-600"
          title={docLabel(pair.canonical)}
        >
          {docLabel(pair.canonical)}
        </span>
        <span className="shrink-0 text-xs text-gray-400 tabular-nums">{metricLabel(pair)}</span>
        <ChevronDown
          size={12}
          className={cn("shrink-0 text-gray-300 transition-transform", open && "rotate-180")}
        />
      </button>

      {open && (
        <div className="grid gap-0 border-t border-black/5 bg-white md:grid-cols-2">
          <ChunkPane title="Bản gốc (giữ lại)" chunk={pair.canonical} tone="canonical" />
          <ChunkPane title="Bản trùng (gắn cờ)" chunk={pair.duplicate} tone="duplicate" />
        </div>
      )}
    </div>
  );
}

function ChunkPane({
  title,
  chunk,
  tone,
}: Readonly<{
  title: string;
  chunk: DedupChunk | null;
  tone: "canonical" | "duplicate";
}>) {
  if (!chunk) {
    return (
      <section className="px-4 py-4 md:border-l md:border-black/6">
        <p className="text-sm text-gray-400">Chunk gốc không còn tồn tại.</p>
      </section>
    );
  }
  return (
    <section className={cn("px-4 py-4", tone === "duplicate" && "md:border-l md:border-black/6")}>
      <div className="mb-2 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          {tone === "canonical" ? (
            <ShieldCheck size={14} className="text-emerald-600" />
          ) : (
            <FileText size={14} className="text-amber-600" />
          )}
          <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-600">{title}</h3>
        </div>
        <span className="rounded bg-gray-100 px-2 py-0.5 text-[11px] text-gray-500">
          {chunk.source_type ?? "source"}
        </span>
      </div>
      <div className="space-y-0.5 text-xs text-gray-500">
        <p className="truncate" title={chunk.source ?? undefined}>
          <span className="font-medium text-gray-700">
            {chunk.document_name ?? chunk.document_id}
          </span>
        </p>
        <p className="truncate">
          {chunk.section ? `Mục: ${toStr(chunk.section)}` : null}
          {chunk.page ? ` · Trang ${toStr(chunk.page)}` : null}
        </p>
        <p className="truncate font-mono text-[11px] text-gray-400">{chunk.chunk_id}</p>
      </div>
      <p className="mt-2 max-h-44 overflow-y-auto whitespace-pre-wrap rounded-md border border-black/6 bg-white px-3 py-2 text-sm leading-relaxed text-gray-700">
        {chunk.text}
      </p>
    </section>
  );
}

function toStr(val: unknown): string {
  if (val === null || val === undefined) return "";
  if (typeof val === "string" || typeof val === "number" || typeof val === "boolean") {
    return String(val);
  }
  return "";
}

function docLabel(chunk: DedupChunk | null): string {
  if (!chunk) return "(không còn tồn tại)";
  return chunk.document_name ?? chunk.document_id ?? chunk.chunk_id;
}

function metricLabel(item: DedupItem) {
  const score =
    typeof item.score === "number" ? item.score.toFixed(4) : (toStr(item.score) || "-");
  if (item.layer === "simhash") {
    return `d=${toStr(item.distance) || "-"} · ${score}`;
  }
  return score;
}
