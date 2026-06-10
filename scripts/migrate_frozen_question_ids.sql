-- Migration: đóng băng danh sách câu hỏi tại thời điểm tạo run
-- Chạy 1 lần trên Neon SQL editor trước khi deploy code mới

ALTER TABLE eval_runs
  ADD COLUMN IF NOT EXISTS frozen_question_ids UUID[] NOT NULL DEFAULT '{}';
