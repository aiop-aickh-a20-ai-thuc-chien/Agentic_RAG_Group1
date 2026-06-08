export type DisplayStatus = "pending" | "approved" | "evaluated";

export interface Row {
  excel_row: number;
  id: string | null;
  question: string | null;
  expected_answer: string | null;
  ground_truth_chunk_ids: string | null;
  is_out_of_scope: boolean | null;
  review_status: "pending" | "approved";
  display_status: DisplayStatus;
  rag_context: string | null;
  bot_response: string | null;
  retrieved_top5_ids: string | null;
  mrr_at_5: number | null;
  recall_at_5: number | null;
  ragas_faithfulness: number | null;
  ragas_answer_relevancy: number | null;
  ragas_context_precision: number | null;
  ragas_context_recall: number | null;
}

export interface RejectedRow extends Omit<Row, "display_status"> {
  reject_row: number;
  display_status: "deleted";
}

export interface Chunk {
  chunk_id: string;
  text: string;
  score: number;
  retriever: string;
  section: string;
  url: string;
}

export interface EvalRowStatus {
  status: "idle" | "queued" | "running" | "done" | "error";
  message: string;
}

export interface JobStatus {
  status: "idle" | "running" | "done" | "error";
  progress: number;
  total: number;
  errors: string[];
  message: string;
}
