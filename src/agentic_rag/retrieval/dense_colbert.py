"""Late Interaction (ColBERT) Dense Retrieval using BGE-M3."""

from __future__ import annotations

import logging
from typing import Any

from agentic_rag.core.contracts import Chunk

logger = logging.getLogger(__name__)

class _PseudoDoc:
    """Mock document class to maintain compatibility with Langchain VectorStore outputs."""
    def __init__(self, metadata: dict[str, Any], page_content: str):
        self.metadata = metadata
        self.page_content = page_content


class ColbertIndex:
    """ColBERT (Late Interaction) index for high-precision dense retrieval."""

    def __init__(self, chunks: list[Chunk], model_name: str = "BAAI/bge-m3") -> None:
        try:
            from FlagEmbedding import BGEM3FlagModel
        except ImportError as exc:
            raise ImportError(
                "ColBERT retrieval requires 'FlagEmbedding'. "
                "Please run `pip install FlagEmbedding`."
            ) from exc

        self.chunks = chunks
        
        logger.info("Loading BGE-M3 model for ColBERT Indexing: %s", model_name)
        self.model = BGEM3FlagModel(model_name, use_fp16=True)
        
        if not chunks:
            self.chunk_vecs = []
            return
            
        texts = [chunk.text for chunk in chunks]
        
        # Encode chunks to get colbert vectors (multi-vectors per chunk)
        output = self.model.encode(
            texts, 
            return_dense=False, 
            return_sparse=False, 
            return_colbert_vecs=True
        )
        self.chunk_vecs = output['colbert_vecs']

    def similarity_search_with_score(self, query: str, k: int = 10, filter: Any = None) -> list[tuple[Any, float]]:
        """Compute ColBERT Max-Sim scores and return pseudo-documents."""
        if not self.chunks:
            return []

        # Encode query into multi-vectors
        output = self.model.encode(
            [query], 
            return_dense=False, 
            return_sparse=False, 
            return_colbert_vecs=True
        )
        query_vecs = output['colbert_vecs'][0]
        
        results = []
        for i, chunk_vec in enumerate(self.chunk_vecs):
            # Evaluate colbert score using BGE-M3's Max-Sim algorithm
            # colbert_score automatically handles tensor operations for Max-Sim
            score = self.model.colbert_score(query_vecs, chunk_vec)
            
            # Create a pseudo-document with chunk_index mapping
            doc = _PseudoDoc(metadata={"chunk_index": i}, page_content=self.chunks[i].text)
            results.append((doc, float(score)))

        # Sort by score descending and take top k
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:k]
