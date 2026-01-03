"""Tools for agent-like file system operations."""

from typing import List, Dict, Any, Optional
from pathlib import Path
import re
from rag.config import RAGConfig
from rag.document_loader import DocumentLoader


class FileSystemTools:
    """Tools for exploring and reading documentation files."""
    
    def __init__(self, docs_dir: Path = None):
        """Initialize tools with docs directory.
        
        Args:
            docs_dir: Path to documentation directory (defaults to RAGConfig.DOCS_DIR)
        """
        self.docs_dir = docs_dir or RAGConfig.DOCS_DIR
        self.loader = DocumentLoader(self.docs_dir)
    
    def list_files(self, directory: str = "", pattern: str = "*.md") -> Dict[str, Any]:
        """List files in a directory, optionally filtered by pattern.
        
        Args:
            directory: Relative path from docs_dir (e.g., "character", "guide/raids")
                      Empty string means root docs_dir
            pattern: File pattern to match (e.g., "*.md", "*Sylvia*")
        
        Returns:
            Dict with 'files' list containing file paths relative to docs_dir
        """
        try:
            if directory:
                target_dir = self.docs_dir / directory
            else:
                target_dir = self.docs_dir
            
            if not target_dir.exists():
                return {"files": [], "error": f"Directory not found: {directory}"}
            
            files = []
            for file_path in target_dir.rglob(pattern):
                if file_path.is_file():
                    # Get relative path from docs_dir
                    rel_path = file_path.relative_to(self.docs_dir)
                    files.append(str(rel_path).replace("\\", "/"))
            
            return {"files": sorted(files), "count": len(files)}
        except Exception as e:
            return {"files": [], "error": str(e)}
    
    def find_characters_by_pattern(self, starts_with: str = "", contains: str = "", doc_type: str = "character") -> Dict[str, Any]:
        """Find character files matching a pattern.
        
        Args:
            starts_with: Character name must start with this letter/string (case-insensitive)
            contains: Character name or filename must contain this string (case-insensitive)
            doc_type: Document type to search (default: "character")
        
        Returns:
            Dict with 'characters' list containing matching character info
        """
        try:
            if doc_type == "character":
                target_dir = self.docs_dir / "character"
            else:
                target_dir = self.docs_dir / doc_type
            
            if not target_dir.exists():
                return {"characters": [], "error": f"Directory not found: {doc_type}"}
            
            characters = []
            pattern = re.compile(r'^\d+-(.+)\.md$')
            
            for file_path in target_dir.glob("*.md"):
                match = pattern.match(file_path.name)
                if match:
                    character_name = match.group(1)
                    file_name_lower = file_path.name.lower()
                    char_name_lower = character_name.lower()
                    
                    # Check filters
                    matches = True
                    if starts_with:
                        if not char_name_lower.startswith(starts_with.lower()):
                            matches = False
                    if contains and matches:
                        if contains.lower() not in char_name_lower and contains.lower() not in file_name_lower:
                            matches = False
                    
                    if matches:
                        rel_path = file_path.relative_to(self.docs_dir)
                        characters.append({
                            "name": character_name,
                            "file": str(rel_path).replace("\\", "/"),
                            "filename": file_path.name
                        })
            
            return {"characters": sorted(characters, key=lambda x: x["name"]), "count": len(characters)}
        except Exception as e:
            return {"characters": [], "error": str(e)}
    
    def read_file(self, file_path: str, max_lines: int = 100) -> Dict[str, Any]:
        """Read a file from the docs directory.
        
        Args:
            file_path: Relative path from docs_dir (e.g., "character/100044-Sylvia_SP.md")
            max_lines: Maximum number of lines to return (default: 100, 0 = all)
        
        Returns:
            Dict with 'content', 'line_count', and 'truncated' flag
        """
        try:
            full_path = self.docs_dir / file_path
            if not full_path.exists():
                return {"content": "", "error": f"File not found: {file_path}"}
            
            with open(full_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            total_lines = len(lines)
            truncated = False
            
            if max_lines > 0 and total_lines > max_lines:
                content_lines = lines[:max_lines]
                truncated = True
            else:
                content_lines = lines
            
            content = ''.join(content_lines)
            
            return {
                "content": content,
                "line_count": total_lines,
                "truncated": truncated,
                "file": file_path
            }
        except Exception as e:
            return {"content": "", "error": str(e)}
    
    def search_in_files(self, search_term: str, directory: str = "", file_pattern: str = "*.md", max_results: int = 10) -> Dict[str, Any]:
        """Search for a term in files.
        
        Args:
            search_term: Text to search for (case-insensitive)
            directory: Relative path from docs_dir to search in (empty = all)
            file_pattern: File pattern to match (default: "*.md")
            max_results: Maximum number of results to return
        
        Returns:
            Dict with 'results' list containing matches
        """
        try:
            if directory:
                target_dir = self.docs_dir / directory
            else:
                target_dir = self.docs_dir
            
            if not target_dir.exists():
                return {"results": [], "error": f"Directory not found: {directory}"}
            
            results = []
            search_lower = search_term.lower()
            
            for file_path in target_dir.rglob(file_pattern):
                if file_path.is_file():
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                        
                        if search_lower in content.lower():
                            rel_path = file_path.relative_to(self.docs_dir)
                            # Count occurrences
                            count = content.lower().count(search_lower)
                            results.append({
                                "file": str(rel_path).replace("\\", "/"),
                                "matches": count
                            })
                            
                            if len(results) >= max_results:
                                break
                    except Exception:
                        continue  # Skip files that can't be read
            
            return {"results": results, "count": len(results)}
        except Exception as e:
            return {"results": [], "error": str(e)}
    
    def get_directory_structure(self, directory: str = "", max_depth: int = 2) -> Dict[str, Any]:
        """Get directory structure.
        
        Args:
            directory: Relative path from docs_dir (empty = root)
            max_depth: Maximum depth to traverse
        
        Returns:
            Dict with directory structure
        """
        try:
            if directory:
                target_dir = self.docs_dir / directory
            else:
                target_dir = self.docs_dir
            
            if not target_dir.exists():
                return {"structure": {}, "error": f"Directory not found: {directory}"}
            
            def build_tree(path: Path, current_depth: int = 0) -> Dict[str, Any]:
                if current_depth >= max_depth:
                    return {}
                
                tree = {}
                try:
                    for item in sorted(path.iterdir()):
                        if item.is_dir():
                            tree[item.name] = {
                                "type": "directory",
                                "contents": build_tree(item, current_depth + 1)
                            }
                        elif item.is_file() and item.suffix in ['.md', '.txt']:
                            tree[item.name] = {
                                "type": "file",
                                "size": item.stat().st_size
                            }
                except PermissionError:
                    pass
                
                return tree
            
            structure = build_tree(target_dir)
            return {"structure": structure, "path": directory or "root"}
        except Exception as e:
            return {"structure": {}, "error": str(e)}


def get_tools_definitions() -> List[Dict[str, Any]]:
    """Get OpenAI function calling tool definitions.
    
    Returns:
        List of tool definitions in OpenAI format
    """
    return [
        {
            "type": "function",
            "function": {
                "name": "list_files",
                "description": "List files in the documentation directory. Use this to explore available files, find character documents, or browse the docs structure.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "directory": {
                            "type": "string",
                            "description": "Relative path from docs_dir (e.g., 'character', 'guide', 'faq'). Empty string means root docs_dir."
                        },
                        "pattern": {
                            "type": "string",
                            "description": "File pattern to match (e.g., '*.md', '*Sylvia*', '100044-*'). Default: '*.md'"
                        }
                    },
                    "required": []
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "find_characters_by_pattern",
                "description": "Find character files matching a pattern. Use this when users ask about characters that 'start with X', 'contain Y', or similar pattern-based queries.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "starts_with": {
                            "type": "string",
                            "description": "Character name must start with this letter/string (case-insensitive). Example: 'S' to find characters starting with S."
                        },
                        "contains": {
                            "type": "string",
                            "description": "Character name or filename must contain this string (case-insensitive). Example: 'SP' to find SP characters."
                        },
                        "doc_type": {
                            "type": "string",
                            "description": "Document type to search. Default: 'character'",
                            "default": "character"
                        }
                    },
                    "required": []
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Read a file from the documentation directory. Use this to read specific character files, guides, or other documentation after finding them.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Relative path from docs_dir (e.g., 'character/100044-Sylvia_SP.md', 'guide/raids.md')"
                        },
                        "max_lines": {
                            "type": "integer",
                            "description": "Maximum number of lines to return. Default: 100. Set to 0 for entire file.",
                            "default": 100
                        }
                    },
                    "required": ["file_path"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "search_in_files",
                "description": "Search for a term across multiple files. Use this to find information that might be in multiple documents.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "search_term": {
                            "type": "string",
                            "description": "Text to search for (case-insensitive)"
                        },
                        "directory": {
                            "type": "string",
                            "description": "Relative path from docs_dir to search in. Empty string searches all docs."
                        },
                        "file_pattern": {
                            "type": "string",
                            "description": "File pattern to match. Default: '*.md'",
                            "default": "*.md"
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of results. Default: 10",
                            "default": 10
                        }
                    },
                    "required": ["search_term"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_directory_structure",
                "description": "Get the directory structure of the docs. Use this to understand the organization of documentation.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "directory": {
                            "type": "string",
                            "description": "Relative path from docs_dir. Empty string means root."
                        },
                        "max_depth": {
                            "type": "integer",
                            "description": "Maximum depth to traverse. Default: 2",
                            "default": 2
                        }
                    },
                    "required": []
                }
            }
        }
    ]

