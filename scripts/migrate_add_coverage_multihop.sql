-- Migration: thêm metric coverage@5 + cờ dataset multi-hop.
-- Idempotent — chạy nhiều lần không lỗi. Chạy trên Neon SQL editor hoặc qua psql.

-- coverage@5: 1.0 khi lấy đủ TẤT CẢ chunk ground-truth trong top-5 (metric multi-hop).
ALTER TABLE eval_results  ADD COLUMN IF NOT EXISTS coverage_at_5 FLOAT;

-- Đánh dấu dataset multi-hop để báo cáo tách khỏi single-hop.
ALTER TABLE eval_datasets ADD COLUMN IF NOT EXISTS is_multihop BOOLEAN DEFAULT FALSE;
