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
        current_answer_lines = []  # Track line numbers for answer lines
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
                        # Calculate line range based on actual answer lines
                        chunk_start_line = question_start_line
                        # Use the last line number from answer lines, then trim backwards
                        if current_answer_lines:
                            chunk_end_line = current_answer_lines[-1]
                            # Trim trailing empty lines and metadata tags
                            while chunk_end_line > chunk_start_line:
                                line_content = lines[chunk_end_line - 1].strip()
                                # Check if it's empty or a metadata tag (||-# fq: ...|| or |||-# fq: ...||)
                                # Also exclude image lines (![...])
                                if (not line_content or 
                                    re.match(r'^\|\|.*\|\|$', line_content) or
                                    re.match(r'^!\[.*\]\(.*\)$', line_content)):
                                    chunk_end_line -= 1
                                else:
                                    break
                        else:
                            chunk_end_line = question_start_line
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
                current_answer_lines = []
                current_section = question_text
                question_start_line = line_num
                answer_start_line = line_num + 1
            else:
                # Add to current answer (but track line numbers, excluding images)
                if current_question:
                    # Exclude image lines from answer content but still track line numbers
                    if not re.match(r'^!\[.*\]\(.*\)$', line):
                        current_answer.append(line)
                        current_answer_lines.append(line_num)
                    else:
                        # For images, just track the line number but don't include in content
                        # This helps with line number calculation
                        pass
        
        # Don't forget the last Q&A
        if current_question and current_answer:
            answer_text = '\n'.join(current_answer).strip()
            if answer_text:
                chunk_start_line = question_start_line
                # Use the last line number from answer lines, then trim backwards
                if current_answer_lines:
                    chunk_end_line = current_answer_lines[-1]
                    # Trim trailing empty lines and metadata tags
                    while chunk_end_line > chunk_start_line:
                        line_content = lines[chunk_end_line - 1].strip()
                        # Check if it's empty or a metadata tag (||-# fq: ...|| or |||-# fq: ...||)
                        # Also exclude image lines (![...])
                        if (not line_content or 
                            re.match(r'^\|\|.*\|\|$', line_content) or
                            re.match(r'^!\[.*\]\(.*\)$', line_content)):
                            chunk_end_line -= 1
                        else:
                            break
                else:
                    chunk_end_line = question_start_line
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
                        # Count leading newlines that will be stripped
                        stripped_section = section.strip()
                        # Count leading newlines (including any whitespace-only lines)
                        leading_newlines = 0
                        for char in section:
                            if char == '\n':
                                leading_newlines += 1
                            elif not char.isspace():
                                break
                        section_start_line = current_line + leading_newlines
                        section_lines = section.count('\n') + (1 if section else 0)
                        section_end_line = section_start_line + section_lines - 1
                        
                        # Use chunker with line tracking
                        chunked = self._chunk_with_line_numbers(stripped_section, self.default_splitter, section_start_line)
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
                    # The header line itself
                    current_line += 1
                else:
                    # This is section content
                    if section.strip() and current_section:
                        # re.split(r'\n(##+\s+.+)\n') includes the newline after the header in section content.
                        # After processing header, current_line points to the line after the header.
                        # Section content starts with a newline (from current_line), then the actual content.
                        # Count leading newlines that will be stripped
                        stripped_section = section.strip()
                        # Count leading newlines (including any whitespace-only lines)
                        leading_newlines = 0
                        for char in section:
                            if char == '\n':
                                leading_newlines += 1
                            elif not char.isspace():
                                break
                        # Section content's first newline corresponds to current_line, 
                        # so actual content starts at current_line + leading_newlines
                        section_start_line = current_line + leading_newlines
                        section_lines = section.count('\n') + (1 if section else 0)
                        section_end_line = section_start_line + section_lines - 1
                        
                        # Use chunker with line tracking
                        chunked = self._chunk_with_line_numbers(stripped_section, self.default_splitter, section_start_line)
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
        
        # Find all header positions to track line numbers accurately
        header_pattern = r'\n(##+\s+.+)\n'
        header_matches = list(re.finditer(header_pattern, content))
        
        if header_matches:
            # Process content before first header
            first_header_start = header_matches[0].start()
            intro_section = content[:first_header_start]
            if intro_section.strip():
                stripped_intro = intro_section.strip()
                leading_newlines = len(intro_section) - len(intro_section.lstrip('\n'))
                intro_start_line = 1 + leading_newlines
                chunked = self._chunk_with_line_numbers(stripped_intro, self.character_splitter, intro_start_line)
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
            
            # Process each header and its following content
            for i, header_match in enumerate(header_matches):
                header_text = header_match.group(1)
                header_start_pos = header_match.start() + 1  # +1 to skip leading \n
                header_line = 1 + content[:header_start_pos].count('\n')
                
                # Extract section name
                current_section = header_text.strip()
                current_section = re.sub(r'^##+\s+', '', current_section)
                current_section = current_section.strip()
                
                # Find content after this header (before next header or end of file)
                if i + 1 < len(header_matches):
                    next_header_start = header_matches[i + 1].start()
                    section_content = content[header_match.end():next_header_start]
                else:
                    section_content = content[header_match.end():]
                
                if section_content.strip():
                    # Calculate line number: header ends with \n, so content starts on next line
                    content_start_pos = header_match.end()
                    content_start_line = 1 + content[:content_start_pos].count('\n')
                    
                    # Count leading newlines that will be stripped
                    stripped_content = section_content.strip()
                    leading_newlines = len(section_content) - len(section_content.lstrip('\n'))
                    # Actual content starts after leading newlines
                    section_start_line = content_start_line + leading_newlines
                    
                    chunked = self._chunk_with_line_numbers(stripped_content, self.character_splitter, section_start_line)
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
        else:
            # No headers found, use default chunking
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

