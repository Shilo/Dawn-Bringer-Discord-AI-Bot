"""Semantic retrieval logic for RAG system."""

from typing import List, Optional, Tuple
from langchain_core.documents import Document as LangChainDocument
from rag.vector_store import VectorStore
from rag.synonyms import SYNONYMS


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
    
    def _expand_query_with_synonyms(self, query: str) -> List[str]:
        """Expand query with common synonyms and abbreviations.
        
        Helps improve retrieval by including variations that might appear in documents.
        For example, "DB" -> "Dawn Bringer" or "Dawnbringer"
        
        Args:
            query: Original query string
            
        Returns:
            List of query variations (original + expanded versions)
        """
        query_lower = query.lower()
        variations = [query]  # Always include original
        
        # Check if query contains abbreviations and expand them
        for abbrev, expansions in SYNONYMS.items():
            if abbrev in query_lower:
                for expansion in expansions:
                    # Replace abbreviation with expansion
                    expanded = query_lower.replace(abbrev, expansion)
                    if expanded != query_lower:  # Only add if different
                        variations.append(expanded)
                    # Also try adding expansion alongside abbreviation
                    expanded_with = query_lower.replace(abbrev, f"{abbrev} {expansion}")
                    if expanded_with != query_lower and expanded_with not in variations:
                        variations.append(expanded_with)
        
        return variations
    
    def _get_retriever(self):
        """Get or create the LangChain retriever."""
        if self._retriever is None:
            self._retriever = self.vector_store.get_retriever(top_k=self.top_k)
        return self._retriever
    
    def retrieve(self, query: str, apply_threshold: bool = True) -> List[LangChainDocument]:
        """Retrieve relevant documents for a query.
        
        Args:
            query: User query string
            apply_threshold: If True, filter out chunks with distance scores above threshold
            
        Returns:
            List of LangChain Document objects with content and metadata
        """
        # If threshold is enabled, use retrieve_with_scores to filter
        if apply_threshold and self.vector_store.config.SCORE_THRESHOLD is not None:
            results = self.retrieve_with_scores(query, score_threshold=self.vector_store.config.SCORE_THRESHOLD)
            return [doc for doc, score in results]
        
        retriever = self._get_retriever()
        # Use invoke() instead of get_relevant_documents() for newer LangChain versions
        docs = retriever.invoke(query)
        return docs
    
    def retrieve_with_scores(self, query: str, score_threshold: Optional[float] = None) -> List[tuple[LangChainDocument, float]]:
        """Retrieve relevant documents with distance scores.
        
        Args:
            query: User query string
            score_threshold: Optional maximum distance threshold (chunks with distance > threshold are filtered out)
                           Lower distance = more relevant. Typical values: 1.0-1.5 for filtering
            
        Returns:
            List of tuples containing (Document, distance_score)
            Lower scores indicate better matches (ChromaDB returns distance, not similarity)
        """
        vector_store = self.vector_store.get_vector_store()
        if vector_store is None:
            raise ValueError("Vector store not initialized.")
        
        k = self.top_k or self.vector_store.config.TOP_K
        
        # Expand query with synonyms (e.g., "DB" -> "Dawn Bringer")
        query_variations = self._expand_query_with_synonyms(query)
        
        # Search with all query variations and collect results
        all_results = []
        seen_content = set()  # Track by content to avoid duplicates
        
        for q in query_variations:
            # Use similarity_search_with_score to get scores
            # ChromaDB returns distance scores (lower = more similar)
            results = vector_store.similarity_search_with_score(q, k=k * 2)  # Get more results to merge
            
            # Add results, avoiding duplicates (by content)
            for doc, score in results:
                content_key = doc.page_content.strip()  # Use content as identifier
                if content_key not in seen_content:
                    seen_content.add(content_key)
                    all_results.append((doc, score))
        
        # Sort by score (lower is better) and take top k
        all_results.sort(key=lambda x: x[1])
        results = all_results[:k]
        
        # Filter by threshold if provided
        if score_threshold is not None:
            results = [(doc, score) for doc, score in results if score <= score_threshold]
        
        return results
    
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

