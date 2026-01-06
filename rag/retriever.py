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
    
    def __init__(self, vector_store: VectorStore, top_k: Optional[int] = None, verbose: bool = False):
        """Initialize the retriever.
        
        Args:
            vector_store: VectorStore instance
            top_k: Number of documents to retrieve (defaults to config)
            verbose: If True, enable verbose logging for debugging (default: False)
        """
        self.vector_store = vector_store
        self.top_k = top_k
        self.verbose = verbose
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
        query_lower = query.lower()  # Query should already be lowercase, but ensure it is
        variations = [query_lower]  # Always include the query (already lowercase)
        
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
                # IMPORTANT: For very short abbreviations (2 chars or less), only match at word boundaries
                # to avoid false matches like "ul" in "should"
                if len(abbrev) <= 2:
                    # Skip partial matches for very short abbreviations to avoid false positives
                    continue
                
                # IMPORTANT: Check if the expansion already contains the abbrev to avoid "valkyrie" -> "valkyrieyrie"
                # Only do partial replacement if the expansion doesn't already contain the abbrev
                for expansion in expansions:
                    expansion_lower = expansion.lower()
                    # Skip if expansion already contains the abbrev (e.g., "valkyrie" already contains "valk")
                    if abbrev in expansion_lower and expansion_lower != abbrev:
                        continue
                    
                    # Use simple string replacement for partial matches
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
            if self.verbose:
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
            if self.verbose:
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
        # Always prioritize to ensure we get the best chunks from each source
        # This helps prevent multiple low-quality chunks from the same source dominating results

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

        # For each source, select chunks (prioritize comprehensive content but maintain count when possible)
        prioritized = []

        # Count total input chunks to ensure we don't reduce below k unnecessarily
        total_input_chunks = len(results)

        # First, collect all chunks with their priority scores
        all_candidates = []
        for source, source_chunks in chunks_by_source.items():
            if len(source_chunks) > 1:
                # Multiple chunks from same source - pick the best ones
                # Sort by score (lower is better), then by start_line, then by size
                sorted_chunks = sorted(source_chunks, key=lambda x: (x[1], x[2], -x[3]))

                # If we need to maintain count, take more chunks from sources with multiples
                max_per_source = 2 if total_input_chunks >= k else min(len(sorted_chunks), 3)
                for chunk in sorted_chunks[:max_per_source]:
                    all_candidates.append((chunk[0], chunk[1], source))
            else:
                # Only one chunk from this source
                doc, score, start_line, size = source_chunks[0]
                if size < 200:
                    # Small chunk - check if there's a better one from same document in all_results
                    better_chunk = self._find_better_chunk_from_same_doc(doc, score, all_results)
                    if better_chunk:
                        all_candidates.append((better_chunk[0], better_chunk[1], source))
                    else:
                        all_candidates.append((doc, score, source))
                else:
                    all_candidates.append((doc, score, source))

        # Sort all candidates by score (lower is better)
        all_candidates.sort(key=lambda x: x[1])

        # Ensure we maintain at least k chunks when we started with k or more
        num_to_take = k if len(all_candidates) >= k else len(all_candidates)
        prioritized = [(doc, score) for doc, score, source in all_candidates[:num_to_take]]

        if self.verbose:
            print(f"\n🔄 [PRIORITIZATION] Selected {len(prioritized)} chunks from {len(all_candidates)} candidates (k={k})")

        # If we have more results than needed, prioritize FAQ and guide content
        if len(prioritized) > k:
            # Boost FAQ content to ensure important answers appear first
            boosted_prioritized = []
            for doc, score in prioritized:
                boosted_score = score
                source = doc.metadata.get("source", "").lower()

                # Give slight preference to FAQ content
                if "faq" in source:
                    boosted_score = max(0.0, score - 0.05)  # Small boost

                boosted_prioritized.append((doc, boosted_score))

            # Sort by boosted score
            boosted_prioritized.sort(key=lambda x: x[1])
            prioritized = boosted_prioritized

        # Sort by score (lower is better)
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
    
    def _get_singular_form(self, query: str) -> str:
        """Get the singular form of a query by applying plural-to-singular conversion.

        Args:
            query: Query string

        Returns:
            Singular form of the query
        """
        words = query.split()
        if len(words) <= 1:
            return query

        singular_words = []
        for word in words:
            word_lower = word.lower()
            singular_word = word  # Default: keep original

            # Apply the same singularization logic as in _expand_query_for_plurals
            # Pattern 1: words ending in 'ies' -> 'y' or 'ie'
            if word_lower.endswith('ies') and len(word_lower) > 3:
                base = word[:-3]  # Remove 'ies'
                if base.lower().endswith('r'):
                    singular_word = base + 'ie'
                else:
                    singular_word = base + 'y'
            # Pattern 2: words ending in 'es' (but not 'ies')
            elif word_lower.endswith('es') and not word_lower.endswith('ies') and len(word_lower) > 2:
                singular_word = word[:-2]  # Remove 'es'
            # Pattern 3: words ending in 's' (but not 'es'/'ies' and not vowel+s)
            elif (word_lower.endswith('s') and
                  not word_lower.endswith(('es', 'ies', 'us', 'is', 'as', 'os')) and
                  len(word_lower) > 1 and
                  word_lower[-2] not in 'aeiou'):
                singular_word = word[:-1]  # Remove 's'

            singular_words.append(singular_word)

        return ' '.join(singular_words)

    def _expand_query_for_plurals(self, query: str) -> List[str]:
        """Expand query to include both singular and plural forms of words.
        
        This helps match queries like "valkyries" with documents containing "Valkyrie"
        and vice versa. Handles common English pluralization rules.
        
        Args:
            query: Original query string
            
        Returns:
            List of query variations (original + plural/singular variations)
        """
        import re
        words = query.strip().split()
        if len(words) <= 1:
            return [query]
        
        variations = [query]  # Always include original
        query_lower = query.lower()
        
        # Common pluralization patterns (order matters - more specific first)
        # Pattern: (regex_pattern, replacement)
        plural_to_singular = [
            (r'\b(\w+)ies\b', r'\1y'),      # valkyries -> valkyrie, cities -> city
            (r'\b(\w+)es\b', r'\1'),        # boxes -> box, classes -> class
            (r'\b(\w+[^aeiou])s\b', r'\1'), # valks -> valk, cats -> cat (avoid words ending in vowel+s like "was")
        ]
        
        # Common stop words and short words that shouldn't be pluralized
        stop_words = {'i', 'a', 'an', 'the', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
                     'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'should', 'could',
                     'can', 'may', 'might', 'must', 'what', 'when', 'where', 'who', 'why', 'how',
                     'this', 'that', 'these', 'those', 'to', 'of', 'in', 'on', 'at', 'by', 'for',
                     'with', 'from', 'as', 'if', 'or', 'and', 'but', 'so', 'use', 'get', 'got'}
        
        singular_to_plural = [
            (r'\b(\w+[^aeiou])y\b', r'\1ies'),  # valkyrie -> valkyries, city -> cities
            (r'\b(\w+[cs]h)\b', r'\1es'),       # wish -> wishes, match -> matches (words ending in ch, sh)
            (r'\b(\w+)x\b', r'\1es'),           # box -> boxes (words ending in x)
            (r'\b(\w+)z\b', r'\1es'),           # quiz -> quizzes (words ending in z)
            # Only pluralize words that are 4+ chars, don't end in s/x/z, and not stop words
            # Use negative lookbehind to ensure last char before boundary is not a/e/i/o/u/s/x/z
            (r'\b(\w{4,})(?<![aeiousxz])\b', r'\1s'),   # valk -> valks (only words 4+ chars)
        ]
        
        # Helper function to check if a word is already plural
        def is_plural(word):
            word_lower = word.lower()
            # Skip stop words (they might end in 's' but aren't plurals)
            if word_lower in stop_words:
                return False
            # Check if word ends in common plural endings (s, es, ies)
            if len(word_lower) > 2:
                if word_lower.endswith('ies'):
                    return True
                if word_lower.endswith('es'):
                    return True
                if word_lower.endswith('s') and not word_lower.endswith(('us', 'is', 'as', 'os')):
                    return True
            return False
        
        # Try converting plurals to singular
        # Process word by word to ensure only the most specific pattern applies
        words = query.split()
        singular_words = []
        for word in words:
            word_lower = word.lower()
            singular_word = word  # Default: keep original
            
            # Apply patterns in order (most specific first)
            # Pattern 1: words ending in 'ies' -> 'y' or 'ie' (valkyries -> valkyrie, cities -> city)
            if word_lower.endswith('ies') and len(word_lower) > 3:
                base = word[:-3]  # Remove 'ies'
                # Special case: if base ends in 'r' (like 'valkyr'), use 'ie' instead of 'y'
                # This handles words like "valkyries" -> "valkyrie"
                if base.lower().endswith('r'):
                    singular_word = base + 'ie'
                else:
                    singular_word = base + 'y'
            # Pattern 2: words ending in 'es' (but not 'ies') -> remove 'es' (boxes -> box)
            elif word_lower.endswith('es') and not word_lower.endswith('ies') and len(word_lower) > 2:
                singular_word = word[:-2]  # Remove 'es'
            # Pattern 3: words ending in 's' (but not 'es'/'ies' and not vowel+s) -> remove 's' (valks -> valk)
            elif (word_lower.endswith('s') and 
                  not word_lower.endswith(('es', 'ies', 'us', 'is', 'as', 'os')) and
                  len(word_lower) > 1 and
                  word_lower[-2] not in 'aeiou'):
                singular_word = word[:-1]  # Remove 's'
            
            singular_words.append(singular_word)
        
        singular_query = ' '.join(singular_words)
        if singular_query.lower() != query_lower and singular_query.lower() not in [v.lower() for v in variations]:
            variations.append(singular_query)
        
        # Try converting singular to plural (but skip stop words, short words, and words already plural)
        for pattern, replacement in singular_to_plural:
            def pluralize_match(match):
                word = match.group(0)  # Full matched word
                word_lower = word.lower()
                # Skip if it's a stop word or already plural (length check redundant - pattern requires 4+ chars)
                if word_lower in stop_words or is_plural(word):
                    return word
                # Apply the pluralization pattern
                try:
                    if r'\1ies' in replacement:
                        # Pattern: (\w+[^aeiou])y -> \1ies
                        base = match.group(1)
                        return base + 'ies'
                    elif r'\1es' in replacement:
                        # Pattern: (\w+[cs]h), (\w+)x, or (\w+)z -> \1es
                        base = match.group(1)
                        return base + 'es'
                    elif r'\1s' in replacement:
                        # Pattern: (\w{4,}[^aeiousxz]) -> \1s
                        base = match.group(1)
                        return base + 's'
                except (IndexError, AttributeError):
                    # If group doesn't exist, return word unchanged
                    return word
                return word
            
            plural_query = re.sub(pattern, pluralize_match, query, flags=re.IGNORECASE)
            # Only add if it's different and not already in variations
            if plural_query.lower() != query_lower and plural_query.lower() not in [v.lower() for v in variations]:
                variations.append(plural_query)
        
        return variations
    
    def _expand_query_semantically(self, query: str) -> List[str]:
        """Expand query with semantic intent recognition for common patterns.

        Maps short, informal queries to more complete questions or topics that are likely
        to match relevant content. This helps bridge the gap between how users ask questions
        and how documentation is structured.

        Examples:
        - "best valk" -> "what valkyrie should i use", "valkyrie tier list"
        - "good team" -> "what team should i use", "recommended team"
        - "f2p" -> "free to play guide", "free to play valkyries"

        Args:
            query: Original query string

        Returns:
            List of semantic query expansions (original + expanded versions)
        """
        query_lower = query.lower().strip()
        variations = [query_lower]  # Always include original

        # Define semantic mappings (query patterns -> expanded queries)
        # These are designed to bridge common user queries to actual document content
        semantic_mappings = {
            # Valkyrie-related queries
            "best valk": ["what valkyrie should i use", "valkyrie tier list", "best valkyrie"],
            "good valk": ["what valkyrie should i use", "valkyrie recommendations"],
            "valk tier": ["valkyrie tier list"],
            "top valk": ["valkyrie tier list", "best valkyrie"],

            # Team-related queries
            "best team": ["what team should i use", "recommended team", "best lineup"],
            "good team": ["what team should i use", "recommended team"],
            "f2p team": ["free to play team", "f2p valkyrie lineup"],

            # General game queries
            "beginner": ["beginner guide", "getting started"],
            "new player": ["beginner guide", "new player guide"],
            "f2p": ["free to play guide", "free to play valkyries"],
            "p2w": ["pay to win guide", "pay to win valkyries"],

            # Specific game modes
            "raid": ["raid guide", "raid valkyries"],
            "arena": ["arena guide", "arena valkyries", "pvp guide"],
            "corridor": ["corridor guide", "dimensional corridor"],
            "simulation": ["simulation guide", "digital simulation"],

            # Character queries
            "db": ["dawn bringer guide", "dawnbringer"],
            "dawnbringer": ["dawn bringer guide", "db guide"],
        }

        # Check for exact matches first (most reliable)
        if query_lower in semantic_mappings:
            variations.extend(semantic_mappings[query_lower])
        else:
            # Check for partial matches (more flexible but less precise)
            for pattern, expansions in semantic_mappings.items():
                if pattern in query_lower:
                    # Only add if it provides meaningful expansion
                    for expansion in expansions:
                        if expansion not in variations and len(expansion) > len(query_lower):
                            variations.append(expansion)

        # Remove duplicates while preserving order
        seen = set()
        unique_variations = []
        for var in variations:
            if var not in seen:
                seen.add(var)
                unique_variations.append(var)

        return unique_variations

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
        
        # Normalize query to lowercase first (embeddings are case-insensitive, so this avoids duplicate processing)
        query_normalized = query.lower()
        
        # First apply semantic expansion to recognize intent (e.g., "best valk" -> "what valkyrie should i use")
        # This provides the most meaningful expansion for short, informal queries
        semantic_variations = self._expand_query_semantically(query_normalized)
        if self.verbose and len(semantic_variations) > 1:
            print(f"\n🧠 [QUERY EXPANSION] Semantic expansion: {semantic_variations}")

        # Then normalize plurals (e.g., "valks" -> "valk") so synonyms can match exact word boundaries
        # This ensures "valk" matches exactly rather than as a partial match in "valks"
        normalized_variations = []
        for semantic_var in semantic_variations:
            plural_vars = self._expand_query_for_plurals(semantic_var)
            normalized_variations.extend(plural_vars)
        if self.verbose and len(normalized_variations) > len(semantic_variations):
            print(f"🔄 [QUERY EXPANSION] Plural normalization: {normalized_variations}")

        # Then expand synonyms on normalized forms (e.g., "valk" -> "valkyrie")
        # Synonyms will now match "valk" exactly (word boundary) instead of partial match in "valks"
        synonym_variations = []
        for normalized_var in normalized_variations:
            synonym_vars = self._expand_query_with_synonyms(normalized_var)
            synonym_variations.extend(synonym_vars)
        if self.verbose and len(synonym_variations) > len(normalized_variations):
            print(f"📝 [QUERY EXPANSION] After synonym expansion: {synonym_variations}")

        # Then expand word order for each synonym variation (prioritize semantically distinct variations)
        query_variations = []
        for synonym_var in synonym_variations:
            word_order_vars = self._expand_query_for_word_order(synonym_var)
            query_variations.extend(word_order_vars)
        if self.verbose:
            print(f"🔀 [QUERY EXPANSION] After word order expansion: {len(query_variations)} variations")
        
        # Note: We skip adding plural forms back - embeddings handle singular/plural similarity well (0.85-0.95)
        # The initial plural normalization is kept to help synonyms match exact word boundaries
        
        # Remove duplicates and prioritize variations (original query first, then semantic variations)
        seen = set()
        unique_variations = []
        prioritized_variations = []

        # First, add the original normalized query (highest priority)
        original_normalized = normalized_variations[0] if normalized_variations else query_normalized
        if original_normalized not in seen:
            seen.add(original_normalized)
            prioritized_variations.append(original_normalized)

        # Then add other normalized variations (singular/plural)
        for var in normalized_variations[1:]:
            var_lower = var.lower()
            if var_lower not in seen:
                seen.add(var_lower)
                prioritized_variations.append(var_lower)

        # Then add synonym variations
        for var in synonym_variations:
            var_lower = var.lower()
            if var_lower not in seen:
                seen.add(var_lower)
                prioritized_variations.append(var_lower)

        # Finally add word order variations (lowest priority, limit to avoid noise)
        word_order_limit = 6  # Limit word order variations to prevent too many
        word_order_count = 0
        for var in query_variations:
            if var not in seen and word_order_count < word_order_limit:
                seen.add(var)
                prioritized_variations.append(var)
                word_order_count += 1

        unique_variations = prioritized_variations
        
        query_variations = unique_variations
        if self.verbose:
            print(f"✅ [QUERY EXPANSION] Final unique variations ({len(query_variations)}): {query_variations[:10]}{'...' if len(query_variations) > 10 else ''}")
        
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
        
        if self.verbose:
            print(f"\n🔍 [SEARCH DEBUG] Searching with k={k}, search_k={search_k}, threshold={effective_threshold}")
        
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
            
            # Log top results for this query variation
            if self.verbose and results:
                top_score = results[0][1]
                source = results[0][0].metadata.get("source", "Unknown")
                print(f"  Query: '{q}' → Top result: [{source}] (score: {top_score:.3f})")
        
        # Convert to list and sort by score (lower is better)
        all_results = list(doc_scores.values())
        
        # Boost FAQ chunks that match the query structure (especially headers)
        # Enhanced to recognize intent patterns and semantic matches
        import re

        # Get semantic variations for better FAQ matching
        semantic_variations = self._expand_query_semantically(query_normalized)
        all_query_words = set()
        for var in semantic_variations:
            all_query_words.update(var.split())
        all_query_words.update(query_normalized.split())

        # Get the normalized (singular) form of the query for comparison
        singular_query = self._get_singular_form(query_normalized)
        normalized_query_words = set(singular_query.split())
        query_words = set(query_normalized.split())

        # Define intent patterns that should strongly boost certain FAQs
        intent_patterns = {
            # Valkyrie-related intents
            frozenset(['best', 'valk', 'valkyrie']): ['what valkyrie should i use', 'valkyrie recommendations'],
            frozenset(['good', 'valk', 'valkyrie']): ['what valkyrie should i use', 'valkyrie recommendations'],
            frozenset(['top', 'valk', 'valkyrie']): ['valkyrie tier list', 'what valkyrie should i use'],
            frozenset(['valkyrie', 'tier', 'list']): ['valkyrie tier list'],

            # Team-related intents
            frozenset(['best', 'team']): ['what team should i use', 'recommended team'],
            frozenset(['good', 'team']): ['what team should i use', 'recommended team'],
            frozenset(['f2p', 'team']): ['free to play team', 'f2p valkyrie lineup'],
        }

        # Check if query matches any intent patterns
        matched_intents = set()
        query_word_set = set(query_normalized.split())
        for pattern, intents in intent_patterns.items():
            if pattern.issubset(query_word_set):
                matched_intents.update(intents)

        boosted_results = []
        for doc, score in all_results:
            boosted_score = score
            source = doc.metadata.get("source", "").lower()
            content = doc.page_content.lower()

            # Check if this is a FAQ chunk
            if "faq" in source:
                # Extract potential header from content (first line or line starting with #)
                header_match = re.search(r'^(?:#+\s*)?(.+?)(?:\n|$)', content, re.MULTILINE)
                if header_match:
                    header_text = header_match.group(1).strip()
                    # Remove markdown formatting, links, emojis
                    header_text = re.sub(r':\w+:', '', header_text)  # Remove emoji
                    header_text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', header_text)  # Remove links
                    header_text = re.sub(r'\*\*(.*?)\*\*', r'\1', header_text)  # Remove bold
                    header_text = re.sub(r'__(.*?)__', r'\1', header_text)  # Remove bold
                    header_text = re.sub(r'\*(.*?)\*', r'\1', header_text)  # Remove italic
                    header_text = re.sub(r'_(.*?)_', r'\1', header_text)  # Remove italic
                    header_text = header_text.strip()
                    header_lower = header_text.lower()
                    header_words = set(header_lower.split())

                    # Check for intent-based matching first (highest priority)
                    intent_boost = 0.0
                    for intent in matched_intents:
                        if intent.lower() in header_lower:
                            intent_boost = 0.25  # Strong boost for intent matches
                            break

                    # Check similarity between header and all query variations
                    matching_words = 0
                    total_query_words = len(all_query_words)

                    # Create a mapping of plural -> singular for better matching
                    plural_to_singular = {}
                    for qw in all_query_words:
                        singular = self._get_singular_form(qw) if qw != self._get_singular_form(qw) else qw
                        plural_to_singular[qw] = singular

                    for qw in all_query_words:
                        if qw in header_words:
                            matching_words += 1
                        else:
                            # Check if singular form matches
                            singular_qw = plural_to_singular.get(qw, qw)
                            if singular_qw in header_words:
                                matching_words += 1

                    # If header closely matches query structure (high word overlap), boost it
                    word_match_ratio = matching_words / max(total_query_words, 1)
                    header_boost = 0.0
                    if word_match_ratio >= 0.5 and matching_words >= 2:
                        # Boost by reducing score (lower = better)
                        header_boost = min(0.2, word_match_ratio * 0.3)

                    # Apply the stronger of intent boost or header boost
                    total_boost = max(intent_boost, header_boost)
                    if total_boost > 0:
                        boosted_score = max(0.0, score - total_boost)
                        if self.verbose and boosted_score < score:
                            boost_reason = "intent match" if intent_boost > header_boost else f"header match ({matching_words}/{total_query_words} words)"
                            print(f"  📋 [FAQ BOOST] {source}: {score:.3f} → {boosted_score:.3f} ({boost_reason}) - header: '{header_text[:50]}...'")
            
            boosted_results.append((doc, boosted_score))
        
        # Boost tier list and guide content for relevant queries
        # This helps queries like "best valk" find the valkyrie tier list documents
        tier_list_boosted_results = []
        for doc, score in boosted_results:
            tier_boosted_score = score
            source = doc.metadata.get("source", "").lower()

            # Check if this document should be boosted for valkyrie-related queries
            is_valkyrie_related = any(word in query_normalized for word in ['valk', 'valkyrie'])
            is_tier_related = any(word in query_normalized for word in ['best', 'good', 'top', 'tier'])

            if is_valkyrie_related and (is_tier_related or 'tier' in source):
                # Boost valkyrie tier list content
                if "valkyrie-tier-list" in source:
                    tier_boosted_score = max(0.0, score - 0.15)  # Moderate boost
                    if self.verbose and tier_boosted_score < score:
                        print(f"  🎯 [TIER LIST BOOST] {source}: {score:.3f} → {tier_boosted_score:.3f}")

                # Also boost general guides that mention valkyries prominently
                elif "guide" in source and "valkyrie" in doc.page_content.lower()[:300]:
                    tier_boosted_score = max(0.0, score - 0.1)  # Smaller boost for general guides

            tier_list_boosted_results.append((doc, tier_boosted_score))

        # Re-sort by boosted score
        tier_list_boosted_results.sort(key=lambda x: x[1])
        all_results = tier_list_boosted_results
        
        # Show aggregated results before filtering (verbose only)
        if self.verbose:
            print(f"\n📊 [RESULTS DEBUG] Aggregated {len(all_results)} unique documents (before threshold filter):")
            for i, (doc, score) in enumerate(all_results[:10], 1):  # Show top 10
                source = doc.metadata.get("source", "Unknown")
                # Check if this is a tier list document
                is_tier_list = "valkyrie-tier-list" in source.lower()
                is_faq = "faq" in source.lower() and "valkyrie" in doc.page_content.lower()[:200]
                tier_marker = " 🎯" if is_tier_list else ""
                faq_marker = " 📋" if is_faq else ""
                print(f"  {i}. [{source}] (score: {score:.3f}){tier_marker}{faq_marker}")
        
        # Filter by effective threshold (adjusted for cross-language queries if needed)
        # But allow more results through for prioritization (2x the target k)
        prioritization_pool_size = min(len(all_results), k * 2)  # Allow up to 2x target for better prioritization

        if effective_threshold is not None:
            filtered_results = [(doc, score) for doc, score in all_results if score <= effective_threshold]

            if self.verbose:
                print(f"\n🎯 [THRESHOLD DEBUG] Threshold: {effective_threshold:.3f}")
                print(f"  Before filter: {len(all_results)} results")
                print(f"  After filter: {len(filtered_results)} results")

            # If threshold filtered out all results (common for cross-language queries),
            # return top prioritization_pool_size results for prioritization
            if not filtered_results and all_results:
                results_for_prioritization = all_results[:prioritization_pool_size]
                if self.verbose:
                    print(f"  ⚠️ Threshold filtered all results, using top {prioritization_pool_size} anyway")
            else:
                # Allow more results through for prioritization, but ensure we have at least k
                results_for_prioritization = filtered_results[:max(prioritization_pool_size, k)]
        else:
            results_for_prioritization = all_results[:prioritization_pool_size]

        # Show results for prioritization (verbose only)
        if self.verbose:
            print(f"\n🔄 [PRIORITIZATION POOL] {len(results_for_prioritization)} documents for prioritization:")
            for i, (doc, score) in enumerate(results_for_prioritization, 1):
                source = doc.metadata.get("source", "Unknown")
                is_tier_list = "valkyrie-tier-list" in source.lower()
                is_faq = "faq" in source.lower() and "valkyrie" in doc.page_content.lower()[:200]
                tier_marker = " 🎯" if is_tier_list else ""
                faq_marker = " 📋" if is_faq else ""
                print(f"  {i}. [{source}] (score: {score:.3f}){tier_marker}{faq_marker}")

        # Expand header-only chunks and small chunks in sections
        expanded_results = []
        for doc, score in results_for_prioritization:
            # First expand header-only chunks
            expanded_doc = self._expand_header_only_chunk(doc)
            # Then expand small chunks that are part of larger sections
            expanded_doc = self._expand_small_chunk_in_section(expanded_doc)
            expanded_results.append((expanded_doc, score))

        # Post-process: prioritize to get the best k results from the expanded pool
        # This ensures better source diversity by working with more candidates
        expanded_results = self._prioritize_comprehensive_chunks(expanded_results, all_results, k)
        
        # Show final results after prioritization (verbose only)
        if self.verbose:
            print(f"\n🎉 [FINAL RESULTS] Final {len(expanded_results)} documents after prioritization:")
            for i, (doc, score) in enumerate(expanded_results, 1):
                source = doc.metadata.get("source", "Unknown")
                is_tier_list = "valkyrie-tier-list" in source.lower()
                is_faq = "faq" in source.lower() and "valkyrie" in doc.page_content.lower()[:200]
                tier_marker = " 🎯" if is_tier_list else ""
                faq_marker = " 📋" if is_faq else ""
                preview = doc.page_content[:100].replace('\n', ' ')
                print(f"  {i}. [{source}] (score: {score:.3f}){tier_marker}{faq_marker}")
                print(f"      Preview: {preview}...")
        
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

