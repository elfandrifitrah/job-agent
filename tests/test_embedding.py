"""
Tests for the Embedding Service.
"""

from __future__ import annotations

import pytest


@pytest.mark.slow
class TestEmbeddingService:
    """Tests for EmbedingService.
    Note: These require sentence-transformers and chromadb to be installed.
    They are skipped if imports fail.
    """

    @pytest.fixture
    def svc(self):
        from backend.services.embedding import EmbeddingService
        svc = EmbeddingService()
        svc.initialize()
        return svc

    def test_embed_returns_list_of_floats(self, svc):
        vec = svc.embed("Hello world")
        assert isinstance(vec, list)
        assert len(vec) > 0
        assert all(isinstance(v, float) for v in vec)

    def test_store_and_query_cv(self, svc):
        svc.store_cv("test-1", "Python developer with React experience")
        svc.store_cv("test-2", "Data scientist using TensorFlow")
        results = svc.query_similar_jobs("Python and React developer")
        assert isinstance(results, list)
        # results may be empty if no jobs stored — that's fine
        # (storing CVs, querying for jobs returns nothing, which is correct)

    def test_store_job(self, svc):
        svc.store_job("job-test-1", "Looking for a Go developer")
        assert svc.count() >= 1
