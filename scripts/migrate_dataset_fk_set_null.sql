-- Migration (tùy chọn, phòng thủ tầng DB): đổi FK dataset_id từ CASCADE → SET NULL
-- để xóa dataset không bao giờ kéo theo câu hỏi trong kho.
-- Code delete_dataset đã detach trước khi xóa nên không chạy cũng không mất data,
-- nhưng chạy thì an toàn tuyệt đối kể cả khi có ai DELETE thẳng trên DB.
-- Chạy 1 lần trên Neon SQL editor.

ALTER TABLE eval_questions DROP CONSTRAINT eval_questions_dataset_id_fkey;
ALTER TABLE eval_questions ADD CONSTRAINT eval_questions_dataset_id_fkey
  FOREIGN KEY (dataset_id) REFERENCES eval_datasets(id) ON DELETE SET NULL;

ALTER TABLE eval_questions_approved DROP CONSTRAINT eval_questions_approved_dataset_id_fkey;
ALTER TABLE eval_questions_approved ADD CONSTRAINT eval_questions_approved_dataset_id_fkey
  FOREIGN KEY (dataset_id) REFERENCES eval_datasets(id) ON DELETE SET NULL;
