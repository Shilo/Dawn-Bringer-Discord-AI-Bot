"""Smart document chunking strategies for different document types."""

from typing import List, Dict, Tuple
import re
from langchain_text_splitters import RecursiveCharacterTextSplitter
from rag.document_loader import Document
from rag.config import RAGConfig


def trim_trailing_whitespace(text: str) -> str:
    """Trim trailing whitespace from each line of text.
    
    Args:
        text: Text to trim
        
    Returns:
        Text with trailing whitespace removed from each line
    """
    return "\n".join(line.rstrip() for line in text.split("\n"))


def find_text_line_numbers(original_content: str, search_text: str, start_from_line: int = 1) -> Tuple[int, int] | None:
    """Find text in original content and return its line numbers.
    
    Simple, straightforward approach: search for the text in the original file
    and calculate line numbers from the position.
    
    Args:
        original_content: The full original file content
        search_text: Text to find (will be normalized by stripping)
        start_from_line: Optional hint for where to start searching (1-indexed)
        
    Returns:
        Tuple of (start_line, end_line) if found, None otherwise
    """
    if not search_text or not original_content:
        return None
    
    # Normalize search text
    search_text = search_text.strip()
    if not search_text:
        return None
    
    # Find the text in original content
    # Try to find exact match first
    pos = original_content.find(search_text)
    
    # If not found, try finding a significant prefix (first 100 chars)
    if pos == -1 and len(search_text) > 100:
        prefix = search_text[:100].strip()
        pos = original_content.find(prefix)
    
    if pos == -1:
        return None
    
    # Calculate line numbers from position
    # Count newlines before the found position
    start_line = 1 + original_content[:pos].count('\n')
    # Count newlines in the search text to get end line
    end_line = start_line + search_text.count('\n')
    
    return (start_line, end_line)


class DocumentChunker:
    """Chunks documents using different strategies based on document type."""
    
    def __init__(self):
        # Default text splitter for guides and general docs
        self.default_splitter = RecursiveCharacterTextSplitter(
            chunk_size=RAGConfig.CHUNK_SIZE,
            chunk_overlap=RAGConfig.CHUNK_OVERLAP,
            separators=["\n\n", "\n", ". ", " ", ""],
        )
        
        # Character-specific splitter (smaller chunks)
        self.character_splitter = RecursiveCharacterTextSplitter(
            chunk_size=RAGConfig.CHARACTER_CHUNK_SIZE,
            chunk_overlap=RAGConfig.CHARACTER_CHUNK_OVERLAP,
            separators=["\n\n", "\n", ". ", " ", ""],
        )
    
    def _chunk_with_line_numbers(self, original_content: str, text: str, splitter: RecursiveCharacterTextSplitter) -> List[Tuple[str, int, int]]:
        """Chunk text and track line numbers by finding chunks in original content.
        
        Simple approach: after chunking, find each chunk in the original file
        and calculate line numbers from there.
        
        Args:
            original_content: The full original file content
            text: Text to chunk (may be a subset of original_content)
            splitter: Text splitter to use
            
        Returns:
            List of tuples: (chunk_text, start_line_num, end_line_num)
        """
        # Split text into chunks
        chunks = splitter.split_text(text)
        
        if not chunks:
            return []
        
        result = []
        for chunk in chunks:
            # Trim trailing whitespace from chunk content
            chunk = trim_trailing_whitespace(chunk)
            # Find this chunk in the original content
            line_nums = find_text_line_numbers(original_content, chunk)
            if line_nums:
                start_line, end_line = line_nums
                result.append((chunk, start_line, end_line))
            else:
                # Fallback: if not found, use approximate calculation
                # This shouldn't happen often, but provides a safety net
                pos = original_content.find(chunk[:50]) if len(chunk) > 50 else original_content.find(chunk)
                if pos != -1:
                    start_line = 1 + original_content[:pos].count('\n')
                    end_line = start_line + chunk.count('\n')
                    result.append((chunk, start_line, end_line))
        
        return result
    
    def chunk_faq_document(self, doc: Document) -> List[Dict[str, any]]:
        """Chunk FAQ documents by question-answer pairs.
        
        Simple approach: process line by line, then find the chunk text in original
        to get accurate line numbers.
        
        Args:
            doc: Document to chunk
            
        Returns:
            List of chunk dictionaries with content and metadata
        """
        chunks = []
        content = doc.content
        
        # Read original file content (before cleaning) for accurate line number calculation
        original_content = None
        file_path = doc.metadata.get("file_path")
        if file_path:
            from rag.config import RAGConfig
            full_path = RAGConfig.DOCS_DIR / file_path
            try:
                with open(full_path, 'r', encoding='utf-8') as f:
                    original_content = f.read()
            except Exception as e:
                print(f"⚠️ Warning: Could not read original file {full_path} for line numbers: {e}")
                # Fallback to using cleaned content
                original_content = content
        else:
            # Fallback to using cleaned content if no file_path
            original_content = content
        
        # Split by markdown headers (## or ###)
        header_pattern = r'^##+\s+(.+)$'
        lines = content.split('\n')
        
        current_question = None
        current_answer = []
        question_start_line = 1
        
        for line_num, line in enumerate(lines, start=1):
            header_match = re.match(header_pattern, line)
            if header_match:
                # Save previous Q&A if exists
                if current_question and current_answer:
                    answer_text = '\n'.join(current_answer).strip()
                    if answer_text:
                        # Build the full chunk content
                        chunk_content = f"{current_question}\n\n{answer_text}"
                        
                        # Find this chunk in the original file content (before cleaning) to get accurate line numbers
                        # First try to find the question header in the original file
                        original_lines = original_content.split('\n')
                        chunk_start_line = None
                        chunk_end_line = None
                        
                        # Search for the question text in original file headers
                        for orig_line_num, orig_line in enumerate(original_lines, start=1):
                            # Check if this line is a header containing the question text
                            if re.match(r'^##+\s+', orig_line):
                                # Extract text from header (remove markdown, emojis, links)
                                header_text = re.sub(r'^##+\s+', '', orig_line)
                                header_text_clean = re.sub(r':\w+:', '', header_text)  # Remove emoji
                                header_text_clean = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', header_text_clean)  # Remove links
                                header_text_clean = header_text_clean.strip()
                                
                                # Check if this header matches our question
                                if current_question.lower() in header_text_clean.lower() or header_text_clean.lower() in current_question.lower():
                                    chunk_start_line = orig_line_num
                                    # Find where this Q&A ends (next header or end of file)
                                    # Count answer lines (approximate based on cleaned answer)
                                    answer_line_count = len(current_answer)
                                    chunk_end_line = min(orig_line_num + answer_line_count + 2, len(original_lines))
                                    
                                    # Try to find a better end by looking for the next header, metadata tag, or image
                                    for end_line_num in range(orig_line_num + 1, min(orig_line_num + answer_line_count + 10, len(original_lines) + 1)):
                                        if end_line_num <= len(original_lines):
                                            end_line = original_lines[end_line_num - 1].strip()
                                            # Stop at next header
                                            if re.match(r'^##+\s+', end_line):
                                                chunk_end_line = end_line_num - 1
                                                break
                                            # Stop at metadata tag start (starts with ||)
                                            if re.match(r'^\|\|', end_line):
                                                chunk_end_line = end_line_num - 1
                                                break
                                            # Stop at image
                                            if re.match(r'^!\[.*\]\(.*\)$', end_line):
                                                chunk_end_line = end_line_num - 1
                                                break
                                    
                                    # Trim trailing empty lines
                                    while chunk_end_line > chunk_start_line:
                                        line_content = original_lines[chunk_end_line - 1].strip()
                                        if not line_content:
                                            chunk_end_line -= 1
                                        else:
                                            break
                                    break
                        
                        # If we couldn't find it by header, try finding the chunk content directly
                        if not chunk_start_line:
                            line_nums = find_text_line_numbers(original_content, chunk_content, question_start_line)
                            if line_nums:
                                chunk_start_line, chunk_end_line = line_nums
                        
                        # Final fallback: use tracked line numbers from cleaned content
                        if not chunk_start_line:
                            chunk_start_line = question_start_line
                            chunk_end_line = line_num - 1
                        
                        # Trim trailing whitespace from chunk content
                        chunk_content = trim_trailing_whitespace(chunk_content)
                        chunks.append({
                            "content": chunk_content,
                            "metadata": {
                                **doc.metadata,
                                "question": current_question,
                                "section": current_question,
                                "chunk_type": "faq_pair",
                                "start_line": chunk_start_line,
                                "end_line": chunk_end_line,
                            }
                        })
                
                # Start new Q&A
                header_text = header_match.group(1).strip()
                question_text = re.sub(r':\w+:', '', header_text)  # Remove emoji
                question_text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', question_text)  # Remove links
                # Remove markdown formatting (order matters: double before single)
                question_text = re.sub(r'__([^_]+)__', r'\1', question_text)  # Remove __bold__
                question_text = re.sub(r'\*\*([^*]+)\*\*', r'\1', question_text)  # Remove **bold**
                question_text = re.sub(r'(?<!_)_([^_]+)_(?!_)', r'\1', question_text)  # Remove _italic_ (not part of __)
                question_text = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', r'\1', question_text)  # Remove *italic* (not part of **)
                question_text = question_text.strip()
                
                current_question = question_text
                current_answer = []
                question_start_line = line_num
            else:
                # Add to current answer (excluding images)
                if current_question and not re.match(r'^!\[.*\]\(.*\)$', line):
                    current_answer.append(line)
        
        # Don't forget the last Q&A
        if current_question and current_answer:
            answer_text = '\n'.join(current_answer).strip()
            if answer_text:
                chunk_content = f"{current_question}\n\n{answer_text}"
                # Find this chunk in the original file content (before cleaning) to get accurate line numbers
                # First try to find the question header in the original file
                original_lines = original_content.split('\n')
                chunk_start_line = None
                chunk_end_line = None
                
                # Search for the question text in original file headers
                for orig_line_num, orig_line in enumerate(original_lines, start=1):
                    # Check if this line is a header containing the question text
                    if re.match(r'^##+\s+', orig_line):
                        # Extract text from header (remove markdown, emojis, links)
                        header_text = re.sub(r'^##+\s+', '', orig_line)
                        header_text_clean = re.sub(r':\w+:', '', header_text)  # Remove emoji
                        header_text_clean = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', header_text_clean)  # Remove links
                        header_text_clean = header_text_clean.strip()
                        
                        # Check if this header matches our question
                        if current_question.lower() in header_text_clean.lower() or header_text_clean.lower() in current_question.lower():
                            chunk_start_line = orig_line_num
                            # Find where this Q&A ends (next header or end of file)
                            # Count answer lines (approximate based on cleaned answer)
                            answer_line_count = len(current_answer)
                            chunk_end_line = min(orig_line_num + answer_line_count + 2, len(original_lines))
                            
                            # Try to find a better end by looking for the next header, metadata tag, or image
                            for end_line_num in range(orig_line_num + 1, min(orig_line_num + answer_line_count + 10, len(original_lines) + 1)):
                                if end_line_num <= len(original_lines):
                                    end_line = original_lines[end_line_num - 1].strip()
                                    # Stop at next header
                                    if re.match(r'^##+\s+', end_line):
                                        chunk_end_line = end_line_num - 1
                                        break
                                    # Stop at metadata tag start (starts with ||)
                                    if re.match(r'^\|\|', end_line):
                                        chunk_end_line = end_line_num - 1
                                        break
                                    # Stop at image
                                    if re.match(r'^!\[.*\]\(.*\)$', end_line):
                                        chunk_end_line = end_line_num - 1
                                        break
                            
                            # Trim trailing empty lines
                            while chunk_end_line > chunk_start_line:
                                line_content = original_lines[chunk_end_line - 1].strip()
                                if not line_content:
                                    chunk_end_line -= 1
                                else:
                                    break
                            break
                
                # If we couldn't find it by header, try finding the chunk content directly
                if not chunk_start_line:
                    line_nums = find_text_line_numbers(original_content, chunk_content, question_start_line)
                    if line_nums:
                        chunk_start_line, chunk_end_line = line_nums
                
                # Final fallback: use tracked line numbers from cleaned content
                if not chunk_start_line:
                    chunk_start_line = question_start_line
                    chunk_end_line = len(original_lines)
                
                # Trim trailing whitespace from chunk content
                chunk_content = trim_trailing_whitespace(chunk_content)
                chunks.append({
                    "content": chunk_content,
                    "metadata": {
                        **doc.metadata,
                        "question": current_question,
                        "section": current_question,
                        "chunk_type": "faq_pair",
                        "start_line": chunk_start_line,
                        "end_line": chunk_end_line,
                    }
                })
        
        # If no headers found, fall back to default chunking
        if not chunks:
            return self.chunk_guide_document(doc)
        
        return chunks
    
    def chunk_guide_document(self, doc: Document) -> List[Dict[str, any]]:
        """Chunk guide documents by sections.
        
        Simple approach: chunk the content, then find each chunk in original to get line numbers.
        
        Args:
            doc: Document to chunk
            
        Returns:
            List of chunk dictionaries with content and metadata
        """
        chunks = []
        content = doc.content
        
        # Read original file content (before cleaning) for accurate line number calculation
        original_content = None
        file_path = doc.metadata.get("file_path")
        if file_path:
            from rag.config import RAGConfig
            full_path = RAGConfig.DOCS_DIR / file_path
            try:
                with open(full_path, 'r', encoding='utf-8') as f:
                    original_content = f.read()
            except Exception as e:
                print(f"⚠️ Warning: Could not read original file {full_path} for line numbers: {e}")
                # Fallback to using cleaned content
                original_content = content
        else:
            # Fallback to using cleaned content if no file_path
            original_content = content
        
        # Try to split by markdown sections first
        sections = re.split(r'\n(##+\s+.+)\n', content)
        
        if len(sections) > 1:
            current_section = None
            
            for i, section in enumerate(sections):
                if i == 0:
                    # First part (before first header)
                    if section.strip():
                        chunked = self._chunk_with_line_numbers(original_content, section.strip(), self.default_splitter)
                        for chunk_text, start_line, end_line in chunked:
                            # chunk_text is already trimmed in _chunk_with_line_numbers
                            chunks.append({
                                "content": chunk_text,
                                "metadata": {
                                    **doc.metadata,
                                    "section": "Introduction",
                                    "chunk_type": "guide_section",
                                    "start_line": start_line,
                                    "end_line": end_line,
                                }
                            })
                elif i % 2 == 1:
                    # This is a header
                    current_section = section.strip()
                    current_section = re.sub(r'^##+\s+', '', current_section)
                    current_section = re.sub(r':\w+:', '', current_section)
                    current_section = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', current_section)
                    current_section = current_section.strip()
                else:
                    # This is section content
                    if section.strip() and current_section:
                        chunked = self._chunk_with_line_numbers(original_content, section.strip(), self.default_splitter)
                        for chunk_text, start_line, end_line in chunked:
                            # chunk_text is already trimmed in _chunk_with_line_numbers
                            chunks.append({
                                "content": chunk_text,
                                "metadata": {
                                    **doc.metadata,
                                    "section": current_section,
                                    "chunk_type": "guide_section",
                                    "start_line": start_line,
                                    "end_line": end_line,
                                }
                            })
        else:
            # No clear sections, use default chunking
            chunked = self._chunk_with_line_numbers(original_content, content, self.default_splitter)
            for i, (chunk_text, start_line, end_line) in enumerate(chunked):
                # chunk_text is already trimmed in _chunk_with_line_numbers
                chunks.append({
                    "content": chunk_text,
                    "metadata": {
                        **doc.metadata,
                        "section": f"Section {i+1}",
                        "chunk_type": "guide_section",
                        "start_line": start_line,
                        "end_line": end_line,
                    }
                })
        
        return chunks
    
    def chunk_character_document(self, doc: Document) -> List[Dict[str, any]]:
        """Chunk character documents by sections (bio, skills, etc.).
        
        Simple approach: chunk the content, then find each chunk in original to get line numbers.
        
        Args:
            doc: Document to chunk
            
        Returns:
            List of chunk dictionaries with content and metadata
        """
        chunks = []
        content = doc.content
        
        # Read original file content (before cleaning) for accurate line number calculation
        original_content = None
        file_path = doc.metadata.get("file_path")
        if file_path:
            from rag.config import RAGConfig
            full_path = RAGConfig.DOCS_DIR / file_path
            try:
                with open(full_path, 'r', encoding='utf-8') as f:
                    original_content = f.read()
            except Exception as e:
                print(f"⚠️ Warning: Could not read original file {full_path} for line numbers: {e}")
                # Fallback to using cleaned content
                original_content = content
        else:
            # Fallback to using cleaned content if no file_path
            original_content = content
        
        # Split by markdown sections
        sections = re.split(r'\n(##+\s+.+)\n', content)
        
        if len(sections) > 1:
            current_section = None
            
            for i, section in enumerate(sections):
                if i == 0:
                    # First part (before first header)
                    if section.strip():
                        chunked = self._chunk_with_line_numbers(original_content, section.strip(), self.character_splitter)
                        for chunk_text, start_line, end_line in chunked:
                            # chunk_text is already trimmed in _chunk_with_line_numbers
                            chunks.append({
                                "content": chunk_text,
                                "metadata": {
                                    **doc.metadata,
                                    "section": "Introduction",
                                    "chunk_type": "character_section",
                                    "start_line": start_line,
                                    "end_line": end_line,
                                }
                            })
                elif i % 2 == 1:
                    # This is a header
                    current_section = section.strip()
                    current_section = re.sub(r'^##+\s+', '', current_section)
                    current_section = current_section.strip()
                else:
                    # This is section content
                    if section.strip() and current_section:
                        chunked = self._chunk_with_line_numbers(original_content, section.strip(), self.character_splitter)
                        for chunk_text, start_line, end_line in chunked:
                            # chunk_text is already trimmed in _chunk_with_line_numbers
                            chunks.append({
                                "content": chunk_text,
                                "metadata": {
                                    **doc.metadata,
                                    "section": current_section,
                                    "chunk_type": "character_section",
                                    "start_line": start_line,
                                    "end_line": end_line,
                                }
                            })
        else:
            # No clear sections, use default chunking
            chunked = self._chunk_with_line_numbers(original_content, content, self.character_splitter)
            for i, (chunk_text, start_line, end_line) in enumerate(chunked):
                # chunk_text is already trimmed in _chunk_with_line_numbers
                chunks.append({
                    "content": chunk_text,
                    "metadata": {
                        **doc.metadata,
                        "section": f"Section {i+1}",
                        "chunk_type": "character_section",
                        "start_line": start_line,
                        "end_line": end_line,
                    }
                })
        
        return chunks
    
    def chunk_document(self, doc: Document) -> List[Dict[str, any]]:
        """Chunk a document based on its type.
        
        Args:
            doc: Document to chunk
            
        Returns:
            List of chunk dictionaries with content and metadata
        """
        doc_type = doc.metadata.get("doc_type", "general")
        
        if doc_type == "faq":
            return self.chunk_faq_document(doc)
        elif doc_type == "character":
            return self.chunk_character_document(doc)
        elif doc_type == "guide":
            return self.chunk_guide_document(doc)
        else:
            # General documents use guide chunking strategy
            return self.chunk_guide_document(doc)

