import os
import discord
from openai import OpenAI
from dotenv import load_dotenv
import signal
import asyncio
import time
import argparse

load_dotenv()

# RAG system imports
from rag.config import RAGConfig
from rag.document_loader import DocumentLoader
from rag.vector_store import VectorStore
from rag.retriever import RAGRetriever
from rag.chain import RAGChain
from rag.utils import estimate_words_from_chunks, format_word_count

BOT_NAMES = ["db", "dawn bringer", "dawn", "dawnbringer"]
QUESTION_STARTERS = ["who", "what", "when", "where", "why", "how", "is", "are", "can", "could",
                     "would", "should", "do", "does", "did", "will", "has", "have", "which"]
PUNCTUATION = ",.!?:;-"
MODEL = "gpt-4o-mini" #"gpt-5-mini"
MAX_TOKENS = 500
TEMPERATURE = 0.7  # LLM temperature (0.0-2.0). For factual RAG responses (but less creative), consider trying 0.0-0.3 for better accuracy
QUESTION_CHANNEL_NAME = "👧ask-dawn-bringer"

# OpenAI API pricing per 1M tokens (as of 2024)
# Source: https://openai.com/api/pricing/
MODEL_PRICING = {
    "gpt-4o-mini": {
        "input": 0.150,   # $0.150 per 1M input tokens
        "output": 0.600   # $0.600 per 1M output tokens
    },
    "gpt-5-mini": {
        "input": 0.25,    # $0.25 per 1M input tokens
        "output": 2.00    # $2.00 per 1M output tokens
    }
}

# Bot Personality and Rules
# Note: This is sent with every message, so keep it concise to save tokens
SYSTEM_PROMPT_FILE = "system_prompt.txt"

# Global flag for rebuilding vector store (set via CLI argument)
FORCE_REBUILD_VECTOR_STORE = False


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


SYSTEM_PROMPT = load_system_prompt()


def calculate_cost(prompt_tokens: int, completion_tokens: int, model: str = MODEL) -> float:
    """Calculate the cost in USD based on token usage and model pricing.
    
    Args:
        prompt_tokens: Number of input/prompt tokens
        completion_tokens: Number of output/completion tokens
        model: Model name (defaults to MODEL constant)
    
    Returns:
        Total cost in USD
    """
    if model not in MODEL_PRICING:
        return 0.0  # Unknown model, return 0
    
    pricing = MODEL_PRICING[model]
    input_cost = (prompt_tokens / 1_000_000) * pricing["input"]
    output_cost = (completion_tokens / 1_000_000) * pricing["output"]
    
    return input_cost + output_cost


def get_token_info(token_usage, model: str = MODEL) -> str:
    """Format token usage and cost information.
    
    Args:
        token_usage: OpenAI Usage object with prompt_tokens, completion_tokens, total_tokens
        model: Model name (defaults to MODEL constant)
    
    Returns:
        Formatted string with cost and token information
    """
    cost = calculate_cost(token_usage.prompt_tokens, token_usage.completion_tokens, model)
    return f"-# `💵 ${cost:.6f} | 🪙 {token_usage.total_tokens} ({token_usage.prompt_tokens} prompt + {token_usage.completion_tokens} completion)`"


# Initialize RAG system (will be set up on startup)
rag_chain: RAGChain | None = None

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
    lines = content.split('\n')
    
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
                current_chunk += code_block_delimiter + "\n"
                in_code_block = False
            
            # Save current chunk if it has content
            if current_chunk.strip():
                chunks.append(current_chunk.rstrip())
                current_chunk = ""
            
            # If we were in a code block, reopen it in the new chunk
            if was_in_code_block:
                current_chunk = code_block_delimiter + "\n"
                in_code_block = True
            
            # If the line itself is too long and we're not in a code block, split it
            if len(line_with_newline) > max_length and not in_code_block:
                words = line.split(' ')
                for word in words:
                    if len(current_chunk) + len(word) + 1 > max_length:
                        if current_chunk:
                            chunks.append(current_chunk.rstrip())
                            current_chunk = ""
                    current_chunk += word + " " if current_chunk else word + " "
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
    
    return chunks


async def send_response_message(message: discord.Message, response_text: str, token_usage, metadata: dict = None, is_unimportant: bool = False):
    """Send a response message with token info, splitting into chunks if necessary.
    
    Args:
        message: The Discord message to reply to
        response_text: The response text to send
        token_usage: The token usage object from OpenAI
        metadata: Optional metadata dict containing sources and retrieved_chunks
        is_unimportant: If True, response was marked as [[UNIMPORTANT]] and sources should not be shown
    """
    print(f"📤 Sending response to {message.author} in {get_channel_name(message.channel)}")
    
    # Get token info and combine with response
    token_info = get_token_info(token_usage, MODEL)
    
    # Generate GitHub source links if available (but not if response is unimportant)
    source_links = []
    if not is_unimportant:
        from rag.utils import format_source_links
        source_links = format_source_links(metadata, max_sources=5)
    
    # Combine response, source links, and token info
    full_message = response_text
    if source_links:
        full_message += "\n\n" + "".join(source_links)
    full_message += "\n\n" + token_info
    
    # Split into chunks if too long
    message_chunks = split_message(full_message)
    
    # Send first chunk as reply, rest as follow-ups
    for i, chunk in enumerate(message_chunks):
        if i == 0:
            await message.reply(chunk)
        else:
            await message.channel.send(chunk)


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
    loader = DocumentLoader(RAGConfig.DOCS_DIR)
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
    
    # Initialize retriever
    retriever = RAGRetriever(vector_store)
    
    # Initialize RAG chain
    chain = RAGChain(
        retriever=retriever,
        model_name=MODEL,
        max_tokens=MAX_TOKENS,
        temperature=TEMPERATURE,
        system_prompt=SYSTEM_PROMPT,
    )
    
    return chain


def get_knowledge_stats_string() -> str:
    """Get a formatted string showing the bot's knowledge base stats.
    
    Returns:
        Formatted string with vector store stats
    """
    if rag_chain is None:
        return "📚 RAG system not initialized"
    
    stats = rag_chain.retriever.vector_store.get_stats()
    doc_count = stats.get("document_count", 0)
    estimated_words = estimate_words_from_chunks(doc_count)
    word_display = format_word_count(estimated_words)
    return f"📚 My game knowledge: ~{word_display} words from {doc_count:,} articles"


intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
openai_client = OpenAI()

# Flags to track bot state (to skip duplicate logout messages)
is_restarting = False
is_shutting_down = False


def get_ai_response(prompt: str, include_scores: bool = False) -> tuple[str, object, str, dict]:
    """Get a response from OpenAI with RAG system.
    
    Args:
        prompt: User's question/prompt
        include_scores: If True, retrieve similarity scores (adds overhead - only use for debugging)
    
    Returns:
        tuple: (response_text, usage_object, full_prompt, metadata)
        usage_object is the OpenAI Usage object with prompt_tokens, completion_tokens, total_tokens
        full_prompt is the full prompt sent to the API (system + user, may include documentation context)
        metadata is a dict containing sources, retrieved_chunks, etc.
    """
    if rag_chain is None:
        # Fallback if RAG system not initialized
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ]
        full_prompt = f"System: {SYSTEM_PROMPT}\n\nUser: {prompt}"
        response = openai_client.chat.completions.create(
            model=MODEL,
            max_completion_tokens=MAX_TOKENS,
            messages=messages
        )
        metadata = {
            "sources": [],
            "retrieved_docs": 0,
            "full_prompt": full_prompt,
            "retrieved_chunks": [],
        }
        return response.choices[0].message.content, response.usage, full_prompt, metadata
    
    # Use RAG chain (without scores for normal queries - scores add overhead)
    response_text, usage, metadata = rag_chain.query_with_usage(prompt, include_scores=include_scores)
    full_prompt = metadata.get("full_prompt", prompt)
    return response_text, usage, full_prompt, metadata


def strip_unimportant_response(response_text: str) -> tuple[str, bool]:
    """Strip the [[UNIMPORTANT]] prefix from response text if present.
    
    Args:
        response_text: The response text from the AI
        
    Returns:
        Tuple of (stripped_response, is_unimportant) where:
        - stripped_response: The response with [[UNIMPORTANT]] prefix removed if it was present
        - is_unimportant: True if the response had the [[UNIMPORTANT]] prefix, False otherwise
    """
    stripped = response_text.strip()
    if stripped.startswith("[[UNIMPORTANT]]"):
        # Remove the prefix and any leading whitespace after it
        return stripped[len("[[UNIMPORTANT]]"):].strip(), True
    return response_text, False


def is_question(text: str) -> bool:
    """Check if text is a question."""
    if "?" in text and len(text.strip()) > 1:
        return True
    
    text_lower = text.lower().strip()
    if not text_lower:
        return False
    
    # Get first word
    space_idx = text_lower.find(" ")
    first_word = text_lower[:space_idx] if space_idx != -1 else text_lower
    
    # Check if first word is exactly in question starters
    if first_word in QUESTION_STARTERS:
        return True
    
    # Check for contractions (whats, what's, whos, who's, wheres, where's, etc.)
    # Common contraction patterns: 's, 're, 'd, 't, 'll, 've, or just 's' without apostrophe
    contraction_suffixes = ["'s", "'re", "'d", "'t", "'ll", "'ve", "s", "re", "d", "t"]
    for starter in QUESTION_STARTERS:
        if first_word.startswith(starter):
            remaining = first_word[len(starter):]
            # Check if remaining part is a valid contraction suffix
            if remaining and remaining in contraction_suffixes:
                return True
            # Also check for apostrophe variants
            if remaining.startswith("'") and remaining[1:] in ["s", "re", "d", "t", "ll", "ve"]:
                return True
    
    return False


def remove_start_mention(content: str, name: str) -> str:
    """Remove mention/name from start of content and strip leading punctuation."""
    content = content[len(name):].strip()
    if content and content[0] in PUNCTUATION:
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


def is_direct_question(message: discord.Message) -> bool:
    """Check if the message is a direct question (question channel or mentions or bot names or !debug command).
    
    Args:
        message: The Discord message to check
        
    Returns:
        True if the message is in the question channel OR bot is mentioned OR message contains bot names OR is a !debug command OR is a DM, False otherwise
    """
    # Check if it's a DM (always treat DMs as direct questions)
    if isinstance(message.channel, discord.DMChannel):
        return True
    
    # Check if in question channel (we know it's not a DM at this point)
    if QUESTION_CHANNEL_NAME and message.channel.name == QUESTION_CHANNEL_NAME:
        return True
    
    # Check if bot is mentioned
    if client.user.mentioned_in(message):
        return True
    
    # Check if message contains bot names
    content_lower = message.content.lower()
    
    for name in BOT_NAMES:
        if name in content_lower:
            return True
    
    # Check if message is a !debug command
    if content_lower.startswith("!debug"):
        return True
    
    return False


def get_prompt(message: discord.Message) -> str | None:
    """Extract prompt from Discord message.
    
    Checks for bot names or mentions in the message. If found at the start (index 0),
    strips the name/mention and leading punctuation from the content.
    
    Returns the processed content if:
    - Bot name or mention is found anywhere in the message
    - Bot is mentioned via Discord's mention system
    - Message is a question
    - Message is in a DM (always respond to DMs)
    
    Returns None if none of the above conditions are met.
    """
    # For DMs, always respond (treat as direct conversation)
    if isinstance(message.channel, discord.DMChannel):
        content = message.content.strip()
        content_lower = content.lower()
        
        # Still check for bot names to strip them if present
        for name in BOT_NAMES:
            index = content_lower.find(name)
            if index != -1:
                if index == 0:
                    content = remove_start_mention(content, name)
                return content
        
        return content
    
    # For guild channels, use existing logic
    content = message.content.strip()
    content_lower = content.lower()

    for name in BOT_NAMES:
        index = content_lower.find(name)
        if index != -1:
            if index == 0:
                content = remove_start_mention(content, name)
            return content

    if client.user.mentioned_in(message):
        return content

    if is_question(content):
        return content

    return None


async def send_message_to_question_channel(message: str, error_context: str = "message"):
    """Send a message to the question channel with proper error handling.
    
    Args:
        message: The message content to send
        error_context: Context for error messages (e.g., "login message", "logout message")
    """
    if not QUESTION_CHANNEL_NAME:
        return
    
    for guild in client.guilds:
        channel = discord.utils.get(guild.text_channels, name=QUESTION_CHANNEL_NAME)
        if channel:
            try:
                # Check if bot has permission to send messages
                if channel.permissions_for(guild.me).send_messages:
                    await channel.send(message)
                else:
                    print(f"⚠️ Bot lacks permission to send messages in #{QUESTION_CHANNEL_NAME}")
            except discord.Forbidden:
                print(f"⚠️ Bot lacks access to send messages in #{QUESTION_CHANNEL_NAME} (403 Forbidden)")
            except Exception as e:
                print(f"⚠️ Error sending {error_context}: {e}")
            break


async def send_logout_message():
    """Send logout message to question channel."""
    await send_message_to_question_channel(
        "🌙 Standing down for now, Survivors. Stay safe—the Infected never rest. I'll be back when you need me.",
        "logout message"
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
    model=MODEL,
    get_knowledge_string_func=get_knowledge_stats_string,
    client=client,
    shutdown_event=None,  # Will be set in main()
    question_channel_name=QUESTION_CHANNEL_NAME,
    set_restarting_flag_func=set_restarting_flag,
    set_shutting_down_flag_func=set_shutting_down_flag
)


@client.event
async def on_ready():
    print(f"🚪 Logged in as {client.user}")
    
    # Initialize RAG system
    global rag_chain, startup_start_time, FORCE_REBUILD_VECTOR_STORE
    try:
        if FORCE_REBUILD_VECTOR_STORE:
            print("🔨 Force rebuilding vector store (--rebuild flag detected)...")
        rag_chain = initialize_rag_system(force_rebuild=FORCE_REBUILD_VECTOR_STORE)
    except Exception as e:
        print(f"❌ Error initializing RAG system: {e}")
        print("⚠️ Bot will continue but RAG features may not work properly.")
    
    # Ready message after RAG is loaded with elapsed time
    if startup_start_time is not None:
        elapsed_time = time.time() - startup_start_time
        print(f"✅ Ready ({elapsed_time:.2f}s)")
    else:
        print("✅ Ready")
    
    # Set bot status to "Playing Run! Goddess"
    await client.change_presence(activity=discord.Game(name="Run! Goddess"))
    
    # Append Discord mention formats to BOT_NAMES
    BOT_NAMES.extend([
        f"<@{client.user.id}>".lower(),
        f"<@!{client.user.id}>".lower()
    ])
    
    # Send login message to question channel
    login_message = f"☀️ Survivors, Commander Dawn Bringer here. Ready to assist with any questions about Run! Goddess.\n`{get_knowledge_stats_string()}`"
    await send_message_to_question_channel(login_message, "login message")


@client.event
async def on_disconnect():
    # Send logout message to question channel (unless we're restarting or already shutting down)
    global is_restarting, is_shutting_down
    if not is_restarting and not is_shutting_down:
        await send_logout_message()


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

    async with message.channel.typing():
        try:
            response_text, token_usage, _, metadata = get_ai_response(prompt)
            
            # Check if the bot cannot answer - if response starts with rare prefix, don't send a response
            response_text, is_unimportant = strip_unimportant_response(response_text)
            is_direct = is_direct_question(message)
            
            # If the response is unimportant and not a direct question, don't send a response
            # In case of users asking each other questions, we don't want to respond to them.
            if is_unimportant and not is_direct:
                return
            
            # Send response message with metadata for source links (but not if unimportant)
            await send_response_message(message, response_text, token_usage, metadata, is_unimportant=is_unimportant)
        except Exception as e:
            await message.reply(f"Error: {e}")


async def main():
    """Main async function to run the bot."""
    global startup_start_time
    startup_start_time = time.time()
    print("\n🚪 Logging in...")
    
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
                    return_when=asyncio.FIRST_COMPLETED
                )
                
                # If shutdown was triggered, close the client
                if shutdown_event.is_set():
                    print("\n🛑 Shutdown command received...")
                    # Set shutting down flag to prevent duplicate logout message from on_disconnect
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
                        
            except (KeyboardInterrupt, asyncio.CancelledError):
                # Send logout message before context manager closes the client
                print("\n🛑 Shutting down gracefully...")
                # Set shutting down flag to prevent duplicate logout message from on_disconnect
                set_shutting_down_flag(True)
                print("🚪 Sending logout message...")
                try:
                    await send_logout_message()
                except Exception as e:
                    print(f"❌ Error sending logout message: {e}")
                # Re-raise to exit the context manager
                raise
    except (KeyboardInterrupt, asyncio.CancelledError):
        # Already handled above, just exit
        pass


if __name__ == "__main__":
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Dawn Bringer Discord AI Bot")
    parser.add_argument(
        "-r", "--rebuild",
        action="store_true",
        help="Force rebuild the vector store from documents (removes existing chunks and rebuilds)"
    )
    args = parser.parse_args()
    
    # Set global flag for vector store rebuild
    FORCE_REBUILD_VECTOR_STORE = args.rebuild
    
    # Convert SIGTERM to KeyboardInterrupt for consistent handling
    def sigterm_handler(signum, frame):
        raise KeyboardInterrupt
    
    signal.signal(signal.SIGTERM, sigterm_handler)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # This should be handled in main(), but fallback just in case
        pass
