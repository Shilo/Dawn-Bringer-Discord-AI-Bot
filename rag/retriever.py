"""Semantic retrieval logic for RAG system."""

from typing import List, Optional, Tuple
import re
from langchain_core.documents import Document as LangChainDocument
from rag.vector_store import VectorStore
from rag.synonyms import SYNONYMS
from rag.utils import get_effective_threshold, is_cjk_query, extract_text_from_file
from rag.config import RAGConfig


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
    
    def _expand_header_only_chunk(self, doc: LangChainDocument) -> LangChainDocument:
        """Expand a chunk that is only a header to include following content.
        
        If a chunk contains only a markdown header (#, ##, ###) and no other content,
        this function reads the original file and expands the chunk to include content
        until it reaches a header of the same level or higher (same or fewer # symbols).
        
        Header hierarchy:
        - # (level 1) includes everything until next # header
        - ## (level 2) includes everything until next ## or # header
        - ### (level 3) includes everything until next ###, ##, or # header
        
        Args:
            doc: LangChain Document that may be header-only
            
        Returns:
            Expanded LangChain Document with additional content if needed
        """
        content = doc.page_content.strip()
        metadata = doc.metadata
        
        # Check if content is only a header (starts with #, ##, or ### and has no other lines)
        header_pattern = r'^(#+)\s+.+$'
        lines = content.split('\n')
        
        # Find the first header line and determine its level
        original_header_level = None
        is_header_only = False
        
        if len(lines) == 1:
            # Single line - check if it's a header
            match = re.match(header_pattern, content)
            if match:
                is_header_only = True
                original_header_level = len(match.group(1))  # Count # symbols
        else:
            # Multiple lines - check if all non-empty lines are headers
            non_empty_lines = [line.strip() for line in lines if line.strip()]
            if non_empty_lines:
                all_headers = all(re.match(header_pattern, line) for line in non_empty_lines)
                if all_headers:
                    is_header_only = True
                    # Get level from first header
                    match = re.match(header_pattern, non_empty_lines[0])
                    if match:
                        original_header_level = len(match.group(1))
        
        if not is_header_only or original_header_level is None:
            # Not a header-only chunk, return as-is
            return doc
        
        # Get file path from metadata
        # file_path is the relative path (e.g., "all-the-guides-topic/4. Classes Guide.md")
        # source is the same but without extension (e.g., "all-the-guides-topic/4. Classes Guide")
        file_path = metadata.get("file_path")
        if not file_path:
            # Try to construct from source
            source = metadata.get("source", "")
            if source:
                # Add .md extension if not already present
                if not source.endswith(('.md', '.txt')):
                    file_path = f"{source}.md"
                else:
                    file_path = source
            else:
                # Can't expand without file path
                return doc
        
        # Get start line from metadata
        start_line = None
        if isinstance(metadata.get("start_line"), (int, str)):
            try:
                start_line = int(metadata.get("start_line"))
            except (ValueError, TypeError):
                pass
        
        if not start_line:
            # Can't expand without start line
            return doc
        
        # Read the original file and expand the chunk
        full_path = RAGConfig.DOCS_DIR / file_path
        if not full_path.exists():
            return doc
        
        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                file_lines = f.readlines()
            
            # Start from the chunk's start line (1-indexed, convert to 0-indexed)
            current_line_idx = start_line - 1
            
            # Expand the chunk: include everything until we hit a header of the same level or higher
            # Higher level = fewer # symbols (e.g., # is higher than ##)
            expanded_lines = []
            
            # First, include the header itself
            if current_line_idx < len(file_lines):
                expanded_lines.append(file_lines[current_line_idx].rstrip())
                current_line_idx += 1
            
            # Now continue reading lines until we hit a header of the same level or higher
            while current_line_idx < len(file_lines):
                line = file_lines[current_line_idx]
                line_stripped = line.strip()
                
                # Handle empty/whitespace lines - include them and continue
                if not line_stripped:
                    expanded_lines.append('')
                    current_line_idx += 1
                    continue
                
                # Check if this line is a header
                header_match = re.match(header_pattern, line_stripped)
                if header_match:
                    # Found a header - check its level
                    header_level = len(header_match.group(1))  # Count # symbols
                    
                    # If this header is the same level or higher (fewer or equal # symbols),
                    # we've reached the end of this section - stop here
                    if header_level <= original_header_level:
                        break
                    
                    # This is a lower-level header (more # symbols), include it and continue
                    expanded_lines.append(line.rstrip())
                    current_line_idx += 1
                    continue
                
                # Not a header - include it (regular content)
                expanded_lines.append(line.rstrip())
                current_line_idx += 1
            
            # If we expanded beyond just the header, update the document
            if len(expanded_lines) > 1:
                # Remove trailing empty lines (from file ending with newline)
                while expanded_lines and expanded_lines[-1] == '':
                    expanded_lines.pop()
                
                expanded_content = '\n'.join(expanded_lines)
                # Trim trailing whitespace from each line and remove trailing newlines
                expanded_content = "\n".join(line.rstrip() for line in expanded_content.split("\n")).rstrip('\n')
                # current_line_idx is 0-indexed and points to the next line after the last included line
                # end_line should be 1-indexed, representing the last included line
                # The last included line is current_line_idx - 1 (0-indexed)
                # To convert to 1-indexed: (current_line_idx - 1) + 1 = current_line_idx
                # So end_line = current_line_idx
                end_line = current_line_idx
                
                # Update metadata with new end line
                new_metadata = metadata.copy()
                new_metadata["end_line"] = end_line
                
                # Create new document with expanded content
                return LangChainDocument(
                    page_content=expanded_content,
                    metadata=new_metadata
                )
            else:
                # Only had the header, no expansion needed (or no content found)
                # Still trim trailing whitespace from the original content
                trimmed_content = "\n".join(line.rstrip() for line in doc.page_content.split("\n"))
                if trimmed_content != doc.page_content:
                    new_metadata = metadata.copy()
                    return LangChainDocument(
                        page_content=trimmed_content,
                        metadata=new_metadata
                    )
                return doc
        
        except Exception as e:
            # If anything goes wrong, return original document
            print(f"⚠️ Warning: Could not expand header-only chunk from {file_path}: {e}")
        
        return doc
    
    def _expand_query_for_word_order(self, query: str) -> List[str]:
        """Expand query to handle word order variations for short queries.
        
        Generates multiple query variations to improve retrieval when word order matters.
        This helps with queries like "class best" vs "best class" or "best DB class" vs "best class DB".
        
        Works for languages with space-separated words (English, Spanish, French, etc.).
        For languages without word boundaries (Chinese, Japanese, Thai), returns original query only.
        
        Strategy:
        - 2 words: Try both orders
        - 3 words: Try original, reversed, and key variations (first-last swapped, etc.)
        - 4+ words: Try original and reversed (to avoid too many permutations)
        
        Args:
            query: Original query string
            
        Returns:
            List of query variations (original + word order variations)
        """
        words = query.strip().split()
        num_words = len(words)
        
        if num_words <= 1:
            # Single word or empty, no variations needed
            return [query]
        
        # Check if query has word boundaries (spaces)
        # If no spaces, likely a language without word boundaries (Chinese, Japanese, etc.)
        # In that case, just return original query
        if " " not in query.strip():
            return [query]
        
        variations = [query]  # Always include original
        
        if num_words == 2:
            # 2 words: try both orders
            variations.append(f"{words[1]} {words[0]}")
        
        elif num_words == 3:
            # 3 words: try several key variations
            # Original: A B C
            # Reversed: C B A
            # First-last swapped: C B A -> but also try: C A B
            # Middle variations: B A C, A C B
            variations.extend([
                f"{words[2]} {words[1]} {words[0]}",  # Reversed: C B A
                f"{words[2]} {words[0]} {words[1]}",  # C A B
                f"{words[1]} {words[0]} {words[2]}",  # B A C
                f"{words[0]} {words[2]} {words[1]}",  # A C B
            ])
        
        elif num_words == 4:
            # 4 words: try original, reversed, and a couple key variations
            variations.extend([
                " ".join(reversed(words)),  # Reversed: D C B A
                f"{words[3]} {words[0]} {words[1]} {words[2]}",  # D A B C (last-first swap)
                f"{words[0]} {words[2]} {words[1]} {words[3]}",  # A C B D (middle swap)
            ])
        
        else:
            # 5+ words: just try original and reversed to avoid too many variations
            variations.append(" ".join(reversed(words)))
        
        # Remove duplicates while preserving order
        seen = set()
        unique_variations = []
        for var in variations:
            if var not in seen:
                seen.add(var)
                unique_variations.append(var)
        
        return unique_variations
    
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
        
        # Expand header-only chunks to include following content
        expanded_docs = [self._expand_header_only_chunk(doc) for doc in docs]
        return expanded_docs
    
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
        
        # First expand synonyms (e.g., "DB" -> "Dawn Bringer")
        synonym_variations = self._expand_query_with_synonyms(query)
        
        # Then expand word order for each synonym variation
        query_variations = []
        for synonym_var in synonym_variations:
            word_order_vars = self._expand_query_for_word_order(synonym_var)
            query_variations.extend(word_order_vars)
        
        # Remove duplicates while preserving order
        seen = set()
        unique_variations = []
        for var in query_variations:
            var_lower = var.lower()
            if var_lower not in seen:
                seen.add(var_lower)
                unique_variations.append(var)
        
        query_variations = unique_variations
        
        # Detect if query might be in a language without spaces (Japanese, Chinese, Thai, etc.)
        # These languages typically have higher distance scores when querying English documents
        has_spaces = " " in query.strip()
        is_likely_cjk = is_cjk_query(query)
        
        # Default values for space-separated languages
        search_k = k * 2  # Normal expansion for space-separated languages
        effective_threshold = get_effective_threshold(query, score_threshold)
        
        # Adjust search_k for non-space languages or CJK characters (get more results)
        if not has_spaces or is_likely_cjk:
            search_k *= 2  # Double the search results for languages that might have higher distances
        
        # Search with all query variations and collect results
        # Use a dict to track best score for each document (by content)
        doc_scores = {}  # content_key -> (doc, best_score)
        
        for q in query_variations:
            # Use similarity_search_with_score to get scores
            # ChromaDB returns distance scores (lower = more similar)
            results = vector_store.similarity_search_with_score(q, k=search_k)
            
            # Track best score for each document
            for doc, score in results:
                content_key = doc.page_content.strip()  # Use content as identifier
                # Keep the best (lowest) score for each document
                if content_key not in doc_scores or score < doc_scores[content_key][1]:
                    doc_scores[content_key] = (doc, score)
        
        # Convert to list and sort by score (lower is better)
        all_results = list(doc_scores.values())
        all_results.sort(key=lambda x: x[1])
        
        # Filter by effective threshold (adjusted for cross-language queries if needed)
        if effective_threshold is not None:
            filtered_results = [(doc, score) for doc, score in all_results if score <= effective_threshold]
            
            # If threshold filtered out all results (common for cross-language queries),
            # return top k results anyway (they're still the best matches available)
            if not filtered_results and all_results:
                results = all_results[:k]
            else:
                results = filtered_results[:k]
        else:
            results = all_results[:k]
        
        # Expand header-only chunks to include following content
        expanded_results = []
        for doc, score in results:
            expanded_doc = self._expand_header_only_chunk(doc)
            expanded_results.append((expanded_doc, score))
        
        return expanded_results
    
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
            # Trim trailing whitespace from each line
            content = "\n".join(line.rstrip() for line in content.split("\n"))
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

