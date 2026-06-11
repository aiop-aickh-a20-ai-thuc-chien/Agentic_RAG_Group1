import sys
import logging

logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger(__name__)

logger.info("Bắt đầu khởi tạo thư viện FlagEmbedding...")
try:
    from FlagEmbedding import BGEM3FlagModel
    logger.info("Import thành công! Đang tiến hành tải mô hình BAAI/bge-m3 từ HuggingFace...")
    # Tải mô hình
    model = BGEM3FlagModel("BAAI/bge-m3", use_fp16=True)
    logger.info("TẢI VÀ NẠP MÔ HÌNH THÀNH CÔNG!")
except Exception as e:
    logger.error(f"Lỗi: {e}", exc_info=True)
