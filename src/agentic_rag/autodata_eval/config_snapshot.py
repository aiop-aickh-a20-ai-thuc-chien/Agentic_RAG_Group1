"""Snapshot cấu hình pipeline từ env tại thời điểm tạo run.

Config được đóng băng theo từng eval run để khi so sánh versions biết
"đổi gì mà điểm đổi". KHÔNG BAO GIỜ snapshot API key — chỉ provider/model
và các knob retrieval. Giá trị giữ gọn để hiển thị dạng `key=value`.

Lưu ý các knob retrieval phụ thuộc đường chạy:
  - Đường Qdrant (DENSE_VECTOR_STORE=qdrant): Qdrant fuse server-side,
    chỉ retrieval_top_k áp dụng; candidate_k / fusion / threshold KHÔNG dùng.
  - Đường in-memory (turbovec): bm25 + dense cùng lấy candidate_k → fusion →
    threshold → cắt top_k.
Vì vậy candidate_k / fusion / threshold chỉ snapshot khi đi turbovec.
"""

from __future__ import annotations

import os
from typing import Any

# Threshold env mặc định TẮT — chỉ snapshot key nào được set tường minh.
_THRESHOLD_ENVS = (
    ("bm25_min_score", "BM25_MIN_SCORE"),
    ("dense_min_score", "DENSE_MIN_SCORE"),
    ("bm25_min_norm_score", "BM25_MIN_NORM_SCORE"),
    ("dense_min_norm_score", "DENSE_MIN_NORM_SCORE"),
    ("fusion_min_score", "FUSION_MIN_SCORE"),
    ("rerank_min_score", "RERANK_MIN_SCORE"),
)


def snapshot_pipeline_config() -> dict[str, Any]:
    """Chụp lại cấu hình pipeline đang hiệu lực từ env để lưu kèm eval run."""
    # Nạp .env trước MỌI lần đọc env — nếu không, các key đọc os.getenv trực tiếp
    # (provider, retrieval knob) có thể rơi về default khi .env chưa được nạp.
    try:
        from agentic_rag.runtime_env import load_local_env

        load_local_env()
    except Exception:
        pass
    return {
        **_provider_config(),
        **_model_config(),
        **_retrieval_config(),
    }


def _provider_config() -> dict[str, Any]:
    """Evidence provider — quyết định knob nào áp dụng + phát hiện cấu hình sai."""
    try:
        from agentic_rag.generation.evidence import configured_evidence_provider_name

        return {"provider": configured_evidence_provider_name()}
    except Exception:  # snapshot không bao giờ được chặn việc tạo run
        return {}


def _model_config() -> dict[str, Any]:
    """LLM / embedding / reranker — KHÔNG bao gồm API key."""
    from agentic_rag.model_runtime.config import (
        resolve_embedding_config,
        resolve_llm_profile,
        resolve_reranker_config,
    )

    out: dict[str, Any] = {}
    try:
        llm = resolve_llm_profile("generation")
        out["llm"] = (
            f"{llm.provider}/{llm.model}"
            if (llm.provider != "none" and llm.model)
            else llm.provider
        )
    except Exception:
        pass
    try:
        emb = resolve_embedding_config()
        out["embedding"] = f"{emb.provider}/{emb.model}"
    except Exception:
        pass
    try:
        rr = resolve_reranker_config()
        out["reranker"] = f"{rr.provider}/{rr.model}" if rr.model else rr.provider
    except Exception:
        pass
    return out


def _resolve_vector_store() -> str:
    """Provider qua resolver chính thức (retrieval.config) — xử lý tên canonical
    VECTOR_STORE_PROVIDER, legacy DENSE_VECTOR_STORE, và suy luận từ QDRANT_URL/
    pgvector. Fallback đọc env thô nếu resolver lỗi — snapshot không được chặn tạo run.
    """
    import warnings

    try:
        from agentic_rag.retrieval.config import resolve_vector_store_config

        with warnings.catch_warnings():  # đừng nag deprecation mỗi lần tạo run
            warnings.simplefilter("ignore")
            return resolve_vector_store_config().provider
    except Exception:
        raw = os.getenv("VECTOR_STORE_PROVIDER") or os.getenv("DENSE_VECTOR_STORE") or "turbovec"
        return raw.strip().lower() or "turbovec"


def _retrieval_config() -> dict[str, Any]:
    """Vector store + breadth (cả 2 đường); fusion/threshold chỉ trên turbovec."""
    vector_store = _resolve_vector_store()
    out: dict[str, Any] = {
        "vector_store": vector_store,
        "retrieval_top_k": _int_env("LOCAL_PDF_RETRIEVAL_TOP_K", 5),  # lấy về trước rerank
        "rerank_top_k": _int_env("AGENT_RERANK_FINAL_TOP_K", 8),  # đưa vào LLM sau rerank
    }

    # Knob CHỈ áp dụng trên đường in-memory (turbovec) — qdrant fuse server-side
    # và bỏ qua toàn bộ fusion/threshold Python. Snapshot chúng khi ở qdrant sẽ
    # gây hiểu lầm (vô tác dụng), nên gom hết vào nhánh này.
    if vector_store != "qdrant":
        out["candidate_k"] = _int_env("LOCAL_PDF_RETRIEVAL_CANDIDATE_K", 20)
        out["fusion"] = os.getenv("FUSION_METHOD", "rrf").strip().lower() or "rrf"
        for key, env_name in _THRESHOLD_ENVS:
            val = _float_env(env_name)
            if val is not None:
                out[key] = val
        mec = _int_env("MIN_EVIDENCE_COUNT", 0)
        if mec > 0:
            out["min_evidence_count"] = mec

    return out


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        v = int(raw)
        return v if v > 0 else default
    except ValueError:
        return default


def _float_env(name: str) -> float | None:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return None
    try:
        return float(raw)
    except ValueError:
        return None
