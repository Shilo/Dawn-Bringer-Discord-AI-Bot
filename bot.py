import os
import discord
from discord import app_commands
from openai import OpenAI
from dotenv import load_dotenv
import signal
import asyncio
import time
import argparse
import re
import socket
from datetime import datetime, timezone
from pathlib import Path

from views import RegenerateView

load_dotenv()

# RAG system imports
from configs import Config

Config.load_from_env()  # Load environment variables into config
from rag.document_loader import DocumentLoader
from rag.vector_store import VectorStore
from rag.retriever import RAGRetriever
from rag.chain import RAGChain
from rag.utils import estimate_words_from_chunks, format_word_count
from rag.openai_client import prompt_openai

# Import status messages from constants module
from constants import StatusMessage, get_status_message

# Gift code channel configuration
# Set these environment variables or modify directly:
# GIFT_CODE_SERVER_ID: Discord server (guild) ID where the gift code channel is located
# GIFT_CODE_CHANNEL_NAME: Name of the channel to search for gift codes
GIFT_CODE_SERVER_ID = os.getenv(
    "GIFT_CODE_SERVER_ID", None
)  # Set to None to disable, or provide server ID as string
GIFT_CODE_CHANNEL_NAME = os.getenv(
    "GIFT_CODE_CHANNEL_NAME", "gift-codes"
)  # Default channel name

# OpenAI API pricing per 1M tokens (as of 2024)
# Source: https://openai.com/api/pricing/
MODEL_PRICING = {
    "gpt-4o-mini": {
        "input": 0.150,  # $0.150 per 1M input tokens
        "output": 0.600,  # $0.600 per 1M output tokens
    },
    "gpt-5": {
        "input": 2.50,  # $2.50 per 1M input tokens
        "output": 10.00,  # $10.00 per 1M output tokens
    },
    "gpt-5-mini": {
        "input": 0.25,  # $0.25 per 1M input tokens
        "output": 2.00,  # $2.00 per 1M output tokens
    },
    "gpt-5-nano": {
        "input": 0.075,  # $0.075 per 1M input tokens
        "output": 0.300,  # $0.300 per 1M output tokens
    },
}

# Bot Personality and Rules
# Note: This is sent with every message, so keep it concise to save tokens
SYSTEM_PROMPT_FILE = "system_prompt.txt"

# Global flag for rebuilding vector store (set via CLI argument or environment variable)
FORCE_REBUILD_VECTOR_STORE = False


def get_lan_ip() -> str:
    """Get the local area network IP address."""
    try:
        # Create a socket and connect to a remote host to determine local IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))  # Connect to Google's DNS server
        lan_ip = s.getsockname()[0]
        s.close()

        # Validate that this is a private network IP (not public)
        if lan_ip.startswith(("192.168.", "10.", "172.")):
            return lan_ip
        else:
            print(f"Warning: Detected IP {lan_ip} is not a private network address")

    except Exception as e:
        print(f"Warning: Could not determine LAN IP: {e}")

    # Fallback: Try to get IP by connecting to a local gateway
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("192.168.1.1", 80))  # Try common gateway
        lan_ip = s.getsockname()[0]
        s.close()
        if lan_ip.startswith(("192.168.", "10.", "172.")):
            return lan_ip
    except Exception:
        pass

    # Last resort: return localhost
    return "127.0.0.1"


def load_system_prompt() -> str:
    """Load the system prompt from file."""
    try:
        with open(SYSTEM_PROMPT_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        print(f"⚠️ Warning: {SYSTEM_PROMPT_FILE} not found. Using default prompt.")
    except Exception as e:
        print(f"❌ Error loading system prompt: {e}. Using default prompt.")
    return "You are Dawn Bringer, a helpful Discord AI assistant."


def load_fallback_gift_code_doc() -> str:
    """Load the fallback gift code documentation from file."""
    fallback_file = Path(__file__).parent / "gift-code-fallback.md"
    try:
        with open(fallback_file, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        print(f"⚠️ Warning: {fallback_file} not found. Using default fallback.")
        return "# Gift Code Information Unavailable\n\nUnable to access gift code channel. Please try again later."
    except Exception as e:
        print(f"❌ Error loading fallback gift code doc: {e}. Using default fallback.")
        return "# Gift Code Information Unavailable\n\nUnable to access gift code channel. Please try again later."


SYSTEM_PROMPT = load_system_prompt()


def calculate_cost(
    prompt_tokens: int, completion_tokens: int, model: str = Config.MODEL
) -> float:
    """Calculate the cost in USD based on token usage and model pricing.

    Args:
        prompt_tokens: Number of input/prompt tokens
        completion_tokens: Number of output/completion tokens
        model: Model name (defaults to Config.MODEL)

    Returns:
        Total cost in USD
    """
    if model not in MODEL_PRICING:
        return 0.0  # Unknown model, return 0

    pricing = MODEL_PRICING[model]
    input_cost = (prompt_tokens / 1_000_000) * pricing["input"]
    output_cost = (completion_tokens / 1_000_000) * pricing["output"]

    return input_cost + output_cost


def get_token_info(token_usage, model: str = Config.MODEL) -> str:
    """Format token usage and cost information.

    Args:
        token_usage: OpenAI Usage object with prompt_tokens, completion_tokens, total_tokens
        model: Model name (defaults to Config.MODEL)

    Returns:
        Formatted string with cost and token information
    """
    cost = calculate_cost(
        token_usage.prompt_tokens, token_usage.completion_tokens, model
    )
    return f"-# `💵 ${cost:.6f} | 🪙 {token_usage.total_tokens} ({token_usage.prompt_tokens} prompt + {token_usage.completion_tokens} completion)`"


# Import shared state for RAG chain access
from shared_state import get_rag_chain, set_rag_chain

# Track startup time
startup_start_time: float | None = None


def split_message(content: str, max_length: int = 2000) -> list[str]:
    """Split a message into chunks that fit within Discord's character limit.

    Preserves code blocks by never splitting inside them. If a split is needed
    while in a code block, it closes the block and reopens it in the next chunk.

    Args:
        content: The message content to split
        max_length: Maximum length per chunk (default 2000 for Discord)

    Returns:
        List of message chunks
    """
    if len(content) <= max_length:
        return [content]

    chunks = []
    current_chunk = ""
    in_code_block = False
    code_block_delimiter = "```"

    # Split by newlines first to preserve formatting
    lines = content.split("\n")

    i = 0
    while i < len(lines):
        line = lines[i]

        # Track code block state by counting delimiters
        delimiter_count = line.count(code_block_delimiter)
        was_in_code_block = in_code_block
        if delimiter_count > 0:
            # Toggle state for each delimiter (handles edge cases like ``` on same line)
            for _ in range(delimiter_count):
                in_code_block = not in_code_block

        line_with_newline = line + "\n"
        potential_chunk = current_chunk + line_with_newline

        # If adding this line would exceed limit
        if len(potential_chunk) > max_length:
            # If we're in a code block (or were before this line), we need to close it first
            if was_in_code_block:
                # Check if adding the closing delimiter would exceed limit
                closing_delimiter = code_block_delimiter + "\n"
                if len(current_chunk) + len(closing_delimiter) > max_length:
                    # Save current chunk first, then start new one with closing delimiter
                    if current_chunk.strip():
                        chunks.append(current_chunk.rstrip())
                    current_chunk = closing_delimiter
                else:
                    current_chunk += closing_delimiter
                in_code_block = False

            # Save current chunk if it has content
            if current_chunk.strip():
                chunks.append(current_chunk.rstrip())
                current_chunk = ""

            # If we were in a code block, reopen it in the new chunk
            if was_in_code_block:
                current_chunk = code_block_delimiter + "\n"
                in_code_block = True

            # If the line itself is too long, split it
            if len(line_with_newline) > max_length:
                if not in_code_block:
                    # Split by words if not in code block
                    words = line.split(" ")
                    for word in words:
                        if len(current_chunk) + len(word) + 1 > max_length:
                            if current_chunk:
                                chunks.append(current_chunk.rstrip())
                                current_chunk = ""
                        current_chunk += word + " " if current_chunk else word + " "
                    i += 1
                    continue
                else:
                    # In code block - just truncate the line to fit
                    remaining_space = max_length - len(current_chunk) - 1
                    if remaining_space > 0:
                        current_chunk += line[:remaining_space] + "\n"
                    # Close code block and start new chunk
                    current_chunk += code_block_delimiter
                    chunks.append(current_chunk.rstrip())
                    current_chunk = (
                        code_block_delimiter + "\n" + line[remaining_space:] + "\n"
                    )
                    i += 1
                    continue

        # Add line to current chunk
        current_chunk += line_with_newline
        i += 1

    # Add remaining chunk
    if current_chunk.strip():
        # Close any open code block
        if in_code_block:
            current_chunk += code_block_delimiter
        chunks.append(current_chunk.rstrip())

    # Safety check: ensure no chunk exceeds the limit (split further if needed)
    final_chunks = []
    for chunk in chunks:
        if len(chunk) <= max_length:
            final_chunks.append(chunk)
        else:
            # Emergency split: split by words if chunk is too long
            words = chunk.split(" ")
            current = ""
            for word in words:
                if len(current) + len(word) + 1 > max_length:
                    if current:
                        final_chunks.append(current.rstrip())
                    current = word + " "
                else:
                    current += word + " "
            if current:
                final_chunks.append(current.rstrip())

    return final_chunks


async def send_response_message(
    message: discord.Message,
    response_text: str,
    token_usage,
    metadata: dict = None,
    prompt: str = None,
    edit_message: discord.Message = None,
):
    """Send a response message with token info, splitting into chunks if necessary.

    Args:
        message: The Discord message to reply to
        response_text: The response text to send
        token_usage: The token usage object from OpenAI
        metadata: Optional metadata dict containing sources and retrieved_chunks
        prompt: The original prompt/question (used for regenerate button)
        edit_message: Optional existing message to edit instead of sending a new reply
    """
    # Log critical response information for Railway deployment
    channel_name = get_channel_name(message.channel)
    cost = calculate_cost(
        token_usage.prompt_tokens, token_usage.completion_tokens, Config.MODEL
    )
    print(
        f"📤 Response sent | User: {message.author} | Channel: {channel_name} | Cost: ${cost:.6f} | Tokens: {token_usage.total_tokens} ({token_usage.prompt_tokens} prompt + {token_usage.completion_tokens} completion) | Response length: {len(response_text)} chars"
    )

    # Get token info and combine with response
    token_info = get_token_info(token_usage, Config.MODEL)

    # Generate GitHub source links if available
    source_links = []
    from rag.utils import format_source_links

    source_links = format_source_links(metadata, max_sources=5)

    # Combine response, source links, and token info
    full_message = response_text
    if source_links:
        full_message += "\n\n" + "".join(source_links)
    full_message += "\n\n" + token_info

    # Split into chunks if too long
    message_chunks = split_message(full_message)

    # Create regenerate view if prompt is provided
    view = None
    if prompt:
        # Add token_usage to metadata so it can be used for sharing
        if metadata is None:
            metadata = {}
        metadata["token_usage"] = token_usage

        view = RegenerateView(
            message,
            prompt,
            get_ai_response,
            strip_unimportant_response,
            is_direct_question,
            get_token_info,
            split_message,
            Config.MODEL,
            SYSTEM_PROMPT,
            response_text=response_text,  # Pass full response text for sharing
            metadata=metadata,  # Pass metadata for sources and token usage
        )

    # Send all chunks, with regenerate button on the last message
    last_message = None
    for i, chunk in enumerate(message_chunks):
        is_last = i == len(message_chunks) - 1
        if i == 0:
            if edit_message:
                # Edit the existing message
                if view and is_last:
                    # Only one chunk, attach view to it
                    await edit_message.edit(content=chunk, view=view)
                    # Store reference to the message in the view for timeout handling
                    view.message = edit_message
                    last_message = edit_message
                else:
                    await edit_message.edit(content=chunk, view=None)
                    last_message = edit_message
            else:
                # Send new reply
                if view and is_last:
                    # Only one chunk, attach view to it
                    reply_msg = await message.reply(chunk, view=view)
                    # Store reference to the message in the view for timeout handling
                    view.message = reply_msg
                    last_message = reply_msg
                else:
                    reply_msg = await message.reply(chunk)
                    last_message = reply_msg
        else:
            if view and is_last:
                # Last chunk, attach view to it
                last_message = await message.channel.send(chunk, view=view)
                # Store reference to the message in the view for timeout handling
                view.message = last_message
            else:
                last_message = await message.channel.send(chunk)

    # Add thumbs up and thumbs down reactions to the last message
    if last_message:
        try:
            await last_message.add_reaction("👍")
            await last_message.add_reaction("👎")
        except:
            pass  # Ignore errors (e.g., missing permissions, deleted message)


def initialize_rag_system(force_rebuild: bool = False) -> RAGChain:
    """Initialize the RAG system.

    Args:
        force_rebuild: If True, rebuild the vector store even if it exists

    Returns:
        Initialized RAGChain instance
    """
    start_time = time.time()
    print("\n🔧 Initializing RAG system...")

    # Load documents
    loader = DocumentLoader(Config.DOCS_DIR)
    documents = loader.load_all_documents()

    if not documents:
        print("⚠️ No documents found. RAG system will not work properly.")
        return None

    # Initialize vector store
    vector_store = VectorStore(force_rebuild=force_rebuild)

    # Check if we need to rebuild
    if vector_store._should_rebuild():
        print("📦 Building vector store from documents...")
        vector_store.build_vector_store(documents)
    else:
        print("📂 Using existing vector store...")
        vector_store.get_vector_store()  # Load existing

    # Initialize retriever (verbose=False for production)
    retriever = RAGRetriever(vector_store, verbose=False)

    # Initialize RAG chain
    chain = RAGChain(
        retriever=retriever,
        model_name=Config.MODEL,
        max_tokens=Config.MAX_TOKENS,
        temperature=Config.TEMPERATURE,
        system_prompt=SYSTEM_PROMPT,
        verbosity=Config.GPT5_VERBOSITY,
        reasoning_effort=Config.GPT5_EFFORT,
    )

    return chain


def get_rag_chain():
    """Get the current rag_chain instance.

    Returns:
        RAGChain instance or None if not initialized
    """
    # Use shared state (single source of truth)
    from shared_state import get_rag_chain as _get_rag_chain

    return _get_rag_chain()


def get_knowledge_stats_string() -> str:
    """Get a formatted string showing the bot's knowledge base stats.

    Returns:
        Formatted string with vector store stats, or "Initializing..." if not ready
    """
    from configs import Config

    # Use shared state (single source of truth)
    from shared_state import get_rag_chain

    rag_chain = get_rag_chain()

    if rag_chain is None:
        return "Initializing knowledge base..."

    try:
        stats = rag_chain.retriever.vector_store.get_stats()
        doc_count = stats.get("document_count", 0)
        estimated_words = estimate_words_from_chunks(doc_count)
        word_display = format_word_count(estimated_words)

        # Format model name nicely (uppercase GPT prefix, title case the rest)
        model_name = re.sub(
            r"\b([a-zA-Z]+)\b",
            lambda m: m.group(1).title(),
            Config.MODEL.replace("-", " "),
        )
        if model_name.startswith("Gpt"):
            model_name = "GPT" + model_name[3:]

        return f"- AI Model: `{model_name}`\n- Knowledge Base: `{word_display} words, {doc_count:,} articles`"
    except Exception as e:
        print(f"- Error getting knowledge stats: {e}")
        return "- Knowledge base unavailable"


def log_web_interface_url():
    """Log the web interface URL based on the current environment."""
    web_port = int(os.getenv("PORT", 8000))
    railway_public_domain = os.getenv("RAILWAY_PUBLIC_DOMAIN")
    railway_environment = os.getenv("RAILWAY_ENVIRONMENT")

    if railway_public_domain:
        # On Railway with public domain configured
        web_url = f"https://{railway_public_domain}"
        print(f"🌐 Web interface: {web_url}")
    elif railway_environment:
        # On Railway but no public domain yet - need to generate one
        print(
            f"🌐 Web interface: Railway port {web_port} (generate domain in Networking tab)"
        )
    else:
        # Local development
        lan_ip = get_lan_ip()
        localhost_url = f"http://localhost:{web_port}"
        lan_url = f"http://{lan_ip}:{web_port}"
        print(f"🌐 Web interface: {localhost_url}")
        print(f"🌐 LAN access: {lan_url}")


intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# Flags to track bot state (to skip duplicate logout messages)
is_restarting = False
is_shutting_down = False

# Flag to track if we've completed initial connection (to distinguish from reconnections)
has_connected = False

# Use shared state for client_ready to ensure it's accessible across module imports
from shared_state import get_client_ready, set_client_ready


async def get_ai_response(
    prompt: str,
    include_scores: bool = False,
    max_tokens_override: int = None,
    top_k_override: int = None,
    score_threshold_override: float = None,
    system_prompt_override: str = None,
    status_updater=None,
) -> tuple[str, object, str, dict]:
    """Get a response from OpenAI with RAG system.

    Args:
        prompt: User's question/prompt
        include_scores: If True, retrieve similarity scores (adds overhead - only use for debugging)
        max_tokens_override: Optional override for max_tokens (temporary, doesn't change global setting)
        top_k_override: Optional override for top_k retrieval (temporary, doesn't change global setting)
        score_threshold_override: Optional override for score threshold (temporary, doesn't change global setting)
        system_prompt_override: Optional override for system prompt (temporary, doesn't change global setting)
        status_updater: Optional callback function to update status messages

    Returns:
        tuple: (response_text, usage_object, full_prompt, metadata)
        usage_object is the OpenAI Usage object with prompt_tokens, completion_tokens, total_tokens
        full_prompt is the full prompt sent to the API (system + user, may include documentation context)
        metadata is a dict containing sources, retrieved_chunks, etc.
    """
    # Use system prompt override if provided, otherwise use global
    system_prompt_to_use = (
        system_prompt_override if system_prompt_override is not None else SYSTEM_PROMPT
    )
    max_tokens_to_use = (
        max_tokens_override if max_tokens_override is not None else Config.MAX_TOKENS
    )

    # Get additional context if applicable (e.g., dynamic gift code document)
    additional_context, additional_metadata = await get_additional_context(prompt)

    # Update status to show we're searching knowledge base
    if status_updater:
        await status_updater(StatusMessage.SEARCHING_KNOWLEDGE_BASE)

    # Get rag_chain from shared state
    rag_chain = get_rag_chain()

    if rag_chain is None:
        # Fallback if RAG system not initialized
        # Add current date to system prompt so the model knows what today's date is
        current_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        system_prompt_with_date = (
            f"{system_prompt_to_use}\n\nCurrent date: {current_date} (UTC)"
        )

        messages = [
            {"role": "system", "content": system_prompt_with_date},
            {"role": "user", "content": prompt},
        ]
        if additional_context:
            messages[1][
                "content"
            ] = f"[Run! Goddess Documentation]\n\n{additional_context}\n\n---\n\n[User Question]\n{prompt}"
        full_prompt = (
            f"System: {system_prompt_with_date}\n\nUser: {messages[1]['content']}"
        )

        # Update status to show we're generating response (fallback mode without RAG)
        if status_updater:
            await status_updater(StatusMessage.GENERATING_RESPONSE)

        # Call the LLM using the unified function
        response_text, usage = prompt_openai(messages, max_tokens_to_use)

        # Update status to show we're processing the response
        if status_updater:
            await status_updater(StatusMessage.PROCESSING_AI_RESPONSE)

        metadata = {
            "sources": [],
            "retrieved_docs": 0,
            "full_prompt": full_prompt,
            "retrieved_chunks": [],
        }
        return response_text, usage, full_prompt, metadata

    # Temporarily override system prompt if provided
    original_system_prompt = None
    if system_prompt_override is not None:
        original_system_prompt = rag_chain.system_prompt
        rag_chain.system_prompt = system_prompt_override

    try:
        # Use RAG chain (without scores for normal queries - scores add overhead)
        response_text, usage, metadata = await rag_chain.query_with_usage(
            prompt,
            include_scores=include_scores,
            max_tokens_override=max_tokens_to_use,
            top_k_override=top_k_override,
            score_threshold_override=score_threshold_override,
            additional_context=additional_context,
            additional_metadata=additional_metadata,
            status_updater=status_updater,
        )
        # The full_prompt in metadata already uses the correct system prompt (from chain.py)
        full_prompt = metadata.get("full_prompt", prompt)
    finally:
        # Restore original system prompt if it was overridden
        if original_system_prompt is not None:
            rag_chain.system_prompt = original_system_prompt

    return response_text, usage, full_prompt, metadata


def strip_unimportant_response(response_text: str) -> tuple[str, bool]:
    """Strip the [[UNIMPORTANT]] marker from response text if present.

    Args:
        response_text: The response text from the AI

    Returns:
        Tuple of (stripped_response, is_unimportant) where:
        - stripped_response: The response with [[UNIMPORTANT]] marker removed if it was present
        - is_unimportant: True if the response had the [[UNIMPORTANT]] marker, False otherwise
    """
    import re

    # Use regex to find [[UNIMPORTANT]] anywhere in the text
    unimportant_pattern = r"\[\[UNIMPORTANT\]\]"

    if re.search(unimportant_pattern, response_text):
        # Remove the marker and clean up whitespace
        stripped = re.sub(unimportant_pattern, "", response_text)
        # Clean up extra whitespace that might result from removal
        stripped = re.sub(
            r"\n\s*\n\s*\n", "\n\n", stripped
        )  # Replace multiple newlines with double
        stripped = stripped.strip()
        return stripped, True

    return response_text, False


def is_question(text: str) -> bool:
    """Check if text is a question."""
    if "?" in text and len(text.strip()) > 1:
        if not is_part_of_url(text, text.find("?")):
            return True

    text_lower = text.lower().strip()
    if not text_lower:
        return False

    # Get first word
    space_idx = text_lower.find(" ")
    first_word = text_lower[:space_idx] if space_idx != -1 else text_lower

    # Check if first word is exactly in question starters
    if first_word in Config.QUESTION_STARTERS:
        return True

    # Check if first two words form a question starter (e.g., "but why", "and what", "but, when")
    if space_idx != -1:
        second_space_idx = text_lower.find(" ", space_idx + 1)
        second_word = (
            text_lower[space_idx + 1 : second_space_idx]
            if second_space_idx != -1
            else text_lower[space_idx + 1 :]
        )
        # Strip punctuation from the second word to handle cases like "but, why"
        second_word_clean = second_word.strip(Config.PUNCTUATION)
        if second_word_clean in Config.QUESTION_STARTERS:
            return True

    # Check for contractions (whats, what's, whos, who's, wheres, where's, etc.)
    # Common contraction patterns: 's, 're, 'd, 't, 'll, 've, or just 's' without apostrophe
    contraction_suffixes = ["'s", "'re", "'d", "'t", "'ll", "'ve", "s", "re", "d", "t"]
    for starter in Config.QUESTION_STARTERS:
        if first_word.startswith(starter):
            remaining = first_word[len(starter) :]
            # Check if remaining part is a valid contraction suffix
            if remaining and remaining in contraction_suffixes:
                return True
            # Also check for apostrophe variants
            if remaining.startswith("'") and remaining[1:] in [
                "s",
                "re",
                "d",
                "t",
                "ll",
                "ve",
            ]:
                return True

    return False


def is_part_of_url(text: str, position: int) -> bool:
    """Check if a position in text is part of an http:// or https:// URL.

    Uses regex to match URL patterns and checks if the position falls within a matched URL.
    URL pattern matches http:// or https:// followed by valid URL characters.

    Args:
        text: The full text to check
        position: The position (index) to check

    Returns:
        True if the position is part of an http:// or https:// URL, False otherwise
    """
    # Regex pattern to match http:// or https:// URLs
    # Matches: http:// or https:// followed by valid URL characters (letters, digits, and URL-safe chars)
    # URL continues until whitespace, end of string, or non-URL characters
    url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'

    # Find all URL matches in the text
    for match in re.finditer(url_pattern, text, re.IGNORECASE):
        # Check if the position falls within this URL match
        if match.start() <= position <= match.end():
            return True

    return False


def remove_start_mention(content: str, name: str) -> str:
    """Remove mention/name from start of content and strip leading punctuation."""
    content = content[len(name) :].strip()
    if content and content[0] in Config.PUNCTUATION:
        content = content[1:].strip()
    return content


def get_channel_name(channel: discord.TextChannel | discord.DMChannel) -> str:
    """Get channel name or identifier safely (handles both guild channels and DMs).

    Args:
        channel: Discord channel (TextChannel or DMChannel)

    Returns:
        Channel name for guild channels, or "DM with {recipient}" for DM channels
    """
    if isinstance(channel, discord.DMChannel):
        recipient = channel.recipient
        if recipient is None:
            return "DM"
        return f"DM with {recipient}"
    return channel.name


def is_gift_code_request(prompt: str) -> bool:
    """Check if the prompt is asking for gift codes or redemption codes.

    Args:
        prompt: The user's prompt/question

    Returns:
        True if the prompt is asking for gift codes, False otherwise
    """
    prompt_lower = prompt.lower().strip()

    # Phrases that indicate gift code requests (check as substrings)
    specific_phrases = ["code", "gift", "redemption", "redeem", "promo", "coupon"]

    # Check if any phrase appears as a substring (no word boundary requirement)
    for phrase in specific_phrases:
        if phrase in prompt_lower:
            return True

    return False


async def search_gift_code_channel(
    limit: int = 50,
) -> tuple[list[discord.Message], discord.TextChannel | None]:
    """Search the configured gift code channel for recent messages.

    Args:
        limit: Maximum number of messages to retrieve (default: 50)

    Returns:
        Tuple of (list of Discord messages, channel object) or ([], None) if channel not found
    """
    import asyncio

    if not GIFT_CODE_SERVER_ID or not GIFT_CODE_CHANNEL_NAME:
        print("⚠️ Gift code channel not configured")
        return [], None

    # Verify client is ready before attempting Discord operations

    # Use the client_ready flag from shared state as the primary check
    client_ready = get_client_ready(client)

    # If client is not ready according to shared state, don't attempt gift code search
    if not client_ready:
        print("⚠️ Discord client not ready")
        return [], None

    try:
        # Try to get channel from shared state first (cached when client is ready)
        from shared_state import get_gift_code_channel, set_gift_code_channel

        channel = get_gift_code_channel()

        if not channel:
            # Channel not in shared state - try to get it from client cache
            server_id = (
                int(GIFT_CODE_SERVER_ID)
                if isinstance(GIFT_CODE_SERVER_ID, str)
                else GIFT_CODE_SERVER_ID
            )
            guild = client.get_guild(server_id)
            if guild:
                channel = discord.utils.get(
                    guild.text_channels, name=GIFT_CODE_CHANNEL_NAME
                )
                if channel:
                    # Cache it for next time
                    set_gift_code_channel(channel)
                else:
                    print(f"❌ Gift code channel '{GIFT_CODE_CHANNEL_NAME}' not found")
                    return [], None
            else:
                print(f"❌ Guild not found: {server_id}")
                return [], None

        if not channel:
            print(f"❌ Gift code channel not found")
            return [], None

        # Check if bot has permission to read message history
        guild = channel.guild
        permissions = channel.permissions_for(guild.me)
        if not permissions.read_message_history:
            print(f"❌ No permission to read gift code channel")
            return [], None

        # Fetch recent messages
        messages = []

        try:
            # Use asyncio.wait_for to properly handle timeout within the task context
            async def fetch_messages():
                async for message in channel.history(limit=limit):
                    messages.append(message)

            # Use the shared state's run_in_discord_loop to ensure Discord operations run in the correct event loop
            from shared_state import run_in_discord_loop

            # Run the Discord operation in the correct event loop with timeout
            await asyncio.wait_for(run_in_discord_loop(fetch_messages()), timeout=30.0)
        except asyncio.TimeoutError:
            print("⚠️ Gift code fetch timeout")
            return [], channel
        except Exception as e:
            # Check if this is an asyncio context manager error
            if "Timeout context manager should be used inside a task" in str(e):
                print(
                    "⚠️ Asyncio context error - Discord client not properly initialized"
                )
                print("💡 This is normal during Railway deployments")
                return [], channel
            else:
                print(f"⚠️ Gift code fetch error: {type(e).__name__}")
                return [], channel

        return messages, channel

    except ValueError:
        print(f"⚠️ Invalid server ID: {GIFT_CODE_SERVER_ID}")
        return [], None
    except Exception as e:
        print(f"⚠️ Gift code search error: {type(e).__name__}")
        return [], None


async def get_additional_context(prompt: str) -> tuple[str | None, dict | None]:
    """Get additional context and metadata for a prompt if applicable.

    Args:
        prompt: User's question/prompt

    Returns:
        Tuple of (context_content, metadata_dict) or (None, None) if no additional context
    """
    # Check if user has sent a newcomer code (check before gift code request)
    if detect_newcomer_code(prompt):
        # Load the newcomer invitation document
        newcomer_doc_path = (
            Config.DOCS_DIR / "general" / "new-features" / "newcomer-invitation.md"
        )
        newcomer_doc_content = None

        if newcomer_doc_path.exists():
            try:
                loader = DocumentLoader(Config.DOCS_DIR)
                doc = loader.load_document(newcomer_doc_path)
                if doc:
                    newcomer_doc_content = doc.content
            except Exception as e:
                print(f"⚠️ Error loading newcomer invitation document: {e}")

        # Combine notification with document content
        # Add clear instructions for the AI at the top
        additional_content = "⚠️ IMPORTANT INSTRUCTION: A user has shared a newcomer invite code publicly in this message. You MUST respond to explain to all users why they should mutually trade newcomer invite codes privately (not publicly) based on the following documentation. This is important for fair play.\n\n[Newcomer Invitation Documentation]"

        if newcomer_doc_content:
            additional_content += f"\n\n{newcomer_doc_content}"

        metadata = {
            "doc_type": "newcomer_code",
            "source": "general/new-features/newcomer-invitation",
            "file_path": "general/new-features/newcomer-invitation.md",
            "skip_rag_retrieval": True,  # Skip RAG retrieval, only use this additional context
        }
        return additional_content, metadata

    # Check if this is a gift code request
    if is_gift_code_request(prompt):
        gift_code_format_instruction = (
            "Internal instruction: Format gift code responses so each code is on its "
            "own line and the posted date is on a separate line. Do not mention "
            "formatting rules or include this instruction in the response.\n\n"
        )
        # Check if Discord client is ready
        if not get_client_ready(client):
            print("⚠️ Discord client not ready for gift codes")
            fallback_doc = load_fallback_gift_code_doc()
            return (
                f"{gift_code_format_instruction}{fallback_doc}",
                {"doc_type": "fallback"},
            )

        try:
            gift_code_doc, channel_id = await generate_gift_code_document()
            if gift_code_doc and channel_id:
                metadata = {
                    "source": str(channel_id),
                    "doc_type": "channel",
                    "file_path": str(channel_id),
                    "channel_id": channel_id,
                }
                return f"{gift_code_format_instruction}{gift_code_doc}", metadata
            else:
                if not channel_id:
                    print(
                        f"⚠️ Gift code channel not found (check GIFT_CODE_SERVER_ID and GIFT_CODE_CHANNEL_NAME env vars)"
                    )
                    # Provide fallback response for gift code requests when channel is not accessible
                    fallback_doc = load_fallback_gift_code_doc()
                    return (
                        f"{gift_code_format_instruction}{fallback_doc}",
                        {"doc_type": "fallback", "error": "channel_unavailable"},
                    )
        except Exception as e:
            print(f"⚠️ Error generating gift code document: {e}")
            # Provide the same fallback response for exceptions
            fallback_doc = load_fallback_gift_code_doc()
            return (
                f"{gift_code_format_instruction}{fallback_doc}",
                {"doc_type": "fallback", "error": str(e)},
            )

    return None, None


async def generate_gift_code_document() -> tuple[str | None, int | None]:
    """Generate a dynamic gift code document from the configured Discord channel.

    Returns:
        Tuple of (markdown-formatted document string with gift codes, channel_id)
        Returns (None, None) if channel not configured/accessible
    """
    # Search gift code channel directly (no double task creation needed)
    messages, channel = await search_gift_code_channel(limit=5)

    if not messages or not channel:
        return None, None

    # Get channel ID for mention format
    channel_id = channel.id

    # Extract gift codes from messages
    gift_codes = []
    seen_codes = set()  # Avoid duplicates

    for msg in messages:
        # Start with original message content
        content_parts = []
        if msg.content.strip():
            content_parts.append(msg.content.strip())

        # Try to get forwarded message content (if available)
        forwarded_content = None
        if msg.reference and msg.reference.message_id:
            # Check if message is already resolved (cached)
            if msg.reference.resolved and isinstance(
                msg.reference.resolved, discord.Message
            ):
                forwarded_content = msg.reference.resolved.content.strip()
            else:
                # Try to fetch the referenced message (may fail for cross-server forwards)
                if msg.reference.channel_id:
                    ref_channel = client.get_channel(msg.reference.channel_id)
                    if not ref_channel and msg.reference.guild_id:
                        guild = client.get_guild(msg.reference.guild_id)
                        if guild:
                            ref_channel = guild.get_channel(
                                msg.reference.channel_id
                            ) or discord.utils.get(
                                guild.text_channels, id=msg.reference.channel_id
                            )

                    if ref_channel:
                        try:
                            # Ensure fetch_message runs in proper task context
                            referenced_msg = await asyncio.create_task(
                                ref_channel.fetch_message(msg.reference.message_id)
                            )
                            forwarded_content = referenced_msg.content.strip()
                        except (discord.NotFound, discord.Forbidden):
                            pass  # Expected for cross-server forwards or inaccessible channels

        # Append forwarded content if available
        if forwarded_content:
            content_parts.append(forwarded_content)

        # Combine all content
        content = "\n".join(content_parts)

        # Skip empty messages
        if not content:
            continue

        # Look for code-like patterns (alphanumeric, 5+ characters, starts with uppercase letter, all uppercase)
        # Pattern: sequences that start with an uppercase letter followed by 4+ uppercase letters or numbers
        code_patterns = re.findall(r"\b[A-Z][A-Z0-9]{4,}\b", content)

        for code in code_patterns:
            # Filter out duplicates
            if code not in seen_codes:
                gift_codes.append(
                    {
                        "code": code,
                        "posted_at": (
                            msg.created_at if hasattr(msg, "created_at") else None
                        ),
                    }
                )
                seen_codes.add(code)

    if not gift_codes:
        return None, None

    # Filter to only active codes (within 1 week of creation)
    from datetime import timedelta

    current_date = datetime.now(timezone.utc)
    week_ago = current_date - timedelta(days=7)

    active_codes = []
    for code_info in gift_codes:
        if code_info.get("posted_at"):
            # Only include codes created within the last week
            if code_info["posted_at"] >= week_ago:
                active_codes.append(
                    {
                        "code": code_info["code"],
                        "timestamp": code_info["posted_at"].strftime("%Y-%m-%d"),
                    }
                )

    # Generate markdown document
    # Add tags with relevant phrases to help the bot recognize and reference this document
    gift_code_phrases = ["code", "gift", "redemption", "redeem", "promo", "coupon"]
    tags_text = ", ".join(gift_code_phrases)

    # Use Discord's native channel mention format which supports emojis
    # Format: <#channel_id> will display as the channel name with emoji
    channel_mention = f"<#{channel_id}>"

    doc_lines = [
        "# Gift Codes (Redemption Codes)",
        "",
        f"**Tags:** {tags_text}",
        "",
        "**Note:** Gift codes expire within approximately 1 week from their creation date. Please use them soon!",
        "",
    ]

    if not active_codes:
        doc_lines.append(
            "No active gift codes found. All codes may have expired or there are no recent codes in the channel."
        )
    else:
        # Add active codes (most recent first, limit to 20)
        recent_codes = active_codes[:20]
        # Only use indexing if there's more than 1 code
        use_indexing = len(recent_codes) > 1

        for i, code_info in enumerate(recent_codes, 1):
            # Format each code with single backticks on its own line
            if use_indexing:
                # Use index numbering when multiple codes
                doc_lines.append(f"{i}.")
            # Code comes first
            doc_lines.append(f"```{code_info['code']}```")
            # Posted date comes after the code
            if code_info.get("timestamp"):
                doc_lines.append(f"Posted: {code_info['timestamp']}")
            doc_lines.append("")

    # if len(active_codes) > 20:
    #     doc_lines.append(f"\n*Note: Showing the 20 most recent active codes. There are {len(active_codes)} total active codes found.*")

    doc_lines.append("## How to Redeem")
    doc_lines.append("")
    doc_lines.append("1. Tap `Avatar → Settings → Redemption Code`")
    doc_lines.append("2. Enter code in `UPPERCASE`")
    doc_lines.append("")
    doc_lines.append(f"For more gift codes, check {channel_mention}.")
    doc_lines.append("")

    final_doc = "\n".join(doc_lines)
    return final_doc, channel_id


def is_direct_question(message: discord.Message) -> bool:
    """Check if the message is a direct question (mentions or bot names or !debug command).

    Args:
        message: The Discord message to check

    Returns:
        True if the bot is mentioned OR message starts with bot names OR is a !debug command OR is a DM, False otherwise
    """
    # Check if it's a DM (always treat DMs as direct questions)
    if isinstance(message.channel, discord.DMChannel):
        return True

    # Deprecated
    # # Check if in question channel (we know it's not a DM at this point)
    # if Config.QUESTION_CHANNEL_NAME and message.channel.name == Config.QUESTION_CHANNEL_NAME:
    #     return True

    # Check if bot is mentioned
    if client.user and client.user.mentioned_in(message):
        return True

    # Check if message starts with bot names
    content_lower = message.content.strip().lower()

    for name in Config.BOT_NAMES:
        # Check if message starts with the bot name (case-insensitive)
        if content_lower.startswith(name.lower()):
            return True

    # Check if message is a !debug command or !! shortcut
    if content_lower.startswith("!debug") or content_lower.startswith("!!"):
        return True

    return False


def get_prompt(message: discord.Message) -> str | None:
    """Extract prompt from Discord message.

    Checks for bot names or mentions in the message. If found at the start,
    strips the name/mention and leading punctuation from the content.

    Returns the processed content if:
    - Bot name is found at the start of the message
    - Bot is mentioned via Discord's mention system
    - Message is a question
    - Message is in a DM (always respond to DMs)
    - Message is in the question channel (always respond to question channel)
    - Message contains a newcomer code (10 uppercase letters, A-Z only)

    Returns None if none of the above conditions are met.
    """
    # For DMs and question channels, always respond (treat as direct conversation)
    if isinstance(message.channel, discord.DMChannel) or (
        Config.QUESTION_CHANNEL_NAME
        and message.channel.name == Config.QUESTION_CHANNEL_NAME
    ):
        content = message.content.strip()
        content_lower = content.lower()

        # Still check for bot names at the start to strip them if present
        for name in Config.BOT_NAMES:
            # Check if message starts with the bot name (case-insensitive)
            if content_lower.startswith(name.lower()):
                content = remove_start_mention(content, name)
                return content

        return content

    # For guild channels, use existing logic
    content = message.content.strip()
    content_lower = content.lower()

    for name in Config.BOT_NAMES:
        # Check if message starts with the bot name (case-insensitive)
        if content_lower.startswith(name.lower()):
            content = remove_start_mention(content, name)
            return content

    if client.user and client.user.mentioned_in(message):
        return content

    if is_question(content):
        return content

    # Check for newcomer codes at the end
    if detect_newcomer_code(content):
        return content

    return None


async def send_message_to_question_channel(
    message: str, error_context: str = "message"
):
    """Send a message to the question channel with proper error handling.

    Args:
        message: The message content to send
        error_context: Context for error messages (e.g., "login message", "logout message")
    """
    if not Config.QUESTION_CHANNEL_NAME:
        return

    for guild in client.guilds:
        channel = discord.utils.get(
            guild.text_channels, name=Config.QUESTION_CHANNEL_NAME
        )
        if channel:
            try:
                # Check if bot has permission to send messages
                if channel.permissions_for(guild.me).send_messages:
                    await channel.send(message)
                else:
                    print(
                        f"⚠️ Bot lacks permission to send messages in #{Config.QUESTION_CHANNEL_NAME}"
                    )
            except discord.Forbidden:
                print(
                    f"⚠️ Bot lacks access to send messages in #{Config.QUESTION_CHANNEL_NAME} (403 Forbidden)"
                )
            except Exception as e:
                print(f"⚠️ Error sending {error_context}: {e}")
            break


async def send_login_message():
    """Send the login message to the question channel with bot capabilities."""
    # Skip login message if running locally
    if not os.getenv("RAILWAY_ENVIRONMENT"):
        return

    login_message = f"Run! Goddess AI: `Online`\n{get_knowledge_stats_string()}"
    await send_message_to_question_channel(login_message, "login message")


async def send_logout_message():
    """Send logout message to question channel."""
    # Skip logout message if running locally
    if not os.getenv("RAILWAY_ENVIRONMENT"):
        return

    await send_message_to_question_channel(
        "Run! Goddess AI: `Offline`", "logout message"
    )


# Initialize command handler after all functions are defined
from commands import CommandHandler


def set_restarting_flag(value: bool):
    """Set the restarting flag to skip logout message during restart."""
    global is_restarting
    is_restarting = value


def set_shutting_down_flag(value: bool):
    """Set the shutting down flag to skip duplicate logout message."""
    global is_shutting_down
    is_shutting_down = value


command_handler = CommandHandler(
    get_ai_response_func=get_ai_response,
    get_token_info_func=get_token_info,
    send_response_message_func=send_response_message,
    get_prompt_func=get_prompt,
    model=Config.MODEL,
    get_knowledge_string_func=get_knowledge_stats_string,
    client=client,
    shutdown_event=None,  # Will be set in main()
    question_channel_name=Config.QUESTION_CHANNEL_NAME,
    set_restarting_flag_func=set_restarting_flag,
    set_shutting_down_flag_func=set_shutting_down_flag,
)


async def send_response_to_interaction(
    interaction: discord.Interaction,
    response_text: str,
    token_usage,
    metadata: dict = None,
    prompt: str = None,
):
    """Send a response to a Discord interaction (slash command).

    Args:
        interaction: The Discord interaction to respond to
        response_text: The response text to send
        token_usage: The token usage object from OpenAI
        metadata: Optional metadata dict containing sources and retrieved_chunks
        prompt: The original prompt/question (used for regenerate button)
    """
    # Log critical response information
    channel_name = (
        get_channel_name(interaction.channel) if interaction.channel else "DM"
    )
    cost = calculate_cost(
        token_usage.prompt_tokens, token_usage.completion_tokens, Config.MODEL
    )
    print(
        f"📤 Slash command response | User: {interaction.user} | Channel: {channel_name} | Cost: ${cost:.6f} | Tokens: {token_usage.total_tokens} ({token_usage.prompt_tokens} prompt + {token_usage.completion_tokens} completion) | Response length: {len(response_text)} chars"
    )

    # Get token info and combine with response
    token_info = get_token_info(token_usage, Config.MODEL)

    # Generate GitHub source links if available
    source_links = []
    from rag.utils import format_source_links

    source_links = format_source_links(metadata, max_sources=5)

    # Combine response, source links, and token info
    full_message = response_text
    if source_links:
        full_message += "\n\n" + "".join(source_links)
    full_message += "\n\n" + token_info

    # Split into chunks if too long
    message_chunks = split_message(full_message)

    # Create InteractionRegenerateView for slash commands
    from views import InteractionRegenerateView

    view = InteractionRegenerateView(
        interaction,
        prompt,
        get_ai_response,
        strip_unimportant_response,
        is_direct_question,
        get_token_info,
        split_message,
        Config.MODEL,
        SYSTEM_PROMPT,
        response_text=response_text,  # Pass full response text for sharing
        metadata=metadata,  # Pass metadata for sources and token usage
    )

    # Send all chunks
    last_message = None
    for i, chunk in enumerate(message_chunks):
        is_last = i == len(message_chunks) - 1
        if i == 0:
            # First chunk - edit the original deferred response
            if is_last and view:
                # Only one chunk, attach view to it
                try:
                    await interaction.edit_original_response(content=chunk, view=view)
                    # For single chunk, try to get the message for reactions and view updates
                    try:
                        last_message = await interaction.original_response()
                        # Store message reference in view for button updates
                        if view:
                            view.message = last_message
                    except:
                        last_message = None
                except discord.NotFound:
                    # If original response was already sent, use followup
                    last_message = await interaction.followup.send(chunk, view=view)
                    # Store message reference in view for button updates
                    if view:
                        view.message = last_message
            else:
                try:
                    await interaction.edit_original_response(content=chunk)
                except discord.NotFound:
                    # If original response was already sent, use followup
                    last_message = await interaction.followup.send(chunk)
        else:
            # Subsequent chunks - use followup
            if is_last and view:
                # Last chunk, attach view to it
                last_message = await interaction.followup.send(chunk, view=view)
                # Store message reference in view for button updates
                if view:
                    view.message = last_message
            else:
                last_message = await interaction.followup.send(chunk)

    # Add reactions to the last message that contains the response
    if last_message:
        try:
            await last_message.add_reaction("👍")
            await last_message.add_reaction("👎")
        except Exception as e:
            # Ignore errors (e.g., missing permissions, deleted message)
            pass


async def handle_dawnbringer_command(interaction: discord.Interaction, message: str):
    """Shared handler for Dawn Bringer slash commands.

    Args:
        interaction: The Discord interaction
        message: The user's message/question
    """
    # Send custom thinking message instead of deferring
    await interaction.response.send_message(get_status_message(StatusMessage.THINKING))

    async def update_status(status_index: int):
        try:
            await interaction.edit_original_response(
                content=get_status_message(status_index)
            )
        except:
            pass  # Ignore errors when updating status

    try:
        # Process the prompt using the same logic as regular messages
        # For slash commands, always treat as direct questions
        result = await process_user_prompt(
            message, is_direct=True, status_updater=update_status
        )
        if result is None:
            await interaction.edit_original_response(
                content="❌ Unable to process your message. Please try again."
            )
            return

        response_text, token_usage, metadata = result

        # Send response using interaction-specific function
        await send_response_to_interaction(
            interaction, response_text, token_usage, metadata, prompt=message
        )
    except Exception as e:
        print(f"❌ Error handling slash command: {e}")
        import traceback

        print(traceback.format_exc())
        try:
            await interaction.edit_original_response(
                content="❌ An error occurred while processing your request. Please try again."
            )
        except:
            pass  # Ignore errors when sending error message


@tree.command(
    name="dawnbringer",
    description="Send a message to Dawn Bringer AI assistant in current channel",
)
@app_commands.describe(message="Your question or message to the AI assistant")
async def dawnbringer_command(interaction: discord.Interaction, message: str):
    """Slash command handler for /dawnbringer command."""
    await handle_dawnbringer_command(interaction, message)


@tree.command(
    name="db",
    description="Send a message to Dawn Bringer AI assistant in current channel (alias)",
)
@app_commands.describe(message="Your question or message to the AI assistant")
async def db_command(interaction: discord.Interaction, message: str):
    """Slash command handler for /db command (alias for /dawnbringer)."""
    await handle_dawnbringer_command(interaction, message)


@tree.command(
    name="chat", description="Open a Direct Message with Dawn Bringer AI assistant"
)
async def chat_command(interaction: discord.Interaction):
    """Slash command handler for /chat command."""
    # Defer the response
    await interaction.response.defer(ephemeral=True)

    try:
        # Create/open DM channel
        dm_channel = await interaction.user.create_dm()

        # Send a greeting message to open the DM window
        greeting = "👋 Hello!\nI am your **Run! Goddess AI**.\n\nHow can I help you?"

        await dm_channel.send(greeting)

        # Send ephemeral confirmation
        await interaction.followup.send(
            "✅ I've opened a DM with you! Check your direct messages.", ephemeral=True
        )
    except discord.Forbidden:
        # User has DMs disabled or blocked the bot
        await interaction.followup.send(
            "❌ I couldn't send you a DM. Please enable DMs from server members or open a DM with me manually first.",
            ephemeral=True,
        )
    except Exception as e:
        print(f"❌ Error opening DM: {e}")
        import traceback

        print(traceback.format_exc())
        await interaction.followup.send(
            "❌ An error occurred while trying to open a DM. Please try again or open a DM with me manually.",
            ephemeral=True,
        )


@tree.error
async def on_app_command_error(
    interaction: discord.Interaction, error: app_commands.AppCommandError
):
    """Handle errors for slash commands."""
    print(f"❌ Slash command error: {error}")
    import traceback

    print(traceback.format_exc())

    # Try to send an error message to the user
    try:
        if interaction.response.is_done():
            await interaction.followup.send(
                "❌ An error occurred while processing your command. Please try again."
            )
        else:
            await interaction.response.send_message(
                "❌ An error occurred while processing your command. Please try again.",
                ephemeral=True,
            )
    except:
        pass  # Ignore errors when sending error message


@client.event
async def on_ready():
    global startup_start_time, FORCE_REBUILD_VECTOR_STORE, has_connected

    # Check if this is the initial connection or a reconnection
    is_reconnection = has_connected
    if is_reconnection:
        print("🔄 Reconnected to Discord")
    else:
        print(f"🚪 Connected to Discord as {client.user}")

    # Set client_ready flag in shared state - this is reliable across async contexts and module imports
    set_client_ready(True)

    # Set the Discord event loop for cross-thread operations
    from shared_state import set_discord_loop

    set_discord_loop(asyncio.get_running_loop())

    # Initialize RAG system (only on initial connection, not reconnection)
    if not is_reconnection:
        try:
            if FORCE_REBUILD_VECTOR_STORE:
                print("🔨 Force rebuilding vector store (--rebuild flag detected)...")
            # Use shared state to set rag_chain
            rag_chain = initialize_rag_system(force_rebuild=FORCE_REBUILD_VECTOR_STORE)
            set_rag_chain(rag_chain)
            if rag_chain is None:
                print("⚠️ RAG system initialization returned None")
        except Exception as e:
            print(f"❌ Error initializing RAG system: {e}")
            print("⚠️ Bot will continue but RAG features may not work properly.")
            # Ensure rag_chain is set to None on error
            set_rag_chain(None)

    # Store gift code channel in shared state for web server access
    # This avoids async context issues when web server tries to access client.guilds
    if GIFT_CODE_SERVER_ID and GIFT_CODE_CHANNEL_NAME:
        try:
            server_id = (
                int(GIFT_CODE_SERVER_ID)
                if isinstance(GIFT_CODE_SERVER_ID, str)
                else GIFT_CODE_SERVER_ID
            )
            guild = client.get_guild(server_id)
            if guild:
                channel = discord.utils.get(
                    guild.text_channels, name=GIFT_CODE_CHANNEL_NAME
                )
                if channel:
                    from shared_state import set_gift_code_channel

                    set_gift_code_channel(channel)
        except Exception as e:
            print(f"⚠️ Could not cache gift code channel: {e}")

    # Log web server public URL
    log_web_interface_url()

    # Ready message after RAG is loaded with elapsed time
    if startup_start_time is not None:
        elapsed_time = time.time() - startup_start_time
        print(f"✅ Ready ({elapsed_time:.2f}s)")
    else:
        print("✅ Ready")

    # Set bot status to "Playing Run! Goddess"
    await client.change_presence(activity=discord.Game(name="Run! Goddess"))

    # Append Discord mention formats to BOT_NAMES (only on initial connection)
    if not is_reconnection:
        Config.BOT_NAMES.extend(
            [f"<@{client.user.id}>".lower(), f"<@!{client.user.id}>".lower()]
        )

    # Sync slash commands globally (available in DMs)
    try:
        synced = await tree.sync()
        if not is_reconnection:
            print(f"✅ Synced {len(synced)} slash command(s)")
    except Exception as e:
        print(f"⚠️ Error syncing slash commands: {e}")

    # Send login message (only on initial connection)
    if not is_reconnection:
        await send_login_message()
        has_connected = True


@client.event
async def on_disconnect():
    """Called when the bot disconnects from Discord."""
    set_client_ready(False)
    print("🔌 Disconnected from Discord")
    # Note: Discord.py will automatically attempt reconnection


@client.event
async def on_resume():
    """Called when the bot resumes a connection after a disconnect."""
    print("🔄 Resumed connection to Discord")
    set_client_ready(True)  # Restore client ready state on resume


@client.event
async def on_connect():
    """Called when the bot connects to Discord (may be called multiple times during reconnection)."""
    if get_client_ready(client):
        print("🔗 Reconnected to Discord (connection maintained)")
        return

    set_client_ready(True)


@client.event
async def on_shard_disconnect(shard_id):
    """Called when a shard disconnects."""
    print(f"🔌 Shard {shard_id} disconnected from Discord")


@client.event
async def on_shard_resume(shard_id):
    """Called when a shard resumes."""
    print(f"🔄 Shard {shard_id} resumed connection to Discord")
    set_client_ready(True)


def detect_newcomer_code(content: str) -> str | None:
    """Detect a newcomer code in the message content.

    A newcomer code is:
    - All UPPERCASE
    - Exactly 10 characters
    - Only A-Z letters, no numbers

    Args:
        content: The message content to check

    Returns:
        The detected newcomer code if found, None otherwise
    """
    # Pattern: exactly 10 uppercase letters (A-Z only, no numbers)
    # Using word boundaries to match complete codes
    pattern = r"\b[A-Z]{10}\b"
    matches = re.findall(pattern, content)

    if matches:
        # Return the first match found
        return matches[0]
    return None


async def process_user_prompt(
    prompt: str, is_direct: bool = True, status_updater=None
) -> tuple[str, object, dict] | None:
    """Process a user prompt and return the AI response.

    This function extracts the core logic from on_message so it can be reused
    by both Discord message handling and web API.

    Args:
        prompt: The user's prompt/question
        is_direct: Whether this is a direct question (default: True for web API)
        status_updater: Optional callback function to update status messages

    Returns:
        Tuple of (response_text, token_usage, metadata) or None if no response
    """
    if not prompt or not prompt.strip():
        return None

    # Limit input length to prevent cost abuse (web interface has no Discord 2K limit)
    original_prompt = prompt.strip()
    was_truncated = False

    if len(original_prompt) > Config.MAX_INPUT_CHARS:
        # Truncate the input
        prompt = original_prompt[: Config.MAX_INPUT_CHARS]
        was_truncated = True
        print(
            f"📝 Input truncated: {len(original_prompt)} chars -> {len(prompt)} chars"
        )

    try:
        response_text, token_usage, _, metadata = await get_ai_response(
            prompt.strip(), status_updater=status_updater
        )

        # Check if the bot cannot answer - if response starts with rare prefix, don't send a response
        response_text, is_unimportant = strip_unimportant_response(response_text)

        # If the response is unimportant and not a direct question, don't send a response
        # In case of users asking each other questions, we don't want to respond to them.
        if is_unimportant and not is_direct:
            return None

        # Add truncation warning if input was truncated
        if was_truncated:
            response_text += "\n\n⚠️ *Your message was truncated due to length limits. Only the first part was processed.*"

        return response_text, token_usage, metadata
    except Exception as e:
        print(f"⚠️ Error processing prompt: {e}")
        import traceback

        print(traceback.format_exc())
        return None


@client.event
async def on_message(message: discord.Message):
    if message.author == client.user:
        return

    # Check for commands first
    if command_handler and await command_handler.handle_command(message):
        return  # Command was handled

    # Handle regular prompts
    prompt = get_prompt(message)
    if not prompt:
        return

    # For direct questions, send a "thinking" message first (like slash commands)
    thinking_message = None

    async def update_status(status_index: int):
        if thinking_message:
            try:
                await thinking_message.edit(content=get_status_message(status_index))
            except:
                pass  # Ignore errors when updating status

    if is_direct_question(message):
        try:
            thinking_message = await message.reply(
                get_status_message(StatusMessage.THINKING)
            )
        except discord.Forbidden:
            # If we can't send messages, fall back to typing indicator only
            pass

    async with message.channel.typing():
        result = await process_user_prompt(
            prompt, is_direct=is_direct_question(message), status_updater=update_status
        )
        if result is None:
            # If no response, delete the thinking message if it exists
            if thinking_message:
                try:
                    await thinking_message.delete()
                except:
                    pass  # Ignore errors when deleting
            return

        response_text, token_usage, metadata = result

        # Send response message with metadata for source links
        if thinking_message:
            # Edit the thinking message with the actual response
            await send_response_message(
                message,
                response_text,
                token_usage,
                metadata,
                prompt=prompt,
                edit_message=thinking_message,
            )
        else:
            # Fall back to normal reply if thinking message couldn't be sent
            await send_response_message(
                message, response_text, token_usage, metadata, prompt=prompt
            )


async def main():
    """Main async function to run the bot."""
    global startup_start_time
    startup_start_time = time.time()
    print("\n🚪 Logging in...")

    # Start web server (skip on Railway - Railway runs it via main.py)
    web_task = None
    if not os.getenv("RAILWAY_ENVIRONMENT"):
        # Only start web server if not on Railway (Railway runs it separately)
        from web_server import create_web_server_task

        web_port = int(os.getenv("PORT", 8000))
        web_task = create_web_server_task(web_port)
    else:
        print("🌐 Web server is running via Railway (main.py)")

    # Create shutdown event in the event loop
    shutdown_event = asyncio.Event()
    # Update command handler with the shutdown event
    command_handler.shutdown_event = shutdown_event

    try:
        async with client:
            try:
                # Start the bot
                bot_task = asyncio.create_task(client.start(os.getenv("DISCORD_TOKEN")))

                # Wait for either the bot to finish or shutdown event
                done, pending = await asyncio.wait(
                    [bot_task, asyncio.create_task(shutdown_event.wait())],
                    return_when=asyncio.FIRST_COMPLETED,
                )

                # If shutdown was triggered, close the client
                if shutdown_event.is_set():
                    print("\n🛑 Shutdown command received...")
                    # Set shutting down flag to prevent duplicate logout messages
                    set_shutting_down_flag(True)
                    print("🚪 Sending logout message...")
                    try:
                        await send_logout_message()
                    except Exception as e:
                        print(f"❌ Error sending logout message: {e}")
                    # Cancel the bot task and close
                    bot_task.cancel()
                    try:
                        await bot_task
                    except asyncio.CancelledError:
                        pass
                    await client.close()

                # Cancel any pending tasks
                for task in pending:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass

                # Cancel web server task (if it was started)
                if web_task is not None:
                    web_task.cancel()
                    try:
                        await web_task
                    except asyncio.CancelledError:
                        pass

            except (KeyboardInterrupt, asyncio.CancelledError):
                # Send logout message before context manager closes the client
                print("\n🛑 Shutting down gracefully...")
                # Set shutting down flag to prevent duplicate logout messages
                set_shutting_down_flag(True)
                try:
                    await send_logout_message()
                except Exception as e:
                    print(f"❌ Error sending logout message: {e}")

                # Cancel web server task (if it was started)
                if web_task is not None:
                    web_task.cancel()
                    try:
                        await web_task
                    except asyncio.CancelledError:
                        pass

                # Re-raise to exit the context manager
                raise
    except (KeyboardInterrupt, asyncio.CancelledError):
        # Cancel web server task if still running (and if it was started)
        if web_task is not None and not web_task.done():
            web_task.cancel()
            try:
                await web_task
            except asyncio.CancelledError:
                pass
        # Already handled above, just exit
        pass


if __name__ == "__main__":
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Dawn Bringer Discord AI Bot")
    parser.add_argument(
        "-r",
        "--rebuild",
        action="store_true",
        help="Force rebuild the vector store from documents (removes existing chunks and rebuilds)",
    )
    args = parser.parse_args()

    # Set global flag for vector store rebuild
    # CLI argument takes precedence over environment variable
    if args.rebuild:
        FORCE_REBUILD_VECTOR_STORE = True
    else:
        # Check environment variable if CLI flag not set
        FORCE_REBUILD_VECTOR_STORE = os.getenv(
            "FORCE_REBUILD_VECTOR_STORE", "false"
        ).lower() in ("true", "1", "yes")

    # Convert SIGTERM to KeyboardInterrupt for consistent handling
    def sigterm_handler(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, sigterm_handler)

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # This should be handled in main(), but fallback just in case
        pass
