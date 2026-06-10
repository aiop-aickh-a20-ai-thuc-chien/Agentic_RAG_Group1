"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import Link from "next/link";
import {
  ArrowUpRight,
  Bot,
  ChevronLeft,
  Eye,
  Maximize2,
  Minimize2,
  FileText,
  Link as LinkIcon,
  Loader2,
  Menu,
  Moon,
  PanelRightOpen,
  RotateCcw,
  Search,
  SearchCheck,
  ShieldCheck,
  Sun,
  Upload,
  UserRound,
  X,
  type LucideIcon,
} from "lucide-react";
import type { Dispatch, ReactNode, SetStateAction } from "react";
import { useEffect, useMemo, useState } from "react";
import { KnowledgeScene } from "@/components/knowledge-scene";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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
  evidence_chunks?: SourceChunk[];
};

type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  status?: "answered" | "not_found" | "thinking";
  citations?: Citation[];
  evidenceChunks?: SourceChunk[];
};

type ChatHistoryMessage = {
  role: "user" | "assistant";
  content: string;
};

type SourceUploadResponse = {
  provider: string;
  dataset_id: string;
  document_id: string;
  name: string;
  parse_started: boolean;
  source_type?: string | null;
  source?: string | null;
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

type SourceListItem = {
  provider: string;
  dataset_id: string;
  document_id: string;
  name: string;
  source_type: string;
  source: string;
  total_chunks: number;
  chunks: SourceChunk[];
  metadata: Record<string, unknown>;
};

type SourceListResponse = {
  provider: string;
  sources: SourceListItem[];
};

type HealthResponse = {
  source_store?: string;
};

type SourceDebugResponse = {
  provider: string;
  document_id: string;
  name: string;
  source_type: string;
  source: string;
  metadata: Record<string, unknown>;
  markdown: string;
  total_chunks: number;
  chunks: SourceChunk[];
};

type UploadedSource = {
  datasetId: string;
  documentId: string;
  name: string;
  provider: string;
  mode: SourceMode;
  source?: string;
  sourceType?: string;
  metadata?: Record<string, unknown>;
  totalChunks: number;
  chunks: SourceChunk[];
  uploadedAt: number;
};

type SourceMode = "pdf" | "url" | "text";
type Theme = "light" | "dark";
type SourceDebugTab = "source" | "markdown" | "chunks";
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

class HttpRequestError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(`${message}: ${status}`);
    this.name = "HttpRequestError";
    this.status = status;
  }
}

type StreamEvent = {
  event: string;
  data: Record<string, unknown>;
};

type ChatPageCache = {
  answer: AnswerResponse | null;
  messages: ChatMessage[];
  selectedCitationChunkId: string | null;
  selectedDocumentIds: string[];
  sourceMode: SourceMode;
};

const API_URL =
  process.env.NEXT_PUBLIC_AGENTIC_RAG_API_URL ?? "http://127.0.0.1:8000";
const URL_UPLOAD_CONCURRENCY = 8;
const SOURCE_CACHE_KEY = "agentic-rag:uploaded-sources:v1";
const SOURCE_MODE_KEY = "agentic-rag:source-mode:v1";
const CHAT_STATE_CACHE_KEY = "agentic-rag:chat-state:v1";

function createWelcomeMessage(): ChatMessage {
  return {
    id: "welcome",
    role: "assistant",
    content: "Tải tài liệu lên, chờ trạng thái sẵn sàng rồi đặt câu hỏi.",
    status: "answered",
    citations: [],
  };
}

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
  const [answer, setAnswer] = useState<AnswerResponse | null>(null);
  const [selectedCitationChunkId, setSelectedCitationChunkId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([createWelcomeMessage()]);
  const [error, setError] = useState("");
  const [hasRestoredClientState, setHasRestoredClientState] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [sourceDeletionDisabled, setSourceDeletionDisabled] = useState(true);

  const isDark = theme === "dark";
  const citationCount = visibleCitationItems(answer?.citations ?? [], answer?.answer ?? "").length;
  const isSourceBusy = sourceStatus === "uploading" || sourceStatus === "processing";
  const selectedSources = useMemo(
    () => uploadedSources.filter((source) => selectedDocumentIds.includes(source.documentId)),
    [selectedDocumentIds, uploadedSources],
  );
  const selectedSourceChunks = useMemo(
    () => selectedSources.flatMap((source) => source.chunks),
    [selectedSources],
  );

  useEffect(() => {
    let cancelled = false;

    async function hydrateSources() {
      const cachedChatState = readCachedChatState();
      const cachedSources = readCachedSources();
      const cachedSelectedIds =
        cachedChatState?.selectedDocumentIds ?? cachedSources.map((source) => source.documentId);

      setSourceMode(cachedChatState?.sourceMode ?? readCachedSourceMode());
      setUploadedSources(cachedSources);
      setSelectedDocumentIds(cachedSelectedIds);
      setAnswer(cachedChatState?.answer ?? null);
      setSelectedCitationChunkId(cachedChatState?.selectedCitationChunkId ?? null);
      setMessages(cachedChatState?.messages ?? [createWelcomeMessage()]);
      if (cachedSources.length) {
        setSourceStatus("ready");
      }

      try {
        const [healthResult, sourceList] = await Promise.all([
          fetchHealth().catch(() => null),
          fetchSources(),
        ]);
        if (cancelled) return;

        if (healthResult) {
          setSourceDeletionDisabled(
            healthResult.source_store !== "jsonl" && healthResult.source_store !== "postgres",
          );
        }
        const metadataSources = sourceList.sources.map((source, index) =>
          uploadedSourceFromListItem(source, index),
        );
        const restoredSources = mergeSourcesWithCachedChunks(metadataSources, cachedSources);
        setUploadedSources(restoredSources);
        setSelectedDocumentIds((current) => {
          const availableIds = new Set(restoredSources.map((source) => source.documentId));
          const preserved = current.filter((id) => availableIds.has(id));
          return preserved.length ? preserved : restoredSources.map((source) => source.documentId);
        });
        if (restoredSources.length) {
          setSourceStatus("ready");
        }

        // NOTE: We intentionally do NOT eager-fetch chunks for every source
        // here. With hundreds of documents that fired one GET /sources/{id}/chunks
        // per doc on every page load (N+1 flood). Chunks are only needed for the
        // client-side evidence preview / source search — and the answer flow gets
        // its evidence from the backend (/answer/stream returns evidence_chunks via
        // server-side Qdrant retrieval). Cached chunks from localStorage are already
        // merged above; anything else loads lazily (upload polling / on demand).
      } catch (hydrateError) {
        if (!cancelled && !cachedSources.length) {
          setError(
            hydrateError instanceof Error
              ? hydrateError.message
              : "Khong tai lai duoc danh sach tai lieu.",
          );
        }
      } finally {
        if (!cancelled) {
          setHasRestoredClientState(true);
        }
      }
    }

    hydrateSources();

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!hasRestoredClientState) return;
    writeCachedSources(uploadedSources);
  }, [hasRestoredClientState, uploadedSources]);

  useEffect(() => {
    if (!hasRestoredClientState) return;
    writeCachedChatState({
      answer,
      messages,
      selectedCitationChunkId,
      selectedDocumentIds,
      sourceMode,
    });
  }, [
    answer,
    hasRestoredClientState,
    messages,
    selectedCitationChunkId,
    selectedDocumentIds,
    sourceMode,
  ]);

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
    setSelectedCitationChunkId(null);
    const requestHistory = chatHistoryForRequest(messages);

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
          document_ids: selectedDocumentIds,
          history: requestHistory,
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
            const finalEvidenceChunks = finalAnswer.evidence_chunks ?? selectedSourceChunks;
            setAnswer(finalAnswer);
            const firstCitation = visibleCitationItems(
              finalAnswer.citations,
              finalAnswer.answer,
            )[0]?.citation;
            setSelectedCitationChunkId(firstCitation?.chunk_id ?? null);
            updateAssistantMessage(assistantMessageId, {
              content: finalAnswer.answer,
              status: finalAnswer.status,
              citations: finalAnswer.citations,
              evidenceChunks: finalEvidenceChunks,
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

  function resetConversation() {
    setMessages([createWelcomeMessage()]);
    setAnswer(null);
    setSelectedCitationChunkId(null);
    setQuestion("");
    setError("");
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
              onSourceRemove={async (documentId) => {
                try {
                  await fetch(
                    `${API_URL}/sources/${encodeURIComponent(documentId)}`,
                    { method: "DELETE" },
                  );
                } catch {
                  // optimistic: xóa UI dù API fail
                }
                setUploadedSources((current) =>
                  current.filter((source) => source.documentId !== documentId),
                );
                setSelectedDocumentIds((current) =>
                  current.filter((id) => id !== documentId),
                );
              }}
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
              onClearAll={async () => {
                try {
                  await fetch(`${API_URL}/sources`, { method: "DELETE" });
                } catch {
                  // optimistic
                }
                setUploadedSources([]);
                setSelectedDocumentIds([]);
              }}
              selectedDocumentIds={selectedDocumentIds}
              setSourceStatus={setSourceStatus}
              setError={setError}
              setFileName={setFileName}
              setSelectedDocumentIds={setSelectedDocumentIds}
              setSourceMode={setSourceMode}
              setSourceText={setSourceText}
              sourceDeletionDisabled={sourceDeletionDisabled}
              sourceMode={sourceMode}
              sourcePlaceholder={sourcePlaceholder}
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
                <div className="flex flex-col gap-2 lg:w-60 xl:w-56 2xl:w-64">
                  <Button
                    className="w-full"
                    disabled={isLoading}
                    onClick={resetConversation}
                    variant="secondary"
                  >
                    <RotateCcw className="h-4 w-4" aria-hidden="true" />
                    Reset hội thoại
                  </Button>
                  <div className="grid grid-cols-2 gap-2">
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
            </div>

            <div className="flex-1 overflow-y-auto px-5 py-5">
              <div className="space-y-4">
                {messages.map((message) => (
                  <ChatBubble
                    key={message.id}
                    message={message}
                    onSelectCitation={setSelectedCitationChunkId}
                    selectedCitationChunkId={selectedCitationChunkId}
                  />
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
            <CitationPanel
              answer={answer}
              onSelectCitation={setSelectedCitationChunkId}
              selectedCitationChunkId={selectedCitationChunkId}
              sourceChunks={answer?.evidence_chunks ?? selectedSourceChunks}
            />
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

function chatHistoryForRequest(messages: ChatMessage[]): ChatHistoryMessage[] {
  return messages
    .filter((message) =>
      message.id !== "welcome"
      && message.status !== "thinking"
      && message.content.trim().length > 0,
    )
    .slice(-6)
    .map((message) => ({
      role: message.role,
      content: message.content.trim(),
    }));
}

function ChatBubble({
  message,
  onSelectCitation,
  selectedCitationChunkId,
}: {
  message: ChatMessage;
  onSelectCitation: (chunkId: string) => void;
  selectedCitationChunkId: string | null;
}) {
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
          isUser ? (
            <p className="whitespace-pre-wrap text-sm leading-7">{message.content}</p>
          ) : (
            <div className="prose prose-sm max-w-none leading-7 dark:prose-invert
              prose-p:my-1
              prose-ul:my-1 prose-ul:pl-4
              prose-ol:my-1 prose-ol:pl-4
              prose-li:my-0
              prose-headings:my-2 prose-headings:font-semibold
              prose-strong:font-semibold
              prose-table:text-sm prose-table:border-collapse
              prose-th:border prose-th:border-mint/30 prose-th:px-2 prose-th:py-1 prose-th:bg-mint/8
              prose-td:border prose-td:border-mint/20 prose-td:px-2 prose-td:py-1">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
            </div>
          )
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
            onSelectCitation={onSelectCitation}
            selectedCitationChunkId={selectedCitationChunkId}
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
  onSelectCitation,
  selectedCitationChunkId,
}: {
  answerText: string;
  citations: Citation[];
  evidenceChunks: SourceChunk[];
  onSelectCitation: (chunkId: string) => void;
  selectedCitationChunkId: string | null;
}) {
  const citationItems = visibleCitationItems(citations, answerText);

  return (
    <div className="mt-3 grid gap-2">
      {citationItems.map(({ citation, markerNumber }) => {
        const evidence = evidenceForCitation(citation, evidenceChunks);
        return (
          <button
            className={cn(
              "min-w-0 rounded-md border px-3 py-2 text-left text-xs transition",
              selectedCitationChunkId === citation.chunk_id
                ? "border-mint bg-mint/10 shadow-lift dark:border-emerald-300/36 dark:bg-emerald-300/12"
                : "border-mint/20 bg-white/62 hover:border-mint/36 hover:bg-white dark:border-emerald-300/20 dark:bg-slate-950/40 dark:hover:bg-slate-900",
            )}
            key={`${citation.chunk_id}-${markerNumber}`}
            onClick={() => onSelectCitation(citation.chunk_id)}
            type="button"
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
          </button>
        );
      })}
    </div>
  );
}

function createMessageId(): string {
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function parseSourceUrls(value: string): string[] {
  const urls = new Set<string>();
  for (const rawToken of value.split(/[\s,]+/)) {
    const token = rawToken.trim().replace(/[),.;]+$/, "");
    if (!/^https?:\/\//i.test(token)) continue;

    try {
      const url = new URL(token);
      if (url.protocol === "http:" || url.protocol === "https:") {
        urls.add(url.href);
      }
    } catch {
      // Ignore malformed tokens so pasted notes around URLs do not block the batch.
    }
  }
  return [...urls];
}

function SourcePanel({
  fileName,
  onSourceRemove,
  onSourceReady,
  onClearAll,
  selectedDocumentIds,
  setSourceStatus,
  setError,
  setFileName,
  setSelectedDocumentIds,
  setSourceMode,
  setSourceText,
  sourceDeletionDisabled,
  sourceMode,
  sourcePlaceholder,
  sourceStatus,
  sourceText,
  uploadedSources,
}: {
  fileName: string;
  onSourceRemove: (documentId: string) => void;
  onSourceReady: (source: UploadedSource) => void;
  onClearAll: () => void;
  selectedDocumentIds: string[];
  setSourceStatus: (status: SourceProcessingStatus) => void;
  setError: (error: string) => void;
  setFileName: (fileName: string) => void;
  setSelectedDocumentIds: Dispatch<SetStateAction<string[]>>;
  setSourceMode: (mode: SourceMode) => void;
  setSourceText: (text: string) => void;
  sourceDeletionDisabled: boolean;
  sourceMode: SourceMode;
  sourcePlaceholder: string;
  sourceStatus: SourceProcessingStatus;
  sourceText: string;
  uploadedSources: UploadedSource[];
}) {
  const [queuedSources, setQueuedSources] = useState<QueuedSource[]>([]);
  const [sourceSearch, setSourceSearch] = useState("");
  const normalizedSourceSearch = normalizeSearchText(sourceSearch);
  const filteredUploadedSources = uploadedSources.filter((source) =>
    sourceMatchesSearch(source, normalizedSourceSearch),
  );
  const uploadedSourceIds = uploadedSources.map((source) => source.documentId);
  const allSourcesSelected =
    uploadedSourceIds.length > 0 &&
    uploadedSourceIds.every((documentId) => selectedDocumentIds.includes(documentId));

  function resetSource() {
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
    setFileName(displayQueuedSourceName(item));
    setSourceStatus("uploading");
    updateQueuedSource(item.id, {
      status: "uploading",
      progress: 35,
      label: "Đang tải tài liệu",
    });

    const uploaded = await upload();
    setFileName(mode === "url" ? displayUrlName(uploaded.source ?? item.name) : uploaded.name);
    setSourceStatus("processing");
    updateQueuedSource(item.id, {
      name: uploaded.name,
      status: "processing",
      progress: 72,
      label: "Đang tách chunk",
    });

    const sourceChunks = await waitForSourceChunks(uploaded.document_id);
    const totalChunks = sourceChunks.total_chunks || sourceChunks.chunks.length;
    setSourceStatus("ready");
    onSourceReady({
      datasetId: uploaded.dataset_id,
      documentId: uploaded.document_id,
      name: uploaded.name,
      provider: uploaded.provider,
      mode,
      source: uploaded.source ?? undefined,
      sourceType: uploaded.source_type ?? undefined,
      metadata: {},
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
        setError(message);
      }
    }

    if (completed > 0) {
      setSourceStatus("ready");
    }
  }

  async function processUrlQueue(urls: string[], items: QueuedSource[]) {
    let completed = 0;
    let failed = 0;
    let visibleFailed = 0;
    let nextIndex = 0;
    setError("");

    async function worker() {
      while (nextIndex < urls.length) {
        const index = nextIndex;
        nextIndex += 1;
        const item = items[index];
        try {
          await processQueuedUpload({
            item,
            mode: "url",
            upload: () => uploadUrlSource(urls[index]),
          });
          completed += 1;
        } catch (queueError) {
          failed += 1;
          if (isHttpStatus(queueError, 422) || isHttpStatus(queueError, 502)) {
            removeQueuedSource(item.id);
            continue;
          }

          visibleFailed += 1;
          const message = sourceErrorMessage(queueError);
          updateQueuedSource(item.id, {
            status: "error",
            progress: 100,
            label: message,
          });
          setError(message);
        }
      }
    }

    const workerCount = Math.min(URL_UPLOAD_CONCURRENCY, urls.length);
    await Promise.all(Array.from({ length: workerCount }, () => worker()));

    if (completed > 0) {
      setSourceStatus("ready");
      return;
    }
    if (visibleFailed > 0) {
      setSourceStatus("error");
      return;
    }
    if (failed > 0) {
      setFileName("");
      setSourceStatus("idle");
    }
  }

  function failSourceImport(sourceError: unknown) {
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

    if (sourceMode === "url") {
      const urls = parseSourceUrls(text);
      if (!urls.length) {
        setError("Nhập ít nhất một URL http/https hợp lệ trước khi nạp nguồn.");
        return;
      }

      const loadedUrls = new Set(
        uploadedSources
          .filter((source) => source.mode === "url")
          .map((source) => normalizeSourceUrl(source.source || source.name))
          .filter(Boolean),
      );
      const urlsToQueue = urls.filter((url) => !loadedUrls.has(normalizeSourceUrl(url)));
      const skippedCount = urls.length - urlsToQueue.length;
      if (!urlsToQueue.length) {
        setError("Tất cả URL đã được nạp trước đó nên đã skip.");
        return;
      }

      const queued = urlsToQueue.map((url) => ({
        id: createMessageId(),
        name: url,
        mode: "url" as const,
        status: "queued" as const,
        progress: 8,
        label: "Đang chờ trong hàng đợi",
      }));

      setError("");
      if (skippedCount > 0) {
        setFileName(`Đã skip ${skippedCount} URL đã nạp.`);
      }
      resetSource();
      setQueuedSources((current) => [...queued, ...current]);
      setSourceText("");
      void processUrlQueue(urlsToQueue, queued);
      return;
    }

    const uploadMode = sourceMode;
    const queuedSource: QueuedSource = {
      id: createMessageId(),
      name: "Văn bản người dùng",
      mode: uploadMode,
      status: "queued",
      progress: 8,
      label: "Đang chờ trong hàng đợi",
    };

    setError("");
    resetSource();
    setQueuedSources((current) => [queuedSource, ...current]);
    setSourceText("");

    const uploadPromise = uploadTextSource({ title: "van-ban-nguoi-dung", text });

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

  function toggleAllSourceSelection() {
    setSelectedDocumentIds(allSourcesSelected ? [] : uploadedSourceIds);
  }

  return (
    <aside className="flex min-h-0 min-w-0 flex-col gap-3 overflow-y-auto pr-1">
      <Panel className="overflow-visible">
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
            <div className="space-y-3">
              <Textarea
                className="min-h-24"
                placeholder={`${sourcePlaceholder}\nCó thể dán nhiều URL, mỗi dòng một link`}
                value={sourceText}
                onChange={(event) => setSourceText(event.target.value)}
              />
              <Button
                className="w-full"
                disabled={!sourceText.trim()}
                onClick={importTextSource}
                type="button"
              >
                <LinkIcon className="h-4 w-4" aria-hidden="true" />
                Nạp URL
              </Button>
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
                disabled={!sourceText.trim()}
                onClick={importTextSource}
                type="button"
              >
                <FileText className="h-4 w-4" aria-hidden="true" />
                Nạp văn bản
              </Button>
            </div>
          )}
        </div>
      </Panel>

      <Panel className="flex min-h-0 flex-col">
        <div className="mb-3 flex items-start justify-between gap-3">
          <h2 className="text-sm font-semibold">Tài liệu đang dùng</h2>
          <div className="flex flex-wrap items-center justify-end gap-2">
            <Badge className="border-mint/20 text-mint dark:border-emerald-300/24 dark:text-emerald-200">
              {selectedDocumentIds.length} chọn
            </Badge>
            {uploadedSources.length > 0 && (
              <button
                className="rounded-full border border-mint/20 bg-white px-2.5 py-1 text-[11px] font-semibold text-mint transition hover:bg-mint/8 dark:border-emerald-300/24 dark:bg-slate-900 dark:text-emerald-200 dark:hover:bg-emerald-300/10"
                onClick={toggleAllSourceSelection}
                type="button"
              >
                {allSourcesSelected ? "Bỏ chọn" : "Chọn tất cả"}
              </button>
            )}
            {uploadedSources.length > 0 && !sourceDeletionDisabled && (
              <button
                className="text-[11px] font-medium text-ink/40 transition hover:text-danger dark:text-slate-500 dark:hover:text-red-300"
                onClick={() => {
                  if (window.confirm(`Xóa tất cả ${uploadedSources.length} tài liệu khỏi vector DB?`)) {
                    onClearAll();
                  }
                }}
                title="Xóa tất cả tài liệu"
                type="button"
              >
                Xóa tất cả
              </button>
            )}
          </div>
        </div>
        <div className="relative mb-3">
          <Search
            className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink/38 dark:text-slate-500"
            aria-hidden="true"
          />
          <input
            className="h-9 w-full rounded-md border border-line bg-white/78 pl-9 pr-9 text-sm text-ink outline-none transition placeholder:text-ink/36 focus:border-mint focus:ring-2 focus:ring-mint/12 dark:border-white/14 dark:bg-slate-900/78 dark:text-slate-50 dark:placeholder:text-slate-500"
            placeholder="Tìm tài liệu, URL, loại..."
            value={sourceSearch}
            onChange={(event) => setSourceSearch(event.target.value)}
          />
          {sourceSearch ? (
            <button
              aria-label="Xóa từ khóa tìm kiếm"
              className="absolute right-2 top-1/2 inline-flex h-6 w-6 -translate-y-1/2 items-center justify-center rounded-md text-ink/42 transition hover:bg-paper hover:text-ink dark:text-slate-500 dark:hover:bg-slate-800 dark:hover:text-slate-200"
              onClick={() => setSourceSearch("")}
              type="button"
            >
              <X className="h-3.5 w-3.5" aria-hidden="true" />
            </button>
          ) : null}
        </div>
        <div className="max-h-[min(38vh,22rem)] min-h-0 space-y-2 overflow-y-auto pr-1">
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
                      <div className="grid min-w-0 grid-cols-[minmax(0,1fr)_auto_auto] items-center gap-2">
                        <p className="min-w-0 truncate text-sm font-medium" title={source.name}>
                          {displayQueuedSourceName(source)}
                        </p>
                        <span className="shrink-0 rounded-full bg-white px-2 py-0.5 text-[11px] text-ink/54 dark:bg-slate-800 dark:text-slate-300">
                          {sourceLabel(source.mode)}
                        </span>
                        {source.status === "error" && (
                          <button
                            aria-label={`Xóa ${source.name}`}
                            className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-md border border-danger/30 bg-white text-danger/70 transition hover:border-danger hover:bg-danger/8 dark:border-red-300/24 dark:bg-slate-900 dark:text-red-300 dark:hover:bg-red-300/10"
                            onClick={() => removeQueuedSource(source.id)}
                            type="button"
                          >
                            <X className="h-3 w-3" aria-hidden="true" />
                          </button>
                        )}
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

              {filteredUploadedSources.map((source) => {
                const selected = selectedDocumentIds.includes(source.documentId);
                return (
                  <article
                    className={cn(
                      "grid min-w-0 grid-cols-[auto_minmax(0,1fr)_auto] items-start gap-3 overflow-hidden rounded-md border p-3 transition",
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
                    <button
                      className="min-w-0 flex-1 text-left"
                      onClick={() => toggleSourceSelection(source.documentId)}
                      type="button"
                    >
                      <span
                        className="line-clamp-2 break-words text-sm font-semibold leading-5 [overflow-wrap:anywhere]"
                        title={source.source || source.name}
                      >
                        {displaySourceName(source)}
                      </span>
                      <span className="mt-1 block text-xs leading-5 text-ink/52 dark:text-slate-300">
                        {formatChunkCount(source.totalChunks)} · {sourceLabel(source.mode)}
                      </span>
                    </button>
                    <div className="flex shrink-0 items-start gap-2">
                      <Link
                        aria-label={`Xem debug ${source.name}`}
                        className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md border border-line bg-white text-mint transition hover:bg-paper dark:border-white/14 dark:bg-slate-900 dark:text-emerald-200 dark:hover:bg-slate-800"
                        href={`/citation-chat/sources/${encodeURIComponent(source.documentId)}`}
                        title="Xem parse và chunk"
                      >
                        <Eye className="h-3.5 w-3.5" aria-hidden="true" />
                      </Link>
                      {!sourceDeletionDisabled && (
                        <button
                          aria-label={`Xóa ${source.name}`}
                          className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md border border-line bg-white text-ink/54 transition hover:border-danger/35 hover:bg-danger/8 hover:text-danger dark:border-white/14 dark:bg-slate-900 dark:text-slate-300 dark:hover:border-red-300/30 dark:hover:bg-red-300/10 dark:hover:text-red-200"
                          onClick={() => onSourceRemove(source.documentId)}
                          title="Xóa khỏi danh sách"
                          type="button"
                        >
                          <X className="h-3.5 w-3.5" aria-hidden="true" />
                        </button>
                      )}
                    </div>
                  </article>
                );
              })}
              {!filteredUploadedSources.length && uploadedSources.length ? (
                <div className="rounded-md border border-dashed border-line bg-paper/70 p-4 text-sm text-ink/54 dark:border-white/14 dark:bg-slate-900/76 dark:text-slate-300">
                  Không tìm thấy tài liệu phù hợp.
                </div>
              ) : null}
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

function SourceDebugPanel({
  activeTab,
  debug,
  error,
  isLoading,
  onClose,
  onTabChange,
}: {
  activeTab: SourceDebugTab;
  debug: SourceDebugResponse | null;
  error: string;
  isLoading: boolean;
  onClose: () => void;
  onTabChange: (tab: SourceDebugTab) => void;
}) {
  const tabs: Array<{ id: SourceDebugTab; label: string }> = [
    { id: "source", label: "Gốc" },
    { id: "markdown", label: "Markdown" },
    { id: "chunks", label: "Chunks" },
  ];

  return (
    <aside className="flex min-h-0 min-w-0 flex-col gap-3 overflow-hidden pr-1">
      <Panel className="flex min-h-0 flex-1 flex-col">
        <div className="mb-4 flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="text-sm font-semibold">Debug ingestion</h2>
            <p className="mt-1 truncate text-xs text-ink/54 dark:text-slate-300">
              {debug?.name ?? "Đang tải source"}
            </p>
          </div>
          <button
            aria-label="Đóng debug source"
            className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-line bg-white text-ink/54 transition hover:bg-paper dark:border-white/14 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800"
            onClick={onClose}
            title="Đóng debug"
            type="button"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>

        <div className="mb-3 grid grid-cols-3 gap-1 rounded-md bg-paper/70 p-1 dark:bg-slate-900/76">
          {tabs.map((tab) => (
            <button
              className={cn(
                "h-8 rounded px-2 text-xs font-medium transition",
                activeTab === tab.id
                  ? "bg-white text-mint shadow-sm dark:bg-slate-800 dark:text-emerald-200"
                  : "text-ink/58 hover:bg-white/70 dark:text-slate-300 dark:hover:bg-slate-800/70",
              )}
              key={tab.id}
              onClick={() => onTabChange(tab.id)}
              type="button"
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto pr-1">
          {isLoading ? (
            <div className="flex items-center gap-2 rounded-md border border-line bg-paper/70 p-4 text-sm text-ink/58 dark:border-white/14 dark:bg-slate-900/76 dark:text-slate-200">
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              Đang tải debug source...
            </div>
          ) : error ? (
            <div className="rounded-md border border-danger/30 bg-danger/8 p-4 text-sm text-danger dark:text-red-200">
              {error}
            </div>
          ) : debug ? (
            <SourceDebugTabContent activeTab={activeTab} debug={debug} />
          ) : null}
        </div>
      </Panel>
    </aside>
  );
}

function SourceDebugTabContent({
  activeTab,
  debug,
}: {
  activeTab: SourceDebugTab;
  debug: SourceDebugResponse;
}) {
  if (activeTab === "markdown") {
    return debug.markdown.trim() ? (
      <pre className="whitespace-pre-wrap break-words rounded-md border border-line bg-paper/70 p-3 text-xs leading-5 text-ink/72 [overflow-wrap:anywhere] dark:border-white/14 dark:bg-slate-900/76 dark:text-slate-200">
        {debug.markdown}
      </pre>
    ) : (
      <EmptyDebugState text="Source này chưa có Markdown lưu trong local artifact." />
    );
  }

  if (activeTab === "chunks") {
    return (
      <div className="space-y-2">
        <div className="rounded-md border border-line bg-paper/70 p-3 text-xs text-ink/58 dark:border-white/14 dark:bg-slate-900/76 dark:text-slate-300">
          {debug.total_chunks} chunk đã tạo
        </div>
        {debug.chunks.map((result) => (
          <article
            className="min-w-0 overflow-hidden rounded-md border border-line bg-paper/70 p-3 dark:border-white/14 dark:bg-slate-900/76"
            key={result.chunk.chunk_id}
          >
            <div className="mb-2 flex min-w-0 items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="truncate text-xs font-semibold text-ink/72 dark:text-slate-200">
                  Chunk {result.rank}
                </p>
                <p className="mt-1 break-words text-[11px] text-ink/46 [overflow-wrap:anywhere] dark:text-slate-400">
                  {result.chunk.chunk_id}
                </p>
              </div>
              <Badge>{metadataValue(result.chunk.metadata, "section") ?? "main"}</Badge>
            </div>
            <p className="break-words text-sm leading-6 text-ink/72 [overflow-wrap:anywhere] dark:text-slate-200">
              {result.chunk.text}
            </p>
          </article>
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <DebugField label="Tên" value={debug.name} />
      <DebugField label="Loại" value={debug.source_type} />
      <DebugField label="Nguồn" value={debug.source} />
      <DebugField label="Provider" value={debug.provider} />
      <DebugField label="Document ID" value={debug.document_id} />
      <div className="rounded-md border border-line bg-paper/70 p-3 dark:border-white/14 dark:bg-slate-900/76">
        <p className="mb-2 text-xs font-semibold text-ink/62 dark:text-slate-300">Metadata</p>
        <div className="space-y-2">
          {Object.entries(debug.metadata).map(([key, value]) => (
            <DebugField key={key} label={key} value={formatDebugValue(value)} />
          ))}
        </div>
      </div>
    </div>
  );
}

function DebugField({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 rounded-md border border-line bg-white/70 px-3 py-2 dark:border-white/14 dark:bg-slate-950/42">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-ink/42 dark:text-slate-400">
        {label}
      </p>
      <p className="mt-1 break-words text-xs leading-5 text-ink/70 [overflow-wrap:anywhere] dark:text-slate-200">
        {value || "-"}
      </p>
    </div>
  );
}

function EmptyDebugState({ text }: { text: string }) {
  return (
    <div className="rounded-md border border-dashed border-line bg-paper/70 p-4 text-sm text-ink/58 dark:border-white/14 dark:bg-slate-900/76 dark:text-slate-200">
      {text}
    </div>
  );
}

function formatDebugValue(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return JSON.stringify(value);
}

function CitationPanel({
  answer,
  onSelectCitation,
  selectedCitationChunkId,
  sourceChunks,
}: {
  answer: AnswerResponse | null;
  onSelectCitation: (chunkId: string) => void;
  selectedCitationChunkId: string | null;
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
              <button
                className={cn(
                  "min-w-0 overflow-hidden rounded-md border p-3 text-left transition",
                  selectedCitationChunkId === citation.chunk_id
                    ? "border-mint bg-mint/10 shadow-lift dark:border-emerald-300/34 dark:bg-emerald-300/12"
                    : "border-line bg-paper/70 hover:border-mint/28 hover:bg-white dark:border-white/14 dark:bg-slate-900/76 dark:hover:bg-slate-800",
                )}
                key={`${citation.chunk_id}-${markerNumber}`}
                onClick={() => onSelectCitation(citation.chunk_id)}
                type="button"
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
              </button>
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
                highlighted={selectedCitationChunkId === result.chunk.chunk_id}
                key={result.chunk.chunk_id}
                markerNumber={markerNumber}
                onSelect={() => onSelectCitation(result.chunk.chunk_id)}
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
  highlighted,
  markerNumber,
  onSelect,
  result,
}: {
  expanded: boolean;
  highlighted: boolean;
  markerNumber: number;
  onSelect: () => void;
  result: SourceChunk;
}) {
  const sourceUrl = evidenceSourceUrl(result);
  const paragraphs = evidenceParagraphs(result);
  const visibleParagraphs = expanded ? paragraphs : paragraphs.slice(0, 2);

  return (
    <article
      className={cn(
        "min-w-0 overflow-hidden rounded-md border p-3 transition",
        highlighted
          ? "border-mint bg-mint/10 shadow-lift dark:border-emerald-300/34 dark:bg-emerald-300/12"
          : "border-transparent bg-paper/70 dark:bg-slate-900/76",
      )}
    >
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
      <button
        className="mb-3 inline-flex rounded-full border border-mint/20 bg-white/70 px-2 py-1 text-[11px] font-medium text-mint transition hover:bg-white dark:border-emerald-300/24 dark:bg-slate-950/50 dark:text-emerald-200"
        onClick={onSelect}
        type="button"
      >
        Đang xem citation [{markerNumber}]
      </button>

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
    const message = await response.text();
    throw new HttpRequestError(message || "URL import failed", response.status);
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

async function fetchSources(includeChunks = false): Promise<SourceListResponse> {
  const response = await fetch(`${API_URL}/sources?include_chunks=${includeChunks ? "true" : "false"}`);
  if (!response.ok) {
    throw new Error(`Khong lay duoc danh sach tai lieu: ${response.status}`);
  }
  return (await response.json()) as SourceListResponse;
}

async function fetchHealth(): Promise<HealthResponse> {
  const response = await fetch(`${API_URL}/health`);
  if (!response.ok) {
    throw new Error(`Khong lay duoc trang thai he thong: ${response.status}`);
  }
  return (await response.json()) as HealthResponse;
}

function uploadedSourceFromListItem(
  source: SourceListItem,
  index: number,
): UploadedSource {
  return {
    datasetId: source.dataset_id,
    documentId: source.document_id,
    name: source.name,
    provider: source.provider,
    mode: sourceModeFromSourceType(source.source_type),
    source: source.source,
    sourceType: source.source_type,
    metadata: source.metadata,
    totalChunks: source.total_chunks || source.chunks.length,
    chunks: source.chunks,
    uploadedAt: Date.now() - index,
  };
}

function mergeSourcesWithCachedChunks(
  sources: UploadedSource[],
  cachedSources: UploadedSource[],
): UploadedSource[] {
  const cacheById = new Map(cachedSources.map((source) => [source.documentId, source]));
  return sources.map((source) => {
    const cached = cacheById.get(source.documentId);
    if (!cached?.chunks.length || source.chunks.length) {
      return source;
    }
    return {
      ...source,
      chunks: cached.chunks,
    };
  });
}

function readCachedSources(): UploadedSource[] {
  if (typeof window === "undefined") return [];

  try {
    const raw = window.localStorage.getItem(SOURCE_CACHE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as UploadedSource[];
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter((source) => source?.documentId && source?.name)
      .map((source, index) => ({
        datasetId: source.datasetId || "local_pdf",
        documentId: source.documentId,
        name: source.name,
        provider: source.provider || "local_pdf",
        mode: source.mode || sourceModeFromSourceType(source.sourceType || ""),
        source: source.source,
        sourceType: source.sourceType,
        metadata:
          source.metadata && typeof source.metadata === "object" && !Array.isArray(source.metadata)
            ? source.metadata
            : {},
        totalChunks: Number(source.totalChunks) || source.chunks?.length || 0,
        chunks: Array.isArray(source.chunks) ? source.chunks : [],
        uploadedAt: Number(source.uploadedAt) || Date.now() - index,
      }));
  } catch {
    return [];
  }
}

function writeCachedSources(sources: UploadedSource[]) {
  if (typeof window === "undefined") return;

  if (!sources.length) {
    window.localStorage.removeItem(SOURCE_CACHE_KEY);
    return;
  }

  const cachePayload = sources.map((source) => ({
    ...source,
    chunks: [],
  }));
  window.localStorage.setItem(SOURCE_CACHE_KEY, JSON.stringify(cachePayload));
}

function readCachedSourceMode(): SourceMode {
  if (typeof window === "undefined") return "pdf";

  const stored = window.localStorage.getItem(SOURCE_MODE_KEY);
  if (stored === "pdf" || stored === "url" || stored === "text") {
    return stored;
  }
  return "pdf";
}

function readCachedChatState(): ChatPageCache | null {
  if (typeof window === "undefined") return null;

  try {
    const raw = window.localStorage.getItem(CHAT_STATE_CACHE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as ChatPageCache;
    if (!Array.isArray(parsed.messages) || !isSourceMode(parsed.sourceMode)) {
      return null;
    }
    return {
      answer: parsed.answer ?? null,
      messages: parsed.messages.length ? parsed.messages : [createWelcomeMessage()],
      selectedCitationChunkId: parsed.selectedCitationChunkId ?? null,
      selectedDocumentIds: Array.isArray(parsed.selectedDocumentIds)
        ? parsed.selectedDocumentIds.filter((id) => typeof id === "string")
        : [],
      sourceMode: parsed.sourceMode,
    };
  } catch {
    return null;
  }
}

function writeCachedChatState(state: ChatPageCache) {
  if (typeof window === "undefined") return;

  window.localStorage.setItem(SOURCE_MODE_KEY, state.sourceMode);
  window.localStorage.setItem(
    CHAT_STATE_CACHE_KEY,
    JSON.stringify({
      ...state,
      messages: state.messages.map((message) => ({
        ...message,
        status: message.status === "thinking" ? "not_found" : message.status,
      })),
    }),
  );
}

function isSourceMode(value: unknown): value is SourceMode {
  return value === "pdf" || value === "url" || value === "text";
}

function sourceModeFromSourceType(sourceType: string): SourceMode {
  if (sourceType === "url") return "url";
  if (sourceType === "text") return "text";
  return "pdf";
}

function displayQueuedSourceName(source: QueuedSource): string {
  if (source.mode === "url") {
    return displayUrlName(source.name);
  }
  return source.name;
}

function displaySourceName(source: UploadedSource): string {
  if (source.mode === "url") {
    return displayUrlName(source.source || source.name);
  }
  return source.name;
}

function sourceMatchesSearch(source: UploadedSource, normalizedQuery: string): boolean {
  if (!normalizedQuery) return true;

  const haystack = normalizeSearchText(sourceSearchText(source));
  const compactHaystack = compactSearchText(haystack);
  const compactQuery = compactSearchText(normalizedQuery);
  if (haystack.includes(normalizedQuery) || compactHaystack.includes(compactQuery)) {
    return true;
  }

  return searchTokens(normalizedQuery).every((token) => {
    const compactToken = compactSearchText(token);
    return haystack.includes(token) || compactHaystack.includes(compactToken);
  });
}

function normalizeSearchText(text: string): string {
  return text
    .trim()
    .toLowerCase()
    .replace(/đ/g, "d")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "");
}

function sourceSearchText(source: UploadedSource): string {
  return [
    displaySourceName(source),
    source.name,
    source.source,
    source.sourceType,
    source.mode,
    source.provider,
    source.datasetId,
    source.documentId,
    ...metadataSearchValues(source.metadata),
    ...source.chunks.slice(0, 8).flatMap((result) => [
      result.chunk.chunk_id,
      metadataSearchValues(result.chunk.metadata).join(" "),
    ]),
  ]
    .filter(Boolean)
    .join(" ");
}

function metadataSearchValues(metadata?: Record<string, unknown>): string[] {
  if (!metadata) return [];

  const preferredKeys = [
    "title",
    "document_name",
    "file_name",
    "source",
    "url",
    "original_url",
    "final_url",
    "canonical_url",
    "section",
    "source_type",
    "language",
  ];
  return preferredKeys
    .map((key) => unknownToSearchText(metadata[key]))
    .filter((value): value is string => Boolean(value));
}

function unknownToSearchText(value: unknown): string | null {
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) {
    return value.map(unknownToSearchText).filter(Boolean).join(" ");
  }
  return null;
}

function searchTokens(normalizedQuery: string): string[] {
  return normalizedQuery.split(/\s+/).filter(Boolean);
}

function compactSearchText(text: string): string {
  return text.replace(/[^a-z0-9]+/g, "");
}

function displayUrlName(value: string): string {
  try {
    const parsed = new URL(value);
    return `${parsed.hostname}${parsed.pathname}`.replace(/\/$/, "") || parsed.hostname;
  } catch {
    return value
      .replace(/^https?:\/\//, "")
      .replace(/\.html\.txt$/, "")
      .replace(/\.txt$/, "");
  }
}

function normalizeSourceUrl(value: string): string {
  try {
    const parsed = new URL(value.trim());
    parsed.hash = "";
    parsed.searchParams.sort();
    return parsed.toString().replace(/\/$/, "");
  } catch {
    return value.trim().replace(/\/$/, "");
  }
}

async function waitForSourceChunks(
  documentId: string,
  attempts = 20,
  delayMs = 3000,
): Promise<SourceChunksResponse> {
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    try {
      const payload = await fetchSourceChunks(documentId);
      if (payload.chunks.length > 0) {
        return payload;
      }
    } catch {
      // The source may still be parsing; keep polling until the caller's timeout.
    }
    await delay(delayMs);
  }

  throw new Error("Tài liệu đã được nhận nhưng chưa tạo chunk. Chờ thêm rồi thử lại.");
}

async function fetchSourceChunks(documentId: string): Promise<SourceChunksResponse> {
  const response = await fetch(`${API_URL}/sources/${documentId}/chunks`);
  if (!response.ok) {
    throw new Error(`Khong lay duoc chunk source: ${response.status}`);
  }
  return (await response.json()) as SourceChunksResponse;
}

async function fetchSourceDebug(documentId: string): Promise<SourceDebugResponse> {
  const response = await fetch(`${API_URL}/sources/${documentId}/debug`);
  if (!response.ok) {
    throw new Error(`Không lấy được debug source: ${response.status}`);
  }
  return (await response.json()) as SourceDebugResponse;
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function sourceStatusText(status: SourceProcessingStatus, chunkCount: number): string {
  if (status === "uploading") return "Đang tải tài liệu";
  if (status === "processing") return "Đang tách đoạn tài liệu";
  if (status === "ready") return `Sẵn sàng hỏi đáp (${chunkCount} chunk)`;
  if (status === "error") return "Chưa nạp được tài liệu";
  return "Tệp sẽ được nạp vào phiên chat";
}

function sourceErrorMessage(error: unknown): string {
  return error instanceof Error
    ? error.message
    : "Không nạp được tài liệu. Kiểm tra cấu hình API.";
}

function isHttpStatus(error: unknown, status: number): boolean {
  if (error instanceof HttpRequestError) {
    return error.status === status;
  }
  if (error instanceof Error) {
    return new RegExp(`(^|[^0-9])${status}([^0-9]|$)`).test(error.message);
  }
  return false;
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
