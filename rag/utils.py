"""Utility functions for RAG system."""

from pathlib import Path
from rag.config import RAGConfig


def estimate_words_from_chunks(doc_count: int) -> int:
    """Estimate total words from document chunk count.
    
    Args:
        doc_count: Number of document chunks
        
    Returns:
        Estimated total word count
    """
    # Convert chunk size (characters) to words (avg 5 chars per word)
    words_per_chunk = RAGConfig.CHUNK_SIZE / 5
    return int(doc_count * words_per_chunk)


def format_word_count(estimated_words: int) -> str:
    """Format word count in a user-friendly way (k for thousands, M for millions).
    
    Args:
        estimated_words: Estimated word count
        
    Returns:
        Formatted string (e.g., "128k", "1.5M", "500")
    """
    if estimated_words >= 1000000:
        return f"{estimated_words / 1000000:.1f}M"
    elif estimated_words >= 1000:
        return f"{estimated_words / 1000:.0f}k"
    else:
        return f"{estimated_words:,}"


def is_cjk_query(query: str) -> bool:
    """Check if query contains CJK (Chinese, Japanese, Korean) characters.
    
    Args:
        query: Query string to check
        
    Returns:
        True if query contains CJK characters, False otherwise
    """
    # CJK = Chinese, Japanese, Korean character sets
    # Unicode ranges: \u4e00-\u9fff (CJK Unified Ideographs), 
    #                  \u3040-\u309f (Hiragana), \u30a0-\u30ff (Katakana)
    return any('\u4e00' <= char <= '\u9fff' or '\u3040' <= char <= '\u309f' or '\u30a0' <= char <= '\u30ff' for char in query)


def get_effective_threshold(query: str, base_threshold: float = None) -> float | None:
    """Get the effective threshold for a query, adjusted for cross-language queries.
    
    Cross-language queries (e.g., Japanese querying English docs) have naturally higher
    distance scores, so the threshold is increased by 25% for better results.
    
    Args:
        query: The query string
        base_threshold: Base threshold value from config (or None if not set)
        
    Returns:
        Effective threshold value (adjusted if needed) or None if base_threshold is None
    """
    if base_threshold is None:
        return None
    
    has_spaces = " " in query.strip()
    is_likely_cjk = is_cjk_query(query)
    
    # Adjust threshold for non-space languages or CJK characters
    if not has_spaces or is_likely_cjk:
        return base_threshold * 1.25  # Increase by 25% for cross-language queries
    
    return base_threshold


def find_text_in_file(file_path: str, search_text: str, start_search_line: int = 1) -> tuple[int, int] | None:
    """Find text in file and return its line range.
    
    This function searches for the given text in the original file and returns
    the exact line numbers where it appears. This can be used to verify/correct
    line numbers calculated during chunking.
    
    Args:
        file_path: Relative file path from docs_dir
        search_text: Text to search for (will be normalized - stripped)
        start_search_line: Line number to start searching from (1-indexed)
        
    Returns:
        Tuple of (start_line, end_line) if found, None otherwise
    """
    # Get full path to file
    full_path = RAGConfig.DOCS_DIR / file_path
    
    if not full_path.exists():
        return None
    
    try:
        with open(full_path, 'r', encoding='utf-8') as f:
            content = f.read()
            lines = content.split('\n')
        
        # Normalize search text (strip whitespace)
        search_text_normalized = search_text.strip()
        
        # Try to find the text in the file
        # Start searching from the specified line
        start_pos = 0
        if start_search_line > 1:
            # Calculate character position for start_search_line
            start_pos = len('\n'.join(lines[:start_search_line - 1])) + (1 if start_search_line > 1 else 0)
        
        # Find the text
        pos = content.find(search_text_normalized, start_pos)
        if pos == -1:
            # Try without the start position constraint
            pos = content.find(search_text_normalized)
        
        if pos == -1:
            return None
        
        # Calculate line numbers from position
        # Count newlines before the found position
        start_line = 1 + content[:pos].count('\n')
        # Count newlines in the search text to get end line
        end_line = start_line + search_text_normalized.count('\n')
        
        return (start_line, end_line)
    except Exception as e:
        print(f"⚠️ Error reading file {full_path}: {e}")
        return None


def extract_text_from_file(file_path: str, start_line: int, end_line: int = None) -> tuple[str, int, int]:
    """Extract exact text from original file using line numbers.
    
    This function reads the original file and extracts the exact text from the specified
    line range. This ensures that documentation.md and GitHub links use the exact same
    original text, avoiding any discrepancies from chunking/stripping.
    
    Args:
        file_path: Relative file path from docs_dir (e.g., "valkyries/100019-Emilius.md")
        start_line: Starting line number (1-indexed)
        end_line: Ending line number (1-indexed, optional. If None, uses start_line)
        
    Returns:
        Tuple of (extracted_text, actual_start_line, actual_end_line)
        The actual line numbers may differ if the requested lines don't exist
    """
    if end_line is None:
        end_line = start_line
    
    # Get full path to file
    full_path = RAGConfig.DOCS_DIR / file_path
    
    if not full_path.exists():
        return ("", start_line, end_line)
    
    try:
        with open(full_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # Adjust for 0-indexed array (line numbers are 1-indexed)
        start_idx = max(0, start_line - 1)
        end_idx = min(len(lines), end_line)
        
        # Extract the lines
        extracted_lines = lines[start_idx:end_idx]
        extracted_text = ''.join(extracted_lines).rstrip('\n')
        
        # Return actual line numbers used
        actual_start = start_idx + 1
        actual_end = end_idx
        
        return (extracted_text, actual_start, actual_end)
    except Exception as e:
        print(f"⚠️ Error reading file {full_path}: {e}")
        return ("", start_line, end_line)


def generate_github_link(file_path: str, start_line: int = None, end_line: int = None) -> str | None:
    """Generate a GitHub link to a file with optional line range.
    
    Args:
        file_path: Relative file path (e.g., "docs/valkyries/100001-Miranda.md")
        start_line: Starting line number (optional)
        end_line: Ending line number (optional)
        
    Returns:
        GitHub URL string, or None if GITHUB_REPO_URL is not configured
    """
    from rag.config import RAGConfig
    from urllib.parse import quote
    
    if not RAGConfig.GITHUB_REPO_URL:
        return None
    
    # Normalize file path (use forward slashes)
    normalized_path = file_path.replace("\\", "/")
    
    # URL-encode each path segment (but preserve slashes)
    # GitHub expects each path segment to be encoded separately
    path_segments = normalized_path.split("/")
    encoded_segments = [quote(segment, safe="") for segment in path_segments]
    encoded_path = "/".join(encoded_segments)
    
    # Build GitHub URL
    base_url = RAGConfig.GITHUB_REPO_URL.rstrip("/")
    
    # Remove /tree/branch if present (we'll add it back with blob)
    if "/tree/" in base_url:
        base_url = base_url.split("/tree/")[0]
    
    # GitHub blob URL format: https://github.com/user/repo/blob/branch/path
    # If no branch specified, use 'main' as default
    if "/blob/" not in base_url:
        # Try to extract branch from original URL if it had /tree/branch
        original_url = RAGConfig.GITHUB_REPO_URL
        if "/tree/" in original_url:
            branch = original_url.split("/tree/")[1].split("/")[0]
            url = f"{base_url}/blob/{branch}/{encoded_path}"
        else:
            # Default to main branch
            url = f"{base_url}/blob/main/{encoded_path}"
    else:
        # Already has blob, just append path
        url = f"{base_url}/{encoded_path}"
    
    # Add line range if provided
    # For Markdown files, GitHub requires ?plain=1 to enable line highlighting
    if start_line is not None:
        # Check if file is a markdown file
        is_markdown = normalized_path.lower().endswith(('.md', '.markdown'))
        if is_markdown:
            url += "?plain=1"
        
        if end_line is not None and end_line != start_line:
            url += f"#L{start_line}-L{end_line}"
        else:
            url += f"#L{start_line}"
    
    return url


def generate_github_docs_link() -> str | None:
    """Generate a GitHub link to the docs directory.
    
    Returns:
        GitHub URL string to the docs directory, or None if GITHUB_REPO_URL is not configured
    """
    from rag.config import RAGConfig
    
    if not RAGConfig.GITHUB_REPO_URL:
        return None
    
    # Build GitHub URL
    base_url = RAGConfig.GITHUB_REPO_URL.rstrip("/")
    
    # Remove /tree/branch and /blob/branch if present
    if "/tree/" in base_url:
        base_url = base_url.split("/tree/")[0]
    if "/blob/" in base_url:
        base_url = base_url.split("/blob/")[0]
    
    # GitHub tree URL format: https://github.com/user/repo/tree/branch/path
    # If no branch specified, use 'main' as default
    original_url = RAGConfig.GITHUB_REPO_URL
    if "/tree/" in original_url:
        branch = original_url.split("/tree/")[1].split("/")[0]
        docs_dir_name = RAGConfig.DOCS_DIR.name
        url = f"{base_url}/tree/{branch}/{docs_dir_name}"
    else:
        # Default to main branch
        docs_dir_name = RAGConfig.DOCS_DIR.name
        url = f"{base_url}/tree/main/{docs_dir_name}"
    
    return url


def read_external_link_from_meta(file_path: str) -> tuple[str, str] | None:
    """Read external link (with reference name) from .meta file next to the source file.
    
    The .meta file should be located next to the source file with the same name
    plus .meta extension (e.g., if file is "docs/guide/example.md", 
    the meta file would be "docs/guide/example.md.meta").
    
    The .meta file format:
    - First line: Reference name (e.g., "Discord", "Website", "Forum")
    - Second line: URL (e.g., "https://discord.com/channels/...")
    - If only one line exists, it's treated as the URL and "External" is used as the name
    
    Args:
        file_path: Relative file path from docs_dir (e.g., "guide/example.md")
        
    Returns:
        Tuple of (reference_name, url) if found, None otherwise
    """
    # Get full path to the .meta file
    full_path = RAGConfig.DOCS_DIR / f"{file_path}.meta"
    
    if not full_path.exists():
        return None
    
    try:
        with open(full_path, 'r', encoding='utf-8') as f:
            lines = [line.strip() for line in f.readlines() if line.strip()]
            
        if not lines:
            return None
        
        # If only one line, treat it as URL with default name
        if len(lines) == 1:
            return ("External", lines[0])
        
        # If two or more lines, first is name, second is URL
        return (lines[0], lines[1])
    except Exception as e:
        print(f"⚠️ Error reading .meta file {full_path}: {e}")
        return None


def format_source_links(metadata: dict, max_sources: int = 5, show_without_links: bool = False, display_line_numbers: bool = False) -> list[str]:
    """Format source links from retrieved chunks metadata.
    
    Args:
        metadata: Metadata dict containing 'retrieved_chunks' key
        max_sources: Maximum number of sources to display (default: 5)
        show_without_links: If True, show sources even without GitHub links (for debug command)
                           If False, only show sources if GitHub links are available
        
    Returns:
        List of formatted source link strings (empty list if no sources found or conditions not met)
    """
    if not metadata or not metadata.get("retrieved_chunks"):
        return []
    
    # Debug: Check if we have chunks
    num_chunks = len(metadata.get("retrieved_chunks", []))
    if num_chunks == 0:
        print("⚠️ Warning: metadata has 'retrieved_chunks' key but it's empty")
        return []
    
    # Collect sources with their line ranges
    # Use a list to preserve order and allow multiple chunks from same file
    source_entries = []
    seen_source_ranges = set()  # Track (file_path, start_line, end_line) to avoid exact duplicates
    
    for chunk in metadata.get("retrieved_chunks", []):
        source = chunk.get("source", "")
        chunk_metadata = chunk.get("metadata", {})
        
        # Debug: Log chunk structure if source is missing
        if not source:
            print(f"⚠️ Warning: Chunk missing 'source': {list(chunk.keys())}")
        
        # Handle metadata that might be stored as strings (ChromaDB converts to strings)
        if isinstance(chunk_metadata, dict):
            start_line_str = chunk_metadata.get("start_line")
            end_line_str = chunk_metadata.get("end_line")
            # Convert string to int if needed
            try:
                start_line = int(start_line_str) if start_line_str else None
            except (ValueError, TypeError):
                start_line = None
            try:
                end_line = int(end_line_str) if end_line_str else None
            except (ValueError, TypeError):
                end_line = None
        else:
            start_line = None
            end_line = None
        
        # Create entry for this source+line range
        if source:
            # Get file path from metadata, fallback to source
            file_path = chunk_metadata.get("file_path", source) if isinstance(chunk_metadata, dict) else source
            # Normalize path (use forward slashes)
            file_path = file_path.replace("\\", "/")
            
            # Prepend DOCS_DIR to file path for GitHub links (file_path is relative to docs_dir)
            docs_dir_name = RAGConfig.DOCS_DIR.name  # Get just the directory name (e.g., "docs")
            github_file_path = f"{docs_dir_name}/{file_path}" if not file_path.startswith(f"{docs_dir_name}/") else file_path
            
            # Generate GitHub link (may be None if GITHUB_REPO_URL not configured)
            github_link = generate_github_link(github_file_path, start_line, end_line)
            
            # Create unique key for this source+line range combination
            range_key = (file_path, start_line, end_line)
            if range_key not in seen_source_ranges:
                seen_source_ranges.add(range_key)
                source_entries.append({
                    "file_path": file_path,
                    "link": github_link,  # May be None
                    "start_line": start_line,
                    "end_line": end_line,
                })
    
    # Format source links
    if not source_entries:
        # Debug: Log why no sources were found
        print(f"⚠️ Warning: No sources found from {num_chunks} retrieved chunks")
        if not RAGConfig.GITHUB_REPO_URL:
            print("   → GITHUB_REPO_URL not configured (sources will show without links)")
        return []
    
    # Check if we have any GitHub links
    has_github_links = any(entry["link"] for entry in source_entries)
    
    # Only show sources if:
    # 1. We have GitHub links available, OR
    # 2. show_without_links is True (for debug command)
    if not has_github_links and not show_without_links:
        return []
    
    source_links_text = "> -# **Source**"

    # Generate link to docs directory

    # DEPRECATED
    # docs_link = generate_github_docs_link()
    # if docs_link:
    #     source_links_text = f"[{source_links_text} ↗]({docs_link})"
    
    for entry in source_entries[:max_sources]:
        file_path = entry["file_path"]
        link = entry["link"]
        start = entry["start_line"]
        end = entry["end_line"]
        
        # Try to read external link from .meta file
        external_link_info = read_external_link_from_meta(file_path)
        
        # Format file name nicely
        file_name = file_path.split("/")[-1]
        
        # Add newline before source item (always add newline, even for first item for consistency)
        source_links_text += "\n"
        
        # Format with or without link
        if link:
            # Has GitHub link (angle brackets suppress Discord link previews)
            if display_line_numbers and start and end:
                base_text = f"> -# • [{file_name} ↗](<{link}>) (lines {start}-{end})"
            elif display_line_numbers and start:
                base_text = f"> -# • [{file_name} ↗](<{link}>) (line {start})"
            else:
                base_text = f"> -# • [{file_name} ↗](<{link}>)"
            
            # Add external link if available
            if external_link_info:
                ref_name, external_url = external_link_info
                source_links_text += f"{base_text} | [{ref_name} ↗](<{external_url}>)"
            else:
                source_links_text += base_text
        else:
            # No GitHub link (GITHUB_REPO_URL not configured or no line numbers)
            # Only show if show_without_links is True
            if show_without_links:
                if display_line_numbers and start and end:
                    base_text = f"> -# • `{file_name}` (lines {start}-{end})"
                elif display_line_numbers and start:
                    base_text = f"> -# • `{file_name}` (line {start})"
                else:
                    base_text = f"> -# • `{file_name}`"
                
                # Add external link if available
                if external_link_info:
                    ref_name, external_url = external_link_info
                    source_links_text += f"{base_text} | [{ref_name} ↗](<{external_url}>)"
                else:
                    source_links_text += base_text
    
    if len(source_entries) > max_sources:
        source_links_text += f"\n*...and {len(source_entries) - max_sources} more source(s)*"
    
    return [source_links_text]