"use client";

import { useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  AlertTriangle,
  ChevronLeft,
  ChevronRight,
  FileText,
  Loader2,
  RefreshCw,
  Search,
} from "lucide-react";
import { cn } from "@/lib/utils";

const API = process.env.NEXT_PUBLIC_AGENTIC_RAG_API_URL ?? "http://localhost:8000";
const PAGE_SIZE = 25;

type ConflictSide = {
  chunk_id: string;
  document_id: string | null;
  document_name: string | null;
  source_type: string | null;
  source: string | null;
  page: unknown;
  section: unknown;
  text: string;
  value: string | null;
};

type ConflictItem = {
  id: string;
  conflict_type: string;
  attribute: string | null;
  entity: string | null;
  severity: string;
  confidence: number | null;
  summary: string | null;
  suggested_action: string | null;
  review_status: string;
  left: ConflictSide | null;
  right: ConflictSide | null;
};

type ConflictCounts = {
  findings: number;
  entities: number;
  warranty_duration: number;
  duration: number;
  price: number;
  distance_km: number;
  date: number;
  corpus_chunks: number;
  corpus_documents: number;
};

type ConflictResponse = {
  provider: string;
  total: number;
  limit: number;
  offset: number;
  counts: ConflictCounts;
  items: ConflictItem[];
};

// Nhãn + màu cho từng loại thuộc tính số bị mâu thuẫn (tầng deterministic_v1).
const ATTRIBUTE_META: Record<string, { label: string; badge: string; dot: string; field: keyof ConflictCounts }> = {
  warranty_duration: { label: "Bảo hành", badge: "border-violet-200 bg-violet-50 text-violet-700", dot: "bg-violet-500", field: "warranty_duration" },
  duration:          { label: "Thời lượng", badge: "border-indigo-200 bg-indigo-50 text-indigo-700", dot: "bg-indigo-500", field: "duration" },
  price:             { label: "Giá",       badge: "border-emerald-200 bg-emerald-50 text-emerald-700", dot: "bg-emerald-500", field: "price" },
  distance_km:       { label: "Quãng đường", badge: "border-sky-200 bg-sky-50 text-sky-700", dot: "bg-sky-500", field: "distance_km" },
  date:              { label: "Ngày/năm",  badge: "border-amber-200 bg-amber-50 text-amber-700", dot: "bg-amber-500", field: "date" },
};

const ATTRIBUTE_ORDER = ["warranty_duration", "price", "distance_km", "duration", "date"] as const;

export default function ConflictReviewPage() {
  const [data, setData] = useState<ConflictResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [attribute, setAttribute] = useState("");
  const [query, setQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    const handle = setTimeout(() => setDebouncedQuery(query.trim()), 350);
    return () => clearTimeout(handle);
  }, [query]);

  useEffect(() => {
    const params = new URLSearchParams();
    params.set("limit", String(PAGE_SIZE));
    params.set("offset", String(offset));
    if (attribute) params.set("attribute", attribute);
    if (debouncedQuery) params.set("q", debouncedQuery);

    setLoading(true);
    setError(null);
    fetch(`${API}/internal/conflicts?${params.toString()}`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((payload: ConflictResponse) => setData(payload))
      .catch((error_: Error) => setError(error_.message))
      .finally(() => setLoading(false));
  }, [attribute, debouncedQuery, offset, refreshKey]);

  const counts = data?.counts;
  const total = data?.total ?? 0;
  const items = useMemo(() => data?.items ?? [], [data]);

  const pageStart = total === 0 ? 0 : offset + 1;
  const pageEnd = Math.min(offset + PAGE_SIZE, total);

  const setAttributeFilter = (value: string) => {
    setAttribute((current) => (current === value ? "" : value));
    setOffset(0);
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">Conflict</h1>
          <p className="text-sm text-gray-500 mt-1">
            Rà soát các chunk mâu thuẫn về số liệu (bảo hành, giá, quãng đường, ngày) — chỉ cảnh báo, không xóa.
          </p>
        </div>
        <button
          onClick={() => setRefreshKey((v) => v + 1)}
          disabled={loading}
          className="inline-flex items-center gap-2 rounded-md border border-black/10 bg-white px-3 py-2 text-sm text-gray-600 hover:bg-gray-50 disabled:opacity-50 pressable"
        >
          <RefreshCw size={14} className={cn(loading && "animate-spin")} />
          Làm mới
        </button>
      </div>

      {/* Stats — corpus overview + breakdown theo loại số mâu thuẫn */}
      <div className="space-y-2">
        <div className="flex flex-wrap items-stretch divide-x divide-black/6 rounded-lg border border-black/8 bg-white">
          <StatCell label="Tổng tài liệu" value={counts?.corpus_documents ?? 0} />
          <StatCell label="Tổng chunk" value={counts?.corpus_chunks ?? 0} />
          <StatCell
            label="Tổng mâu thuẫn"
            value={counts?.findings ?? 0}
            sub={`${counts?.entities ?? 0} thực thể`}
            active={attribute === ""}
            onClick={() => setAttributeFilter("")}
          />
        </div>
        <div className="flex flex-wrap items-stretch divide-x divide-black/6 rounded-lg border border-black/8 bg-white">
          {ATTRIBUTE_ORDER.map((key) => {
            const meta = ATTRIBUTE_META[key];
            return (
              <StatCell
                key={key}
                label={meta.label}
                value={counts?.[meta.field] ?? 0}
                dot={meta.dot}
                active={attribute === key}
                onClick={() => setAttributeFilter(key)}
              />
            );
          })}
        </div>
      </div>

      <div className="relative min-w-[240px]">
        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
        <input
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setOffset(0);
          }}
          placeholder="Tìm theo thực thể, tên tài liệu, nội dung..."
          className="w-full rounded-md border border-black/10 bg-white py-2 pl-9 pr-3 text-sm focus:outline-none focus:ring-2 focus:ring-rose-500/30"
        />
      </div>

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

      {!loading && !error && items.length === 0 && (
        <div className="flex h-44 flex-col items-center justify-center gap-1 rounded-lg border border-black/8 bg-white text-sm text-gray-400">
          <p>Không có mâu thuẫn nào khớp bộ lọc.</p>
          {total === 0 && (counts?.findings ?? 0) === 0 && (
            <p className="text-xs">
              Nếu chưa có dữ liệu, chạy <span className="font-mono">python scripts/scan_conflicts.py</span>.
            </p>
          )}
        </div>
      )}

      {!loading && !error && items.length > 0 && (
        <div className="space-y-3">
          <div className="space-y-3">
            {items.map((item) => (
              <ConflictCard key={item.id} item={item} />
            ))}
          </div>

          <div className="flex items-center justify-between gap-3">
            <p className="text-xs text-gray-500 tabular-nums">
              {pageStart}–{pageEnd} / {total.toLocaleString()} mâu thuẫn
            </p>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setOffset(Math.max(offset - PAGE_SIZE, 0))}
                disabled={offset === 0}
                className="inline-flex items-center gap-1 rounded-md border border-black/10 bg-white px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-50 disabled:opacity-40 pressable"
              >
                <ChevronLeft size={14} />
                Trước
              </button>
              <button
                onClick={() => setOffset(offset + PAGE_SIZE)}
                disabled={pageEnd >= total}
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

function ConflictCard({ item }: Readonly<{ item: ConflictItem }>) {
  const meta = item.attribute ? ATTRIBUTE_META[item.attribute] : undefined;
  return (
    <div className="overflow-hidden rounded-lg border border-rose-200/70 bg-white">
      <div className="flex flex-wrap items-center gap-2 border-b border-black/6 bg-rose-50/50 px-4 py-2.5">
        <AlertTriangle size={14} className="shrink-0 text-rose-500" />
        <span className="text-sm font-semibold text-gray-800">{item.entity ?? "—"}</span>
        <span
          className={cn(
            "inline-flex shrink-0 rounded-full border px-2 py-0.5 text-[11px] font-medium",
            meta?.badge ?? "border-gray-200 bg-gray-50 text-gray-600",
          )}
        >
          {meta?.label ?? item.attribute ?? item.conflict_type}
        </span>
        {item.confidence != null && (
          <span className="ml-auto text-[11px] text-gray-400 tabular-nums">
            độ tin {Math.round(item.confidence * 100)}%
          </span>
        )}
      </div>

      {item.summary && (
        <p className="px-4 pt-3 text-sm text-gray-700">{item.summary}</p>
      )}

      <div className="grid gap-0 px-1 py-3 md:grid-cols-2">
        <SidePane side={item.left} label="Nguồn A" />
        <SidePane side={item.right} label="Nguồn B" divider />
      </div>

      {item.suggested_action && (
        <p className="border-t border-black/6 bg-gray-50/60 px-4 py-2 text-xs text-gray-500">
          💡 {item.suggested_action}
        </p>
      )}
    </div>
  );
}

function SidePane({
  side,
  label,
  divider = false,
}: Readonly<{ side: ConflictSide | null; label: string; divider?: boolean }>) {
  if (!side) {
    return (
      <section className={cn("px-4 py-2", divider && "md:border-l md:border-black/6")}>
        <p className="text-sm text-gray-400">Chunk không còn tồn tại.</p>
      </section>
    );
  }
  return (
    <section className={cn("px-4 py-2", divider && "md:border-l md:border-black/6")}>
      <div className="mb-2 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <FileText size={13} className="text-gray-400" />
          <h3 className="text-[11px] font-semibold uppercase tracking-wide text-gray-500">{label}</h3>
        </div>
        {side.value && (
          <span className="rounded-md border border-rose-200 bg-rose-50 px-2 py-0.5 text-xs font-semibold text-rose-700">
            {side.value}
          </span>
        )}
      </div>
      <div className="space-y-0.5 text-xs text-gray-500">
        <p className="truncate" title={side.source ?? undefined}>
          <span className="font-medium text-gray-700">{side.document_name ?? side.document_id}</span>
        </p>
        <p className="truncate">
          {side.section ? `Mục: ${toStr(side.section)}` : null}
          {side.page ? ` · Trang ${toStr(side.page)}` : null}
        </p>
        <p className="truncate font-mono text-[11px] text-gray-400">{side.chunk_id}</p>
      </div>
      <p className="mt-2 max-h-40 overflow-y-auto whitespace-pre-wrap rounded-md border border-black/6 bg-white px-3 py-2 text-sm leading-relaxed text-gray-700">
        {side.text}
      </p>
    </section>
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
        "flex min-w-[120px] flex-1 items-center gap-3 px-4 py-3 text-left",
        onClick && "cursor-pointer transition-colors hover:bg-gray-50",
        active && onClick && "bg-rose-50/60",
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

function toStr(val: unknown): string {
  if (val === null || val === undefined) return "";
  if (typeof val === "string" || typeof val === "number" || typeof val === "boolean") {
    return String(val);
  }
  return "";
}
