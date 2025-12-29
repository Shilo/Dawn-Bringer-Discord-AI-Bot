"""Smart document chunking strategies for different document types."""

from typing import List, Dict
import re
from langchain.text_splitter import RecursiveCharacterTextSplitter
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
        
        for line in lines:
            # Check if this is a header
            header_match = re.match(header_pattern, line)
            if header_match:
                # Save previous Q&A if exists
                if current_question and current_answer:
                    answer_text = '\n'.join(current_answer).strip()
                    if answer_text:
                        chunks.append({
                            "content": f"{current_question}\n\n{answer_text}",
                            "metadata": {
                                **doc.metadata,
                                "question": current_question,
                                "section": current_section,
                                "chunk_type": "faq_pair",
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
            else:
                # Add to current answer
                if current_question:
                    current_answer.append(line)
        
        # Don't forget the last Q&A
        if current_question and current_answer:
            answer_text = '\n'.join(current_answer).strip()
            if answer_text:
                chunks.append({
                    "content": f"{current_question}\n\n{answer_text}",
                    "metadata": {
                        **doc.metadata,
                        "question": current_question,
                        "section": current_section,
                        "chunk_type": "faq_pair",
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
        
        # Try to split by markdown sections first
        sections = re.split(r'\n(##+\s+.+)\n', content)
        
        if len(sections) > 1:
            # We have sections
            current_section = None
            for i, section in enumerate(sections):
                if i == 0:
                    # First part might be before first header
                    if section.strip():
                        # Use default splitter for intro content
                        intro_chunks = self.default_splitter.split_text(section.strip())
                        for chunk in intro_chunks:
                            chunks.append({
                                "content": chunk,
                                "metadata": {
                                    **doc.metadata,
                                    "section": "Introduction",
                                    "chunk_type": "guide_section",
                                }
                            })
                elif i % 2 == 1:
                    # This is a header
                    current_section = section.strip()
                    # Remove markdown formatting
                    current_section = re.sub(r'^##+\s+', '', current_section)
                    current_section = re.sub(r':\w+:', '', current_section)  # Remove emoji
                    current_section = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', current_section)  # Remove links
                    current_section = current_section.strip()
                else:
                    # This is section content
                    if section.strip() and current_section:
                        # Use default splitter for section content
                        section_chunks = self.default_splitter.split_text(section.strip())
                        for chunk in section_chunks:
                            chunks.append({
                                "content": chunk,
                                "metadata": {
                                    **doc.metadata,
                                    "section": current_section,
                                    "chunk_type": "guide_section",
                                }
                            })
        else:
            # No clear sections, use default chunking
            text_chunks = self.default_splitter.split_text(content)
            for i, chunk in enumerate(text_chunks):
                chunks.append({
                    "content": chunk,
                    "metadata": {
                        **doc.metadata,
                        "section": f"Section {i+1}",
                        "chunk_type": "guide_section",
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
            for i, section in enumerate(sections):
                if i == 0:
                    # First part (usually title and bio)
                    if section.strip():
                        intro_chunks = self.character_splitter.split_text(section.strip())
                        for chunk in intro_chunks:
                            chunks.append({
                                "content": chunk,
                                "metadata": {
                                    **doc.metadata,
                                    "section": "Introduction",
                                    "chunk_type": "character_section",
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
                        section_chunks = self.character_splitter.split_text(section.strip())
                        for chunk in section_chunks:
                            chunks.append({
                                "content": chunk,
                                "metadata": {
                                    **doc.metadata,
                                    "section": current_section,
                                    "chunk_type": "character_section",
                                }
                            })
        else:
            # No clear sections, use character splitter
            text_chunks = self.character_splitter.split_text(content)
            for i, chunk in enumerate(text_chunks):
                chunks.append({
                    "content": chunk,
                    "metadata": {
                        **doc.metadata,
                        "section": f"Section {i+1}",
                        "chunk_type": "character_section",
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

