"""Utility functions for RAG system."""

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


def format_source_links(metadata: dict, max_sources: int = 5, show_without_links: bool = False) -> list[str]:
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
    
    # Collect unique sources with line ranges
    seen_sources = {}
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
        
        # Create a unique key for this source+line range
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
            
            # Add to seen_sources even if no GitHub link (we'll show it without link)
            if file_path not in seen_sources:
                seen_sources[file_path] = {
                    "link": github_link,  # May be None
                    "start_line": start_line,
                    "end_line": end_line,
                }
    
    # Format source links
    if not seen_sources:
        # Debug: Log why no sources were found
        print(f"⚠️ Warning: No sources found from {num_chunks} retrieved chunks")
        if not RAGConfig.GITHUB_REPO_URL:
            print("   → GITHUB_REPO_URL not configured (sources will show without links)")
        return []
    
    # Check if we have any GitHub links
    has_github_links = any(link_info["link"] for link_info in seen_sources.values())
    
    # Only show sources if:
    # 1. We have GitHub links available, OR
    # 2. show_without_links is True (for debug command)
    if not has_github_links and not show_without_links:
        return []
    
    source_links_text = "**Sources**"

    # Generate link to docs directory
    docs_link = generate_github_docs_link()
    if docs_link:
        source_links_text = f"[{source_links_text} ↗]({docs_link})"
    for file_path, link_info in list(seen_sources.items())[:max_sources]:
        link = link_info["link"]
        start = link_info["start_line"]
        end = link_info["end_line"]
        
        # Format file name nicely
        file_name = file_path.split("/")[-1]
        
        # Add newline before source item (always add newline, even for first item for consistency)
        source_links_text += "\n"
        
        # Format with or without link
        if link:
            # Has GitHub link
            if start and end:
                source_links_text += f"• [{file_name} ↗]({link}) (lines {start}-{end})"
            elif start:
                source_links_text += f"• [{file_name} ↗]({link}) (line {start})"
            else:
                source_links_text += f"• [{file_name} ↗]({link})"
        else:
            # No GitHub link (GITHUB_REPO_URL not configured or no line numbers)
            # Only show if show_without_links is True
            if show_without_links:
                if start and end:
                    source_links_text += f"• `{file_name}` (lines {start}-{end})"
                elif start:
                    source_links_text += f"• `{file_name}` (line {start})"
                else:
                    source_links_text += f"• `{file_name}`"
    
    if len(seen_sources) > max_sources:
        source_links_text += f"\n*...and {len(seen_sources) - max_sources} more source(s)*"
    
    return [source_links_text]