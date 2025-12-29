"""Configuration for RAG system."""

import os
from pathlib import Path
from typing import Optional


class RAGConfig:
    """Configuration settings for the RAG system."""
    
    # Embedding model
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
    
    # Chunking settings
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 200
    
    # Retrieval settings
    TOP_K: int = int(os.getenv("RAG_TOP_K", "5"))
    
    # Vector store settings
    VECTOR_STORE_PATH: Path = Path(os.getenv("CHROMA_DB_PATH", "./chroma_db"))
    COLLECTION_NAME: str = "dawn_bringer_docs"
    
    # Documentation settings
    DOCS_DIR: Path = Path("docs")
    
    # Character chunk size (smaller for focused content)
    CHARACTER_CHUNK_SIZE: int = 800
    CHARACTER_CHUNK_OVERLAP: int = 150
    
    @classmethod
    def get_vector_store_path(cls) -> Path:
        """Get the vector store path, creating it if needed."""
        cls.VECTOR_STORE_PATH.mkdir(parents=True, exist_ok=True)
        return cls.VECTOR_STORE_PATH

