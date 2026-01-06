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
        For example, "DB" -> "Dawn Bringer" or "Dawnbringer", "valk" -> "valkyrie" (handles "valks" -> "valkyries" automatically)
        
        Args:
            query: Original query string
            
        Returns:
            List of query variations (original + expanded versions)
        """
        import re
        query_lower = query.lower()
        variations = [query]  # Always include original
        
        # Check if query contains abbreviations and expand them
        # Sort by length (longest first) to handle plurals correctly (e.g., "valks" before "valk")
        sorted_synonyms = sorted(SYNONYMS.items(), key=lambda x: len(x[0]), reverse=True)
        
        for abbrev, expansions in sorted_synonyms:
            # Try exact word match with word boundaries first (most accurate)
            pattern = r'\b' + re.escape(abbrev) + r'\b'
            if re.search(pattern, query_lower):
                # Exact word match - replace with word boundary
                for expansion in expansions:
                    expanded = re.sub(pattern, expansion, query_lower)
                    if expanded != query_lower and expanded not in variations:
                        variations.append(expanded)
                    # Also try adding expansion alongside abbreviation
                    expanded_with = re.sub(pattern, f"{abbrev} {expansion}", query_lower)
                    if expanded_with != query_lower and expanded_with not in variations:
                        variations.append(expanded_with)
            elif abbrev in query_lower:
                # Partial match (for cases like "valk" in "valks" or short abbreviations)
                # Use simple string replacement for partial matches
                for expansion in expansions:
                    expanded = query_lower.replace(abbrev, expansion)
                    if expanded != query_lower and expanded not in variations:
                        variations.append(expanded)
                    # Also try adding expansion alongside abbreviation
                    expanded_with = query_lower.replace(abbrev, f"{abbrev} {expansion}")
                    if expanded_with != query_lower and expanded_with not in variations:
                        variations.append(expanded_with)
        
        return variations
    
    def _expand_small_chunk_in_section(self, doc: LangChainDocument) -> LangChainDocument:
        """Expand a small chunk that is part of a larger section.
        
        If a chunk is very small (less than 200 characters) and is clearly part of a section
        (has a header above it), expand it to include the full section content.
        
        This helps when small chunks match queries well but miss important context.
        
        Args:
            doc: LangChain Document that may be a small chunk in a section
            
        Returns:
            Expanded LangChain Document with full section if applicable
        """
        content = doc.page_content.strip()
        metadata = doc.metadata
        
        # Only expand if chunk is small (less than 200 chars) and has line numbers
        if len(content) >= 200:
            return doc
        
        # Get file path and start line from metadata
        file_path = metadata.get("file_path")
        if not file_path:
            source = metadata.get("source", "")
            if source:
                if not source.endswith(('.md', '.txt')):
                    file_path = f"{source}.md"
                else:
                    file_path = source
            else:
                return doc
        
        start_line = None
        if isinstance(metadata.get("start_line"), (int, str)):
            try:
                start_line = int(metadata.get("start_line"))
            except (ValueError, TypeError):
                pass
        
        if not start_line:
            return doc
        
        # Read the original file
        full_path = RAGConfig.DOCS_DIR / file_path
        if not full_path.exists():
            return doc
        
        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                file_lines = f.readlines()
            
            # Look backwards to find the section header
            # Start from the chunk's start line (1-indexed, convert to 0-indexed)
            current_line_idx = start_line - 1
            
            # Find the section header (## or ###) that this chunk belongs to
            section_start_idx = None
            section_header_level = None
            
            # Look backwards from the chunk to find the nearest header
            for i in range(current_line_idx, -1, -1):
                if i >= len(file_lines):
                    continue
                line = file_lines[i].strip()
                header_match = re.match(r'^(#+)\s+.+$', line)
                if header_match:
                    section_start_idx = i
                    section_header_level = len(header_match.group(1))
                    break
            
            # If we found a section header, expand to include the full section
            if section_start_idx is not None:
                # Find where this section ends (next header of same or higher level)
                section_end_idx = len(file_lines)
                
                for i in range(section_start_idx + 1, len(file_lines)):
                    line = file_lines[i].strip()
                    if not line:
                        continue
                    
                    header_match = re.match(r'^(#+)\s+.+$', line)
                    if header_match:
                        header_level = len(header_match.group(1))
                        # If this header is the same level or higher, we've reached the end
                        if header_level <= section_header_level:
                            section_end_idx = i
                            break
                
                # Build expanded content
                expanded_lines = []
                for i in range(section_start_idx, section_end_idx):
                    if i < len(file_lines):
                        expanded_lines.append(file_lines[i].rstrip())
                
                # Remove trailing empty lines
                while expanded_lines and expanded_lines[-1] == '':
                    expanded_lines.pop()
                
                if len(expanded_lines) > 1:
                    expanded_content = '\n'.join(expanded_lines)
                    end_line = section_start_idx + len(expanded_lines)
                    
                    # Only expand if the expanded content is significantly larger
                    # (at least 2x the original, or more than 300 chars)
                    if len(expanded_content) > max(len(content) * 2, 300):
                        new_metadata = metadata.copy()
                        new_metadata["start_line"] = section_start_idx + 1
                        new_metadata["end_line"] = end_line
                        
                        return LangChainDocument(
                            page_content=expanded_content,
                            metadata=new_metadata
                        )
        
        except Exception as e:
            # If anything goes wrong, return original document
            print(f"⚠️ Warning: Could not expand small chunk from {file_path}: {e}")
        
        return doc
    
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
                # Calculate end_line based on actual number of lines included
                # start_line is 1-indexed, and we included len(expanded_lines) lines
                # So end_line = start_line + len(expanded_lines) - 1
                end_line = start_line + len(expanded_lines) - 1
                
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
                return doc
        
        except Exception as e:
            # If anything goes wrong, return original document
            print(f"⚠️ Warning: Could not expand header-only chunk from {file_path}: {e}")
        
        return doc
    
    def _prioritize_comprehensive_chunks(self, results: List[Tuple[LangChainDocument, float]], 
                                         all_results: List[Tuple[LangChainDocument, float]], 
                                         k: int) -> List[Tuple[LangChainDocument, float]]:
        """Prioritize more comprehensive chunks when multiple chunks from same document are retrieved.
        
        When multiple chunks from the same source document are retrieved, this function:
        1. Groups chunks by source document
        2. For each document, prefers chunks that:
           - Start earlier in the document (likely include main headers)
           - Are larger (more comprehensive)
           - Have the best score
        3. If a small chunk (< 200 chars) is in results, also check all_results for
           better chunks from the same document that start earlier
        
        Args:
            results: List of (Document, score) tuples (already expanded)
            all_results: List of all (Document, score) tuples from search (before filtering)
            k: Maximum number of results to return
            
        Returns:
            List of prioritized (Document, score) tuples
        """
        if len(results) <= k:
            # Still check if we should replace small chunks with better ones from same document
            results = self._replace_small_chunks_with_better_ones(results, all_results)
            return results[:k]
        
        # Group chunks by source document
        chunks_by_source = {}  # source -> list of (doc, score, start_line, size)
        
        for doc, score in results:
            source = doc.metadata.get("source", "unknown")
            start_line = None
            if isinstance(doc.metadata.get("start_line"), (int, str)):
                try:
                    start_line = int(doc.metadata.get("start_line"))
                except (ValueError, TypeError):
                    pass
            
            size = len(doc.page_content)
            
            if source not in chunks_by_source:
                chunks_by_source[source] = []
            chunks_by_source[source].append((doc, score, start_line or 999999, size))
        
        # For each source, if multiple chunks, prefer the best one
        prioritized = []
        
        # Process each source and pick the best chunk
        for source, source_chunks in chunks_by_source.items():
            if len(source_chunks) > 1:
                # Multiple chunks from same source - pick the best one
                # Prefer: earlier start line, larger size, better score
                best_chunk = min(source_chunks, key=lambda x: (
                    x[2],  # start_line (earlier is better)
                    -x[3],  # size (larger is better, so negate)
                    x[1]    # score (lower is better)
                ))
                prioritized.append((best_chunk[0], best_chunk[1]))
            else:
                # Only one chunk from this source - but check if it's a small chunk
                # that should be replaced with a better one from all_results
                doc, score, start_line, size = source_chunks[0]
                if size < 200:
                    # Small chunk - check if there's a better one from same document in all_results
                    better_chunk = self._find_better_chunk_from_same_doc(doc, score, all_results)
                    if better_chunk:
                        prioritized.append(better_chunk)
                    else:
                        prioritized.append((doc, score))
                else:
                    prioritized.append((doc, score))
        
        # Sort by score again (lower is better)
        prioritized.sort(key=lambda x: x[1])
        
        # Return top k
        return prioritized[:k]
    
    def _replace_small_chunks_with_better_ones(self, results: List[Tuple[LangChainDocument, float]], 
                                               all_results: List[Tuple[LangChainDocument, float]]) -> List[Tuple[LangChainDocument, float]]:
        """Replace small chunks in results with better chunks from same document if available.
        
        Args:
            results: Current results
            all_results: All search results to check
            
        Returns:
            Updated results with small chunks potentially replaced
        """
        updated_results = []
        for doc, score in results:
            size = len(doc.page_content)
            if size < 200:
                # Small chunk - check for better one
                better_chunk = self._find_better_chunk_from_same_doc(doc, score, all_results)
                if better_chunk:
                    updated_results.append(better_chunk)
                else:
                    updated_results.append((doc, score))
            else:
                updated_results.append((doc, score))
        return updated_results
    
    def _find_better_chunk_from_same_doc(self, small_chunk: LangChainDocument, small_score: float,
                                        all_results: List[Tuple[LangChainDocument, float]]) -> Optional[Tuple[LangChainDocument, float]]:
        """Find a better chunk from the same document that starts earlier.
        
        Args:
            small_chunk: The small chunk to potentially replace
            small_score: Score of the small chunk
            all_results: All search results to check
            
        Returns:
            Better chunk from same document if found, None otherwise
        """
        source = small_chunk.metadata.get("source", "unknown")
        small_start_line = None
        if isinstance(small_chunk.metadata.get("start_line"), (int, str)):
            try:
                small_start_line = int(small_chunk.metadata.get("start_line"))
            except (ValueError, TypeError):
                pass
        
        if not small_start_line:
            return None
        
        # Look for chunks from same document that start earlier
        best_chunk = None
        best_score = small_score
        
        for doc, score in all_results:
            if doc.metadata.get("source") != source:
                continue
            
            # Check if this chunk starts earlier
            start_line = None
            if isinstance(doc.metadata.get("start_line"), (int, str)):
                try:
                    start_line = int(doc.metadata.get("start_line"))
                except (ValueError, TypeError):
                    pass
            
            if start_line and start_line < small_start_line:
                # This chunk starts earlier - prefer it if it's not too much worse in score
                # Allow up to 0.3 worse score if it starts significantly earlier (within first 10 lines)
                score_penalty = score - small_score
                if start_line <= 10 and score_penalty <= 0.3:
                    if best_chunk is None or (start_line < best_chunk[1] or (start_line == best_chunk[1] and score < best_chunk[2])):
                        best_chunk = (doc, start_line, score)
        
        if best_chunk:
            doc, _, score = best_chunk
            # Expand the chunk before returning
            expanded_doc = self._expand_header_only_chunk(doc)
            expanded_doc = self._expand_small_chunk_in_section(expanded_doc)
            return (expanded_doc, score)
        return None
    
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
    
    def retrieve(self, query: str, apply_threshold: bool = True, top_k_override: Optional[int] = None, score_threshold_override: Optional[float] = None) -> List[LangChainDocument]:
        """Retrieve relevant documents for a query.
        
        Args:
            query: User query string
            apply_threshold: If True, filter out chunks with distance scores above threshold
            top_k_override: Optional override for top_k (temporary, doesn't change instance setting)
            score_threshold_override: Optional override for score threshold (temporary, doesn't change global setting)
            
        Returns:
            List of LangChain Document objects with content and metadata
        """
        # If threshold is enabled, use retrieve_with_scores to filter
        threshold_to_use = score_threshold_override if score_threshold_override is not None else self.vector_store.config.SCORE_THRESHOLD
        if apply_threshold and threshold_to_use is not None:
            results = self.retrieve_with_scores(query, score_threshold=threshold_to_use, top_k_override=top_k_override)
            return [doc for doc, score in results]
        
        # Temporarily override top_k if provided
        original_top_k = self.top_k
        original_retriever = self._retriever
        if top_k_override is not None:
            self.top_k = top_k_override
            # Clear cached retriever so it uses the new top_k
            self._retriever = None
        
        try:
            retriever = self._get_retriever()
            # Use invoke() instead of get_relevant_documents() for newer LangChain versions
            docs = retriever.invoke(query)
        finally:
            # Restore original top_k and retriever if it was overridden
            if top_k_override is not None:
                self.top_k = original_top_k
                self._retriever = original_retriever
        
        # Expand header-only chunks and small chunks in sections
        expanded_docs = []
        for doc in docs:
            expanded_doc = self._expand_header_only_chunk(doc)
            expanded_doc = self._expand_small_chunk_in_section(expanded_doc)
            expanded_docs.append(expanded_doc)
        return expanded_docs
    
    def retrieve_with_scores(self, query: str, score_threshold: Optional[float] = None, top_k_override: Optional[int] = None) -> List[tuple[LangChainDocument, float]]:
        """Retrieve relevant documents with distance scores.
        
        Args:
            query: User query string
            score_threshold: Optional maximum distance threshold (chunks with distance > threshold are filtered out)
                           Lower distance = more relevant. Typical values: 1.0-1.5 for filtering
            top_k_override: Optional override for top_k (temporary, doesn't change instance setting)
            
        Returns:
            List of tuples containing (Document, distance_score)
            Lower scores indicate better matches (ChromaDB returns distance, not similarity)
        """
        vector_store = self.vector_store.get_vector_store()
        if vector_store is None:
            raise ValueError("Vector store not initialized.")
        
        k = top_k_override if top_k_override is not None else (self.top_k or self.vector_store.config.TOP_K)
        
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
        
        # Expand header-only chunks and small chunks in sections
        expanded_results = []
        for doc, score in results:
            # First expand header-only chunks
            expanded_doc = self._expand_header_only_chunk(doc)
            # Then expand small chunks that are part of larger sections
            expanded_doc = self._expand_small_chunk_in_section(expanded_doc)
            expanded_results.append((expanded_doc, score))
        
        # Post-process: if multiple chunks from same document, prefer larger/more comprehensive ones
        # Also check all_results for better chunks from same documents
        expanded_results = self._prioritize_comprehensive_chunks(expanded_results, all_results, k)
        
        return expanded_results
    
    def format_context(self, documents: List[LangChainDocument], number_sources: bool = False) -> str:
        """Format retrieved documents into context string.
        
        Args:
            documents: List of retrieved LangChain Document objects
            number_sources: If True, number each source (Source 1, Source 2, etc.) for citation tracking
            
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
            if number_sources:
                # Number each document chunk individually for citation tracking
                context_parts.append(f"[Source {i}: {source}]\n{content}")
            else:
                # Original behavior: group by source
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

