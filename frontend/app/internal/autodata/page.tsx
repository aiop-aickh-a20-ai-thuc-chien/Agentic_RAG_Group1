"use client";

import { useEffect, useState } from "react";
import {
  AlertCircle, CheckCircle2, ChevronRight, FileText,
  Globe, Loader2, RefreshCw, Sparkles,
} from "lucide-react";
import { cn } from "@/lib/utils";

const API = process.env.NEXT_PUBLIC_AGENTIC_RAG_API_URL ?? "http://localhost:8000";

type Source   = { document_id: string; name: string; source_type: string; total_chunks: number };
type Section  = { section: string; chunk_count: number };
type Dataset  = { id: string; name: string; is_benchmark: boolean };

export default function AutodataPage() {
  const [sources,          setSources]          = useState<Source[]>([]);
  const [datasets,         setDatasets]         = useState<Dataset[]>([]);
  const [selectedDataset,  setSelectedDataset]  = useState<string>("");
  const [qCounts,          setQCounts]          = useState<Record<string, number>>({});

  const [selectedDoc,      setSelectedDoc]      = useState<string | null>(null);
  const [sections,         setSections]         = useState<Section[]>([]);
  const [selectedSections, setSelectedSections] = useState<Set<string>>(new Set());
  const [qps,              setQps]              = useState(3);
  const [loadingSections,  setLoadingSections]  = useState(false);

  const [jobId,     setJobId]     = useState<string | null>(null);
  const [jobStatus, setJobStatus] = useState<"idle" | "running" | "done" | "failed">("idle");

  // Load sources + datasets
  useEffect(() => {
    fetch(`${API}/sources?include_chunks=false`)
      .then((r) => r.json())
      .then((d) => setSources(d.sources ?? []))
      .catch(() => {});

    fetch(`${API}/internal/datasets`)
      .then((r) => r.json())
      .then((d: Dataset[]) => {
        setDatasets(d);
        if (d.length) setSelectedDataset(d[0].id);
      })
      .catch(() => {});
  }, []);

  // Load question counts when dataset changes
  useEffect(() => {
    if (!selectedDataset) return;
    fetch(`${API}/internal/datasets/${selectedDataset}/doc-question-counts`)
      .then((r) => r.json())
      .then((d) => setQCounts(typeof d === "object" && !Array.isArray(d) ? d : {}))
      .catch(() => {});
  }, [selectedDataset]);

  // Load sections when doc selected
  useEffect(() => {
    if (!selectedDoc) return;
    setLoadingSections(true);
    setSections([]);
    setSelectedSections(new Set());
    fetch(`${API}/internal/datasets/${selectedDataset || "default"}/sections?document_id=${selectedDoc}`)
      .then((r) => r.json())
      .then((d) => { setSections(Array.isArray(d) ? d : []); setLoadingSections(false); })
      .catch(() => { setSections([]); setLoadingSections(false); });
  }, [selectedDoc, selectedDataset]);

  // Poll job
  useEffect(() => {
    if (!jobId || jobStatus !== "running") return;
    const id = setInterval(async () => {
      try {
        const r = await fetch(`${API}/internal/autodata/jobs/${jobId}`);
        const d = await r.json();
        if (d.status === "done" || d.status === "failed") {
          setJobStatus(d.status);
          clearInterval(id);
          // Refresh counts
          if (selectedDataset) {
            fetch(`${API}/internal/datasets/${selectedDataset}/doc-question-counts`)
              .then((r) => r.json())
              .then((d) => setQCounts(typeof d === "object" && !Array.isArray(d) ? d : {}))
              .catch(() => {});
          }
        }
      } catch { clearInterval(id); }
    }, 2000);
    return () => clearInterval(id);
  }, [jobId, jobStatus, selectedDataset]);

  const handleGenerate = async () => {
    if (!selectedDoc || !selectedDataset) return;
    setJobStatus("running");
    try {
      const r = await fetch(`${API}/internal/autodata/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          document_id: selectedDoc,
          dataset_id: selectedDataset,
          section_filters: selectedSections.size ? [...selectedSections] : null,
          questions_per_section: qps,
        }),
      });
      const d = await r.json();
      setJobId(d.job_id);
    } catch { setJobStatus("failed"); }
  };

  const toggleSection = (s: string) =>
    setSelectedSections((prev) => { const n = new Set(prev); n.has(s) ? n.delete(s) : n.add(s); return n; });

  const toggleAll = () =>
    setSelectedSections(selectedSections.size === sections.length ? new Set() : new Set(sections.map((s) => s.section)));

  // Split docs
  const generated    = sources.filter((s) => (qCounts[s.document_id] ?? 0) > 0);
  const notGenerated = sources.filter((s) => (qCounts[s.document_id] ?? 0) === 0);
  const selectedDocInfo = sources.find((s) => s.document_id === selectedDoc);
  const alreadyGenerated = selectedDoc ? (qCounts[selectedDoc] ?? 0) > 0 : false;

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">Tạo câu hỏi</h1>
          <p className="text-sm text-gray-500 mt-1">Chọn tài liệu và section để AutoData sinh Q&amp;A</p>
        </div>
        <select
          value={selectedDataset}
          onChange={(e) => { setSelectedDataset(e.target.value); setSelectedDoc(null); }}
          className="text-sm border border-black/12 rounded-lg px-3 py-1.5 bg-white focus:outline-none focus:ring-2 focus:ring-emerald-500/40"
        >
          {datasets.map((d) => (
            <option key={d.id} value={d.id}>{d.name}{d.is_benchmark ? " ★" : ""}</option>
          ))}
        </select>
      </div>

      <div className="grid grid-cols-[300px_1fr] gap-5">
        {/* Left — Document list */}
        <div className="space-y-3">
          {/* Chưa sinh */}
          <div className="bg-white rounded-xl border border-black/8 overflow-hidden">
            <div className="px-4 py-2.5 border-b border-black/6 bg-gray-50/60 flex items-center justify-between">
              <p className="text-xs font-semibold uppercase tracking-wider text-gray-500">Chưa sinh câu hỏi</p>
              <span className="text-xs text-gray-400 tabular-nums">{notGenerated.length}</span>
            </div>
            <div className="overflow-y-auto max-h-60">
              {notGenerated.length === 0 && (
                <p className="text-xs text-gray-400 p-4 text-center">Tất cả đã được sinh</p>
              )}
              {notGenerated.map((s) => (
                <button
                  key={s.document_id}
                  onClick={() => { setSelectedDoc(s.document_id); setJobStatus("idle"); }}
                  className={cn(
                    "w-full flex items-center gap-2.5 px-4 py-2.5 text-left transition-colors hover:bg-gray-50 border-b border-black/5 last:border-0",
                    selectedDoc === s.document_id && "bg-emerald-50 hover:bg-emerald-50"
                  )}
                >
                  {s.source_type === "pdf"
                    ? <FileText size={14} className="text-emerald-600 shrink-0" />
                    : <Globe size={14} className="text-blue-500 shrink-0" />}
                  <span className="text-sm text-gray-700 truncate flex-1">{s.name || s.document_id}</span>
                  {selectedDoc === s.document_id && <ChevronRight size={13} className="text-emerald-600 shrink-0" />}
                </button>
              ))}
            </div>
          </div>

          {/* Đã sinh */}
          <div className="bg-white rounded-xl border border-black/8 overflow-hidden">
            <div className="px-4 py-2.5 border-b border-black/6 bg-emerald-50/60 flex items-center justify-between">
              <p className="text-xs font-semibold uppercase tracking-wider text-emerald-700">Đã sinh câu hỏi</p>
              <span className="text-xs text-emerald-600 tabular-nums">{generated.length}</span>
            </div>
            <div className="overflow-y-auto max-h-60">
              {generated.length === 0 && (
                <p className="text-xs text-gray-400 p-4 text-center">Chưa có tài liệu nào</p>
              )}
              {generated.map((s) => (
                <button
                  key={s.document_id}
                  onClick={() => { setSelectedDoc(s.document_id); setJobStatus("idle"); }}
                  className={cn(
                    "w-full flex items-center gap-2.5 px-4 py-2.5 text-left transition-colors hover:bg-gray-50 border-b border-black/5 last:border-0",
                    selectedDoc === s.document_id && "bg-emerald-50 hover:bg-emerald-50"
                  )}
                >
                  {s.source_type === "pdf"
                    ? <FileText size={14} className="text-emerald-600 shrink-0" />
                    : <Globe size={14} className="text-blue-500 shrink-0" />}
                  <span className="text-sm text-gray-700 truncate flex-1">{s.name || s.document_id}</span>
                  <span className="text-xs text-emerald-700 bg-emerald-100 px-1.5 py-0.5 rounded-full tabular-nums shrink-0">
                    {qCounts[s.document_id]}
                  </span>
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Right — Sections + config */}
        <div className="space-y-4">
          {!selectedDoc ? (
            <div className="bg-white rounded-xl border border-black/8 h-48 flex items-center justify-center text-gray-400 text-sm">
              ← Chọn tài liệu để bắt đầu
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
                {alreadyGenerated && (
                  <span className="flex items-center gap-1.5 text-xs text-emerald-700 bg-emerald-50 border border-emerald-200 px-2.5 py-1 rounded-full shrink-0">
                    <CheckCircle2 size={12} /> {qCounts[selectedDoc]} câu đã sinh
                  </span>
                )}
              </div>

              {/* Warning if already generated */}
              {alreadyGenerated && (
                <div className="flex items-start gap-2.5 bg-amber-50 border border-amber-200 rounded-xl px-4 py-3 text-sm text-amber-800">
                  <AlertCircle size={15} className="shrink-0 mt-0.5 text-amber-600" />
                  <span>Tài liệu này đã có {qCounts[selectedDoc]} câu hỏi. Sinh thêm sẽ thêm vào dataset, không ghi đè.</span>
                </div>
              )}

              {/* Sections */}
              <div className="bg-white rounded-xl border border-black/8 overflow-hidden">
                <div className="px-5 py-3 border-b border-black/6 bg-gray-50/60 flex items-center justify-between">
                  <p className="text-xs font-semibold uppercase tracking-wider text-gray-500">Sections</p>
                  {sections.length > 0 && (
                    <button onClick={toggleAll} className="text-xs text-emerald-700 hover:underline">
                      {selectedSections.size === sections.length ? "Bỏ chọn tất cả" : "Chọn tất cả"}
                    </button>
                  )}
                </div>
                <div className="max-h-64 overflow-y-auto">
                  {loadingSections && (
                    <div className="flex items-center justify-center p-8 gap-2 text-gray-400">
                      <Loader2 size={15} className="animate-spin" />
                      <span className="text-sm">Đang tải sections...</span>
                    </div>
                  )}
                  {!loadingSections && sections.length === 0 && (
                    <p className="text-sm text-gray-400 p-5 text-center">Không tìm thấy section nào</p>
                  )}
                  {!loadingSections && sections.map((s) => (
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
                      <span className="text-xs text-gray-400 bg-gray-100 px-2 py-0.5 rounded-full shrink-0">
                        {s.chunk_count} chunks
                      </span>
                    </label>
                  ))}
                </div>
              </div>

              {/* Config + Generate */}
              <div className="bg-white rounded-xl border border-black/8 px-5 py-4 flex items-center gap-6 flex-wrap">
                <div className="flex items-center gap-2.5">
                  <label className="text-sm text-gray-600 whitespace-nowrap">Số câu/section:</label>
                  <input
                    type="number" min={1} max={20} value={qps}
                    onChange={(e) => setQps(Number(e.target.value))}
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
                      <CheckCircle2 size={15} /> Hoàn thành!
                    </span>
                  )}
                  {jobStatus === "failed" && (
                    <span className="text-sm text-red-600">Thất bại. Thử lại.</span>
                  )}
                  <button
                    onClick={handleGenerate}
                    disabled={!selectedDataset || jobStatus === "running" || sections.length === 0}
                    className={cn(
                      "flex items-center gap-2 px-5 py-2 rounded-lg text-sm font-medium transition-all",
                      alreadyGenerated
                        ? "bg-amber-600 hover:bg-amber-700 text-white disabled:opacity-40"
                        : "bg-emerald-700 hover:bg-emerald-800 text-white disabled:opacity-40",
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
