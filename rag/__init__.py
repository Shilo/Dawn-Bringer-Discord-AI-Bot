"""
RAG (Retrieval-Augmented Generation) module for Dawn Bringer Discord Bot.

This module provides semantic search capabilities using LangChain, OpenAI embeddings,
and ChromaDB vector database.
"""

from rag.config import RAGConfig
from rag.document_loader import DocumentLoader, Document
from rag.chunking import DocumentChunker
from rag.vector_store import VectorStore
from rag.retriever import RAGRetriever
from rag.chain import RAGChain

__all__ = [
    "RAGConfig",
    "DocumentLoader",
    "Document",
    "DocumentChunker",
    "VectorStore",
    "RAGRetriever",
    "RAGChain",
]

