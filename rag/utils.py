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

