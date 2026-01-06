"""
Configuration module for RAG (Retrieval-Augmented Generation) system.

This module contains configuration settings and constants used throughout the RAG system.
"""

from pathlib import Path
from typing import Optional


class Config:
    """Configuration class for the Dawn Bringer Discord Bot."""

    # ============================================================================
    # GENERIC/APP-WIDE SETTINGS
    # ============================================================================

    # Model settings
    MODEL = "gpt-5-mini"  # Main language model for generation
    MAX_TOKENS = 500
    TEMPERATURE = 0.1  # LLM temperature (0.0-2.0). For factual RAG responses (but less creative), consider trying 0.0-0.3 for better accuracy

    # Bot identity and behavior
    BOT_NAMES = ["db", "dawn bringer", "dawn", "dawnbringer"]
    QUESTION_STARTERS = ["who", "what", "when", "where", "why", "how", "is", "are", "can", "could",
                         "would", "should", "do", "does", "did", "will", "has", "have", "which"]
    PUNCTUATION = ",.!?:;-"
    QUESTION_CHANNEL_NAME = "👧ask-dawn-bringer"

    # GitHub repository URL (optional, for linking to source) - set via .env
    GITHUB_REPO_URL: Optional[str] = None

    # ============================================================================
    # RAG (Retrieval-Augmented Generation) SETTINGS
    # ============================================================================

    # Document directory
    DOCS_DIR = Path(__file__).parent.parent / "docs"

    # Embedding settings
    EMBEDDING_MODEL = "text-embedding-3-small"
    EMBEDDING_DIMENSION = 1536

    # Vector store settings
    VECTOR_STORE_PATH = Path(__file__).parent.parent / "chroma_db"
    COLLECTION_NAME = "dawn_bringer_docs"

    # Chunking settings
    CHUNK_SIZE = 1000  # words per chunk
    CHUNK_OVERLAP = 200  # words overlap between chunks

    # Character-level chunking (for fallback)
    CHARACTER_CHUNK_SIZE = 4000  # characters per chunk
    CHARACTER_CHUNK_OVERLAP = 800  # characters overlap

    # Retrieval settings
    SCORE_THRESHOLD = 1.2  # similarity score threshold
    TOP_K = 5  # number of documents to retrieve

    # ============================================================================
    # METHODS
    # ============================================================================

    @classmethod
    def get_vector_store_path(cls) -> Path:
        """Get the vector store path."""
        return cls.VECTOR_STORE_PATH
