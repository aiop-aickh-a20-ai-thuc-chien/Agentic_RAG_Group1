from pathlib import Path

from huggingface_hub import snapshot_download

LOCAL_DIR = Path(__file__).resolve().parent / "data"
LOCAL_DIR.mkdir(exist_ok=True)

# # Tải toàn bộ kho dữ liệu ParseBench (gồm cả file PDF và JSONL)
parsebench_saved_path = LOCAL_DIR / "parsebench_dataset"
snapshot_download(
    repo_id="llamaindex/ParseBench", repo_type="dataset", local_dir=str(parsebench_saved_path)
)
print("Đã tải xong ParseBench!")

# Tải toàn bộ kho dữ liệu ảnh và cấu trúc nhãn của MDPBench
mdpbench_saved_path = LOCAL_DIR / "mdpbench_dataset"
snapshot_download(
    repo_id="Delores-Lin/MDPBench", repo_type="dataset", local_dir=str(mdpbench_saved_path)
)
print("Đã tải xong MDPBench!")
