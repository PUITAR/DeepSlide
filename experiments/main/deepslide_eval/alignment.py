from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np


@dataclass(frozen=True)
class AlignmentResult:
    top_indices: List[int]
    top_scores: List[float]


def _l2_normalize(x: np.ndarray) -> np.ndarray:
    denom = np.linalg.norm(x, axis=1, keepdims=True) + 1e-12
    return x / denom


def cosine_topk(query: np.ndarray, keys: np.ndarray, k: int = 5) -> AlignmentResult:
    q = query.reshape(1, -1)
    qn = _l2_normalize(q)
    kn = _l2_normalize(keys)
    sims = (kn @ qn.T).reshape(-1)
    if sims.size == 0:
        return AlignmentResult(top_indices=[], top_scores=[])
    kk = min(k, sims.size)
    idx = np.argpartition(-sims, kk - 1)[:kk]
    idx = idx[np.argsort(-sims[idx])]
    return AlignmentResult(top_indices=[int(i) for i in idx], top_scores=[float(sims[i]) for i in idx])


class Embedder:
    def __init__(self, method: str = "tfidf", model_name: Optional[str] = None):
        self.method = method
        self.model_name = model_name
        self._st_model = None
        self._tfidf = None

    def embed(self, texts: List[str]) -> np.ndarray:
        texts = [t if isinstance(t, str) else "" for t in texts]
        if self.method == "sentence_transformers":
            return self._embed_st(texts)
        return self._embed_tfidf(texts)

    def _embed_st(self, texts: List[str]) -> np.ndarray:
        if self._st_model is None:
            from sentence_transformers import SentenceTransformer

            name = self.model_name or "all-MiniLM-L6-v2"
            self._st_model = SentenceTransformer(name)
        arr = self._st_model.encode(texts, normalize_embeddings=False, show_progress_bar=False)
        return np.asarray(arr, dtype=np.float32)

    def _embed_tfidf(self, texts: List[str]) -> np.ndarray:
        from sklearn.feature_extraction.text import TfidfVectorizer

        vec = TfidfVectorizer(max_features=50_000, ngram_range=(1, 2))
        m = vec.fit_transform(texts)
        return m.toarray().astype(np.float32)
