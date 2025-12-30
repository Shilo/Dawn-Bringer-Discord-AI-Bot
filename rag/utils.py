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
    
    if not RAGConfig.GITHUB_REPO_URL:
        return None
    
    # Normalize file path (use forward slashes)
    normalized_path = file_path.replace("\\", "/")
    
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
            url = f"{base_url}/blob/{branch}/{normalized_path}"
        else:
            # Default to main branch
            url = f"{base_url}/blob/main/{normalized_path}"
    else:
        # Already has blob, just append path
        url = f"{base_url}/{normalized_path}"
    
    # Add line range if provided
    if start_line is not None:
        if end_line is not None and end_line != start_line:
            url += f"#L{start_line}-L{end_line}"
        else:
            url += f"#L{start_line}"
    
    return url