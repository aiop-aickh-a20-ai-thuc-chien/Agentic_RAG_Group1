"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Check, ChevronLeft, Loader2, Save } from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

const API = process.env.NEXT_PUBLIC_AGENTIC_RAG_API_URL ?? "http://localhost:8000";

type RetrievalConfig = {
  hard_filter_enabled: boolean;
  metadata_boosting_enabled: boolean;
  question_index_enabled: boolean;
  entity_prefilter_llm: boolean;
  graph_retrieval_enabled: boolean;
  question_min_score: number | null;
  exclude_dedup_layers: string[];
};
type QIStatus = {
  exists: boolean;
  count: number;
  build_status: "idle" | "running" | "done" | "error";
  build_message: string;
};
type DedupStats = {
  corpus_chunks: number;
  exact_chunks: number;
  simhash_chunks: number;
  embedding_chunks: number;
};
const DEDUP_LAYERS = [
  { key: "exact_sha256", label: "L1 Exact", field: "exact_chunks" },
  { key: "simhash", label: "L2 SimHash", field: "simhash_chunks" },
  { key: "embedding_similarity", label: "L3 Embedding", field: "embedding_chunks" },
] as const;

const TOGGLES: { key: keyof RetrievalConfig; label: string; hint: string }[] = [
  { key: "hard_filter_enabled", label: "Hard filter (entity)", hint: "Lọc kết quả theo entity (model/địa điểm) phát hiện trong câu hỏi." },
  { key: "metadata_boosting_enabled", label: "Metadata boosting", hint: "Tăng/giảm điểm theo document_type × độ mới × dedup." },
  { key: "question_index_enabled", label: "Question-index retriever", hint: "Đường thứ 3 (RRF): khớp câu hỏi người dùng với câu hỏi của chunk." },
  { key: "entity_prefilter_llm", label: "LLM map entity", hint: "Khi từ điển không bắt được, dùng LLM đoán entity. Chỉ tác dụng khi hard filter bật." },
  { key: "graph_retrieval_enabled", label: "Graph retrieval (KG)", hint: "Đường RRF: liên kết câu hỏi với thực thể trong knowledge-graph (Neo4j), đi quan hệ và trộn chunk dẫn chứng." },
];

function Switch({ checked, onChange }: { checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      type="button"
      onClick={() => onChange(!checked)}
      className={cn(
        "flex h-6 w-11 shrink-0 items-center rounded-full p-0.5 transition",
        checked ? "bg-mint" : "bg-mist",
      )}
    >
      <span
        className={cn(
          "h-5 w-5 rounded-full bg-white shadow transition-transform",
          checked ? "translate-x-5" : "translate-x-0",
        )}
      />
    </button>
  );
}

export default function ConfigPage() {
  const [cfg, setCfg] = useState<RetrievalConfig | null>(null);
  const [qi, setQi] = useState<QIStatus | null>(null);
  const [dedupStats, setDedupStats] = useState<DedupStats | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [minScoreText, setMinScoreText] = useState("");
  const qiPollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    fetch(`${API}/config/retrieval`)
      .then((r) => r.json())
      .then((c: RetrievalConfig) => {
        setCfg(c);
        setMinScoreText(c.question_min_score == null ? "" : String(c.question_min_score));
      })
      .catch(() => toast.error("Không tải được cấu hình"));
    fetch(`${API}/eval-review/api/eval/question-index`)
      .then((r) => r.json())
      .then(setQi)
      .catch(() => {});
    fetch(`${API}/internal/dedup?limit=1`)
      .then((r) => (r.ok ? r.json() : null))
      .then((p) => {
        const c = p?.counts;
        if (c) {
          setDedupStats({
            corpus_chunks: c.corpus_chunks ?? 0,
            exact_chunks: c.exact_chunks ?? 0,
            simhash_chunks: c.simhash_chunks ?? 0,
            embedding_chunks: c.embedding_chunks ?? 0,
          });
        }
      })
      .catch(() => {});
    return () => {
      if (qiPollRef.current) clearInterval(qiPollRef.current);
    };
  }, []);

  const toggleDedupLayer = (key: string) => {
    setCfg((c) => {
      if (!c) return c;
      const has = c.exclude_dedup_layers.includes(key);
      return {
        ...c,
        exclude_dedup_layers: has
          ? c.exclude_dedup_layers.filter((k) => k !== key)
          : [...c.exclude_dedup_layers, key],
      };
    });
    setSaved(false);
  };

  const setFlag = (key: keyof RetrievalConfig, value: boolean) => {
    setCfg((c) => (c ? { ...c, [key]: value } : c));
    setSaved(false);
  };

  async function save() {
    if (!cfg) return;
    const raw = minScoreText.trim();
    const parsed = raw === "" ? null : Number(raw);
    if (parsed != null && (Number.isNaN(parsed) || parsed < 0 || parsed > 1)) {
      toast.error("Ngưỡng câu hỏi phải trong khoảng 0–1 (hoặc để trống)");
      return;
    }
    setSaving(true);
    try {
      const body = { ...cfg, question_min_score: parsed };
      const r = await fetch(`${API}/config/retrieval`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!r.ok) throw new Error(await r.text());
      const updated: RetrievalConfig = await r.json();
      setCfg(updated);
      setMinScoreText(updated.question_min_score == null ? "" : String(updated.question_min_score));
      setSaved(true);
      toast.success("Đã lưu cấu hình — áp dụng ngay cho chat (lưu vào .env)");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Lưu thất bại");
    } finally {
      setSaving(false);
    }
  }

  async function buildQi() {
    setQi((q) => (q ? { ...q, build_status: "running", build_message: "Đang build..." } : q));
    try {
      await fetch(`${API}/eval-review/api/eval/question-index/build`, { method: "POST" });
    } catch {
      return;
    }
    if (qiPollRef.current) clearInterval(qiPollRef.current);
    qiPollRef.current = setInterval(async () => {
      try {
        const s: QIStatus = await fetch(`${API}/eval-review/api/eval/question-index`).then((r) => r.json());
        setQi(s);
        if (s.build_status === "done" || s.build_status === "error") {
          if (qiPollRef.current) clearInterval(qiPollRef.current);
          qiPollRef.current = null;
          if (s.build_status === "done") toast.success(`Question index: ${s.count} câu hỏi`);
        }
      } catch {}
    }, 2000);
  }

  return (
    <div className="mx-auto max-w-2xl px-4 py-8">
      <div className="mb-6 flex items-center gap-3">
        <Link
          href="/citation-chat"
          className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-line bg-white text-ink/50 transition hover:bg-paper"
        >
          <ChevronLeft className="h-4 w-4" />
        </Link>
        <div>
          <h1 className="text-lg font-semibold text-ink">Cấu hình retrieval</h1>
          <p className="text-sm text-ink/50">
            Áp cho pipeline chat (/answer). Lưu vào .env nên giữ sau khi restart.
          </p>
        </div>
      </div>

      {cfg == null ? (
        <div className="flex items-center gap-2 text-sm text-ink/50">
          <Loader2 className="h-4 w-4 animate-spin" /> Đang tải cấu hình...
        </div>
      ) : (
        <div className="space-y-3">
          {TOGGLES.map((t) => (
            <div
              key={t.key}
              className="flex items-start justify-between gap-4 rounded-xl border border-line bg-white px-4 py-3"
            >
              <div className="min-w-0">
                <p className="text-sm font-medium text-ink">{t.label}</p>
                <p className="text-xs leading-snug text-ink/50">{t.hint}</p>
              </div>
              <Switch
                checked={cfg[t.key] as boolean}
                onChange={(v) => setFlag(t.key, v)}
              />
            </div>
          ))}

          {/* Question min score */}
          <div className="flex items-center justify-between gap-4 rounded-xl border border-line bg-white px-4 py-3">
            <div className="min-w-0">
              <p className="text-sm font-medium text-ink">Ngưỡng câu hỏi (QUESTION_MIN_SCORE)</p>
              <p className="text-xs leading-snug text-ink/50">
                Sàn cosine giữ question match (0–1). Để trống = tắt lọc. Gợi ý ~0.7.
              </p>
            </div>
            <input
              type="number"
              min={0}
              max={1}
              step={0.05}
              value={minScoreText}
              onChange={(e) => {
                setMinScoreText(e.target.value);
                setSaved(false);
              }}
              placeholder="trống"
              className="h-9 w-20 rounded-lg border border-line bg-white px-2 text-sm text-ink focus:outline-none focus:ring-2 focus:ring-mint/40"
            />
          </div>

          {/* Dedup filter (loại chunk trùng khi retrieval) */}
          <div className="rounded-xl border border-line bg-white px-4 py-3">
            <p className="text-sm font-medium text-ink">Lọc retrieval (loại chunk trùng)</p>
            <p className="mb-2.5 text-xs leading-snug text-ink/50">
              Loại các tầng chunk trùng khỏi kết quả tìm kiếm.
              {dedupStats ? ` Corpus: ${dedupStats.corpus_chunks.toLocaleString()} chunk.` : ""}
            </p>
            <div className="grid grid-cols-3 gap-2">
              {DEDUP_LAYERS.map(({ key, label, field }) => {
                const active = cfg.exclude_dedup_layers.includes(key);
                const count = dedupStats?.[field];
                return (
                  <button
                    key={key}
                    type="button"
                    onClick={() => toggleDedupLayer(key)}
                    className={cn(
                      "relative rounded-lg border px-3 py-2.5 text-left transition",
                      active
                        ? "border-mint bg-mint/8 ring-1 ring-mint/30"
                        : "border-line bg-white hover:bg-paper",
                    )}
                  >
                    <span
                      className={cn(
                        "absolute right-2 top-2 flex h-4 w-4 items-center justify-center rounded-full border text-[10px]",
                        active ? "border-mint bg-mint text-white" : "border-line text-transparent",
                      )}
                    >
                      <Check className="h-3 w-3" />
                    </span>
                    <p className={cn("text-xs font-semibold", active ? "text-mint" : "text-ink/70")}>
                      {label}
                    </p>
                    <p className="mt-0.5 text-[11px] text-ink/40">
                      {count != null ? `−${count.toLocaleString()}` : "—"}
                    </p>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Question index side collection */}
          <div className="rounded-xl border border-line bg-paper px-4 py-3">
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <p className="text-sm font-medium text-ink">Question index (collection phụ Qdrant)</p>
                <p className="text-xs text-ink/50">
                  {qi == null
                    ? "Đang kiểm tra..."
                    : qi.build_status === "running"
                      ? "Đang build..."
                      : qi.exists
                        ? `Đã build: ${qi.count.toLocaleString()} câu hỏi`
                        : "Chưa build — sẽ fallback in-memory"}
                </p>
              </div>
              <button
                type="button"
                onClick={buildQi}
                disabled={qi?.build_status === "running"}
                className="flex h-8 shrink-0 items-center gap-1.5 rounded-lg border border-line bg-white px-3 text-xs font-medium text-ink/70 transition hover:bg-white disabled:opacity-50"
              >
                {qi?.build_status === "running" && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                {qi?.exists ? "Build lại" : "Build"}
              </button>
            </div>
            {qi?.build_status === "error" && (
              <p className="mt-1.5 text-xs text-danger">{qi.build_message}</p>
            )}
          </div>

          <p className="text-[11px] leading-snug text-ink/40">
            Lưu ý: BM25 keyword-augment là cờ lúc index nên không có ở đây — đổi cần chạy lại{" "}
            <span className="font-mono">reupsert_sparse.py</span>.
          </p>

          <button
            onClick={save}
            disabled={saving}
            className="flex h-10 w-full items-center justify-center gap-2 rounded-lg bg-mint text-sm font-semibold text-white transition hover:bg-mint/90 disabled:opacity-50"
          >
            {saving ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : saved ? (
              <Check className="h-4 w-4" />
            ) : (
              <Save className="h-4 w-4" />
            )}
            {saved ? "Đã lưu" : "Lưu cấu hình"}
          </button>
        </div>
      )}
    </div>
  );
}
