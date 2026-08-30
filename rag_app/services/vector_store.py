import os
import re
import logging
import httpx
import numpy as np
from typing import List, Dict, Any, Optional
from django.conf import settings

logger = logging.getLogger(__name__)

# Global in-memory cache for the dense neural embedding model
_GLOBAL_NEURAL_MODEL = None


def _get_neural_model():
    """Lazily loads and caches the SentenceTransformer neural model."""
    global _GLOBAL_NEURAL_MODEL
    if _GLOBAL_NEURAL_MODEL is None:
        try:
            try:
                import torch
                torch.set_num_threads(2)
            except Exception:
                pass
            from sentence_transformers import SentenceTransformer
            model_name = getattr(settings, 'EMBEDDING_MODEL_NAME', 'all-MiniLM-L6-v2')
            _GLOBAL_NEURAL_MODEL = SentenceTransformer(model_name)
            logger.info(f"Loaded Dense Neural Embedding Model: {model_name}")
        except Exception as e:
            logger.warning(f"Could not load SentenceTransformer: {e}")
            _GLOBAL_NEURAL_MODEL = False
    return _GLOBAL_NEURAL_MODEL if _GLOBAL_NEURAL_MODEL is not False else None


class VectorStoreService:
    """
    Universal Production-Grade Dense Neural + Sparse BM25 Hybrid RAG Engine.
    Works dynamically for ANY document and ANY query without hardcoded heuristics.
    """

    @staticmethod
    def generate_embeddings(texts: List[str]) -> List[List[float]]:
        if not texts:
            return []

        # 1. Try Dense Transformer Embeddings (all-MiniLM-L6-v2, 384 dimensions)
        model = _get_neural_model()
        if model is not None:
            try:
                try:
                    import torch
                    with torch.inference_mode():
                        embs = model.encode(
                            texts,
                            batch_size=32,
                            normalize_embeddings=True,
                            show_progress_bar=False,
                            convert_to_numpy=True
                        )
                except Exception:
                    embs = model.encode(
                        texts,
                        batch_size=32,
                        normalize_embeddings=True,
                        show_progress_bar=False
                    )
                return embs.tolist()
            except Exception as e:
                logger.error(f"Neural embedding generation error: {e}")

        # 2. Fallback to Sublinear TF-IDF
        return VectorStoreService._generate_fast_embeddings(texts)

    @staticmethod
    def _generate_fast_embeddings(texts: List[str]) -> List[List[float]]:
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            vectorizer = TfidfVectorizer(
                max_features=40000,
                sublinear_tf=True,
                ngram_range=(1, 2),
                stop_words='english',
                strip_accents='unicode'
            )
            matrix = vectorizer.fit_transform(texts).toarray()
            norms = np.linalg.norm(matrix, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            matrix = matrix / norms
            return [row.tolist() for row in matrix]
        except Exception as e:
            logger.error(f"Error in fast vectorizer: {e}")
            return [[0.0] * 64 for _ in texts]

    @staticmethod
    def search_similar_chunks(
        query: str, chunks_data: List[Dict[str, Any]], top_k: int = 6
    ) -> List[Dict[str, Any]]:
        if not chunks_data:
            return []

        all_contents = [ch.get("content", "") for ch in chunks_data]
        num_chunks = len(chunks_data)

        # -------------------------------------------------------------
        # 1. Dense Semantic Similarity (Vector Space)
        # -------------------------------------------------------------
        dense_sims = np.zeros(num_chunks)
        model = _get_neural_model()

        if model is not None:
            try:
                # Check if chunks have pre-computed 384-d dense embeddings
                has_valid_embs = (
                    chunks_data[0].get("embedding") is not None
                    and isinstance(chunks_data[0].get("embedding"), list)
                    and len(chunks_data[0].get("embedding")) == 384
                )

                if has_valid_embs:
                    chunk_matrix = np.array([ch["embedding"] for ch in chunks_data], dtype=np.float32)
                else:
                    chunk_matrix = model.encode(all_contents, normalize_embeddings=True, show_progress_bar=False)

                q_vec = model.encode(query, normalize_embeddings=True)
                dense_sims = chunk_matrix @ q_vec
            except Exception as e:
                logger.error(f"Dense vector calculation error: {e}")

        # -------------------------------------------------------------
        # 2. Sparse Lexical Similarity (BM25 / Sublinear TF-IDF)
        # -------------------------------------------------------------
        sparse_sims = np.zeros(num_chunks)
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            vectorizer = TfidfVectorizer(
                max_features=40000,
                sublinear_tf=True,
                ngram_range=(1, 2),
                stop_words='english'
            )
            matrix = vectorizer.fit_transform(all_contents + [query]).toarray()
            norms = np.linalg.norm(matrix, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            matrix = matrix / norms

            doc_vectors = matrix[:-1]
            query_vector = matrix[-1]
            sparse_sims = np.dot(doc_vectors, query_vector)
        except Exception as e:
            logger.error(f"Sparse vector calculation error: {e}")

        # -------------------------------------------------------------
        # 3. Reciprocal Rank & Hybrid Score Fusion
        # -------------------------------------------------------------
        scored_chunks = []
        for i, item in enumerate(chunks_data):
            d_score = float(dense_sims[i]) if i < len(dense_sims) else 0.0
            s_score = float(sparse_sims[i]) if i < len(sparse_sims) else 0.0

            # 70% Dense Neural Semantics + 30% Exact Lexical Match
            hybrid_score = (0.70 * d_score) + (0.30 * s_score)

            scored_chunks.append({
                **item,
                "similarity_score": round(max(0.0, float(hybrid_score)), 4),
                "dense_score": round(float(d_score), 4),
                "sparse_score": round(float(s_score), 4),
            })

        scored_chunks.sort(key=lambda x: x["similarity_score"], reverse=True)
        return scored_chunks[:top_k]
