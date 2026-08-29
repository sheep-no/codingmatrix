"""Unified retrieval contracts and source adapters."""

from .models import RetrievalChunk, RetrievalRequest, RetrievalResult
from .service import CallableRetriever, RetrievalService

__all__ = [
    "CallableRetriever",
    "RetrievalChunk",
    "RetrievalRequest",
    "RetrievalResult",
    "RetrievalService",
]
