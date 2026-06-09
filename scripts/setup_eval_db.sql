-- Eval Pipeline DB Schema
-- Chạy 1 lần trên Supabase SQL editor

-- ── Datasets ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS eval_datasets (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name         TEXT NOT NULL,
  description  TEXT,
  is_benchmark BOOLEAN DEFAULT FALSE,
  created_at   TIMESTAMPTZ DEFAULT NOW()
);

-- ── Draft questions (AutoData sinh ra) ───────────────────────────────────────
CREATE TABLE IF NOT EXISTS eval_questions (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  dataset_id       UUID REFERENCES eval_datasets(id) ON DELETE CASCADE,
  document_id      TEXT NOT NULL,
  section          TEXT,
  question         TEXT NOT NULL,
  ground_truth     TEXT NOT NULL,
  source_chunk_ids TEXT[],
  deleted_at       TIMESTAMPTZ,
  created_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_eval_questions_dataset   ON eval_questions(dataset_id);
CREATE INDEX IF NOT EXISTS idx_eval_questions_deleted   ON eval_questions(deleted_at) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_eval_questions_document  ON eval_questions(document_id);

-- ── Approved questions (đã tích xanh) ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS eval_questions_approved (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  question_id  UUID NOT NULL REFERENCES eval_questions(id) ON DELETE CASCADE,
  dataset_id   UUID NOT NULL REFERENCES eval_datasets(id) ON DELETE CASCADE,
  reviewed_by  TEXT,
  reviewed_at  TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(question_id)
);

CREATE INDEX IF NOT EXISTS idx_eval_approved_dataset ON eval_questions_approved(dataset_id);

-- ── Eval runs (mỗi lần bấm chạy = 1 run/version) ────────────────────────────
CREATE TABLE IF NOT EXISTS eval_runs (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  dataset_id   UUID REFERENCES eval_datasets(id),
  name         TEXT NOT NULL,
  description  TEXT,
  config       JSONB DEFAULT '{}',
  status       TEXT NOT NULL DEFAULT 'queued',
  total        INTEGER DEFAULT 0,
  success      INTEGER DEFAULT 0,
  failed       INTEGER DEFAULT 0,
  created_at   TIMESTAMPTZ DEFAULT NOW(),
  completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_eval_runs_dataset ON eval_runs(dataset_id);
CREATE INDEX IF NOT EXISTS idx_eval_runs_status  ON eval_runs(status);

-- ── Eval results (kết quả từng câu trong từng run) ───────────────────────────
CREATE TABLE IF NOT EXISTS eval_results (
  id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  question_id              UUID NOT NULL REFERENCES eval_questions(id),
  run_id                   UUID NOT NULL REFERENCES eval_runs(id) ON DELETE CASCADE,
  -- Pipeline output
  rag_context              TEXT,
  bot_response             TEXT,
  bot_citations            JSONB,
  trace_url                TEXT,
  -- Auto metrics
  retrieved_top5_ids       TEXT[],
  ground_truth_rank        INTEGER,
  recall_at_5              FLOAT,
  mrr_at_5                 FLOAT,
  citation_chunk_match     FLOAT,
  guardrail_pass           BOOLEAN,
  -- RAGAS (nullable, chạy riêng)
  ragas_faithfulness       FLOAT,
  ragas_answer_relevancy   FLOAT,
  ragas_context_precision  FLOAT,
  ragas_context_recall     FLOAT,
  -- Error tracking
  eval_error               TEXT,
  ran_at                   TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(question_id, run_id)
);

CREATE INDEX IF NOT EXISTS idx_eval_results_run      ON eval_results(run_id);
CREATE INDEX IF NOT EXISTS idx_eval_results_question ON eval_results(question_id);
CREATE INDEX IF NOT EXISTS idx_eval_results_error    ON eval_results(run_id) WHERE eval_error IS NOT NULL;
