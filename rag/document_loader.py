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
        
        Types are determined by the immediate parent directory name inside docs/.
        If the parent directory is one of: 'faq', 'guide', 'character', 'general',
        that type is used. Otherwise, falls back to legacy detection logic.
        
        Args:
            file_path: Path to the document file
            
        Returns:
            Document type: 'faq', 'guide', 'character', or 'general'
        """
        # Get relative path from docs_dir
        try:
            relative_path = file_path.relative_to(self.docs_dir)
            # Get the first part of the path (the type directory)
            path_parts = relative_path.parts
            if len(path_parts) > 0:
                parent_dir = path_parts[0].lower()
                # Check if parent directory is a type directory
                if parent_dir in ["faq", "guide", "character", "general"]:
                    return parent_dir
        except ValueError:
            # File is not relative to docs_dir, fall through to legacy detection
            pass
        
        # Legacy detection logic for files not in type directories
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
            print(f"❌ Error loading {file_path}: {e}")
            return None
    
    def load_all_documents(self) -> List[Document]:
        """Load all documentation files from the docs directory.
        
        Returns:
            List of Document objects
        """
        documents = []
        
        if not self.docs_dir.exists():
            print(f"⚠️ Warning: {self.docs_dir} directory not found.")
            return documents
        
        # Load both .txt and .md files recursively
        for pattern in ["*.txt", "*.md"]:
            for file_path in self.docs_dir.rglob(pattern):
                doc = self.load_document(file_path)
                if doc:
                    documents.append(doc)
                    print(f"📄 Loaded: {doc.metadata['source']} ({doc.metadata['doc_type']})")
        
        print(f"📚 Total documents loaded: {len(documents)}")
        return documents
    
    def _clean_content(self, content: str) -> str:
        """Clean document content to improve chunking, embedding, and searching.
        
        Removes:
        - Metadata tags (|||-# fq: ...|| or ||-# fq: ...||, including multi-line)
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
        in_tag_block = False
        
        for line in lines:
            stripped = line.strip()
            
            # Check if we're starting a metadata tag block
            # Patterns: |||-# fq: ... or ||-# fq: ... (with 2-3 pipes at start)
            # Match lines starting with || or ||| followed by -# and containing fq:
            if re.match(r'^\|\|+\s*-#.*fq:', stripped):
                # Check if it's a single-line tag (ends with ||)
                if stripped.endswith('||'):
                    # Single-line tag, skip it
                    continue
                else:
                    # Multi-line tag starting, skip this line and mark as in tag block
                    in_tag_block = True
                    continue
            
            # Check if we're in a tag block continuation
            if in_tag_block:
                # Check if this line is part of the tag (starts with -#)
                if stripped.startswith('-#'):
                    # Check if this is the closing line (ends with ||)
                    if stripped.endswith('||'):
                        # End of tag block, skip this line and exit tag block
                        in_tag_block = False
                        continue
                    else:
                        # Continuation line, skip it
                        continue
                else:
                    # Not a tag line, but we were in a tag block
                    # This shouldn't happen normally, but reset just in case
                    in_tag_block = False
            
            # Remove TODO/FIXME/XXX comments
            if re.match(r'^#?\s*(TODO|FIXME|XXX):', stripped, re.IGNORECASE):
                continue
            
            # Remove image markdown entirely (images don't provide searchable text)
            # Pattern: ![alt text](url)
            if re.match(r'^!\[([^\]]+)\]\([^\)]+\)$', stripped):
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

