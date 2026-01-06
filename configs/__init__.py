"""
Configuration module for RAG (Retrieval-Augmented Generation) system.

This module contains configuration settings and constants used throughout the RAG system.
"""

from pathlib import Path
from typing import Optional


class Config:
    """Configuration class for RAG system settings."""

    # Document directory
    DOCS_DIR = Path(__file__).parent.parent / "docs"

    # Chunking settings
    CHUNK_SIZE = 1000  # words per chunk
    CHUNK_OVERLAP = 200  # words overlap between chunks

    # Character-level chunking (for fallback)
    CHARACTER_CHUNK_SIZE = 4000  # characters per chunk
    CHARACTER_CHUNK_OVERLAP = 800  # characters overlap

    # Retrieval settings
    SCORE_THRESHOLD = 1.2  # similarity score threshold

    # GitHub repository URL (optional, for linking to source)
    GITHUB_REPO_URL: Optional[str] = None

    # Vector store settings
    VECTOR_STORE_PATH = Path(__file__).parent.parent / "chroma_db"
    COLLECTION_NAME = "dawn_bringer_docs"

    # Model settings
    MODEL = "gpt-4o-mini" # "gpt-5-mini" # Main language model for generation

    # Embedding settings
    EMBEDDING_MODEL = "text-embedding-3-small"
    EMBEDDING_DIMENSION = 1536

    @classmethod
    def get_vector_store_path(cls) -> Path:
        """Get the vector store path."""
        return cls.VECTOR_STORE_PATH
