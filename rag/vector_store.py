"""ChromaDB vector store management."""

import hashlib
import os
from pathlib import Path
from typing import List, Dict, Optional
import chromadb
from chromadb.config import Settings
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import Chroma
from rag.config import RAGConfig
from rag.document_loader import Document
from rag.chunking import DocumentChunker


class VectorStore:
    """Manages ChromaDB vector store for document embeddings."""
    
    def __init__(self, force_rebuild: bool = False):
        """Initialize the vector store.
        
        Args:
            force_rebuild: If True, rebuild the vector store even if it exists
        """
        self.config = RAGConfig
        self.vector_store_path = self.config.get_vector_store_path()
        self.collection_name = self.config.COLLECTION_NAME
        self.force_rebuild = force_rebuild
        
        # Initialize embeddings
        # Explicitly get API key from environment to avoid sync/async issues
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set")
        
        self.embeddings = OpenAIEmbeddings(
            model=self.config.EMBEDDING_MODEL,
            openai_api_key=api_key,
        )
        
        # Initialize ChromaDB client
        self.client = chromadb.PersistentClient(
            path=str(self.vector_store_path),
            settings=Settings(anonymized_telemetry=False)
        )
        
        # Initialize chunker
        self.chunker = DocumentChunker()
        
        # Vector store instance (will be created when needed)
        self.vector_store: Optional[Chroma] = None
    
    def _get_file_hash(self, file_path: Path) -> str:
        """Get hash of file content for change detection.
        
        Args:
            file_path: Path to file
            
        Returns:
            SHA256 hash of file content
        """
        with open(file_path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    
    def _should_rebuild(self) -> bool:
        """Check if vector store should be rebuilt.
        
        Returns:
            True if vector store should be rebuilt
        """
        if self.force_rebuild:
            return True
        
        # Check if collection exists
        try:
            collection = self.client.get_collection(name=self.collection_name)
            if collection.count() == 0:
                return True
        except Exception:
            # Collection doesn't exist
            return True
        
        # Check if docs directory has changed
        # For now, we'll rebuild if collection is empty or doesn't exist
        # In production, you might want to track file hashes
        return False
    
    def build_vector_store(self, documents: List[Document]) -> None:
        """Build the vector store from documents.
        
        Args:
            documents: List of Document objects to embed and store
        """
        print("🔨 Building vector store...")
        
        # Collect all chunks
        all_chunks = []
        all_metadatas = []
        
        for doc in documents:
            chunks = self.chunker.chunk_document(doc)
            for chunk in chunks:
                all_chunks.append(chunk["content"])
                # Convert metadata to strings (ChromaDB requirement)
                metadata = {}
                for key, value in chunk["metadata"].items():
                    if isinstance(value, (str, int, float, bool)):
                        metadata[key] = str(value)
                    else:
                        metadata[key] = str(value)
                all_metadatas.append(metadata)
        
        print(f"📦 Created {len(all_chunks)} chunks from {len(documents)} documents")
        
        # Delete existing collection if it exists
        try:
            self.client.delete_collection(name=self.collection_name)
        except Exception:
            pass
        
        # Create new collection and add documents
        print("🔢 Embedding documents...")
        self.vector_store = Chroma.from_texts(
            texts=all_chunks,
            metadatas=all_metadatas,
            embedding=self.embeddings,
            collection_name=self.collection_name,
            client=self.client,
            persist_directory=str(self.vector_store_path),
        )
        
        print(f"✅ Vector store built with {len(all_chunks)} chunks")
    
    def get_vector_store(self) -> Chroma:
        """Get or create the vector store instance.
        
        Returns:
            Chroma vector store instance
        """
        if self.vector_store is None:
            # Try to load existing vector store
            try:
                self.vector_store = Chroma(
                    collection_name=self.collection_name,
                    embedding_function=self.embeddings,
                    client=self.client,
                    persist_directory=str(self.vector_store_path),
                )
                print(f"📂 Loaded existing vector store with {self.vector_store._collection.count()} documents")
            except Exception as e:
                print(f"⚠️ Could not load vector store: {e}")
                # Will be created when build_vector_store is called
                self.vector_store = None
        
        return self.vector_store
    
    def get_retriever(self, top_k: Optional[int] = None):
        """Get a retriever from the vector store.
        
        Args:
            top_k: Number of documents to retrieve (defaults to config)
            
        Returns:
            LangChain retriever
        """
        vector_store = self.get_vector_store()
        if vector_store is None:
            raise ValueError("Vector store not initialized. Call build_vector_store() first.")
        
        k = top_k or self.config.TOP_K
        return vector_store.as_retriever(
            search_type="similarity",
            search_kwargs={"k": k}
        )
    
    def get_stats(self) -> Dict[str, any]:
        """Get statistics about the vector store.
        
        Returns:
            Dictionary with stats
        """
        try:
            collection = self.client.get_collection(name=self.collection_name)
            count = collection.count()
            return {
                "collection_name": self.collection_name,
                "document_count": count,
                "vector_store_path": str(self.vector_store_path),
            }
        except Exception:
            return {
                "collection_name": self.collection_name,
                "document_count": 0,
                "vector_store_path": str(self.vector_store_path),
                "status": "not_initialized",
            }

