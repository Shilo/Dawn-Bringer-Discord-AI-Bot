# Status messages for processing updates
class StatusMessage:
    THINKING = 0
    SEARCHING_KNOWLEDGE_BASE = 1
    SEARCHING_VECTOR_DATABASE = 2
    PROCESSING_RETRIEVED_DOCS = 3
    FORMATTING_DOC_CONTEXT = 4
    GENERATING_RESPONSE = 5
    PROCESSING_AI_RESPONSE = 6


STATUS_MESSAGES = [
    "Thinking",  # StatusMessage.THINKING
    "Searching knowledge base",  # StatusMessage.SEARCHING_KNOWLEDGE_BASE
    "Searching vector database",  # StatusMessage.SEARCHING_VECTOR_DATABASE
    "Processing retrieved documents",  # StatusMessage.PROCESSING_RETRIEVED_DOCS
    "Formatting document context",  # StatusMessage.FORMATTING_DOC_CONTEXT
    "Generating response",  # StatusMessage.GENERATING_RESPONSE
    "Processing AI response",  # StatusMessage.PROCESSING_AI_RESPONSE
]


def get_status_message(status_index: int) -> str:
    """Get a status message wrapped in bold markdown formatting.

    Args:
        status_index: Index of the status message to retrieve

    Returns:
        Status message wrapped in ** ** for bold formatting
    """
    message = (
        STATUS_MESSAGES[status_index]
        if 0 <= status_index < len(STATUS_MESSAGES)
        else "Thinking"
    )
    return f"-# ⏳ {message}..."
