"""ChromaDB vector store management."""

import hashlib
import json
import os
from pathlib import Path
from typing import List, Dict, Optional
import chromadb
from chromadb.config import Settings
from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma
from rag.config import RAGConfig
from rag.document_loader import Document, DocumentLoader
from rag.chunking import DocumentChunker
from rag.utils import estimate_words_from_chunks, format_word_count


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
    
    def _get_file_hashes_path(self) -> Path:
        """Get the path to the file hashes metadata file.
        
        Returns:
            Path to the file hashes JSON file
        """
        return self.vector_store_path / "file_hashes.json"
    
    def _load_stored_file_hashes(self) -> Dict[str, str]:
        """Load stored file hashes from metadata file.
        
        Returns:
            Dictionary mapping file paths (relative to docs dir) to their hashes
        """
        hashes_path = self._get_file_hashes_path()
        if not hashes_path.exists():
            return {}
        
        try:
            with open(hashes_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️ Error loading file hashes: {e}")
            return {}
    
    def _save_file_hashes(self, file_hashes: Dict[str, str]) -> None:
        """Save file hashes to metadata file.
        
        Args:
            file_hashes: Dictionary mapping file paths (relative to docs dir) to their hashes
        """
        hashes_path = self._get_file_hashes_path()
        try:
            with open(hashes_path, "w", encoding="utf-8") as f:
                json.dump(file_hashes, f, indent=2)
        except Exception as e:
            print(f"⚠️ Error saving file hashes: {e}")
    
    def _get_current_file_hashes(self) -> Dict[str, str]:
        """Get current file hashes for all documents in the docs directory.
        
        Returns:
            Dictionary mapping file paths (relative to docs dir) to their hashes
        """
        docs_dir = self.config.DOCS_DIR
        file_hashes = {}
        
        if not docs_dir.exists():
            return file_hashes
        
        # Load all documents to get the list of files
        loader = DocumentLoader(docs_dir)
        for pattern in ["*.txt", "*.md"]:
            for file_path in docs_dir.rglob(pattern):
                # Skip README.md files (same logic as DocumentLoader)
                if file_path.stem.upper() == "README":
                    continue
                
                try:
                    # Get relative path from docs_dir
                    relative_path = file_path.relative_to(docs_dir)
                    # Use forward slashes for consistency (works on Windows too)
                    key = str(relative_path).replace("\\", "/")
                    file_hashes[key] = self._get_file_hash(file_path)
                except Exception as e:
                    print(f"⚠️ Error hashing {file_path}: {e}")
        
        return file_hashes
    
    def _should_rebuild(self) -> bool:
        """Check if vector store should be rebuilt.
        
        Checks:
        1. If force_rebuild flag is set
        2. If collection doesn't exist or is empty
        3. If any source files have changed (by comparing file hashes)
        
        Returns:
            True if vector store should be rebuilt
        """
        if self.force_rebuild:
            print("🔨 Force rebuild requested (--rebuild flag or force_rebuild=True)")
            return True
        
        # Check if collection exists
        collection_exists = False
        try:
            collection = self.client.get_collection(name=self.collection_name)
            count = collection.count()
            if count == 0:
                print("⚠️ Vector store collection exists but is empty - rebuilding...")
                return True
            collection_exists = True
        except Exception:
            # Collection doesn't exist - this is normal on first run
            print("⚠️ Vector store collection not found - will rebuild")
            return True
        
        # If collection exists, check if files have changed
        if collection_exists:
            stored_hashes = self._load_stored_file_hashes()
            current_hashes = self._get_current_file_hashes()
            
            # If no stored hashes exist, rebuild (first time or metadata was lost)
            if not stored_hashes:
                print("📝 No file hash metadata found - rebuilding to capture current state...")
                return True
            
            # Check for changed or new files
            changed_files = []
            for file_path, current_hash in current_hashes.items():
                stored_hash = stored_hashes.get(file_path)
                if stored_hash is None:
                    changed_files.append(f"{file_path} (new)")
                elif stored_hash != current_hash:
                    changed_files.append(f"{file_path} (modified)")
            
            # Check for deleted files
            deleted_files = []
            for file_path in stored_hashes:
                if file_path not in current_hashes:
                    deleted_files.append(file_path)
            
            if changed_files or deleted_files:
                if changed_files:
                    print(f"📝 Detected {len(changed_files)} changed/new file(s):")
                    for file in changed_files[:5]:  # Show first 5
                        print(f"   - {file}")
                    if len(changed_files) > 5:
                        print(f"   ... and {len(changed_files) - 5} more")
                if deleted_files:
                    print(f"📝 Detected {len(deleted_files)} deleted file(s):")
                    for file in deleted_files[:5]:  # Show first 5
                        print(f"   - {file}")
                    if len(deleted_files) > 5:
                        print(f"   ... and {len(deleted_files) - 5} more")
                print("🔄 Rebuilding vector store to reflect changes...")
                return True
            
            # All files match - no rebuild needed
            return False
        
        return False
    
    def build_vector_store(self, documents: List[Document]) -> None:
        """Build the vector store from documents.
        
        Args:
            documents: List of Document objects to embed and store
        """
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
        
        # Save file hashes after successful build
        current_hashes = self._get_current_file_hashes()
        self._save_file_hashes(current_hashes)
        print(f"💾 Saved file hashes for {len(current_hashes)} files")
    
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
                doc_count = self.vector_store._collection.count()
                estimated_words = estimate_words_from_chunks(doc_count)
                word_display = format_word_count(estimated_words)
                print(f"📂 Loaded knowledge base: ~{word_display} words from {doc_count:,} articles")
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

