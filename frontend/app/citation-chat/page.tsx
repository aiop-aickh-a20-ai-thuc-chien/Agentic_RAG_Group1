"use client";

import Link from "next/link";
import {
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

type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  status?: "answered" | "not_found" | "thinking";
  citations?: Citation[];
};

type SourceUploadResponse = {
  provider: string;
  dataset_id: string;
  document_id: string;
  name: string;
  parse_started: boolean;
};

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

type SourceChunksResponse = {
  provider: string;
  document_id: string;
  chunks: SourceChunk[];
};

type SourceMode = "pdf" | "url" | "text";
type Theme = "light" | "dark";
type SourceProcessingStatus = "idle" | "uploading" | "processing" | "ready" | "error";
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

export default function CitationChatPage() {
  const [theme, setTheme] = useState<Theme>("light");
  const [showSources, setShowSources] = useState(true);
  const [showCitations, setShowCitations] = useState(true);
  const [sourceMode, setSourceMode] = useState<SourceMode>("pdf");
  const [question, setQuestion] = useState("");
  const [sourceText, setSourceText] = useState("");
  const [fileName, setFileName] = useState("");
  const [documentIds, setDocumentIds] = useState<string[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [sourceStatus, setSourceStatus] = useState<SourceProcessingStatus>("idle");
  const [sourceChunkCount, setSourceChunkCount] = useState(0);
  const [sourceChunks, setSourceChunks] = useState<SourceChunk[]>([]);
  const [answer, setAnswer] = useState<AnswerResponse | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: "welcome",
      role: "assistant",
      content: "Tải tài liệu lên, chờ trạng thái sẵn sàng rồi đặt câu hỏi.",
      status: "answered",
      citations: [],
    },
  ]);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const isDark = theme === "dark";
  const citationCount = answer?.citations.length ?? 0;
  const isSourceBusy = sourceStatus === "uploading" || sourceStatus === "processing";

  const sourcePlaceholder = useMemo(() => {
    if (sourceMode === "url") return "https://example.com/chinh-sach";
    if (sourceMode === "text") return "Dán nội dung tài liệu hoặc ghi chú ở đây";
    return fileName || "Chưa chọn tệp";
  }, [fileName, sourceMode]);

  async function askQuestion() {
    const userQuestion = question.trim();
    if (!userQuestion) return;
    if (sourceMode === "pdf" && fileName && sourceStatus !== "ready") {
      setError("Tài liệu vẫn đang được RAGFlow xử lý. Chờ trạng thái sẵn sàng rồi hỏi lại.");
      return;
    }
    if (!documentIds.length) {
      setError("Hãy tải tài liệu lên và chờ trạng thái sẵn sàng trước khi đặt câu hỏi.");
      return;
    }

    setError("");
    setIsLoading(true);
    setQuestion("");

    const userMessage: ChatMessage = {
      id: createMessageId(),
      role: "user",
      content: userQuestion,
    };
    const assistantMessageId = createMessageId();
    const assistantMessage: ChatMessage = {
      id: assistantMessageId,
      role: "assistant",
      content: "",
      status: "thinking",
      citations: [],
    };
    setMessages((current) => [...current, userMessage, assistantMessage]);

    try {
      const response = await fetch(`${API_URL}/answer/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: userQuestion,
          evidence_provider: "ragflow",
          document_ids: documentIds,
          use_mock_evidence: false,
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
              updateAssistantMessage(assistantMessageId, {
                content: streamedAnswer,
                status: "thinking",
                citations: streamedCitations,
              });
            }
          }

          if (streamEvent.event === "citation") {
            const citation = streamEvent.data as Citation;
            streamedCitations = [...streamedCitations, citation];
            updateAssistantMessage(assistantMessageId, {
              content: streamedAnswer,
              status: "thinking",
              citations: streamedCitations,
            });
          }

          if (streamEvent.event === "done") {
            const finalAnswer = streamEvent.data as AnswerResponse;
            setAnswer(finalAnswer);
            updateAssistantMessage(assistantMessageId, {
              content: finalAnswer.answer,
              status: finalAnswer.status,
              citations: finalAnswer.citations,
            });
          }
        }
      }
    } catch (requestError) {
      updateAssistantMessage(assistantMessageId, {
        content: "Không kết nối được API trả lời.",
        status: "not_found",
        citations: [],
      });
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Không kết nối được API trả lời",
      );
    } finally {
      setIsLoading(false);
    }
  }

  function updateAssistantMessage(
    messageId: string,
    patch: Partial<ChatMessage>,
  ) {
    setMessages((current) =>
      current.map((message) =>
        message.id === messageId ? { ...message, ...patch } : message,
      ),
    );
  }

  const contentGrid = cn(
    "grid min-h-0 flex-1 gap-3 overflow-y-auto xl:overflow-hidden",
    showSources && showCitations && "xl:grid-cols-[280px_minmax(0,1fr)_300px] 2xl:grid-cols-[310px_minmax(0,1fr)_330px]",
    showSources && !showCitations && "xl:grid-cols-[300px_minmax(0,1fr)]",
    !showSources && showCitations && "xl:grid-cols-[minmax(0,1fr)_320px]",
    !showSources && !showCitations && "xl:grid-cols-1",
  );

  return (
    <main
      className={cn(
        "relative h-[100dvh] max-h-[100dvh] overflow-hidden transition-colors",
        isDark
          ? "dark bg-[#0b1220] text-white"
          : "bg-[linear-gradient(135deg,#fbfcf8,#edf7f1_52%,#f7f8f2)] text-ink",
      )}
    >
      <KnowledgeScene />
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_80%_10%,rgba(15,143,114,0.14),transparent_28rem)] dark:bg-[radial-gradient(circle_at_78%_12%,rgba(52,211,153,0.18),transparent_30rem)]" />

      <section className="relative z-10 mx-auto flex h-[100dvh] max-h-[100dvh] w-full max-w-[1500px] flex-col gap-3 overflow-hidden p-3 lg:p-4">
        <header className="shrink-0 rounded-lg border border-line/80 bg-white/84 px-4 py-3 shadow-panel backdrop-blur-xl dark:border-white/14 dark:bg-slate-950/90">
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
              <div className="min-w-0">
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
              isUploading={isUploading}
              setSourceChunkCount={setSourceChunkCount}
              setSourceChunks={setSourceChunks}
              setSourceStatus={setSourceStatus}
              setDocumentIds={setDocumentIds}
              setError={setError}
              setFileName={setFileName}
              setIsUploading={setIsUploading}
              setSourceMode={setSourceMode}
              setSourceText={setSourceText}
              sourceMode={sourceMode}
              sourcePlaceholder={sourcePlaceholder}
              sourceChunkCount={sourceChunkCount}
              sourceStatus={sourceStatus}
              sourceText={sourceText}
            />
          ) : null}

          <section className="flex min-h-0 min-w-0 flex-col overflow-hidden rounded-lg border border-line/80 bg-white/90 shadow-panel backdrop-blur-xl dark:border-white/14 dark:bg-slate-950/90">
            <div className="shrink-0 border-b border-line px-5 py-4 dark:border-white/14">
              <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
                <div>
                  <p className="text-sm font-semibold text-mint dark:text-emerald-200">
                    Phiên hỏi đáp
                  </p>
                  <h2 className="mt-2 max-w-3xl text-2xl font-semibold leading-tight tracking-normal sm:text-3xl">
                    Đặt câu hỏi, nhận câu trả lời cùng nguồn.
                  </h2>
                </div>
                <div className="grid grid-cols-3 gap-2 text-center lg:w-72 xl:w-64 2xl:w-72">
                  <Metric label="Nguồn" value={sourceChunkCount ? `${sourceChunkCount} đoạn` : "0 đoạn"} />
                  <Metric label="Kiểm chứng" value="bật" />
                  <Metric
                    label="Trạng thái"
                    value={
                      isSourceBusy
                        ? "đang nạp"
                        : sourceStatus === "ready"
                          ? answer
                            ? "đã trả lời"
                            : "sẵn sàng"
                          : "chưa nạp"
                    }
                  />
                </div>
              </div>
            </div>

            <div className="flex-1 overflow-y-auto px-5 py-5">
              <div className="space-y-4">
                {messages.map((message) => (
                  <ChatBubble key={message.id} message={message} />
                ))}

                {error ? (
                  <div className="rounded-md border border-danger/30 bg-danger/8 px-3 py-2 text-sm text-danger dark:text-red-200">
                    {error}
                  </div>
                ) : null}
              </div>
            </div>

            <div className="shrink-0 border-t border-line bg-white/78 p-4 dark:border-white/14 dark:bg-slate-950/72">
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
                  disabled={isLoading || isSourceBusy || !question.trim()}
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

          {showCitations ? (
            <CitationPanel answer={answer} sourceChunks={sourceChunks} />
          ) : null}
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

function ChatBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  return (
    <div
      className={cn(
        "flex",
        isUser ? "justify-end" : "justify-start",
      )}
    >
      <article
        className={cn(
          "max-w-[86%] rounded-lg px-4 py-3",
          isUser
            ? "bg-ink text-white dark:bg-white dark:text-ink"
            : "border border-mint/25 bg-mint/8 dark:border-emerald-300/24 dark:bg-emerald-300/12",
        )}
      >
        <div
          className={cn(
            "mb-2 flex items-center gap-2 text-xs font-semibold",
            isUser ? "text-white/70 dark:text-ink/60" : "text-mint dark:text-emerald-200",
          )}
        >
          {isUser ? (
            <UserRound className="h-3.5 w-3.5" aria-hidden="true" />
          ) : (
            <Bot className="h-3.5 w-3.5" aria-hidden="true" />
          )}
          {isUser ? "Bạn" : "Agentic RAG"}
          {!isUser && message.status === "thinking" ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
          ) : null}
        </div>
        {message.content ? (
          <p className="whitespace-pre-wrap text-sm leading-7">{message.content}</p>
        ) : (
          <div className="space-y-2 py-1">
            <div className="h-3 w-48 rounded-full bg-mint/12 dark:bg-white/16" />
            <div className="h-3 w-32 rounded-full bg-mint/10 dark:bg-white/12" />
          </div>
        )}
        {!isUser && message.citations?.length ? (
          <div className="mt-3 flex flex-wrap gap-2">
            {message.citations.map((citation, index) => (
              <Badge
                className="border-mint/25 text-mint dark:border-emerald-300/24 dark:text-emerald-200"
                key={`${citation.chunk_id}-${index}`}
              >
                [{index + 1}] {citation.source}
              </Badge>
            ))}
          </div>
        ) : null}
      </article>
    </div>
  );
}

function createMessageId(): string {
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function SourcePanel({
  fileName,
  isUploading,
  setSourceChunkCount,
  setSourceChunks,
  setSourceStatus,
  setDocumentIds,
  setError,
  setFileName,
  setIsUploading,
  setSourceMode,
  setSourceText,
  sourceMode,
  sourcePlaceholder,
  sourceChunkCount,
  sourceStatus,
  sourceText,
}: {
  fileName: string;
  isUploading: boolean;
  setSourceChunkCount: (count: number) => void;
  setSourceChunks: (chunks: SourceChunk[]) => void;
  setSourceStatus: (status: SourceProcessingStatus) => void;
  setDocumentIds: (documentIds: string[]) => void;
  setError: (error: string) => void;
  setFileName: (fileName: string) => void;
  setIsUploading: (isUploading: boolean) => void;
  setSourceMode: (mode: SourceMode) => void;
  setSourceText: (text: string) => void;
  sourceMode: SourceMode;
  sourcePlaceholder: string;
  sourceChunkCount: number;
  sourceStatus: SourceProcessingStatus;
  sourceText: string;
}) {
  const sourceStatusLabel = sourceStatusText(sourceStatus, sourceChunkCount);
  const sourceProgress = sourceStatusProgress(sourceStatus);

  return (
    <aside className="flex min-h-0 min-w-0 flex-col gap-3 overflow-y-auto pr-1">
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
            <label className="flex min-h-32 min-w-0 cursor-pointer flex-col items-center justify-center overflow-hidden rounded-lg border border-dashed border-mint/40 bg-mist/70 px-3 py-4 text-center transition hover:border-mint hover:bg-white dark:border-emerald-300/34 dark:bg-slate-900/76 dark:hover:bg-slate-800">
              <Upload className="mb-2 h-5 w-5 text-mint dark:text-emerald-300" aria-hidden="true" />
              <span
                className="block max-w-full truncate px-1 text-sm font-medium"
                title={fileName || "Chọn tệp PDF"}
              >
                {fileName || "Chọn tệp PDF"}
              </span>
              <span className="mt-1 text-xs text-ink/50 dark:text-slate-300">
                {isUploading ? "Đang nạp vào RAGFlow" : sourceStatusLabel}
              </span>
              {fileName ? (
                <div className="mx-auto mt-3 w-full max-w-48 px-1">
                  <div
                    aria-label="Tiến trình nạp tài liệu"
                    aria-valuemax={100}
                    aria-valuemin={0}
                    aria-valuenow={sourceProgress}
                    className="h-1.5 overflow-hidden rounded-full bg-white/80 dark:bg-slate-800"
                    role="progressbar"
                  >
                    <div
                      className={cn(
                        "h-full rounded-full transition-all duration-500",
                        sourceStatus === "error"
                          ? "bg-danger"
                          : "bg-mint dark:bg-emerald-300",
                      )}
                      style={{ width: `${sourceProgress}%` }}
                    />
                  </div>
                  <div className="mt-1 flex min-w-0 items-center justify-between gap-3 text-[11px] text-ink/46 dark:text-slate-300">
                    <span className="min-w-0 truncate">{sourceStatusLabel}</span>
                    <span>{sourceProgress}%</span>
                  </div>
                </div>
              ) : null}
              <input
                accept="application/pdf"
                className="sr-only"
                type="file"
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  if (!file) {
                    setFileName("");
                    setDocumentIds([]);
                    setSourceChunkCount(0);
                    setSourceChunks([]);
                    setSourceStatus("idle");
                    return;
                  }

                  setFileName(file.name);
                  setError("");
                  setDocumentIds([]);
                  setSourceChunkCount(0);
                  setSourceChunks([]);
                  setSourceStatus("uploading");
                  setIsUploading(true);
                  void uploadSource(file)
                    .then((uploaded) => {
                      setDocumentIds([uploaded.document_id]);
                      setSourceStatus("processing");
                      return waitForSourceChunks(uploaded.document_id);
                    })
                    .then((chunks) => {
                      setSourceChunks(chunks);
                      setSourceChunkCount(chunks.length);
                      setSourceStatus("ready");
                    })
                    .catch((uploadError) => {
                      setSourceChunkCount(0);
                      setSourceChunks([]);
                      setSourceStatus("error");
                      setError(
                        uploadError instanceof Error
                          ? uploadError.message
                          : "Không nạp được tài liệu vào RAGFlow. Kiểm tra cấu hình API.",
                      );
                    })
                    .finally(() => setIsUploading(false));
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
          <h2 className="text-sm font-semibold">Tài liệu đang dùng</h2>
          <Badge className="border-mint/20 text-mint dark:border-emerald-300/24 dark:text-emerald-200">
            Thật
          </Badge>
        </div>
        <div className="space-y-2">
          {fileName ? (
            <article
              className="min-w-0 overflow-hidden rounded-md border border-line bg-paper/70 p-3 dark:border-white/14 dark:bg-slate-900/76"
            >
              <div className="flex min-w-0 items-start justify-between gap-2">
                <p className="min-w-0 flex-1 truncate text-sm font-medium" title={fileName}>
                  {fileName}
                </p>
                <span
                  className="max-w-24 shrink-0 truncate rounded-full bg-white px-2 py-0.5 text-[11px] text-ink/56 dark:bg-slate-800 dark:text-slate-200"
                  title={sourceStatus === "ready" ? "Sẵn sàng" : sourceStatusLabel}
                >
                  {sourceStatus === "ready" ? "Sẵn sàng" : sourceStatusLabel}
                </span>
              </div>
              <p className="mt-1 text-xs text-ink/52 dark:text-slate-300">
                {sourceChunkCount
                  ? `${sourceChunkCount} đoạn bằng chứng đã được tạo`
                  : "Đang chờ RAGFlow xử lý tài liệu"}
              </p>
            </article>
          ) : (
            <div className="rounded-md border border-dashed border-line bg-paper/70 p-4 text-sm text-ink/58 dark:border-white/14 dark:bg-slate-900/76 dark:text-slate-200">
              Chưa có tài liệu. Tải PDF lên để bắt đầu phiên hỏi đáp thật.
            </div>
          )}
        </div>
      </Panel>
    </aside>
  );
}

function CitationPanel({
  answer,
  sourceChunks,
}: {
  answer: AnswerResponse | null;
  sourceChunks: SourceChunk[];
}) {
  const evidenceItems = sourceChunks.slice(0, 4);

  return (
    <aside className="flex min-h-0 min-w-0 flex-col gap-3 overflow-y-auto pr-1">
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
                className="min-w-0 overflow-hidden rounded-md border border-line bg-paper/70 p-3 dark:border-white/14 dark:bg-slate-900/76"
                key={citation.chunk_id}
              >
                <div className="mb-2 flex min-w-0 items-center justify-between gap-2">
                  <span
                    className="min-w-0 flex-1 truncate rounded-full border border-mint/25 bg-white/70 px-2 py-1 text-xs font-medium text-mint dark:border-emerald-300/24 dark:bg-slate-950/70 dark:text-emerald-200"
                    title={citation.source}
                  >
                    [{index + 1}] {citation.source}
                  </span>
                  {citation.page ? <Badge>tr.{citation.page}</Badge> : null}
                </div>
                <p className="break-words text-xs leading-5 text-ink/62 [overflow-wrap:anywhere] dark:text-slate-300">
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
          {evidenceItems.length ? (
            evidenceItems.map((result, index) => (
            <div
              className="min-w-0 overflow-hidden rounded-md bg-paper/70 p-3 dark:bg-slate-900/76"
              key={result.chunk.chunk_id}
            >
              <div className="mb-2 flex min-w-0 items-center gap-2">
                <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-mint/10 text-xs font-semibold text-mint dark:bg-emerald-300/12 dark:text-emerald-200">
                  {index + 1}
                </span>
                <p
                  className="min-w-0 flex-1 truncate text-xs font-medium text-ink/52 dark:text-slate-300"
                  title={chunkSourceLabel(result)}
                >
                  {chunkSourceLabel(result)}
                </p>
              </div>
              <p className="max-h-36 overflow-hidden break-words text-sm leading-6 text-ink/72 [overflow-wrap:anywhere] dark:text-slate-200">
                {result.chunk.text}
              </p>
              <p className="mt-2 text-[11px] text-ink/46 dark:text-slate-400">
                {result.retriever} · điểm {result.score.toFixed(3)}
              </p>
            </div>
            ))
          ) : (
            <div className="rounded-md border border-dashed border-line bg-paper/70 p-4 text-sm text-ink/58 dark:border-white/14 dark:bg-slate-900/76 dark:text-slate-200">
              Các đoạn bằng chứng thật sẽ hiện ở đây sau khi PDF được xử lý.
            </div>
          )}
        </div>
      </Panel>
    </aside>
  );
}

async function uploadSource(file: File): Promise<SourceUploadResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(`${API_URL}/sources/upload`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    throw new Error(`Upload failed: ${response.status}`);
  }

  return (await response.json()) as SourceUploadResponse;
}

async function waitForSourceChunks(
  documentId: string,
  attempts = 20,
  delayMs = 3000,
): Promise<SourceChunk[]> {
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    const response = await fetch(`${API_URL}/sources/${documentId}/chunks`);
    if (response.ok) {
      const payload = (await response.json()) as SourceChunksResponse;
      if (payload.chunks.length > 0) {
        return payload.chunks;
      }
    }
    await delay(delayMs);
  }

  throw new Error("RAGFlow đã nhận tài liệu nhưng chưa tạo chunk. Chờ thêm rồi thử lại.");
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function sourceStatusText(status: SourceProcessingStatus, chunkCount: number): string {
  if (status === "uploading") return "Đang tải tài liệu lên RAGFlow";
  if (status === "processing") return "RAGFlow đang tách đoạn tài liệu";
  if (status === "ready") return `Sẵn sàng hỏi đáp (${chunkCount} đoạn)`;
  if (status === "error") return "Chưa nạp được tài liệu";
  return "Tệp sẽ được nạp vào RAGFlow";
}

function sourceStatusProgress(status: SourceProcessingStatus): number {
  if (status === "uploading") return 35;
  if (status === "processing") return 72;
  if (status === "ready") return 100;
  if (status === "error") return 100;
  return 0;
}

function chunkSourceLabel(result: SourceChunk): string {
  const source = metadataValue(result.chunk.metadata, "source")
    ?? metadataValue(result.chunk.metadata, "file_name")
    ?? "Đoạn nguồn";
  const page = metadataValue(result.chunk.metadata, "page");
  return page ? `${source} · tr.${page}` : source;
}

function metadataValue(
  metadata: Record<string, unknown>,
  key: string,
): string | null {
  const value = metadata[key];
  if (typeof value === "string" && value.trim()) return value;
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  return null;
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
        "min-w-0 overflow-hidden rounded-lg border border-line/80 bg-white/88 p-4 shadow-panel backdrop-blur-xl dark:border-white/14 dark:bg-slate-950/90",
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
