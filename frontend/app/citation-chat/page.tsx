"use client";

import Link from "next/link";
import {
  ArrowUpRight,
  Bot,
  ChevronLeft,
  Maximize2,
  Minimize2,
  FileText,
  Link as LinkIcon,
  Loader2,
  Menu,
  Moon,
  PanelRightOpen,
  SearchCheck,
  ShieldCheck,
  Sun,
  Upload,
  UserRound,
  X,
  type LucideIcon,
} from "lucide-react";
import type { Dispatch, ReactNode, SetStateAction } from "react";
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
  evidenceChunks?: SourceChunk[];
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
  total_chunks: number;
  chunks: SourceChunk[];
};

type UploadedSource = {
  datasetId: string;
  documentId: string;
  name: string;
  provider: string;
  mode: SourceMode;
  totalChunks: number;
  chunks: SourceChunk[];
  uploadedAt: number;
};

type SourceMode = "pdf" | "url" | "text";
type Theme = "light" | "dark";
type SourceProcessingStatus = "idle" | "uploading" | "processing" | "ready" | "error";
type SourceQueueStatus = "queued" | "uploading" | "processing" | "error";

type QueuedSource = {
  id: string;
  name: string;
  mode: SourceMode;
  status: SourceQueueStatus;
  progress: number;
  label: string;
};

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
  const [uploadedSources, setUploadedSources] = useState<UploadedSource[]>([]);
  const [selectedDocumentIds, setSelectedDocumentIds] = useState<string[]>([]);
  const [sourceStatus, setSourceStatus] = useState<SourceProcessingStatus>("idle");
  const [sourceChunkCount, setSourceChunkCount] = useState(0);
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
  const selectedSources = useMemo(
    () => uploadedSources.filter((source) => selectedDocumentIds.includes(source.documentId)),
    [selectedDocumentIds, uploadedSources],
  );
  const selectedSourceChunks = useMemo(
    () => selectedSources.flatMap((source) => source.chunks),
    [selectedSources],
  );

  const sourcePlaceholder = useMemo(() => {
    if (sourceMode === "url") return "https://example.com/chinh-sach";
    if (sourceMode === "text") return "Dán nội dung tài liệu hoặc ghi chú ở đây";
    return fileName || "Chưa chọn tệp";
  }, [fileName, sourceMode]);

  async function askQuestion() {
    const userQuestion = question.trim();
    if (!userQuestion) return;
    if (!selectedDocumentIds.length && !isSmallTalkQuestion(userQuestion)) {
      setError("Hãy chọn ít nhất một tài liệu đã nạp thành công trước khi đặt câu hỏi.");
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
          document_ids: selectedDocumentIds,
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
                evidenceChunks: selectedSourceChunks,
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
              evidenceChunks: selectedSourceChunks,
            });
          }

          if (streamEvent.event === "done") {
            const finalAnswer = streamEvent.data as AnswerResponse;
            setAnswer(finalAnswer);
            updateAssistantMessage(assistantMessageId, {
              content: finalAnswer.answer,
              status: finalAnswer.status,
              citations: finalAnswer.citations,
              evidenceChunks: selectedSourceChunks,
            });
          }
        }
      }
    } catch (requestError) {
      updateAssistantMessage(assistantMessageId, {
        content: "Không kết nối được API trả lời.",
        status: "not_found",
        citations: [],
        evidenceChunks: [],
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
                  Chat với tài liệu có nguồn kiểm chứng
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
              onSourceReady={(source) => {
                setUploadedSources((current) => [
                  source,
                  ...current.filter((item) => item.documentId !== source.documentId),
                ]);
                setSelectedDocumentIds((current) =>
                  current.includes(source.documentId)
                    ? current
                    : [...current, source.documentId],
                );
              }}
              selectedDocumentIds={selectedDocumentIds}
              setSourceChunkCount={setSourceChunkCount}
              setSourceStatus={setSourceStatus}
              setError={setError}
              setFileName={setFileName}
              setSelectedDocumentIds={setSelectedDocumentIds}
              setSourceMode={setSourceMode}
              setSourceText={setSourceText}
              sourceMode={sourceMode}
              sourcePlaceholder={sourcePlaceholder}
              sourceChunkCount={sourceChunkCount}
              sourceStatus={sourceStatus}
              sourceText={sourceText}
              uploadedSources={uploadedSources}
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
                <div className="grid grid-cols-2 gap-2 lg:w-60 xl:w-56 2xl:w-64">
                  <Metric
                    label="Tài liệu"
                    value={
                      selectedDocumentIds.length
                        ? `${selectedDocumentIds.length} đang dùng`
                        : "chưa chọn"
                    }
                  />
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
                  disabled={
                    isLoading
                    || !question.trim()
                    || (!selectedDocumentIds.length && !isSmallTalkQuestion(question))
                  }
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
            <CitationPanel answer={answer} sourceChunks={selectedSourceChunks} />
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
          <CitationSummary
            answerText={message.content}
            citations={message.citations}
            evidenceChunks={message.evidenceChunks ?? []}
          />
        ) : null}
      </article>
    </div>
  );
}

function CitationSummary({
  answerText,
  citations,
  evidenceChunks,
}: {
  answerText: string;
  citations: Citation[];
  evidenceChunks: SourceChunk[];
}) {
  const citationItems = visibleCitationItems(citations, answerText);

  return (
    <div className="mt-3 grid gap-2">
      {citationItems.map(({ citation, markerNumber }) => {
        const evidence = evidenceForCitation(citation, evidenceChunks);
        return (
          <article
            className="min-w-0 rounded-md border border-mint/20 bg-white/62 px-3 py-2 text-xs dark:border-emerald-300/20 dark:bg-slate-950/40"
            key={`${citation.chunk_id}-${markerNumber}`}
          >
            <div className="flex min-w-0 items-center justify-between gap-2">
              <span className="shrink-0 font-semibold text-mint dark:text-emerald-200">
                [{markerNumber}] Đoạn {evidence?.rank ?? markerNumber}
              </span>
              {evidence ? (
                <span className="shrink-0 text-[11px] text-ink/46 dark:text-slate-400">
                  điểm {evidence.score.toFixed(3)}
                </span>
              ) : null}
            </div>
            <p className="mt-1 truncate font-medium text-ink/70 dark:text-slate-200">
              {shortSourceName(citation.source)}
            </p>
            <p className="mt-1 line-clamp-2 break-words leading-5 text-ink/56 [overflow-wrap:anywhere] dark:text-slate-300">
              {evidence ? evidencePreviewText(evidence) : citation.chunk_id}
            </p>
          </article>
        );
      })}
    </div>
  );
}

function createMessageId(): string {
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function SourcePanel({
  fileName,
  onSourceReady,
  selectedDocumentIds,
  setSourceChunkCount,
  setSourceStatus,
  setError,
  setFileName,
  setSelectedDocumentIds,
  setSourceMode,
  setSourceText,
  sourceMode,
  sourcePlaceholder,
  sourceChunkCount,
  sourceStatus,
  sourceText,
  uploadedSources,
}: {
  fileName: string;
  onSourceReady: (source: UploadedSource) => void;
  selectedDocumentIds: string[];
  setSourceChunkCount: (count: number) => void;
  setSourceStatus: (status: SourceProcessingStatus) => void;
  setError: (error: string) => void;
  setFileName: (fileName: string) => void;
  setSelectedDocumentIds: Dispatch<SetStateAction<string[]>>;
  setSourceMode: (mode: SourceMode) => void;
  setSourceText: (text: string) => void;
  sourceMode: SourceMode;
  sourcePlaceholder: string;
  sourceChunkCount: number;
  sourceStatus: SourceProcessingStatus;
  sourceText: string;
  uploadedSources: UploadedSource[];
}) {
  const [queuedSources, setQueuedSources] = useState<QueuedSource[]>([]);
  const sourceStatusLabel = sourceStatusText(sourceStatus, sourceChunkCount);
  const sourceProgress = sourceStatusProgress(sourceStatus);
  const isSourceBusy = sourceStatus === "uploading" || sourceStatus === "processing";

  function resetSource() {
    setSourceChunkCount(0);
    setSourceStatus("idle");
  }

  function updateQueuedSource(id: string, patch: Partial<QueuedSource>) {
    setQueuedSources((current) =>
      current.map((source) => (source.id === id ? { ...source, ...patch } : source)),
    );
  }

  function removeQueuedSource(id: string) {
    setQueuedSources((current) => current.filter((source) => source.id !== id));
  }

  async function processQueuedUpload({
    item,
    mode,
    upload,
  }: {
    item: QueuedSource;
    mode: SourceMode;
    upload: () => Promise<SourceUploadResponse>;
  }) {
    setFileName(item.name);
    setSourceStatus("uploading");
    updateQueuedSource(item.id, {
      status: "uploading",
      progress: 35,
      label: "Đang tải lên RAGFlow",
    });

    const uploaded = await upload();
    setFileName(uploaded.name);
    setSourceStatus("processing");
    updateQueuedSource(item.id, {
      name: uploaded.name,
      status: "processing",
      progress: 72,
      label: "RAGFlow đang tách chunk",
    });

    const sourceChunks = await waitForSourceChunks(uploaded.document_id);
    const totalChunks = sourceChunks.total_chunks || sourceChunks.chunks.length;
    setSourceChunkCount(totalChunks);
    setSourceStatus("ready");
    onSourceReady({
      datasetId: uploaded.dataset_id,
      documentId: uploaded.document_id,
      name: uploaded.name,
      provider: uploaded.provider,
      mode,
      totalChunks,
      chunks: sourceChunks.chunks,
      uploadedAt: Date.now(),
    });
    removeQueuedSource(item.id);
  }

  async function processPdfQueue(files: File[], items: QueuedSource[]) {
    let completed = 0;
    setError("");

    for (const [index, file] of files.entries()) {
      const item = items[index];
      try {
        await processQueuedUpload({
          item,
          mode: "pdf",
          upload: () => uploadSource(file),
        });
        completed += 1;
      } catch (queueError) {
        const message = sourceErrorMessage(queueError);
        updateQueuedSource(item.id, {
          status: "error",
          progress: 100,
          label: message,
        });
        setSourceStatus("error");
        setSourceChunkCount(0);
        setError(message);
      }
    }

    if (completed > 0) {
      setSourceStatus("ready");
    }
  }

  function failSourceImport(sourceError: unknown) {
    setSourceChunkCount(0);
    setSourceStatus("error");
    setError(sourceErrorMessage(sourceError));
  }

  function importTextSource() {
    const text = sourceText.trim();
    if (!text) {
      setError(
        sourceMode === "url"
          ? "Nhập URL trước khi nạp nguồn."
          : "Nhập nội dung văn bản trước khi nạp nguồn.",
      );
      return;
    }

    const uploadMode = sourceMode;
    const queuedSource: QueuedSource = {
      id: createMessageId(),
      name: sourceMode === "url" ? text : "Văn bản người dùng",
      mode: uploadMode,
      status: "queued",
      progress: 8,
      label: "Đang chờ trong hàng đợi",
    };

    setError("");
    resetSource();
    setQueuedSources((current) => [queuedSource, ...current]);

    const uploadPromise =
      sourceMode === "url"
        ? uploadUrlSource(text)
        : uploadTextSource({ title: "van-ban-nguoi-dung", text });

    void processQueuedUpload({
      item: queuedSource,
      mode: uploadMode,
      upload: () => uploadPromise,
    })
      .catch((sourceError) => {
        const message = sourceErrorMessage(sourceError);
        updateQueuedSource(queuedSource.id, {
          status: "error",
          progress: 100,
          label: message,
        });
        failSourceImport(sourceError);
      });
  }

  function toggleSourceSelection(documentId: string) {
    setSelectedDocumentIds(
      selectedDocumentIds.includes(documentId)
        ? selectedDocumentIds.filter((id) => id !== documentId)
        : [...selectedDocumentIds, documentId],
    );
  }

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
            <label
              className="flex min-h-32 min-w-0 cursor-pointer flex-col items-center justify-center overflow-hidden rounded-lg border border-dashed border-mint/40 bg-mist/70 px-3 py-4 text-center transition hover:border-mint hover:bg-white dark:border-emerald-300/34 dark:bg-slate-900/76 dark:hover:bg-slate-800"
            >
              <Upload className="mb-2 h-5 w-5 text-mint dark:text-emerald-300" aria-hidden="true" />
              <span
                className="block max-w-full truncate px-1 text-sm font-medium"
                title="Chọn một hoặc nhiều PDF"
              >
                Chọn một hoặc nhiều PDF
              </span>
              <span className="mt-1 text-xs text-ink/50 dark:text-slate-300">
                Tài liệu sẽ được thêm vào danh sách bên dưới
              </span>
              <input
                accept="application/pdf"
                className="sr-only"
                multiple
                type="file"
                onChange={(event) => {
                  const files = Array.from(event.target.files ?? []);
                  if (!files.length) {
                    return;
                  }

                  const queued = files.map((file) => ({
                    id: createMessageId(),
                    name: file.name,
                    mode: "pdf" as const,
                    status: "queued" as const,
                    progress: 8,
                    label: "Đang chờ trong hàng đợi",
                  }));

                  setError("");
                  setQueuedSources((current) => [...queued, ...current]);
                  event.currentTarget.value = "";
                  void processPdfQueue(files, queued);
                }}
              />
            </label>
          ) : sourceMode === "url" ? (
            <div className="space-y-2">
              <Input
                placeholder={sourcePlaceholder}
                value={sourceText}
                onChange={(event) => setSourceText(event.target.value)}
              />
              <Button
                className="w-full"
                disabled={isSourceBusy || !sourceText.trim()}
                onClick={importTextSource}
                type="button"
              >
                {isSourceBusy ? (
                  <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                ) : (
                  <LinkIcon className="h-4 w-4" aria-hidden="true" />
                )}
                Nạp URL
              </Button>
              <SourceProgress
                label={sourceStatusLabel}
                progress={sourceProgress}
                status={sourceStatus}
                visible={Boolean(fileName)}
              />
            </div>
          ) : (
            <div className="space-y-2">
              <Textarea
                className="min-h-32"
                placeholder={sourcePlaceholder}
                value={sourceText}
                onChange={(event) => setSourceText(event.target.value)}
              />
              <Button
                className="w-full"
                disabled={isSourceBusy || !sourceText.trim()}
                onClick={importTextSource}
                type="button"
              >
                {isSourceBusy ? (
                  <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                ) : (
                  <FileText className="h-4 w-4" aria-hidden="true" />
                )}
                Nạp văn bản
              </Button>
              <SourceProgress
                label={sourceStatusLabel}
                progress={sourceProgress}
                status={sourceStatus}
                visible={Boolean(fileName)}
              />
            </div>
          )}
        </div>
      </Panel>

      <Panel>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold">Tài liệu đang dùng</h2>
          <Badge className="border-mint/20 text-mint dark:border-emerald-300/24 dark:text-emerald-200">
            {selectedDocumentIds.length} chọn
          </Badge>
        </div>
        <div className="space-y-2">
          {uploadedSources.length || queuedSources.length ? (
            <>
              {queuedSources.map((source) => (
                <article
                  className={cn(
                    "min-w-0 overflow-hidden rounded-md border p-3",
                    source.status === "error"
                      ? "border-danger/35 bg-danger/8 dark:border-red-300/24 dark:bg-red-300/10"
                      : "border-line bg-paper/70 dark:border-white/14 dark:bg-slate-900/76",
                  )}
                  key={source.id}
                >
                  <div className="flex min-w-0 items-start gap-3">
                    <span
                      className={cn(
                        "mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full",
                        source.status === "error"
                          ? "bg-danger/12 text-danger dark:text-red-200"
                          : "bg-mint/10 text-mint dark:bg-emerald-300/12 dark:text-emerald-200",
                      )}
                    >
                      <Loader2
                        className={cn(
                          "h-3.5 w-3.5",
                          source.status !== "error" && "animate-spin",
                        )}
                        aria-hidden="true"
                      />
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex min-w-0 items-center justify-between gap-2">
                        <p className="truncate text-sm font-medium" title={source.name}>
                          {source.name}
                        </p>
                        <span className="shrink-0 rounded-full bg-white px-2 py-0.5 text-[11px] text-ink/54 dark:bg-slate-800 dark:text-slate-300">
                          {sourceLabel(source.mode)}
                        </span>
                      </div>
                      <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-white/80 dark:bg-slate-800">
                        <div
                          className={cn(
                            "h-full rounded-full transition-all duration-500",
                            source.status === "error"
                              ? "bg-danger"
                              : "bg-mint dark:bg-emerald-300",
                          )}
                          style={{ width: `${source.progress}%` }}
                        />
                      </div>
                      <p
                        className={cn(
                          "mt-1 text-xs",
                          source.status === "error"
                            ? "text-danger dark:text-red-200"
                            : "text-ink/52 dark:text-slate-300",
                        )}
                      >
                        {source.label}
                      </p>
                    </div>
                  </div>
                </article>
              ))}

              {uploadedSources.map((source) => {
              const selected = selectedDocumentIds.includes(source.documentId);
              return (
                <label
                  className={cn(
                    "flex min-w-0 cursor-pointer items-start gap-3 overflow-hidden rounded-md border p-3 transition",
                    selected
                      ? "border-mint/45 bg-mint/8 dark:border-emerald-300/30 dark:bg-emerald-300/12"
                      : "border-line bg-paper/70 hover:bg-white dark:border-white/14 dark:bg-slate-900/76 dark:hover:bg-slate-800",
                  )}
                  key={source.documentId}
                >
                  <input
                    checked={selected}
                    className="mt-1 h-4 w-4 shrink-0 accent-mint"
                    onChange={() => toggleSourceSelection(source.documentId)}
                    type="checkbox"
                  />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium" title={source.name}>
                      {source.name}
                    </span>
                    <span className="mt-1 block text-xs text-ink/52 dark:text-slate-300">
                      {formatChunkCount(source.totalChunks)} · {sourceLabel(source.mode)}
                    </span>
                  </span>
                  <span className="shrink-0 rounded-full bg-white px-2 py-0.5 text-[11px] text-mint dark:bg-slate-800 dark:text-emerald-200">
                    sẵn sàng
                  </span>
                </label>
              );
              })}
            </>
          ) : (
            <div className="rounded-md border border-dashed border-line bg-paper/70 p-4 text-sm text-ink/58 dark:border-white/14 dark:bg-slate-900/76 dark:text-slate-200">
              Chưa có tài liệu. Tải PDF, URL hoặc văn bản lên để chọn nguồn hỏi đáp.
            </div>
          )}
        </div>
      </Panel>
    </aside>
  );
}

function SourceProgress({
  className,
  label,
  progress,
  status,
  visible,
}: {
  className?: string;
  label: string;
  progress: number;
  status: SourceProcessingStatus;
  visible: boolean;
}) {
  if (!visible) return null;

  return (
    <div className={cn("w-full rounded-md bg-white/54 p-2 dark:bg-slate-950/34", className)}>
      <div
        aria-label="Tiến trình nạp tài liệu"
        aria-valuemax={100}
        aria-valuemin={0}
        aria-valuenow={progress}
        className="h-1.5 overflow-hidden rounded-full bg-mint/12 dark:bg-slate-800"
        role="progressbar"
      >
        <div
          className={cn(
            "h-full rounded-full transition-all duration-500",
            status === "error" ? "bg-danger" : "bg-mint dark:bg-emerald-300",
          )}
          style={{ width: `${progress}%` }}
        />
      </div>
      <div className="mt-1 flex min-w-0 items-center justify-between gap-3 text-[11px] text-ink/46 dark:text-slate-300">
        <span className="min-w-0 truncate">{label}</span>
        <span>{progress}%</span>
      </div>
      {status === "ready" ? (
        <p className="mt-1 text-[11px] font-medium text-mint dark:text-emerald-200">
          Đã upload thành công, có thể chọn ở danh sách tài liệu.
        </p>
      ) : null}
    </div>
  );
}

function CitationPanel({
  answer,
  sourceChunks,
}: {
  answer: AnswerResponse | null;
  sourceChunks: SourceChunk[];
}) {
  const [expandedEvidence, setExpandedEvidence] = useState(false);
  const citationItems = visibleCitationItems(answer?.citations ?? [], answer?.answer ?? "");
  const citedEvidenceItems = citationItems.flatMap(({ citation, markerNumber }) => {
    const result = evidenceForCitation(citation, sourceChunks);
    return result ? [{ markerNumber, result }] : [];
  });
  const evidenceItems = answer ? citedEvidenceItems : [];

  return (
    <aside className="flex min-h-0 min-w-0 flex-col gap-3 overflow-hidden pr-1">
      <Panel className="flex min-h-0 basis-[38%] flex-col">
        <div className="mb-4 flex items-center justify-between">
          <div>
            <h2 className="text-sm font-semibold">Trích dẫn</h2>
            <p className="mt-1 text-xs text-ink/54 dark:text-slate-300">
              Nguồn được dùng trong câu trả lời
            </p>
          </div>
          <PanelRightOpen className="h-4 w-4 text-mint dark:text-emerald-300" aria-hidden="true" />
        </div>

        <div className="min-h-0 flex-1 space-y-3 overflow-y-auto pr-1">
          {citationItems.length ? (
            citationItems.map(({ citation, markerNumber }) => (
              <article
                className="min-w-0 overflow-hidden rounded-md border border-line bg-paper/70 p-3 dark:border-white/14 dark:bg-slate-900/76"
                key={`${citation.chunk_id}-${markerNumber}`}
              >
                <div className="mb-2 flex min-w-0 items-center justify-between gap-2">
                  <span
                    className="min-w-0 flex-1 truncate rounded-full border border-mint/25 bg-white/70 px-2 py-1 text-xs font-medium text-mint dark:border-emerald-300/24 dark:bg-slate-950/70 dark:text-emerald-200"
                    title={citation.source}
                  >
                    [{markerNumber}] {citation.source}
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

      <Panel className="flex min-h-0 flex-1 flex-col">
        <div className="mb-3 flex items-center justify-between gap-2">
          <h2 className="text-sm font-semibold">Đoạn bằng chứng</h2>
          <button
            aria-label={expandedEvidence ? "Thu nhỏ đoạn bằng chứng" : "Phóng to đoạn bằng chứng"}
            className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-line bg-white text-mint transition hover:bg-paper dark:border-white/14 dark:bg-slate-900/82 dark:text-emerald-200 dark:hover:bg-slate-800"
            onClick={() => setExpandedEvidence((value) => !value)}
            title={expandedEvidence ? "Thu nhỏ nội dung" : "Phóng to nội dung"}
            type="button"
          >
            {expandedEvidence ? (
              <Minimize2 className="h-4 w-4" aria-hidden="true" />
            ) : (
              <Maximize2 className="h-4 w-4" aria-hidden="true" />
            )}
          </button>
        </div>
        <div className="min-h-0 flex-1 space-y-2 overflow-y-auto pr-1">
          {evidenceItems.length ? (
            evidenceItems.map(({ markerNumber, result }) => (
              <EvidenceCard
                expanded={expandedEvidence}
                key={result.chunk.chunk_id}
                markerNumber={markerNumber}
                result={result}
              />
            ))
          ) : (
            <div className="rounded-md border border-dashed border-line bg-paper/70 p-4 text-sm text-ink/58 dark:border-white/14 dark:bg-slate-900/76 dark:text-slate-200">
              Đặt câu hỏi để xem các đoạn bằng chứng được retrieval dùng trong câu trả lời.
            </div>
          )}
        </div>
      </Panel>
    </aside>
  );
}

function EvidenceCard({
  expanded,
  markerNumber,
  result,
}: {
  expanded: boolean;
  markerNumber: number;
  result: SourceChunk;
}) {
  const sourceUrl = evidenceSourceUrl(result);
  const paragraphs = evidenceParagraphs(result);
  const visibleParagraphs = expanded ? paragraphs : paragraphs.slice(0, 2);

  return (
    <article className="min-w-0 overflow-hidden rounded-md bg-paper/70 p-3 dark:bg-slate-900/76">
      <div className="mb-3 flex min-w-0 items-start gap-2">
        <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-mint/10 text-xs font-semibold text-mint dark:bg-emerald-300/12 dark:text-emerald-200">
          {markerNumber}
        </span>
        <div className="min-w-0 flex-1">
          <p
            className="truncate text-xs font-semibold text-ink/72 dark:text-slate-200"
            title={chunkSourceLabel(result)}
          >
            {chunkSourceLabel(result)}
          </p>
          <p className="mt-1 text-[11px] text-ink/46 dark:text-slate-400">
            {result.retriever} · điểm {result.score.toFixed(3)}
          </p>
        </div>
      </div>

      {sourceUrl ? (
        <div className="mb-3 rounded-md border border-line/70 bg-white/70 px-3 py-2 dark:border-white/14 dark:bg-slate-950/50">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-ink/42 dark:text-slate-400">
            URL nguồn
          </p>
          <a
            className="mt-1 block break-words text-xs leading-5 text-mint [overflow-wrap:anywhere] hover:underline dark:text-emerald-200"
            href={sourceUrl}
            rel="noreferrer"
            target="_blank"
          >
            {sourceUrl}
          </a>
        </div>
      ) : null}

      <div
        className={cn(
          "space-y-2 overflow-hidden",
          expanded ? "max-h-none" : "max-h-40",
        )}
      >
        {visibleParagraphs.map((paragraph, paragraphIndex) => (
          <p
            className="break-words text-sm leading-6 text-ink/72 [overflow-wrap:anywhere] dark:text-slate-200"
            key={`${result.chunk.chunk_id}-${paragraphIndex}`}
          >
            {paragraph}
          </p>
        ))}
      </div>

      {!expanded && paragraphs.length > visibleParagraphs.length ? (
        <p className="mt-2 text-[11px] text-ink/46 dark:text-slate-400">
          Còn {paragraphs.length - visibleParagraphs.length} đoạn, bấm phóng to để xem thêm.
        </p>
      ) : null}
    </article>
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

async function uploadUrlSource(url: string): Promise<SourceUploadResponse> {
  const response = await fetch(`${API_URL}/sources/url`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
  });

  if (!response.ok) {
    throw new Error(`URL import failed: ${response.status}`);
  }

  return (await response.json()) as SourceUploadResponse;
}

async function uploadTextSource({
  title,
  text,
}: {
  title: string;
  text: string;
}): Promise<SourceUploadResponse> {
  const response = await fetch(`${API_URL}/sources/text`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title, text }),
  });

  if (!response.ok) {
    throw new Error(`Text import failed: ${response.status}`);
  }

  return (await response.json()) as SourceUploadResponse;
}

async function waitForSourceChunks(
  documentId: string,
  attempts = 20,
  delayMs = 3000,
): Promise<SourceChunksResponse> {
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    const response = await fetch(`${API_URL}/sources/${documentId}/chunks`);
    if (response.ok) {
      const payload = (await response.json()) as SourceChunksResponse;
      if (payload.chunks.length > 0) {
        return payload;
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
  if (status === "ready") return `Sẵn sàng hỏi đáp (${chunkCount} chunk)`;
  if (status === "error") return "Chưa nạp được tài liệu";
  return "Tệp sẽ được nạp vào RAGFlow";
}

function sourceErrorMessage(error: unknown): string {
  return error instanceof Error
    ? error.message
    : "Không nạp được tài liệu vào RAGFlow. Kiểm tra cấu hình API.";
}

function isSmallTalkQuestion(text: string): boolean {
  const normalized = normalizeSmallTalkText(text);
  if (!normalized) return false;

  const smallTalkPhrases = new Set([
    "alo",
    "ban co the lam gi",
    "ban giup duoc gi",
    "ban la ai",
    "cam on",
    "cam on ban",
    "chao",
    "chao ban",
    "hello",
    "help",
    "hey",
    "hi",
    "huong dan",
    "ok cam on",
    "thank you",
    "thanks",
    "tro giup",
    "xin chao",
    "xin chao ban",
  ]);
  return smallTalkPhrases.has(normalized);
}

function normalizeSmallTalkText(text: string): string {
  return text
    .trim()
    .toLowerCase()
    .replace(/đ/g, "d")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9\s]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function sourceStatusProgress(status: SourceProcessingStatus): number {
  if (status === "uploading") return 35;
  if (status === "processing") return 72;
  if (status === "ready") return 100;
  if (status === "error") return 100;
  return 0;
}

function sourceLabel(mode: SourceMode): string {
  if (mode === "pdf") return "PDF";
  if (mode === "url") return "URL";
  return "Văn bản";
}

function formatChunkCount(count: number): string {
  return `${count} chunk đã tạo`;
}

function chunkSourceLabel(result: SourceChunk): string {
  const source = metadataValue(result.chunk.metadata, "source")
    ?? metadataValue(result.chunk.metadata, "file_name")
    ?? "Đoạn nguồn";
  const page = metadataValue(result.chunk.metadata, "page");
  return page ? `${source} · tr.${page}` : source;
}

function evidenceSourceUrl(result: SourceChunk): string | null {
  const metadataUrl = metadataValue(result.chunk.metadata, "url");
  if (metadataUrl?.startsWith("http")) return metadataUrl;

  const match = result.chunk.text.match(/Source URL:\s*(https?:\/\/\S+)/i);
  return match?.[1] ?? null;
}

function evidenceParagraphs(result: SourceChunk): string[] {
  const withoutSourceUrl = result.chunk.text
    .replace(/Source URL:\s*https?:\/\/\S+/i, "")
    .trim();
  const normalized = withoutSourceUrl.replace(/\s+/g, " ");
  const sentences = normalized
    .split(/(?<=[.!?])\s+/)
    .map((item) => item.trim())
    .filter(Boolean);

  if (sentences.length > 1) {
    return sentences;
  }
  return normalized ? [normalized] : ["Không có nội dung hiển thị cho đoạn này."];
}

function visibleCitationItems(
  citations: Citation[],
  answerText: string,
): Array<{ citation: Citation; markerNumber: number }> {
  const markerNumbers = citationMarkersInAnswer(answerText);
  if (!markerNumbers.length) {
    return citations.map((citation, index) => ({
      citation,
      markerNumber: index + 1,
    }));
  }

  return markerNumbers
    .filter((markerNumber) => markerNumber >= 1 && markerNumber <= citations.length)
    .map((markerNumber) => ({
      citation: citations[markerNumber - 1],
      markerNumber,
    }));
}

function citationMarkersInAnswer(answerText: string): number[] {
  const markerPattern = /\[(\d+)\]/g;
  const seen = new Set<number>();
  const markers: number[] = [];

  for (const match of answerText.matchAll(markerPattern)) {
    const markerNumber = Number(match[1]);
    if (!Number.isInteger(markerNumber) || seen.has(markerNumber)) continue;
    seen.add(markerNumber);
    markers.push(markerNumber);
  }

  return markers;
}

function evidenceForCitation(
  citation: Citation,
  evidenceChunks: SourceChunk[],
): SourceChunk | undefined {
  return evidenceChunks.find((result) => result.chunk.chunk_id === citation.chunk_id);
}

function evidencePreviewText(result: SourceChunk): string {
  return evidenceParagraphs(result).join(" ").slice(0, 220);
}

function shortSourceName(source: string): string {
  const withoutExtension = source.replace(/\.(pdf|txt|md|html?)$/i, "");
  if (withoutExtension.length <= 54) return withoutExtension;
  return `${withoutExtension.slice(0, 28)}...${withoutExtension.slice(-18)}`;
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
    <div className="rounded-md border border-line/80 bg-white/72 px-3 py-2 text-left shadow-sm dark:border-white/14 dark:bg-slate-900/76">
      <p className="text-[11px] font-medium text-ink/48 dark:text-slate-300">{label}</p>
      <p className="mt-1 truncate text-sm font-semibold text-ink dark:text-white">{value}</p>
    </div>
  );
}
