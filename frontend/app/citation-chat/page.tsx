"use client";

import Link from "next/link";
import {
  ArrowLeft,
  ArrowUpRight,
  Bot,
  ChevronLeft,
  FileText,
  Link as LinkIcon,
  Loader2,
  Menu,
  Moon,
  PanelRightOpen,
  Quote,
  SearchCheck,
  ShieldCheck,
  Sun,
  Upload,
  UserRound,
  X,
  type LucideIcon,
} from "lucide-react";
import type { ReactNode } from "react";
import { useMemo, useState } from "react";
import { KnowledgeScene } from "@/components/knowledge-scene";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

type Citation = {
  source: string;
  chunk_id: string;
  page?: number | null;
  section?: string | null;
  url?: string | null;
  index?: number;
};

type AnswerResponse = {
  answer: string;
  status: "answered" | "not_found";
  citations: Citation[];
};

type SourceMode = "pdf" | "url" | "text";
type Theme = "light" | "dark";
type StreamEvent = {
  event: string;
  data: Record<string, unknown>;
};

const API_URL =
  process.env.NEXT_PUBLIC_AGENTIC_RAG_API_URL ?? "http://127.0.0.1:8000";

const sourceModes: Array<{ id: SourceMode; label: string; icon: LucideIcon }> = [
  { id: "pdf", label: "PDF", icon: Upload },
  { id: "url", label: "URL", icon: LinkIcon },
  { id: "text", label: "Văn bản", icon: FileText },
];

const sampleSources = [
  {
    name: "vinfast_warranty.pdf",
    detail: "Chính sách bảo hành xe điện",
    status: "Đã nạp",
  },
  {
    name: "example.com/warranty",
    detail: "Trang chính sách từ website",
    status: "Chưa nạp",
  },
  {
    name: "Ghi chú của tôi",
    detail: "Văn bản người dùng tự nhập",
    status: "Bản nháp",
  },
];

const evidencePreview = [
  "Pin cao áp được bảo hành 8 năm hoặc 160.000 km.",
  "Nội dung chính từ website về chính sách bảo hành.",
];

const suggestedQuestions = [
  "Pin VF8 được bảo hành bao lâu?",
  "Điều kiện bảo hành pin là gì?",
  "Nguồn nào nói về thời hạn bảo hành?",
];

export default function CitationChatPage() {
  const [theme, setTheme] = useState<Theme>("light");
  const [showSources, setShowSources] = useState(true);
  const [showCitations, setShowCitations] = useState(true);
  const [sourceMode, setSourceMode] = useState<SourceMode>("pdf");
  const [question, setQuestion] = useState("Pin VF8 được bảo hành bao lâu?");
  const [sourceText, setSourceText] = useState("");
  const [fileName, setFileName] = useState("");
  const [answer, setAnswer] = useState<AnswerResponse | null>(null);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const isDark = theme === "dark";
  const citationCount = answer?.citations.length ?? 0;

  const sourcePlaceholder = useMemo(() => {
    if (sourceMode === "url") return "https://example.com/chinh-sach";
    if (sourceMode === "text") return "Dán nội dung tài liệu hoặc ghi chú ở đây";
    return fileName || "Chưa chọn tệp";
  }, [fileName, sourceMode]);

  async function askQuestion() {
    if (!question.trim()) return;

    setError("");
    setIsLoading(true);

    try {
      const response = await fetch(`${API_URL}/answer/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question,
          use_mock_evidence: true,
        }),
      });

      if (!response.ok) {
        throw new Error(`Yêu cầu thất bại: ${response.status}`);
      }
      if (!response.body) {
        throw new Error("Trình duyệt không hỗ trợ streaming response");
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let streamedAnswer = "";
      let streamedCitations: Citation[] = [];
      setAnswer({ answer: "", status: "answered", citations: [] });

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const parsed = takeStreamEvents(buffer);
        buffer = parsed.remainder;

        for (const streamEvent of parsed.events) {
          if (streamEvent.event === "answer_delta") {
            const text = streamEvent.data.text;
            if (typeof text === "string") {
              streamedAnswer += text;
              setAnswer({
                answer: streamedAnswer,
                status: "answered",
                citations: streamedCitations,
              });
            }
          }

          if (streamEvent.event === "citation") {
            const citation = streamEvent.data as Citation;
            streamedCitations = [...streamedCitations, citation];
            setAnswer({
              answer: streamedAnswer,
              status: "answered",
              citations: streamedCitations,
            });
          }

          if (streamEvent.event === "done") {
            setAnswer(streamEvent.data as AnswerResponse);
          }
        }
      }
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Không kết nối được API trả lời",
      );
    } finally {
      setIsLoading(false);
    }
  }

  const contentGrid = cn(
    "grid min-h-0 flex-1 gap-3",
    showSources && showCitations && "xl:grid-cols-[310px_minmax(0,1fr)_340px]",
    showSources && !showCitations && "xl:grid-cols-[310px_minmax(0,1fr)]",
    !showSources && showCitations && "xl:grid-cols-[minmax(0,1fr)_340px]",
    !showSources && !showCitations && "xl:grid-cols-1",
  );

  return (
    <main
      className={cn(
        "relative min-h-[100dvh] overflow-hidden transition-colors",
        isDark
          ? "dark bg-[#0b1220] text-white"
          : "bg-[linear-gradient(135deg,#fbfcf8,#edf7f1_52%,#f7f8f2)] text-ink",
      )}
    >
      <KnowledgeScene />
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_80%_10%,rgba(15,143,114,0.14),transparent_28rem)] dark:bg-[radial-gradient(circle_at_78%_12%,rgba(52,211,153,0.18),transparent_30rem)]" />

      <section className="relative z-10 mx-auto flex min-h-[100dvh] max-w-[1500px] flex-col gap-3 p-3 lg:p-4">
        <header className="rounded-lg border border-line/80 bg-white/84 px-4 py-3 shadow-panel backdrop-blur-xl dark:border-white/14 dark:bg-slate-950/90">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div className="flex items-center gap-3">
              <Link
                aria-label="Quay lại trang chọn công cụ"
                className="inline-flex h-10 w-10 items-center justify-center rounded-md border border-line bg-white transition hover:bg-paper dark:border-white/14 dark:bg-slate-900/82 dark:text-slate-50 dark:hover:bg-slate-800"
                href="/"
              >
                <ChevronLeft className="h-4 w-4" aria-hidden="true" />
              </Link>
              <div className="flex h-11 w-11 items-center justify-center rounded-lg bg-ink text-white dark:bg-white dark:text-ink">
                <Bot className="h-5 w-5" aria-hidden="true" />
              </div>
              <div>
                <h1 className="text-lg font-semibold tracking-normal">
                  Hỏi đáp có trích dẫn
                </h1>
                <p className="text-sm text-ink/58 dark:text-slate-200">
                  Chat với tài liệu theo phong cách NotebookLM
                </p>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <Badge className="border-mint/24 bg-mint/8 text-mint dark:border-emerald-300/28 dark:bg-emerald-300/12 dark:text-emerald-200">
                <ShieldCheck className="mr-1 h-3.5 w-3.5" aria-hidden="true" />
                Có kiểm chứng nguồn
              </Badge>
              <Badge>{citationCount} trích dẫn</Badge>
              <Button
                onClick={() => setShowSources((value) => !value)}
                variant="secondary"
              >
                {showSources ? (
                  <X className="h-4 w-4" aria-hidden="true" />
                ) : (
                  <Menu className="h-4 w-4" aria-hidden="true" />
                )}
                Nguồn
              </Button>
              <Button
                onClick={() => setShowCitations((value) => !value)}
                variant="secondary"
              >
                <PanelRightOpen className="h-4 w-4" aria-hidden="true" />
                Trích dẫn
              </Button>
              <button
                className="inline-flex h-10 items-center gap-2 rounded-md border border-line bg-white px-3 text-sm font-medium transition hover:bg-paper dark:border-white/14 dark:bg-slate-900/82 dark:text-slate-50 dark:hover:bg-slate-800"
                onClick={() => setTheme(isDark ? "light" : "dark")}
                type="button"
              >
                {isDark ? (
                  <Sun className="h-4 w-4" aria-hidden="true" />
                ) : (
                  <Moon className="h-4 w-4" aria-hidden="true" />
                )}
                {isDark ? "Sáng" : "Tối"}
              </button>
              <Button>
                <UserRound className="h-4 w-4" aria-hidden="true" />
                Đăng nhập
              </Button>
            </div>
          </div>
        </header>

        <div className={contentGrid}>
          {showSources ? (
            <SourcePanel
              fileName={fileName}
              setFileName={setFileName}
              setSourceMode={setSourceMode}
              setSourceText={setSourceText}
              sourceMode={sourceMode}
              sourcePlaceholder={sourcePlaceholder}
              sourceText={sourceText}
            />
          ) : null}

          <section className="flex min-h-[calc(100dvh-7rem)] flex-col overflow-hidden rounded-lg border border-line/80 bg-white/90 shadow-panel backdrop-blur-xl dark:border-white/14 dark:bg-slate-950/90">
            <div className="border-b border-line px-5 py-4 dark:border-white/14">
              <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
                <div>
                  <p className="text-sm font-semibold text-mint dark:text-emerald-200">
                    Phiên hỏi đáp
                  </p>
                  <h2 className="mt-2 max-w-3xl text-3xl font-semibold leading-tight tracking-normal">
                    Đặt câu hỏi, nhận câu trả lời cùng nguồn.
                  </h2>
                </div>
                <div className="grid grid-cols-3 gap-2 text-center lg:w-72">
                  <Metric label="Nguồn" value="2 mẫu" />
                  <Metric label="Kiểm chứng" value="bật" />
                  <Metric label="Trạng thái" value={answer ? "đã trả lời" : "sẵn sàng"} />
                </div>
              </div>
            </div>

            <div className="flex-1 overflow-y-auto px-5 py-5">
              <div className="space-y-4">
                <div className="max-w-[84%] rounded-lg bg-paper px-4 py-3 dark:bg-slate-900/82">
                  <div className="mb-1 flex items-center gap-2 text-xs font-medium text-ink/52 dark:text-slate-300">
                    <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
                    Bạn hỏi
                  </div>
                  <p className="text-sm leading-6 text-ink/84 dark:text-white/88">
                    {question}
                  </p>
                </div>

                <div className="ml-auto max-w-[90%] rounded-lg border border-mint/25 bg-mint/8 px-4 py-3 dark:border-emerald-300/24 dark:bg-emerald-300/12">
                  <div className="mb-2 flex items-center justify-between gap-3">
                    <div className="flex items-center gap-2 text-sm font-semibold text-mint dark:text-emerald-200">
                      <Bot className="h-4 w-4" aria-hidden="true" />
                      Câu trả lời
                    </div>
                    <Badge className="border-mint/25 text-mint dark:border-emerald-300/24 dark:text-emerald-200">
                      {answer?.status === "answered" ? "đã kiểm chứng" : "chưa gửi"}
                    </Badge>
                  </div>
                  {answer ? (
                    <p className="text-sm leading-7 text-ink/84 dark:text-white/88">
                      {answer.answer}
                    </p>
                  ) : (
                    <div className="space-y-2">
                      <div className="h-3 w-11/12 rounded-full bg-mint/12 dark:bg-white/16" />
                      <div className="h-3 w-8/12 rounded-full bg-mint/10 dark:bg-white/12" />
                      <p className="pt-1 text-sm leading-6 text-ink/58 dark:text-slate-200">
                        Nhấn Enter để gửi. Câu trả lời sẽ chỉ dựa trên nguồn có sẵn.
                      </p>
                    </div>
                  )}
                </div>

                {error ? (
                  <div className="rounded-md border border-danger/30 bg-danger/8 px-3 py-2 text-sm text-danger dark:text-red-200">
                    {error}
                  </div>
                ) : null}
              </div>
            </div>

            <div className="border-t border-line bg-white/78 p-4 dark:border-white/14 dark:bg-slate-950/72">
              <div className="mb-3 flex flex-wrap gap-2">
                {suggestedQuestions.map((item) => (
                  <button
                    className="rounded-full border border-line bg-white px-3 py-1 text-xs text-ink/62 transition hover:border-mint hover:text-mint dark:border-white/14 dark:bg-slate-900/82 dark:text-slate-200 dark:hover:border-emerald-300 dark:hover:text-emerald-200"
                    key={item}
                    onClick={() => setQuestion(item)}
                    type="button"
                  >
                    {item}
                  </button>
                ))}
              </div>
              <div className="flex flex-col gap-2 sm:flex-row">
                <Textarea
                  className="min-h-11 flex-1 py-2"
                  value={question}
                  onChange={(event) => setQuestion(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" && !event.shiftKey) {
                      event.preventDefault();
                      void askQuestion();
                    }
                  }}
                  placeholder="Nhập câu hỏi, nhấn Enter để gửi"
                  rows={1}
                />
                <Button
                  className="shrink-0 shadow-lift"
                  disabled={isLoading || !question.trim()}
                  onClick={askQuestion}
                >
                  {isLoading ? (
                    <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                  ) : (
                    <ArrowUpRight className="h-4 w-4" aria-hidden="true" />
                  )}
                  Gửi
                </Button>
              </div>
            </div>
          </section>

          {showCitations ? <CitationPanel answer={answer} /> : null}
        </div>
      </section>
    </main>
  );
}

function takeStreamEvents(buffer: string): {
  events: StreamEvent[];
  remainder: string;
} {
  const events: StreamEvent[] = [];
  const chunks = buffer.split("\n\n");
  const remainder = chunks.pop() ?? "";

  for (const chunk of chunks) {
    const event = parseStreamEvent(chunk);
    if (event) events.push(event);
  }

  return { events, remainder };
}

function parseStreamEvent(chunk: string): StreamEvent | null {
  const eventLine = chunk
    .split("\n")
    .find((line) => line.startsWith("event: "));
  const dataLine = chunk
    .split("\n")
    .find((line) => line.startsWith("data: "));

  if (!eventLine || !dataLine) return null;

  try {
    return {
      event: eventLine.slice("event: ".length),
      data: JSON.parse(dataLine.slice("data: ".length)) as Record<string, unknown>,
    };
  } catch {
    return null;
  }
}

function SourcePanel({
  fileName,
  setFileName,
  setSourceMode,
  setSourceText,
  sourceMode,
  sourcePlaceholder,
  sourceText,
}: {
  fileName: string;
  setFileName: (fileName: string) => void;
  setSourceMode: (mode: SourceMode) => void;
  setSourceText: (text: string) => void;
  sourceMode: SourceMode;
  sourcePlaceholder: string;
  sourceText: string;
}) {
  return (
    <aside className="grid content-start gap-3">
      <Panel>
        <div className="mb-4 flex items-center justify-between">
          <div>
            <h2 className="text-sm font-semibold">Nguồn</h2>
            <p className="mt-1 text-xs text-ink/54 dark:text-slate-300">
              Thêm tài liệu cho phiên chat
            </p>
          </div>
          <SearchCheck className="h-4 w-4 text-mint dark:text-emerald-300" aria-hidden="true" />
        </div>

        <div className="grid grid-cols-3 gap-2">
          {sourceModes.map((mode) => {
            const Icon = mode.icon;
            const active = sourceMode === mode.id;
            return (
              <button
                key={mode.id}
                className={cn(
                  "flex h-14 flex-col items-center justify-center gap-1 rounded-md border text-xs font-medium transition active:translate-y-px",
                  active
                    ? "border-mint bg-mint/10 text-mint dark:border-emerald-300/42 dark:bg-emerald-300/12 dark:text-emerald-200"
                    : "border-line bg-paper/70 text-ink/64 hover:bg-white dark:border-white/14 dark:bg-slate-900/76 dark:text-slate-200 dark:hover:bg-slate-800",
                )}
                onClick={() => setSourceMode(mode.id)}
                type="button"
              >
                <Icon className="h-4 w-4" aria-hidden="true" />
                {mode.label}
              </button>
            );
          })}
        </div>

        <div className="mt-4">
          {sourceMode === "pdf" ? (
            <label className="flex min-h-32 cursor-pointer flex-col items-center justify-center rounded-lg border border-dashed border-mint/40 bg-mist/70 px-3 py-4 text-center transition hover:border-mint hover:bg-white dark:border-emerald-300/34 dark:bg-slate-900/76 dark:hover:bg-slate-800">
              <Upload className="mb-2 h-5 w-5 text-mint dark:text-emerald-300" aria-hidden="true" />
              <span className="text-sm font-medium">{fileName || "Chọn tệp PDF"}</span>
              <span className="mt-1 text-xs text-ink/50 dark:text-slate-300">
                Tệp đã sẵn sàng trong phiên làm việc
              </span>
              <input
                accept="application/pdf"
                className="sr-only"
                type="file"
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  setFileName(file?.name ?? "");
                }}
              />
            </label>
          ) : sourceMode === "url" ? (
            <Input
              placeholder={sourcePlaceholder}
              value={sourceText}
              onChange={(event) => setSourceText(event.target.value)}
            />
          ) : (
            <Textarea
              className="min-h-32"
              placeholder={sourcePlaceholder}
              value={sourceText}
              onChange={(event) => setSourceText(event.target.value)}
            />
          )}
        </div>
      </Panel>

      <Panel>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold">Thư viện</h2>
          <Badge className="border-mint/20 text-mint dark:border-emerald-300/24 dark:text-emerald-200">
            Mẫu
          </Badge>
        </div>
        <div className="space-y-2">
          {sampleSources.map((source) => (
            <article
              className="rounded-md border border-line bg-paper/70 p-3 dark:border-white/14 dark:bg-slate-900/76"
              key={source.name}
            >
              <div className="flex items-center justify-between gap-2">
                <p className="truncate text-sm font-medium">{source.name}</p>
                <span className="rounded-full bg-white px-2 py-0.5 text-[11px] text-ink/56 dark:bg-slate-800 dark:text-slate-200">
                  {source.status}
                </span>
              </div>
              <p className="mt-1 text-xs text-ink/52 dark:text-slate-300">
                {source.detail}
              </p>
            </article>
          ))}
        </div>
      </Panel>
    </aside>
  );
}

function CitationPanel({ answer }: { answer: AnswerResponse | null }) {
  return (
    <aside className="grid content-start gap-3">
      <Panel>
        <div className="mb-4 flex items-center justify-between">
          <div>
            <h2 className="text-sm font-semibold">Trích dẫn</h2>
            <p className="mt-1 text-xs text-ink/54 dark:text-slate-300">
              Nguồn được dùng trong câu trả lời
            </p>
          </div>
          <PanelRightOpen className="h-4 w-4 text-mint dark:text-emerald-300" aria-hidden="true" />
        </div>

        <div className="space-y-3">
          {answer?.citations.length ? (
            answer.citations.map((citation, index) => (
              <article
                className="rounded-md border border-line bg-paper/70 p-3 dark:border-white/14 dark:bg-slate-900/76"
                key={citation.chunk_id}
              >
                <div className="mb-2 flex items-center justify-between gap-2">
                  <Badge className="border-mint/25 text-mint dark:border-emerald-300/24 dark:text-emerald-200">
                    [{index + 1}] {citation.source}
                  </Badge>
                  {citation.page ? <Badge>tr.{citation.page}</Badge> : null}
                </div>
                <p className="break-all text-xs leading-5 text-ink/62 dark:text-slate-300">
                  {citation.chunk_id}
                </p>
                {citation.section ? (
                  <p className="mt-2 text-xs text-ink/52 dark:text-slate-300">
                    {citation.section}
                  </p>
                ) : null}
              </article>
            ))
          ) : (
            <div className="rounded-md border border-dashed border-line bg-paper/70 p-4 text-sm text-ink/58 dark:border-white/14 dark:bg-slate-900/76 dark:text-slate-200">
              Trích dẫn sẽ xuất hiện sau khi có câu trả lời.
            </div>
          )}
        </div>
      </Panel>

      <Panel>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold">Đoạn bằng chứng</h2>
          <Quote className="h-4 w-4 text-mint dark:text-emerald-300" aria-hidden="true" />
        </div>
        <div className="space-y-2">
          {evidencePreview.map((text, index) => (
            <div className="rounded-md bg-paper/70 p-3 dark:bg-slate-900/76" key={text}>
              <div className="mb-2 flex items-center gap-2">
                <span className="flex h-5 w-5 items-center justify-center rounded-full bg-mint/10 text-xs font-semibold text-mint dark:bg-emerald-300/12 dark:text-emerald-200">
                  {index + 1}
                </span>
                <p className="text-xs font-medium text-ink/52 dark:text-slate-300">
                  Đoạn nguồn
                </p>
              </div>
              <p className="text-sm leading-6 text-ink/72 dark:text-slate-200">{text}</p>
            </div>
          ))}
        </div>
      </Panel>
    </aside>
  );
}

function Panel({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={cn(
        "rounded-lg border border-line/80 bg-white/88 p-4 shadow-panel backdrop-blur-xl dark:border-white/14 dark:bg-slate-950/90",
        className,
      )}
    >
      {children}
    </section>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-line bg-paper/70 px-3 py-2 dark:border-white/14 dark:bg-slate-900/76">
      <p className="text-[11px] text-ink/46 dark:text-slate-300">{label}</p>
      <p className="mt-1 text-sm font-semibold text-ink dark:text-white">{value}</p>
    </div>
  );
}
