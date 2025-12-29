"""Semantic retrieval logic for RAG system."""

from typing import List, Optional
from langchain_core.documents import Document as LangChainDocument
from rag.vector_store import VectorStore


class RAGRetriever:
    """Handles semantic retrieval of relevant document chunks."""
    
    def __init__(self, vector_store: VectorStore, top_k: Optional[int] = None):
        """Initialize the retriever.
        
        Args:
            vector_store: VectorStore instance
            top_k: Number of documents to retrieve (defaults to config)
        """
        self.vector_store = vector_store
        self.top_k = top_k
        self._retriever = None
    
    def _get_retriever(self):
        """Get or create the LangChain retriever."""
        if self._retriever is None:
            self._retriever = self.vector_store.get_retriever(top_k=self.top_k)
        return self._retriever
    
    def retrieve(self, query: str) -> List[LangChainDocument]:
        """Retrieve relevant documents for a query.
        
        Args:
            query: User query string
            
        Returns:
            List of LangChain Document objects with content and metadata
        """
        retriever = self._get_retriever()
        # Use invoke() instead of get_relevant_documents() for newer LangChain versions
        docs = retriever.invoke(query)
        return docs
    
    def format_context(self, documents: List[LangChainDocument]) -> str:
        """Format retrieved documents into context string.
        
        Args:
            documents: List of retrieved LangChain Document objects
            
        Returns:
            Formatted context string with source citations
        """
        if not documents:
            return ""
        
        context_parts = []
        seen_sources = set()
        
        for i, doc in enumerate(documents, 1):
            content = doc.page_content.strip()
            metadata = doc.metadata
            
            # Get source information
            source = metadata.get("source", "Unknown")
            doc_type = metadata.get("doc_type", "general")
            
            # Create source identifier
            source_id = f"{source}"
            if source_id in seen_sources:
                # Already included this source, just add content
                context_parts.append(content)
            else:
                seen_sources.add(source_id)
                # Format with source header
                context_parts.append(f"[From {source}]\n{content}")
        
        return "\n\n---\n\n".join(context_parts)
    
    def retrieve_and_format(self, query: str) -> str:
        """Retrieve documents and format as context.
        
        Args:
            query: User query string
            
        Returns:
            Formatted context string
        """
        documents = self.retrieve(query)
        return self.format_context(documents)
    
    def get_sources(self, documents: List[LangChainDocument]) -> List[str]:
        """Extract unique source paths from documents.
        
        Args:
            documents: List of retrieved LangChain Document objects
            
        Returns:
            List of unique source paths
        """
        sources = set()
        for doc in documents:
            source = doc.metadata.get("source", "Unknown")
            sources.add(source)
        return sorted(list(sources))

