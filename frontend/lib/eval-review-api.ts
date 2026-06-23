import type {
  Chunk,
  EvalFlags,
  EvalRowStatus,
  JobStatus,
  QuestionIndexStatus,
  RejectedRow,
  Row,
} from "./eval-review-types";

const BASE = `${process.env.NEXT_PUBLIC_AGENTIC_RAG_API_URL ?? "http://127.0.0.1:8000"}/eval-review`;

async function fetchJSON<T>(input: string, init?: RequestInit): Promise<T> {
  const res = await fetch(input, init);
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

export const evalApi = {
  getRows: (slim = false) =>
    fetchJSON<Row[]>(`${BASE}/api/rows${slim ? "?slim=true" : ""}`),

  updateRow: (excelRow: number, update: Partial<Row>) =>
    fetchJSON<Row>(`${BASE}/api/rows/${excelRow}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(update),
    }),

  approveRow: (excelRow: number) =>
    fetchJSON<Row>(`${BASE}/api/rows/${excelRow}/approve`, { method: "POST" }),

  rejectRow: (excelRow: number) =>
    fetchJSON<{ ok: boolean }>(`${BASE}/api/rows/${excelRow}/reject`, {
      method: "POST",
    }),

  getRejectedRows: () => fetchJSON<RejectedRow[]>(`${BASE}/api/rejected`),

  restoreRejectedRow: (rejectRow: number) =>
    fetchJSON<{ ok: boolean; restored_row: Row }>(
      `${BASE}/api/rejected/${rejectRow}/restore`,
      { method: "POST" },
    ),

  runEval: (runRagas = true, toggles?: Partial<EvalFlags>) =>
    fetchJSON<{ message: string }>(`${BASE}/api/eval/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ run_ragas: runRagas, ...toggles }),
    }),

  getEvalFlags: () => fetchJSON<EvalFlags>(`${BASE}/api/eval/flags`),

  getQuestionIndexStatus: () =>
    fetchJSON<QuestionIndexStatus>(`${BASE}/api/eval/question-index`),

  buildQuestionIndex: () =>
    fetchJSON<{ message: string }>(`${BASE}/api/eval/question-index/build`, {
      method: "POST",
    }),

  getEvalStatus: () => fetchJSON<JobStatus>(`${BASE}/api/eval/status`),

  getChunks: (question: string) =>
    fetchJSON<Chunk[]>(`${BASE}/api/chunks?q=${encodeURIComponent(question)}`),

  getDocChunks: (chunkId: string) =>
    fetchJSON<{ document_id: string; found: boolean; chunks: Chunk[] }>(
      `${BASE}/api/doc-chunks?chunk_id=${encodeURIComponent(chunkId)}`,
    ),

  approveAndEval: (excelRow: number) =>
    fetchJSON<Row & { _eval_status: EvalRowStatus }>(
      `${BASE}/api/rows/${excelRow}/approve-and-eval`,
      { method: "POST" },
    ),

  reEval: (excelRow: number) =>
    fetchJSON<Row & { _eval_status: EvalRowStatus }>(
      `${BASE}/api/rows/${excelRow}/re-eval`,
      { method: "POST" },
    ),

  getRowEvalStatus: (excelRow: number) =>
    fetchJSON<EvalRowStatus>(`${BASE}/api/rows/${excelRow}/eval-status`),

  getActiveEvalStatus: () =>
    fetchJSON<Record<string, EvalRowStatus>>(`${BASE}/api/eval/active-status`),
};
