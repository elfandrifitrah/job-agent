"""
Embedding Service — generates vector embeddings for text and manages a vector store.

Pipeline:
  1. Load a SentenceTransformer model
  2. Generate embeddings for CV text, job descriptions, etc.
  3. Store & query vectors via ChromaDB
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from backend.config import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Manages text embedding and vector similarity search."""

    DEFAULT_MODEL = "all-MiniLM-L6-v2"  # fast, 384-dim, good for semantic similarity

    def __init__(self, model_name: str = DEFAULT_MODEL, persist_dir: str | Path | None = None):
        self.model_name = model_name
        self._model = None
        self._chroma_client = None
        self._collection = None
        self.persist_dir = Path(persist_dir or settings.chroma_persist_dir)
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self._initialized = False

    def initialize(self) -> None:
        """Lazy-load the model and ChromaDB client."""
        if self._initialized:
            return

        logger.info("Loading embedding model: %s", self.model_name)
        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_name)
        except ImportError:
            logger.error("sentence-transformers is not installed.")
            raise

        logger.info("Initializing ChromaDB at %s", self.persist_dir)
        try:
            import chromadb
            self._chroma_client = chromadb.PersistentClient(path=str(self.persist_dir))
            self._collection = self._chroma_client.get_or_create_collection(
                name="job_embeddings",
                metadata={"hnsw:space": "cosine"},
            )
        except ImportError:
            logger.error("chromadb is not installed.")
            raise

        self._initialized = True

    @property
    def model(self):
        if not self._model:
            self.initialize()
        return self._model

    @property
    def collection(self):
        if not self._collection:
            self.initialize()
        return self._collection

    def embed(self, text: str) -> list[float]:
        """Generate a single embedding vector for a text string."""
        emb = self.model.encode(text, show_progress_bar=False)
        return emb.tolist()

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a batch of texts."""
        embs = self.model.encode(texts, show_progress_bar=False)
        return [e.tolist() for e in embs]

    def store_cv(self, profile_id: str, text: str, metadata: Optional[dict] = None) -> None:
        """Store a CV embedding in the vector DB."""
        self.initialize()
        embedding = self.embed(text)
        self.collection.add(
            ids=[f"cv_{profile_id}"],
            embeddings=[embedding],
            metadatas=[metadata or {"type": "cv", "profile_id": profile_id}],
            documents=[text[:5000]],
        )
        logger.info("Stored CV embedding: %s", profile_id)

    def store_job(self, job_id: str, description: str, metadata: Optional[dict] = None) -> None:
        """Store a job posting embedding in the vector DB."""
        self.initialize()
        embedding = self.embed(description)
        self.collection.add(
            ids=[f"job_{job_id}"],
            embeddings=[embedding],
            metadatas=[metadata or {"type": "job", "job_id": job_id}],
            documents=[description[:5000]],
        )

    def query_similar_jobs(
        self, cv_text: str, top_k: int = 10
    ) -> list[dict]:
        """Find the most similar job postings for a given CV text."""
        self.initialize()
        embedding = self.embed(cv_text)
        results = self.collection.query(
            query_embeddings=[embedding],
            n_results=top_k,
            where={"type": "job"},
        )
        output = []
        if results["ids"]:
            for i in range(len(results["ids"][0])):
                output.append({
                    "id": results["ids"][0][i],
                    "distance": results["distances"][0][i] if results.get("distances") else 0.0,
                    "metadata": results["metadatas"][0][i] if results.get("metadatas") else {},
                })
        return output

    def query_similar_cvs(self, job_text: str, top_k: int = 10) -> list[dict]:
        """Find CVs similar to a job description (reverse matching)."""
        self.initialize()
        embedding = self.embed(job_text)
        results = self.collection.query(
            query_embeddings=[embedding],
            n_results=top_k,
            where={"type": "cv"},
        )
        output = []
        if results["ids"]:
            for i in range(len(results["ids"][0])):
                output.append({
                    "id": results["ids"][0][i],
                    "distance": results["distances"][0][i] if results.get("distances") else 0.0,
                    "metadata": results["metadatas"][0][i] if results.get("metadatas") else {},
                })
        return output

    def count(self) -> int:
        """Return the number of documents in the collection."""
        self.initialize()
        return self.collection.count()
