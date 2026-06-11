"""Neural Sparse Retrieval using BGE-M3 (SPLADE architecture equivalent)."""

from __future__ import annotations

import logging
from typing import Any

from agentic_rag.core.contracts import Chunk

logger = logging.getLogger(__name__)


class NeuralSparseIndex:
    """A drop-in replacement for BM25Okapi using Neural Sparse Weights (BGE-M3/SPLADE)."""

    def __init__(self, chunks: list[Chunk], model_name: str = "BAAI/bge-m3") -> None:
        try:
            from FlagEmbedding import BGEM3FlagModel
            import scipy.sparse as sp
        except ImportError as exc:
            raise ImportError(
                "Neural sparse retrieval requires 'FlagEmbedding' and 'scipy'. "
                "Please run `pip install FlagEmbedding scipy`."
            ) from exc

        self.chunks = chunks
        
        # Load the BGE-M3 model for sparse extraction only
        logger.info("Loading BGE-M3 model for Neural Sparse Indexing: %s", model_name)
        self.model = BGEM3FlagModel(model_name, use_fp16=True)
        self.vocab_size = len(self.model.tokenizer)

        if not chunks:
            self.chunk_matrix = sp.csr_matrix((0, self.vocab_size))
            return

        texts = [chunk.text for chunk in chunks]
        
        # Encode chunks to get lexical weights (the 'SPLADE' part of BGE-M3)
        # BGE-M3 outputs lexical weights as a list of dictionaries: {token_id_str: weight_float}
        output = self.model.encode(
            texts, 
            return_dense=False, 
            return_sparse=True, 
            return_colbert_vecs=False
        )
        lexical_weights_list = output['lexical_weights']

        rows = []
        cols = []
        data = []
        for i, weight_dict in enumerate(lexical_weights_list):
            for token_str, weight in weight_dict.items():
                rows.append(i)
                cols.append(int(token_str))
                data.append(weight)

        if not rows:
            self.chunk_matrix = sp.csr_matrix((len(chunks), self.vocab_size))
        else:
            self.chunk_matrix = sp.csr_matrix(
                (data, (rows, cols)), 
                shape=(len(chunks), self.vocab_size)
            )

    def get_scores(self, query: str | list[str]) -> list[float]:
        """Compute sparse dot product scores against all chunks."""
        import scipy.sparse as sp

        if not self.chunks:
            return []

        if isinstance(query, list):
            query = " ".join(query)

        output = self.model.encode(
            [query], 
            return_dense=False, 
            return_sparse=True, 
            return_colbert_vecs=False
        )
        lexical_weights = output['lexical_weights'][0]

        rows = []
        cols = []
        data = []
        for token_str, weight in lexical_weights.items():
            rows.append(0)
            cols.append(int(token_str))
            data.append(weight)

        if not rows:
            query_matrix = sp.csr_matrix((1, self.vocab_size))
        else:
            query_matrix = sp.csr_matrix(
                (data, (rows, cols)), 
                shape=(1, self.vocab_size)
            )

        # Dot product between chunks and query
        scores = self.chunk_matrix.dot(query_matrix.T).toarray().flatten()
        return scores.tolist()
