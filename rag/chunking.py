"""Smart document chunking strategies for different document types."""

from typing import List, Dict, Tuple
import re
from langchain_text_splitters import RecursiveCharacterTextSplitter
from rag.document_loader import Document
from rag.config import RAGConfig


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
    
    def _chunk_with_line_numbers(self, text: str, splitter: RecursiveCharacterTextSplitter, start_line: int = 1) -> List[Tuple[str, int, int]]:
        """Chunk text and track line numbers for each chunk.
        
        Args:
            text: Text to chunk
            splitter: Text splitter to use
            start_line: Starting line number (default: 1)
            
        Returns:
            List of tuples: (chunk_text, start_line_num, end_line_num)
        """
        # Split text into chunks
        chunks = splitter.split_text(text)
        
        if not chunks:
            return []
        
        # Track line numbers for each chunk
        result = []
        current_pos = 0
        
        for chunk in chunks:
            # Find where this chunk starts in the original text
            # Try to find exact match first
            chunk_start_pos = text.find(chunk, current_pos)
            
            # If exact match not found (can happen with overlap), try to find partial match
            if chunk_start_pos == -1:
                # Try finding a substring that matches the beginning of the chunk
                # This handles cases where the chunk might have been modified slightly
                chunk_prefix = chunk[:min(50, len(chunk))]  # Use first 50 chars
                chunk_start_pos = text.find(chunk_prefix, current_pos)
                if chunk_start_pos == -1:
                    # Last resort: use current position
                    chunk_start_pos = current_pos
            
            # Calculate line numbers
            # Count newlines before the chunk start position
            chunk_start_line = start_line + text[:chunk_start_pos].count('\n')
            # Count newlines in the chunk itself to get end line
            chunk_end_line = chunk_start_line + chunk.count('\n')
            
            # Ensure end_line is at least start_line
            if chunk_end_line < chunk_start_line:
                chunk_end_line = chunk_start_line
            
            result.append((chunk, chunk_start_line, chunk_end_line))
            
            # Update current position for next search
            # Move past this chunk, accounting for overlap
            # Use the overlap from config (splitter might not expose it directly)
            overlap = RAGConfig.CHUNK_OVERLAP if splitter == self.default_splitter else RAGConfig.CHARACTER_CHUNK_OVERLAP
            current_pos = max(current_pos, chunk_start_pos + len(chunk) - overlap)
        
        return result
    
    def chunk_faq_document(self, doc: Document) -> List[Dict[str, any]]:
        """Chunk FAQ documents by question-answer pairs.
        
        Args:
            doc: Document to chunk
            
        Returns:
            List of chunk dictionaries with content and metadata
        """
        chunks = []
        content = doc.content
        
        # Split by markdown headers (## or ###)
        # Pattern matches headers like: ## :emoji: [Question Text](link)
        header_pattern = r'^##+\s+(.+)$'
        lines = content.split('\n')
        
        current_question = None
        current_answer = []
        current_section = None
        question_start_line = 1
        answer_start_line = 1
        
        for line_num, line in enumerate(lines, start=1):
            # Check if this is a header
            header_match = re.match(header_pattern, line)
            if header_match:
                # Save previous Q&A if exists
                if current_question and current_answer:
                    answer_text = '\n'.join(current_answer).strip()
                    if answer_text:
                        # Calculate line range
                        chunk_start_line = question_start_line
                        chunk_end_line = line_num - 1
                        chunks.append({
                            "content": f"{current_question}\n\n{answer_text}",
                            "metadata": {
                                **doc.metadata,
                                "question": current_question,
                                "section": current_section,
                                "chunk_type": "faq_pair",
                                "start_line": chunk_start_line,
                                "end_line": chunk_end_line,
                            }
                        })
                
                # Start new Q&A
                header_text = header_match.group(1).strip()
                # Remove emoji and links from header for cleaner question
                question_text = re.sub(r':\w+:', '', header_text)  # Remove emoji
                question_text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', question_text)  # Remove markdown links
                question_text = question_text.strip()
                
                current_question = question_text
                current_answer = []
                current_section = question_text
                question_start_line = line_num
                answer_start_line = line_num + 1
            else:
                # Add to current answer
                if current_question:
                    current_answer.append(line)
        
        # Don't forget the last Q&A
        if current_question and current_answer:
            answer_text = '\n'.join(current_answer).strip()
            if answer_text:
                chunk_start_line = question_start_line
                chunk_end_line = len(lines)
                chunks.append({
                    "content": f"{current_question}\n\n{answer_text}",
                    "metadata": {
                        **doc.metadata,
                        "question": current_question,
                        "section": current_section,
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
        
        Args:
            doc: Document to chunk
            
        Returns:
            List of chunk dictionaries with content and metadata
        """
        chunks = []
        content = doc.content
        lines = content.split('\n')
        
        # Try to split by markdown sections first
        sections = re.split(r'\n(##+\s+.+)\n', content)
        
        if len(sections) > 1:
            # We have sections
            current_section = None
            current_line = 1
            
            for i, section in enumerate(sections):
                if i == 0:
                    # First part might be before first header
                    if section.strip():
                        # Calculate line range for intro
                        section_start_line = current_line
                        section_lines = section.count('\n') + (1 if section else 0)
                        section_end_line = section_start_line + section_lines - 1
                        
                        # Use chunker with line tracking
                        chunked = self._chunk_with_line_numbers(section.strip(), self.default_splitter, section_start_line)
                        for chunk_text, start_line, end_line in chunked:
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
                        current_line = section_end_line + 1
                elif i % 2 == 1:
                    # This is a header
                    current_section = section.strip()
                    # Remove markdown formatting
                    current_section = re.sub(r'^##+\s+', '', current_section)
                    current_section = re.sub(r':\w+:', '', current_section)  # Remove emoji
                    current_section = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', current_section)  # Remove links
                    current_section = current_section.strip()
                    # Header is on current_line, section content starts after
                    current_line += 1
                else:
                    # This is section content
                    if section.strip() and current_section:
                        section_start_line = current_line
                        section_lines = section.count('\n') + (1 if section else 0)
                        section_end_line = section_start_line + section_lines - 1
                        
                        # Use chunker with line tracking
                        chunked = self._chunk_with_line_numbers(section.strip(), self.default_splitter, section_start_line)
                        for chunk_text, start_line, end_line in chunked:
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
                        current_line = section_end_line + 1
        else:
            # No clear sections, use default chunking with line tracking
            chunked = self._chunk_with_line_numbers(content, self.default_splitter, 1)
            for i, (chunk_text, start_line, end_line) in enumerate(chunked):
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
        
        Args:
            doc: Document to chunk
            
        Returns:
            List of chunk dictionaries with content and metadata
        """
        chunks = []
        content = doc.content
        
        # Split by markdown sections
        sections = re.split(r'\n(##+\s+.+)\n', content)
        
        if len(sections) > 1:
            current_section = None
            current_line = 1
            
            for i, section in enumerate(sections):
                if i == 0:
                    # First part (usually title and bio)
                    if section.strip():
                        section_start_line = current_line
                        section_lines = section.count('\n') + (1 if section else 0)
                        section_end_line = section_start_line + section_lines - 1
                        
                        chunked = self._chunk_with_line_numbers(section.strip(), self.character_splitter, section_start_line)
                        for chunk_text, start_line, end_line in chunked:
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
                        current_line = section_end_line + 1
                elif i % 2 == 1:
                    # This is a header
                    current_section = section.strip()
                    current_section = re.sub(r'^##+\s+', '', current_section)
                    current_section = current_section.strip()
                    current_line += 1
                else:
                    # This is section content
                    if section.strip() and current_section:
                        section_start_line = current_line
                        section_lines = section.count('\n') + (1 if section else 0)
                        section_end_line = section_start_line + section_lines - 1
                        
                        chunked = self._chunk_with_line_numbers(section.strip(), self.character_splitter, section_start_line)
                        for chunk_text, start_line, end_line in chunked:
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
                        current_line = section_end_line + 1
        else:
            # No clear sections, use character splitter with line tracking
            chunked = self._chunk_with_line_numbers(content, self.character_splitter, 1)
            for i, (chunk_text, start_line, end_line) in enumerate(chunked):
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

