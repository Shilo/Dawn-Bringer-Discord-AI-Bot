"""Document loader for parsing and loading documentation files."""

from pathlib import Path
from typing import List, Dict, Optional
import re


class Document:
    """Represents a loaded document with metadata."""
    
    def __init__(self, content: str, metadata: Dict[str, str]):
        self.content = content
        self.metadata = metadata
    
    def __repr__(self):
        return f"Document(source={self.metadata.get('source')}, type={self.metadata.get('doc_type')})"


class DocumentLoader:
    """Loads and parses documentation files."""
    
    def __init__(self, docs_dir: Path):
        self.docs_dir = Path(docs_dir)
    
    def detect_document_type(self, file_path: Path) -> str:
        """Detect document type based on file path and content.
        
        Args:
            file_path: Path to the document file
            
        Returns:
            Document type: 'faq', 'guide', 'character', or 'general'
        """
        path_str = str(file_path).lower()
        
        # Check path for type indicators
        if "faq" in path_str or "frequently-asked" in path_str:
            return "faq"
        if "valkyries" in path_str or "valkyrie" in path_str:
            return "character"
        if "guide" in path_str or "guides" in path_str:
            return "guide"
        
        # Check filename pattern for character docs (e.g., 100001-Miranda.md)
        if re.match(r'\d+-[A-Za-z].*\.md$', file_path.name):
            return "character"
        
        return "general"
    
    def load_document(self, file_path: Path) -> Optional[Document]:
        """Load a single document file.
        
        Args:
            file_path: Path to the document file
            
        Returns:
            Document object or None if file should be skipped
        """
        # Skip README.md files
        if file_path.stem.upper() == "README":
            return None
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
            
            if not content:
                return None
            
            # Clean content for better chunking, embedding, and searching
            content = self._clean_content(content)
            
            # Get relative path for metadata
            relative_path = file_path.relative_to(self.docs_dir)
            doc_key = str(relative_path.with_suffix("")).replace("\\", "/")
            
            # Detect document type
            doc_type = self.detect_document_type(file_path)
            
            # Extract character name for character docs
            character_name = None
            if doc_type == "character":
                # Extract name from filename (e.g., "100001-Miranda.md" -> "Miranda")
                match = re.match(r'\d+-(.+)\.md$', file_path.name)
                if match:
                    character_name = match.group(1)
            
            metadata = {
                "source": doc_key,
                "file_path": str(relative_path),
                "doc_type": doc_type,
            }
            
            if character_name:
                metadata["character"] = character_name
            
            return Document(content, metadata)
        
        except Exception as e:
            print(f"Error loading {file_path}: {e}")
            return None
    
    def load_all_documents(self) -> List[Document]:
        """Load all documentation files from the docs directory.
        
        Returns:
            List of Document objects
        """
        documents = []
        
        if not self.docs_dir.exists():
            print(f"Warning: {self.docs_dir} directory not found.")
            return documents
        
        # Load both .txt and .md files recursively
        for pattern in ["*.txt", "*.md"]:
            for file_path in self.docs_dir.rglob(pattern):
                doc = self.load_document(file_path)
                if doc:
                    documents.append(doc)
                    print(f"Loaded: {doc.metadata['source']} ({doc.metadata['doc_type']})")
        
        print(f"📚 Total documents loaded: {len(documents)}")
        return documents
    
    def _clean_content(self, content: str) -> str:
        """Clean document content to improve chunking, embedding, and searching.
        
        Removes:
        - Metadata tags (|||-# fq: ...||)
        - Discord navigation links in headers ([▲Top](...))
        - Broken/empty links (https://#, https://.)
        - Image markdown (removes entirely as they don't provide searchable text)
        - Discord channel links in arrow_right format (:arrow_right: [text](discord link))
        - TODO/FIXME/XXX comments
        - Escaped newlines (\n) converted to actual newlines
        
        Args:
            content: Raw document content
            
        Returns:
            Cleaned content
        """
        # Convert escaped newlines to actual newlines (e.g., \n in strings)
        content = content.replace('\\n', '\n')
        
        lines = content.split('\n')
        cleaned_lines = []
        
        for line in lines:
            # Remove metadata tags (|||-# fq: ...||)
            if line.strip().startswith('|||-#') and line.strip().endswith('||'):
                continue
            
            # Remove TODO/FIXME/XXX comments
            if re.match(r'^#?\s*(TODO|FIXME|XXX):', line.strip(), re.IGNORECASE):
                continue
            
            # Remove image markdown entirely (images don't provide searchable text)
            # Pattern: ![alt text](url)
            if re.match(r'^!\[([^\]]+)\]\([^\)]+\)$', line.strip()):
                continue
            
            # Remove Discord navigation links from headers
            # Pattern: [▲Top](https://discord.com/...)
            line = re.sub(r'\s*\[▲Top\]\(https://discord\.com/[^\)]+\)', '', line)
            
            # Remove broken/empty links but keep the link text
            # Pattern: [text](https://#) or [text](https://.)
            line = re.sub(r'\[([^\]]+)\]\(https://[#\.]\)', r'\1', line)
            
            # Clean Discord channel links in arrow_right format
            # Pattern: :arrow_right: [text](https://discord.com/...)
            # Keep the text but remove the link
            line = re.sub(r':arrow_right:\s*\[([^\]]+)\]\(https://discord\.com/[^\)]+\)', r'→ \1', line)
            
            # Remove standalone Discord links but keep surrounding text
            # Pattern: [text](https://discord.com/...) when not part of arrow_right
            line = re.sub(r'\[([^\]]+)\]\(https://discord\.com/[^\)]+\)', r'\1', line)
            
            # Clean up multiple spaces that might result from removals
            line = re.sub(r'  +', ' ', line)
            
            # Keep the line if it wasn't filtered out
            if line.strip() or not cleaned_lines or cleaned_lines[-1].strip():
                cleaned_lines.append(line)
        
        # Join and clean up multiple consecutive empty lines
        cleaned_content = '\n'.join(cleaned_lines)
        cleaned_content = re.sub(r'\n{3,}', '\n\n', cleaned_content)
        
        return cleaned_content.strip()

