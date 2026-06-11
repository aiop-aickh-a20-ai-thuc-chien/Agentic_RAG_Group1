"use client";

import { useEffect, useState } from "react";
import {
  AlertCircle, CheckCircle2, ChevronDown, ChevronRight, FileText,
  Globe, Layers, Loader2, Pencil, RefreshCw, RotateCcw, Sparkles, Zap,
} from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { Skeleton } from "../_components/fx";

const API = process.env.NEXT_PUBLIC_AGENTIC_RAG_API_URL ?? "http://localhost:8000";
const PROMPT_STORAGE_KEY = "autodata_custom_prompt";

// Backend giới hạn 1-10 câu/section; xóa trống input → Number('') = NaN nên phải kẹp lại
function clampQps(raw: string): number {
  const v = Math.round(Number(raw));
  if (!Number.isFinite(v)) return 1;
  return Math.min(10, Math.max(1, v));
}

type Source   = { document_id: string; name: string; source_type: string; total_chunks: number };
type Section  = { section: string; chunk_count: number; question_count: number };
type JobProgress = { total: number; done: number; created: number };
// Map global (bảng lớn): tổng câu + đã duyệt; chờ review = total - approved.
// Trang này KHÔNG dính dataset — sinh câu là bước toàn cục, gán dataset là bước sau.
type DocCount = { total: number; approved: number };

export default function AutodataPage() {
  const [sources,          setSources]          = useState<Source[]>([]);
  const [docCounts,        setDocCounts]        = useState<Record<string, DocCount>>({});

  const [selectedDoc,      setSelectedDoc]      = useState<string | null>(null);
  const [sections,         setSections]         = useState<Section[]>([]);
  const [selectedSections, setSelectedSections] = useState<Set<string>>(new Set());
  const [qps,              setQps]              = useState(3);
  const [loadingSections,  setLoadingSections]  = useState(false);

  const [jobId,       setJobId]       = useState<string | null>(null);
  const [jobStatus,   setJobStatus]   = useState<"idle" | "running" | "done" | "failed">("idle");
  const [jobProgress, setJobProgress] = useState<JobProgress | null>(null);

  // Bulk mode
  const [bulkMode, setBulkMode] = useState(false);
  const [bulkDocs, setBulkDocs] = useState<Set<string>>(new Set());
  const [onlyMissing, setOnlyMissing] = useState(true);

  // Prompt tùy chỉnh
  const [promptTemplate, setPromptTemplate] = useState("");
  const [customPrompt,   setCustomPrompt]   = useState("");

  const refreshCounts = () => {
    fetch(`${API}/internal/doc-question-counts`)
      .then((r) => r.json())
      .then((d) => setDocCounts(d && typeof d === "object" && !Array.isArray(d) ? d : {}))
      .catch(() => {});
  };

  // Load sources + counts + prompt mặc định
  useEffect(() => {
    fetch(`${API}/sources?include_chunks=false`)
      .then((r) => r.json())
      .then((d) => setSources(d.sources ?? []))
      .catch(() => {});

    refreshCounts();

    fetch(`${API}/internal/autodata/prompt-template`)
      .then((r) => r.json())
      .then((d) => {
        const tpl = d.template ?? "";
        setPromptTemplate(tpl);
        const saved = typeof window !== "undefined" ? localStorage.getItem(PROMPT_STORAGE_KEY) : null;
        setCustomPrompt(saved ?? tpl);
      })
      .catch(() => {});
  }, []);

  // Load sections when doc selected (single mode)
  useEffect(() => {
    if (!selectedDoc) return;
    setLoadingSections(true);
    setSections([]);
    setSelectedSections(new Set());
    fetch(`${API}/internal/autodata/sections?document_id=${selectedDoc}`)
      .then((r) => r.json())
      .then((d) => { setSections(Array.isArray(d) ? d : []); setLoadingSections(false); })
      .catch(() => { setSections([]); setLoadingSections(false); });
  }, [selectedDoc]);

  // Poll job
  useEffect(() => {
    if (!jobId || jobStatus !== "running") return;
    let consecutiveErrors = 0;
    const id = setInterval(async () => {
      try {
        const r = await fetch(`${API}/internal/autodata/jobs/${jobId}`);
        const d = await r.json();
        consecutiveErrors = 0;
        setJobProgress({ total: d.total_sections ?? 0, done: d.done_sections ?? 0, created: d.questions_created ?? 0 });
        if (d.status === "done" || d.status === "failed") {
          setJobStatus(d.status);
          clearInterval(id);
          refreshCounts();
          if (d.status === "done") {
            toast.success(`Sinh xong: +${d.questions_created ?? 0} câu hỏi từ ${d.done_sections ?? 0} sections`, {
              description: "Qua trang Review để duyệt câu mới.",
            });
          } else {
            toast.error("Job sinh câu thất bại", { description: "Xem log backend để biết lý do." });
          }
          // reload sections của doc đang xem để badge cập nhật
          if (selectedDoc && !bulkMode) {
            fetch(`${API}/internal/autodata/sections?document_id=${selectedDoc}`)
              .then((r) => r.json())
              .then((d) => setSections(Array.isArray(d) ? d : []))
              .catch(() => {});
          }
        }
      } catch {
        // Lỗi mạng thoáng qua không được giết polling — chỉ dừng khi lỗi liên tục
        consecutiveErrors += 1;
        if (consecutiveErrors >= 5) {
          clearInterval(id);
          setJobStatus("failed");
        }
      }
    }, 2000);
    return () => clearInterval(id);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId, jobStatus, selectedDoc, bulkMode]);

  // Prompt gửi đi: chỉ gửi khi user thật sự chỉnh khác mặc định
  const promptToSend = customPrompt.trim() && customPrompt !== promptTemplate ? customPrompt : null;

  const updatePrompt = (v: string) => {
    setCustomPrompt(v);
    if (v === promptTemplate) localStorage.removeItem(PROMPT_STORAGE_KEY);
    else localStorage.setItem(PROMPT_STORAGE_KEY, v);
  };

  const resetPrompt = () => {
    setCustomPrompt(promptTemplate);
    localStorage.removeItem(PROMPT_STORAGE_KEY);
  };

  const handleGenerate = async () => {
    if (!selectedDoc) return;
    setJobStatus("running");
    setJobProgress(null);
    try {
      const r = await fetch(`${API}/internal/autodata/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          document_id: selectedDoc,
          section_filters: selectedSections.size ? [...selectedSections] : null,
          questions_per_section: qps,
          custom_prompt: promptToSend,
        }),
      });
      const d = await r.json();
      if (!r.ok || !d.job_id) { setJobStatus("failed"); return; }
      setJobId(d.job_id);
    } catch { setJobStatus("failed"); }
  };

  const handleGenerateBulk = async () => {
    if (bulkDocs.size === 0) return;
    setJobStatus("running");
    setJobProgress(null);
    try {
      const r = await fetch(`${API}/internal/autodata/generate-bulk`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          document_ids: [...bulkDocs],
          questions_per_section: qps,
          only_missing: onlyMissing,
          custom_prompt: promptToSend,
        }),
      });
      const d = await r.json();
      if (!r.ok || !d.job_id) { setJobStatus("failed"); return; }
      setJobId(d.job_id);
    } catch { setJobStatus("failed"); }
  };

  const toggleSection = (s: string) =>
    setSelectedSections((prev) => { const n = new Set(prev); n.has(s) ? n.delete(s) : n.add(s); return n; });

  const toggleAll = () =>
    setSelectedSections(selectedSections.size === sections.length ? new Set() : new Set(sections.map((s) => s.section)));

  const selectUngenerated = () =>
    setSelectedSections(new Set(sections.filter((s) => s.question_count === 0).map((s) => s.section)));

  const toggleBulkDoc = (id: string) =>
    setBulkDocs((prev) => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n; });

  // Tích/bỏ tích cả 1 nhóm doc trong bulk mode
  const toggleBulkGroup = (docs: Source[]) =>
    setBulkDocs((prev) => {
      const ids = docs.map((d) => d.document_id);
      const allIn = ids.every((id) => prev.has(id));
      const n = new Set(prev);
      ids.forEach((id) => { if (allIn) n.delete(id); else n.add(id); });
      return n;
    });

  const generated    = sources.filter((s) => (docCounts[s.document_id]?.total ?? 0) > 0);
  const notGenerated = sources.filter((s) => (docCounts[s.document_id]?.total ?? 0) === 0);

  // Tổng thật toàn hệ thống (mọi doc) — hiển thị ở dòng chú thích đầu trang
  const globalTotals = Object.values(docCounts).reduce(
    (acc, c) => ({ total: acc.total + c.total, approved: acc.approved + c.approved }),
    { total: 0, approved: 0 },
  );
  const selectedDocInfo = sources.find((s) => s.document_id === selectedDoc);
  const selectedCount = selectedDoc ? docCounts[selectedDoc] : undefined;
  const alreadyGenerated = (selectedCount?.total ?? 0) > 0;

  // 1 click: vào bulk mode + tích sẵn toàn bộ doc chưa sinh (tài liệu mới upload nằm hết ở đây)
  const quickSelectNew = () => {
    setBulkMode(true);
    setBulkDocs(new Set(notGenerated.map((d) => d.document_id)));
    setOnlyMissing(true);
    setJobStatus("idle");
  };

  // Sort: chưa-sinh lên đầu, rồi theo tên
  const sortedSections = [...sections].sort((a, b) => {
    if ((a.question_count === 0) !== (b.question_count === 0)) return a.question_count === 0 ? -1 : 1;
    return a.section.localeCompare(b.section);
  });
  const ungeneratedCount = sections.filter((s) => s.question_count === 0).length;

  const renderDocRow = (s: Source) => {
    const checked = bulkDocs.has(s.document_id);
    const c = docCounts[s.document_id];
    const pending = c ? c.total - c.approved : 0;
    const icon = s.source_type === "pdf"
      ? <FileText size={14} className="text-emerald-600 shrink-0" />
      : <Globe size={14} className="text-blue-500 shrink-0" />;

    // Badge map với Review (bảng lớn): tổng câu · ✓đã duyệt · chờ review
    const badges = c && c.total > 0 && (
      <span className="flex items-center gap-1 shrink-0">
        <span className="text-xs text-emerald-700 bg-emerald-100 px-1.5 py-0.5 rounded-full tabular-nums" title="Tổng câu đã sinh">
          {c.total}
        </span>
        {c.approved > 0 && (
          <span className="text-xs text-blue-700 bg-blue-50 border border-blue-200 px-1.5 py-0.5 rounded-full tabular-nums" title="Đã duyệt">
            ✓{c.approved}
          </span>
        )}
        {pending > 0 && (
          <span className="text-xs text-amber-700 bg-amber-50 border border-amber-200 px-1.5 py-0.5 rounded-full tabular-nums" title="Chờ review">
            {pending} chờ
          </span>
        )}
      </span>
    );

    if (bulkMode) {
      return (
        <label
          key={s.document_id}
          className={cn(
            "w-full flex items-center gap-2.5 px-4 py-2.5 text-left cursor-pointer transition-colors hover:bg-gray-50 border-b border-black/5 last:border-0",
            checked && "bg-emerald-50 hover:bg-emerald-50"
          )}
        >
          <input type="checkbox" checked={checked} onChange={() => toggleBulkDoc(s.document_id)} className="accent-emerald-600" />
          {icon}
          <span className="text-sm text-gray-700 truncate flex-1">{s.name || s.document_id}</span>
          {badges}
        </label>
      );
    }
    return (
      <button
        key={s.document_id}
        onClick={() => { setSelectedDoc(s.document_id); setJobStatus("idle"); }}
        className={cn(
          "w-full flex items-center gap-2.5 px-4 py-2.5 text-left hover:bg-gray-50 border-b border-black/5 last:border-0 row-hover",
          selectedDoc === s.document_id && "bg-emerald-50 hover:bg-emerald-50"
        )}
      >
        {icon}
        <span className="text-sm text-gray-700 truncate flex-1">{s.name || s.document_id}</span>
        {badges}
        {!c?.total && selectedDoc === s.document_id && <ChevronRight size={13} className="text-emerald-600 shrink-0" />}
      </button>
    );
  };

  const renderDocGroup = (title: string, docs: Source[], accent: "gray" | "emerald") => {
    const allChecked = docs.length > 0 && docs.every((d) => bulkDocs.has(d.document_id));
    return (
      <div className="bg-white rounded-xl border border-black/8 overflow-hidden">
        <div className={cn(
          "px-4 py-2.5 border-b border-black/6 flex items-center justify-between gap-2",
          accent === "emerald" ? "bg-emerald-50/60" : "bg-gray-50/60"
        )}>
          <p className={cn(
            "text-xs font-semibold uppercase tracking-wider",
            accent === "emerald" ? "text-emerald-700" : "text-gray-500"
          )}>
            {title}
          </p>
          <div className="flex items-center gap-2">
            {bulkMode && docs.length > 0 && (
              <button onClick={() => toggleBulkGroup(docs)} className="text-xs text-emerald-700 hover:underline">
                {allChecked ? "Bỏ chọn hết" : "Chọn hết"}
              </button>
            )}
            <span className={cn("text-xs tabular-nums", accent === "emerald" ? "text-emerald-600" : "text-gray-400")}>
              {docs.length}
            </span>
          </div>
        </div>
        <div className="overflow-y-auto max-h-60">
          {docs.length === 0 && (
            <p className="text-xs text-gray-400 p-4 text-center">
              {accent === "emerald" ? "Chưa có tài liệu nào" : "Tất cả đã được sinh"}
            </p>
          )}
          {docs.map(renderDocRow)}
        </div>
      </div>
    );
  };

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">Tạo câu hỏi</h1>
          <p className="text-sm text-gray-500 mt-1">Chọn tài liệu và section để AutoData sinh Q&amp;A</p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          {notGenerated.length > 0 && (
            <button
              onClick={quickSelectNew}
              className="flex items-center gap-1.5 text-sm px-3 py-1.5 rounded-lg bg-emerald-700 text-white hover:bg-emerald-800 hover:shadow-lg hover:shadow-emerald-700/25 transition-all pressable"
              title="Vào chế độ bulk và tích sẵn toàn bộ tài liệu chưa sinh câu hỏi"
            >
              <Zap size={14} /> Sinh cho {notGenerated.length} doc mới
            </button>
          )}
          <button
            onClick={() => { setBulkMode((v) => !v); setJobStatus("idle"); setBulkDocs(new Set()); }}
            className={cn(
              "flex items-center gap-1.5 text-sm px-3 py-1.5 rounded-lg border transition-colors",
              bulkMode ? "bg-emerald-700 border-emerald-700 text-white" : "border-black/12 text-gray-600 hover:bg-gray-50"
            )}
          >
            <Layers size={14} /> {bulkMode ? "Đang bulk" : "Bulk nhiều tài liệu"}
          </button>
        </div>
      </div>

      {/* Thống kê thật toàn hệ thống — đồng thời là chú thích ý nghĩa badge */}
      <div className="flex items-center gap-2 text-xs text-gray-400 flex-wrap">
        <span>Toàn hệ thống (map với trang Review):</span>
        <span className="text-emerald-700 bg-emerald-100 px-1.5 py-0.5 rounded-full tabular-nums">{globalTotals.total}</span>
        <span>tổng câu</span>
        <span className="text-gray-300">·</span>
        <span className="text-blue-700 bg-blue-50 border border-blue-200 px-1.5 py-0.5 rounded-full tabular-nums">✓{globalTotals.approved}</span>
        <span>đã duyệt</span>
        <span className="text-gray-300">·</span>
        <span className="text-amber-700 bg-amber-50 border border-amber-200 px-1.5 py-0.5 rounded-full tabular-nums">{globalTotals.total - globalTotals.approved} chờ</span>
        <span>chờ review</span>
      </div>

      <div className="grid grid-cols-[300px_1fr] gap-5">
        {/* Left — Document list */}
        <div className="space-y-3">
          {renderDocGroup("Chưa sinh câu hỏi", notGenerated, "gray")}
          {renderDocGroup("Đã sinh câu hỏi", generated, "emerald")}
        </div>

        {/* Right — Bulk panel OR Sections + config */}
        <div className="space-y-4">
          {bulkMode ? (
            <>
              <BulkPanel
                count={bulkDocs.size}
                qps={qps} setQps={setQps}
                onlyMissing={onlyMissing} setOnlyMissing={setOnlyMissing}
                jobStatus={jobStatus} jobProgress={jobProgress}
                onGenerate={handleGenerateBulk}
              />
              <PromptEditor
                value={customPrompt}
                isCustom={!!promptToSend}
                onChange={updatePrompt}
                onReset={resetPrompt}
              />
            </>
          ) : !selectedDoc ? (
            <div className="bg-white rounded-xl border border-black/8 h-48 flex items-center justify-center text-gray-400 text-sm">
              ← Chọn tài liệu để bắt đầu, hoặc bấm &quot;Sinh cho doc mới&quot; để làm hàng loạt
            </div>
          ) : (
            <>
              {/* Doc info */}
              <div className="bg-white rounded-xl border border-black/8 px-5 py-3 flex items-center gap-3">
                {selectedDocInfo?.source_type === "pdf"
                  ? <FileText size={16} className="text-emerald-600 shrink-0" />
                  : <Globe size={16} className="text-blue-500 shrink-0" />}
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-gray-800 truncate">{selectedDocInfo?.name || selectedDoc}</p>
                  <p className="text-xs text-gray-400 mt-0.5">{selectedDocInfo?.total_chunks ?? 0} chunks</p>
                </div>
                {alreadyGenerated && selectedCount && (
                  <span className="flex items-center gap-1.5 text-xs text-emerald-700 bg-emerald-50 border border-emerald-200 px-2.5 py-1 rounded-full shrink-0">
                    <CheckCircle2 size={12} />
                    {selectedCount.total} câu · ✓{selectedCount.approved} duyệt · {selectedCount.total - selectedCount.approved} chờ
                  </span>
                )}
              </div>

              {/* Warning if already generated */}
              {alreadyGenerated && (
                <div className="flex items-start gap-2.5 bg-amber-50 border border-amber-200 rounded-xl px-4 py-3 text-sm text-amber-800">
                  <AlertCircle size={15} className="shrink-0 mt-0.5 text-amber-600" />
                  <span>Tài liệu này đã có {selectedCount?.total} câu hỏi. Sinh thêm sẽ thêm vào dataset, không ghi đè.</span>
                </div>
              )}

              {/* Sections */}
              <div className="bg-white rounded-xl border border-black/8 overflow-hidden">
                <div className="px-5 py-3 border-b border-black/6 bg-gray-50/60 flex items-center justify-between gap-2">
                  <p className="text-xs font-semibold uppercase tracking-wider text-gray-500">
                    Sections {ungeneratedCount > 0 && <span className="text-amber-600 normal-case font-normal">· {ungeneratedCount} chưa sinh</span>}
                  </p>
                  {sections.length > 0 && (
                    <div className="flex items-center gap-3">
                      {ungeneratedCount > 0 && (
                        <button onClick={selectUngenerated} className="text-xs text-amber-700 hover:underline">
                          Chọn chưa sinh ({ungeneratedCount})
                        </button>
                      )}
                      <button onClick={toggleAll} className="text-xs text-emerald-700 hover:underline">
                        {selectedSections.size === sections.length ? "Bỏ chọn tất cả" : "Chọn tất cả"}
                      </button>
                    </div>
                  )}
                </div>
                <div className="max-h-64 overflow-y-auto">
                  {loadingSections && (
                    <div className="p-5 space-y-3">
                      {Array.from({ length: 5 }, (_, i) => (
                        <div key={i} className="flex items-center gap-3">
                          <Skeleton className="h-4 w-4 rounded" />
                          <Skeleton className={cn("h-4", i % 2 ? "w-3/5" : "w-2/5")} />
                          <Skeleton className="h-4 w-16 ml-auto rounded-full" />
                          <Skeleton className="h-4 w-20 rounded-full" />
                        </div>
                      ))}
                    </div>
                  )}
                  {!loadingSections && sections.length === 0 && (
                    <p className="text-sm text-gray-400 p-5 text-center">Không tìm thấy section nào</p>
                  )}
                  {!loadingSections && sortedSections.map((s) => (
                    <label
                      key={s.section}
                      className={cn(
                        "flex items-center gap-3 px-5 py-2.5 cursor-pointer border-b border-black/5 last:border-0 hover:bg-gray-50 transition-colors",
                        selectedSections.has(s.section) && "bg-emerald-50"
                      )}
                    >
                      <input
                        type="checkbox"
                        checked={selectedSections.has(s.section)}
                        onChange={() => toggleSection(s.section)}
                        className="accent-emerald-600"
                      />
                      <span className="text-sm text-gray-700 flex-1 line-clamp-1">{s.section}</span>
                      {s.question_count > 0 ? (
                        <span className="flex items-center gap-1 text-xs text-emerald-700 bg-emerald-100 px-2 py-0.5 rounded-full shrink-0">
                          <CheckCircle2 size={11} /> {s.question_count} câu
                        </span>
                      ) : (
                        <span className="text-xs text-amber-700 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded-full shrink-0">
                          chưa sinh
                        </span>
                      )}
                      <span className="text-xs text-gray-400 bg-gray-100 px-2 py-0.5 rounded-full shrink-0">
                        {s.chunk_count} chunks
                      </span>
                    </label>
                  ))}
                </div>
              </div>

              {/* Prompt tùy chỉnh */}
              <PromptEditor
                value={customPrompt}
                isCustom={!!promptToSend}
                onChange={updatePrompt}
                onReset={resetPrompt}
              />

              {/* Config + Generate */}
              <div className="bg-white rounded-xl border border-black/8 px-5 py-4 flex items-center gap-6 flex-wrap">
                <div className="flex items-center gap-2.5">
                  <label className="text-sm text-gray-600 whitespace-nowrap">Số câu/section:</label>
                  <input
                    type="number" min={1} max={10} value={qps}
                    onChange={(e) => setQps(clampQps(e.target.value))}
                    className="w-16 text-sm border border-black/12 rounded-lg px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-emerald-500/40"
                  />
                </div>
                {selectedSections.size > 0 && (
                  <p className="text-sm text-gray-500">
                    Sẽ sinh <span className="font-semibold text-gray-800">{selectedSections.size * qps}</span> câu
                    từ <span className="font-semibold text-gray-800">{selectedSections.size}</span> sections
                  </p>
                )}
                <div className="ml-auto flex items-center gap-3">
                  {jobStatus === "done" && (
                    <span className="flex items-center gap-1.5 text-sm text-emerald-700 font-medium">
                      <CheckCircle2 size={15} /> Hoàn thành!{jobProgress ? ` (+${jobProgress.created} câu)` : ""}
                    </span>
                  )}
                  {jobStatus === "failed" && (
                    <span className="text-sm text-red-600">Thất bại. Thử lại.</span>
                  )}
                  <button
                    onClick={handleGenerate}
                    disabled={jobStatus === "running" || sections.length === 0}
                    className={cn(
                      "flex items-center gap-2 px-5 py-2 rounded-lg text-sm font-medium transition-all pressable",
                      alreadyGenerated
                        ? "bg-amber-600 hover:bg-amber-700 hover:shadow-lg hover:shadow-amber-600/25 text-white disabled:opacity-40"
                        : "bg-emerald-700 hover:bg-emerald-800 hover:shadow-lg hover:shadow-emerald-700/25 text-white disabled:opacity-40",
                      "disabled:cursor-not-allowed"
                    )}
                  >
                    {jobStatus === "running"
                      ? <><Loader2 size={14} className="animate-spin" /> Đang tạo...</>
                      : alreadyGenerated
                        ? <><RefreshCw size={14} /> Sinh thêm</>
                        : <><Sparkles size={14} /> Tạo câu hỏi</>
                    }
                  </button>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function PromptEditor({
  value, isCustom, onChange, onReset,
}: {
  value: string;
  isCustom: boolean;
  onChange: (v: string) => void;
  onReset: () => void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="bg-white rounded-xl border border-black/8 overflow-hidden">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full px-5 py-3 flex items-center gap-2.5 text-left hover:bg-gray-50/60 transition-colors"
      >
        <Pencil size={14} className="text-gray-400 shrink-0" />
        <span className="text-sm font-medium text-gray-700 flex-1">Tùy chỉnh prompt sinh câu hỏi</span>
        {isCustom && (
          <span className="text-xs text-violet-700 bg-violet-50 border border-violet-200 px-2 py-0.5 rounded-full">
            đã chỉnh
          </span>
        )}
        {open ? <ChevronDown size={14} className="text-gray-400" /> : <ChevronRight size={14} className="text-gray-400" />}
      </button>
      {open && (
        <div className="px-5 pb-4 space-y-3 border-t border-black/6 pt-3">
          <p className="text-xs text-gray-500 leading-relaxed">
            Prompt này được gửi cho LLM để sinh Q&amp;A. Dùng placeholder:{" "}
            <code className="bg-gray-100 px-1 rounded">{"{n}"}</code> số câu,{" "}
            <code className="bg-gray-100 px-1 rounded">{"{section}"}</code> tên section,{" "}
            <code className="bg-gray-100 px-1 rounded">{"{context}"}</code> nội dung văn bản.
            Lưu ý: kết quả phải là JSON array <code className="bg-gray-100 px-1 rounded">{'[{"question": "...", "answer": "..."}]'}</code> để hệ thống đọc được.
          </p>
          <textarea
            value={value}
            onChange={(e) => onChange(e.target.value)}
            rows={10}
            spellCheck={false}
            className="w-full text-xs font-mono border border-black/12 rounded-lg px-3 py-2.5 focus:outline-none focus:ring-2 focus:ring-emerald-500/40 leading-relaxed resize-y"
          />
          <div className="flex items-center justify-between">
            <p className="text-xs text-gray-400">
              {isCustom ? "Đang dùng prompt tùy chỉnh (tự lưu trên trình duyệt)" : "Đang dùng prompt mặc định"}
            </p>
            {isCustom && (
              <button
                onClick={onReset}
                className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-700 px-2 py-1 rounded hover:bg-gray-100 transition-colors"
              >
                <RotateCcw size={12} /> Khôi phục mặc định
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function BulkPanel({
  count, qps, setQps, onlyMissing, setOnlyMissing, jobStatus, jobProgress, onGenerate,
}: {
  count: number;
  qps: number; setQps: (n: number) => void;
  onlyMissing: boolean; setOnlyMissing: (b: boolean) => void;
  jobStatus: "idle" | "running" | "done" | "failed";
  jobProgress: JobProgress | null;
  onGenerate: () => void;
}) {
  const pct = jobProgress && jobProgress.total > 0
    ? Math.round((jobProgress.done / jobProgress.total) * 100) : 0;
  return (
    <div className="space-y-4">
      <div className="bg-white rounded-xl border border-black/8 px-5 py-4 flex items-start gap-2.5">
        <Layers size={16} className="text-emerald-600 shrink-0 mt-0.5" />
        <div className="text-sm text-gray-600">
          Chế độ bulk: tích chọn nhiều tài liệu ở danh sách bên trái (hoặc &quot;Chọn hết&quot; theo nhóm), rồi sinh câu cho tất cả cùng lúc.
          <p className="text-gray-800 font-medium mt-1">Đã chọn {count} tài liệu</p>
        </div>
      </div>

      <div className="bg-white rounded-xl border border-black/8 px-5 py-4 space-y-4">
        <label className="flex items-center gap-2.5 cursor-pointer">
          <input type="checkbox" checked={onlyMissing} onChange={(e) => setOnlyMissing(e.target.checked)} className="accent-emerald-600" />
          <span className="text-sm text-gray-700">Chỉ sinh cho section <span className="font-medium">chưa có câu</span> (bỏ qua phần đã làm)</span>
        </label>

        <div className="flex items-center gap-2.5">
          <label className="text-sm text-gray-600 whitespace-nowrap">Số câu/section:</label>
          <input
            type="number" min={1} max={10} value={qps}
            onChange={(e) => setQps(clampQps(e.target.value))}
            className="w-16 text-sm border border-black/12 rounded-lg px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-emerald-500/40"
          />
        </div>

        {/* Progress */}
        {jobStatus === "running" && (
          <div>
            <div className="flex justify-between text-xs text-gray-500 mb-1.5">
              <span>
                {jobProgress && jobProgress.total > 0
                  ? `Sinh ${jobProgress.done}/${jobProgress.total} sections · +${jobProgress.created} câu`
                  : "Đang chuẩn bị..."}
              </span>
              <span>{pct}%</span>
            </div>
            <div className="h-2.5 bg-gray-100 rounded-full overflow-hidden shadow-inner">
              <div className="h-full bg-gradient-to-r from-emerald-500 to-emerald-400 rounded-full transition-all duration-500 progress-active" style={{ width: `${pct}%` }} />
            </div>
          </div>
        )}
        {jobStatus === "done" && (
          <div className="flex items-center gap-1.5 text-sm text-emerald-700 font-medium">
            <CheckCircle2 size={15} /> Hoàn thành! Đã sinh {jobProgress?.created ?? 0} câu từ {jobProgress?.done ?? 0} sections.
          </div>
        )}
        {jobStatus === "failed" && <p className="text-sm text-red-600">Thất bại. Thử lại.</p>}

        <button
          onClick={onGenerate}
          disabled={count === 0 || jobStatus === "running"}
          className="w-full flex items-center justify-center gap-2 px-5 py-2.5 rounded-lg text-sm font-medium bg-emerald-700 hover:bg-emerald-800 hover:shadow-lg hover:shadow-emerald-700/25 text-white disabled:opacity-40 disabled:cursor-not-allowed transition-all pressable"
        >
          {jobStatus === "running"
            ? <><Loader2 size={14} className="animate-spin" /> Đang sinh hàng loạt...</>
            : <><Sparkles size={14} /> Sinh câu cho {count} tài liệu</>}
        </button>
      </div>
    </div>
  );
}
