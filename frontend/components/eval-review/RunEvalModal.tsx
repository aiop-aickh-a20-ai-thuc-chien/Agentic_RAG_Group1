"use client";

import { useEffect, useRef, useState } from "react";
import { AlertCircle, CheckCircle2, Loader2, X, Zap } from "lucide-react";
import { evalApi } from "@/lib/eval-review-api";
import type {
  EvalFlags,
  JobStatus,
  QuestionIndexStatus,
} from "@/lib/eval-review-types";
import { cn } from "@/lib/utils";

interface Props {
  approvedCount: number;
  onClose: () => void;
}

type Phase = "confirm" | "running" | "done" | "error";

const TOGGLES: { key: keyof EvalFlags; label: string; hint: string }[] = [
  {
    key: "hard_filter_enabled",
    label: "Hard filter (entity)",
    hint: "Lọc theo entity (model/địa điểm) phát hiện trong câu hỏi",
  },
  {
    key: "metadata_boosting_enabled",
    label: "Metadata boosting",
    hint: "Tăng/giảm điểm theo document_type × recency × dedup",
  },
  {
    key: "question_index_enabled",
    label: "Question-index retriever",
    hint: "Đường thứ 3 (RRF): khớp câu hỏi ↔ câu hỏi của chunk",
  },
  {
    key: "entity_prefilter_llm",
    label: "LLM map entity",
    hint: "Khi từ điển trượt, dùng LLM đoán entity (chỉ khi hard filter bật)",
  },
];

function Toggle({
  checked,
  onChange,
  label,
  hint,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
  hint: string;
}) {
  return (
    <button
      type="button"
      onClick={() => onChange(!checked)}
      className="flex w-full items-start justify-between gap-3 rounded-lg border border-line px-3 py-2.5 text-left transition hover:bg-paper"
    >
      <div className="min-w-0">
        <p className="text-sm font-medium text-ink">{label}</p>
        <p className="text-xs leading-snug text-ink/50">{hint}</p>
      </div>
      <span
        className={cn(
          "mt-0.5 flex h-5 w-9 shrink-0 items-center rounded-full p-0.5 transition",
          checked ? "bg-mint" : "bg-mist",
        )}
      >
        <span
          className={cn(
            "h-4 w-4 rounded-full bg-white shadow transition-transform",
            checked ? "translate-x-4" : "translate-x-0",
          )}
        />
      </span>
    </button>
  );
}

export function RunEvalModal({ approvedCount, onClose }: Props) {
  const [phase, setPhase] = useState<Phase>("confirm");
  const [status, setStatus] = useState<JobStatus | null>(null);
  const [runRagas, setRunRagas] = useState(true);
  const [flags, setFlags] = useState<EvalFlags | null>(null);
  const [qi, setQi] = useState<QuestionIndexStatus | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const qiPollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    evalApi
      .getEvalFlags()
      .then(setFlags)
      .catch(() => setFlags(null));
    evalApi
      .getQuestionIndexStatus()
      .then(setQi)
      .catch(() => setQi(null));
    return () => {
      if (qiPollRef.current) clearInterval(qiPollRef.current);
    };
  }, []);

  const handleBuildQi = async () => {
    setQi((prev) =>
      prev
        ? { ...prev, build_status: "running", build_message: "Đang build..." }
        : prev,
    );
    try {
      await evalApi.buildQuestionIndex();
    } catch (e) {
      setQi((prev) =>
        prev
          ? {
              ...prev,
              build_status: "error",
              build_message: e instanceof Error ? e.message : String(e),
            }
          : prev,
      );
      return;
    }
    if (qiPollRef.current) clearInterval(qiPollRef.current);
    qiPollRef.current = setInterval(async () => {
      try {
        const s = await evalApi.getQuestionIndexStatus();
        setQi(s);
        if (s.build_status === "done" || s.build_status === "error") {
          if (qiPollRef.current) clearInterval(qiPollRef.current);
          qiPollRef.current = null;
        }
      } catch {}
    }, 2000);
  };

  const stopPoll = () => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  };

  useEffect(() => () => stopPoll(), []);

  const handleStart = async () => {
    setPhase("running");
    try {
      await evalApi.runEval(runRagas, flags ?? undefined);
    } catch (e) {
      setStatus({
        status: "error",
        progress: 0,
        total: 0,
        errors: [e instanceof Error ? e.message : String(e)],
        message: "Không thể khởi động evaluation",
      });
      setPhase("error");
      return;
    }

    pollRef.current = setInterval(async () => {
      try {
        const s = await evalApi.getEvalStatus();
        setStatus(s);
        if (s.status === "done" || s.status === "error") {
          stopPoll();
          setPhase(s.status);
        }
      } catch {}
    }, 2000);
  };

  const pct =
    status && status.total > 0
      ? Math.round((status.progress / status.total) * 100)
      : 0;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/30 p-4 backdrop-blur-sm">
      <div className="w-full max-w-md rounded-2xl border border-line bg-white shadow-panel">
        {/* Header */}
        <div className="flex items-start justify-between border-b border-line px-6 pt-5 pb-4">
          <div className="flex items-center gap-3">
            <div
              className={cn(
                "flex h-10 w-10 items-center justify-center rounded-xl",
                phase === "done"
                  ? "bg-mint/12"
                  : phase === "error"
                    ? "bg-danger/10"
                    : "bg-mint/12",
              )}
            >
              {phase === "done" ? (
                <CheckCircle2 className="h-5 w-5 text-mint" />
              ) : phase === "error" ? (
                <AlertCircle className="h-5 w-5 text-danger" />
              ) : (
                <Zap className="h-5 w-5 text-mint" />
              )}
            </div>
            <div>
              <h2 className="text-base font-semibold text-ink">
                {phase === "confirm" && "Run Evaluate + RAGAS"}
                {phase === "running" && "Đang đánh giá..."}
                {phase === "done" && "Hoàn thành!"}
                {phase === "error" && "Có lỗi xảy ra"}
              </h2>
              {phase === "running" && status && (
                <p className="text-xs text-ink/50">{status.message}</p>
              )}
            </div>
          </div>
          {phase !== "running" && (
            <button
              onClick={onClose}
              className="flex h-7 w-7 items-center justify-center rounded-md text-ink/40 transition hover:bg-paper"
            >
              <X className="h-4 w-4" />
            </button>
          )}
        </div>

        {/* Body */}
        <div className="px-6 py-5">
          {phase === "confirm" && (
            <div className="space-y-4">
              <p className="text-sm leading-relaxed text-ink/65">
                Sẽ chạy RAG pipeline + RAGAS metrics trên{" "}
                <span className="font-semibold text-mint">
                  {approvedCount} câu hỏi đã approved
                </span>
                . Quá trình này có thể mất vài phút tùy số lượng câu hỏi.
              </p>
              <div className="rounded-lg border border-line bg-paper px-4 py-3 text-xs text-ink/60">
                <p className="font-medium text-ink/80 mb-1">Sẽ tính toán:</p>
                <ul className="space-y-0.5 list-disc list-inside">
                  <li>MRR@5, Recall@5, Ground Truth Rank</li>
                  <li>RAGAS: Faithfulness, Answer Relevancy</li>
                  <li>RAGAS: Context Precision, Context Recall</li>
                </ul>
              </div>

              <div className="space-y-2">
                <p className="text-xs font-medium text-ink/80">
                  Cấu hình retrieval (áp cho lần chạy này, không cần restart):
                </p>
                {flags ? (
                  TOGGLES.map((t) => (
                    <Toggle
                      key={t.key}
                      label={t.label}
                      hint={t.hint}
                      checked={flags[t.key]}
                      onChange={(v) => setFlags({ ...flags, [t.key]: v })}
                    />
                  ))
                ) : (
                  <p className="text-xs text-ink/40">Đang tải cấu hình hiện tại...</p>
                )}
                <Toggle
                  label="RAGAS metrics"
                  hint="Faithfulness, Answer Relevancy, Context Precision/Recall (chậm hơn)"
                  checked={runRagas}
                  onChange={setRunRagas}
                />
              </div>

              {/* Question-index side collection: build/rebuild without the CLI */}
              <div className="rounded-lg border border-line bg-paper px-3 py-2.5">
                <div className="flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-xs font-medium text-ink/80">
                      Question index (collection phụ Qdrant)
                    </p>
                    <p className="text-xs text-ink/50">
                      {qi == null
                        ? "Đang kiểm tra..."
                        : qi.build_status === "running"
                          ? "Đang build..."
                          : qi.exists
                            ? `Đã build: ${qi.count.toLocaleString()} câu hỏi`
                            : "Chưa build — sẽ chạy fallback in-memory"}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={handleBuildQi}
                    disabled={qi?.build_status === "running"}
                    className="flex h-8 shrink-0 items-center gap-1.5 rounded-lg border border-line px-3 text-xs font-medium text-ink/70 transition hover:bg-white disabled:opacity-50"
                  >
                    {qi?.build_status === "running" && (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    )}
                    {qi?.exists ? "Build lại" : "Build"}
                  </button>
                </div>
                {qi?.build_status === "error" && (
                  <p className="mt-1.5 text-xs text-danger">{qi.build_message}</p>
                )}
              </div>

              <p className="text-[11px] leading-snug text-ink/40">
                Lưu ý: BM25 keyword-augment là cờ lúc index nên không có ở đây — đổi nó cần
                chạy lại <span className="font-mono">reupsert_sparse.py</span>.
              </p>
            </div>
          )}

          {phase === "running" && (
            <div className="space-y-4">
              <div className="flex items-center justify-between text-xs text-ink/55">
                <span>Tiến độ</span>
                <span className="font-mono font-medium">
                  {status?.progress ?? 0} / {status?.total ?? approvedCount}
                </span>
              </div>
              <div className="h-2.5 w-full overflow-hidden rounded-full bg-mist">
                <div
                  className="h-full rounded-full bg-mint transition-all duration-500"
                  style={{ width: `${pct}%` }}
                />
              </div>
              <div className="flex items-center gap-2 text-sm text-ink/50">
                <Loader2 className="h-4 w-4 animate-spin text-mint" />
                Đang xử lý — không đóng tab này
              </div>
            </div>
          )}

          {phase === "done" && (
            <p className="text-sm leading-relaxed text-ink/65">
              {status?.message ?? "Đánh giá hoàn tất."}
              <br />
              <span className="text-xs text-ink/45">
                Kết quả đã được ghi vào result.xlsx.
              </span>
            </p>
          )}

          {phase === "error" && (
            <div className="rounded-lg border border-danger/25 bg-danger/6 px-4 py-3 text-sm text-danger">
              {status?.errors[0] ?? "Không rõ lỗi. Kiểm tra terminal backend."}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex gap-3 border-t border-line px-6 py-4">
          {phase === "confirm" && (
            <>
              <button
                onClick={onClose}
                className="flex h-10 flex-1 items-center justify-center rounded-lg border border-line text-sm font-medium text-ink/65 transition hover:bg-paper"
              >
                Hủy
              </button>
              <button
                onClick={handleStart}
                className="flex h-10 flex-1 items-center justify-center gap-2 rounded-lg bg-mint text-sm font-semibold text-white transition hover:bg-mint/90 active:scale-98"
              >
                <Zap className="h-4 w-4" />
                Bắt đầu
              </button>
            </>
          )}
          {(phase === "done" || phase === "error") && (
            <button
              onClick={onClose}
              className={cn(
                "flex h-10 w-full items-center justify-center rounded-lg text-sm font-semibold text-white transition hover:opacity-90 active:scale-98",
                phase === "done" ? "bg-mint" : "bg-ink",
              )}
            >
              {phase === "done" ? "Xem kết quả" : "Đóng"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
