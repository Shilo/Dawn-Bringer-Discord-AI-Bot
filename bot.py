import os
import discord
from openai import OpenAI
from dotenv import load_dotenv
from pathlib import Path
import re
import signal
import asyncio
import sys
from enum import Enum

load_dotenv()

BOT_NAMES = ["db", "dawn bringer", "dawn", "dawnbringer"]
QUESTION_STARTERS = ["who", "what", "when", "where", "why", "how", "is", "are", "can", "could",
                     "would", "should", "do", "does", "did", "will", "has", "have", "which"]
PUNCTUATION = ",.!?:;-"
MODEL = "gpt-4o-mini" #"gpt-5-mini"
MAX_TOKENS = 500
QUESTION_CHANNEL_NAME = "👧ask-dawn-bringer"
DOCS_DIR = "docs"
MAX_DOC_CONTEXT = 1000  # Max characters of documentation to include per query


class DocFilterMode(Enum):
    """Documentation filter mode enum."""
    PARAGRAPH = "paragraph"  # Extract relevant paragraphs from files
    FILE = "file"  # Return entire relevant files
    ALL_FILES = "all_files"  # Return all files regardless of relevance


# Documentation filter mode (change this to switch between modes)
DOC_FILTER_MODE = DocFilterMode.PARAGRAPH

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


def load_system_prompt() -> str:
    """Load the system prompt from file."""
    try:
        with open(SYSTEM_PROMPT_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        print(f"Warning: {SYSTEM_PROMPT_FILE} not found. Using default prompt.")
    except Exception as e:
        print(f"Error loading system prompt: {e}. Using default prompt.")
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
    return f"`💵 ${cost:.6f} | 🪙 {token_usage.total_tokens} total ({token_usage.prompt_tokens} prompt + {token_usage.completion_tokens} completion)`"


def split_message(content: str, max_length: int = 2000) -> list[str]:
    """Split a message into chunks that fit within Discord's character limit.
    
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
    
    # Split by newlines first to preserve formatting
    lines = content.split('\n')
    
    for line in lines:
        # If a single line is too long, split it by words
        if len(line) > max_length:
            if current_chunk:
                chunks.append(current_chunk)
                current_chunk = ""
            
            words = line.split(' ')
            for word in words:
                if len(current_chunk) + len(word) + 1 > max_length:
                    if current_chunk:
                        chunks.append(current_chunk)
                        current_chunk = ""
                current_chunk += word + " " if current_chunk else word + " "
        else:
            # Check if adding this line would exceed limit
            if len(current_chunk) + len(line) + 1 > max_length:
                if current_chunk:
                    chunks.append(current_chunk.rstrip())
                    current_chunk = ""
            current_chunk += line + "\n"
    
    if current_chunk:
        chunks.append(current_chunk.rstrip())
    
    return chunks


async def send_response_message(message: discord.Message, response_text: str, token_usage):
    """Send a response message with token info, splitting into chunks if necessary.
    
    Args:
        message: The Discord message to reply to
        response_text: The response text to send
        token_usage: The token usage object from OpenAI
    """
    print(f"📤 Sending response to {message.author} in {message.channel.name}")
    
    # Get token info and combine with response
    token_info = get_token_info(token_usage, MODEL)
    full_message = response_text + "\n\n" + token_info
    
    # Split into chunks if too long
    message_chunks = split_message(full_message)
    
    # Send first chunk as reply, rest as follow-ups
    for i, chunk in enumerate(message_chunks):
        if i == 0:
            await message.reply(chunk)
        else:
            await message.channel.send(chunk)


def load_documentation() -> tuple[dict[str, str], int]:
    """Load all documentation files from the docs directory and subdirectories.
    
    Supports .txt and .md files, but ignores README.md files.
    Returns a tuple of (dictionary mapping filename to content, total word count).
    Includes subdirectory path in the key to avoid naming conflicts.
    """
    docs = {}
    total_words = 0
    docs_path = Path(DOCS_DIR)
    
    if not docs_path.exists():
        print(f"Warning: {DOCS_DIR} directory not found. Documentation will not be available.")
        return docs, 0
    
    # Load both .txt and .md files recursively, but skip README.md
    for pattern in ["*.txt", "*.md"]:
        for file_path in docs_path.rglob(pattern):
            # Skip README.md files (case-insensitive)
            if file_path.stem == "README":
                continue
            
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if content:
                        # Count words in this document
                        words = len(re.findall(r'\b\w+\b', content))
                        total_words += words
                        
                        # Use relative path from docs_dir as key to preserve subdirectory structure
                        relative_path = file_path.relative_to(docs_path)
                        # Remove extension and use forward slashes for consistency
                        doc_key = str(relative_path.with_suffix("")).replace("\\", "/")
                        docs[doc_key] = content
                        print(f"Loaded documentation: {relative_path}")
            except Exception as e:
                print(f"Error loading {file_path}: {e}")
    
    print(f"📚 Total documentation files loaded: {len(docs)} | Total words: {total_words:,}")
    return docs, total_words


def find_relevant_docs(query: str, docs: dict[str, str], filter_mode: DocFilterMode = DOC_FILTER_MODE) -> str:
    """Find relevant documentation sections based on the user's query.
    
    Uses keyword matching with prioritization for filename relevance and keyword frequency.
    Returns a formatted string with relevant context (up to MAX_DOC_CONTEXT chars).
    
    Args:
        query: The user's query string
        docs: Dictionary mapping doc names to content
        filter_mode: The filter mode to use (PARAGRAPH, FILE, or ALL_FILES)
    """
    if not docs:
        return ""
    
    # ALL_FILES mode: return all files regardless of relevance
    if filter_mode == DocFilterMode.ALL_FILES:
        context_parts = []
        total_chars = 0
        
        for name, content in docs.items():
            if total_chars >= MAX_DOC_CONTEXT:
                break
            
            remaining = MAX_DOC_CONTEXT - total_chars
            if len(content) <= remaining:
                context_parts.append(f"[From {name}]\n{content}")
                total_chars += len(content)
            else:
                # Truncate if needed
                if remaining > 100:  # Only add if meaningful amount left
                    context_parts.append(f"[From {name}]\n{content[:remaining]}...")
                break
        
        if context_parts:
            return "\n\n---\n\n".join(context_parts)
        return ""
    
    query_lower = query.lower()
    query_words = set(re.findall(r'\b\w+\b', query_lower))
    
    # Score each doc by keyword matches
    scored_docs = []
    for name, content in docs.items():
        content_lower = content.lower()
        name_lower = name.lower()
        
        # Base score from content keyword matches
        content_score = sum(1 for word in query_words if word in content_lower and len(word) > 2)
        
        # Bonus for filename containing query keywords (strong indicator of relevance)
        filename_bonus = sum(2 for word in query_words if word in name_lower and len(word) > 2)
        
        # Count keyword frequency in content (density matters)
        keyword_frequency = sum(content_lower.count(word) for word in query_words if len(word) > 2)
        frequency_bonus = min(keyword_frequency // 3, 3)  # Cap at 3 bonus points
        
        total_score = content_score + filename_bonus + frequency_bonus
        
        if total_score > 0:
            scored_docs.append((total_score, name, content))
    
    # Sort by score and get top matches
    scored_docs.sort(reverse=True, key=lambda x: x[0])
    
    # FILE mode: return entire files
    if filter_mode == DocFilterMode.FILE:
        context_parts = []
        total_chars = 0
        
        for score, name, content in scored_docs[:3]:  # Top 3 most relevant
            if total_chars >= MAX_DOC_CONTEXT:
                break
            
            remaining = MAX_DOC_CONTEXT - total_chars
            if len(content) <= remaining:
                context_parts.append(f"[From {name}]\n{content}")
                total_chars += len(content)
            else:
                # Truncate if needed
                if remaining > 100:  # Only add if meaningful amount left
                    context_parts.append(f"[From {name}]\n{content[:remaining]}...")
                break
        
        if context_parts:
            return "\n\n---\n\n".join(context_parts)
        return ""
    
    # PARAGRAPH mode: extract relevant paragraphs (default behavior)
    context_parts = []
    total_chars = 0
    
    for score, name, content in scored_docs[:3]:  # Top 3 most relevant
        if total_chars >= MAX_DOC_CONTEXT:
            break
        
        # Try to extract relevant sections (paragraphs containing keywords)
        paragraphs = content.split('\n\n')
        relevant_paragraphs = []
        
        for para in paragraphs:
            para_lower = para.lower()
            if any(word in para_lower for word in query_words if len(word) > 2):
                if total_chars + len(para) <= MAX_DOC_CONTEXT:
                    relevant_paragraphs.append(para)
                    total_chars += len(para)
                else:
                    # Truncate if needed
                    remaining = MAX_DOC_CONTEXT - total_chars
                    if remaining > 100:  # Only add if meaningful amount left
                        relevant_paragraphs.append(para[:remaining] + "...")
                    break
        
        if relevant_paragraphs:
            context_parts.append(f"[From {name}]\n" + "\n\n".join(relevant_paragraphs))
    
    if context_parts:
        return "\n\n---\n\n".join(context_parts)
    return ""


# Load documentation on startup
DOCUMENTATION, DOCUMENTATION_WORDS = load_documentation()
DOCUMENTATION_COUNT = len(DOCUMENTATION)


def get_knowledge_string() -> str:
    """Get a formatted string showing the bot's knowledge base stats.
    
    Returns:
        Formatted string with file count and word count
    """
    return f"📚 My game knowledge: {DOCUMENTATION_COUNT} files | {DOCUMENTATION_WORDS:,} words"


intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
openai_client = OpenAI()

# Flags to track bot state (to skip duplicate logout messages)
is_restarting = False
is_shutting_down = False


def get_ai_response(prompt: str) -> tuple[str, object, str]:
    """Get a response from OpenAI with personality and rules applied.
    
    Returns:
        tuple: (response_text, usage_object, prompt)
        usage_object is the OpenAI Usage object with prompt_tokens, completion_tokens, total_tokens
        prompt is the prompt sent to the API (may include documentation context)
    """
    # Find relevant documentation and append to prompt
    doc_context = find_relevant_docs(prompt, DOCUMENTATION)
    if doc_context:
        prompt = f"{prompt}\n\n[Run! Goddess Documentation]\n{doc_context}"
    
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt}
    ]
    
    response = openai_client.chat.completions.create(
        model=MODEL,
        max_completion_tokens=MAX_TOKENS,
        messages=messages
    )
    
    return response.choices[0].message.content, response.usage, prompt


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
    if text.endswith("?"):
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


def is_direct_question(message: discord.Message) -> bool:
    """Check if the message is a direct question (question channel or mentions or bot names or !debug command).
    
    Args:
        message: The Discord message to check
        
    Returns:
        True if the message is in the question channel OR bot is mentioned OR message contains bot names OR is a !debug command, False otherwise
    """
    # Check if in question channel
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
    
    Returns None if none of the above conditions are met.
    """
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


async def send_logout_message():
    """Send logout message to question channel."""
    if QUESTION_CHANNEL_NAME:
        for guild in client.guilds:
            channel = discord.utils.get(guild.text_channels, name=QUESTION_CHANNEL_NAME)
            if channel:
                try:
                    await channel.send("🌙 Standing down for now, Survivors. Stay safe—the Infected never rest. I'll be back when you need me.")
                except Exception as e:
                    print(f"Error sending logout message: {e}")
                break


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
    get_knowledge_string_func=get_knowledge_string,
    client=client,
    shutdown_event=None,  # Will be set in main()
    question_channel_name=QUESTION_CHANNEL_NAME,
    set_restarting_flag_func=set_restarting_flag,
    set_shutting_down_flag_func=set_shutting_down_flag
)


@client.event
async def on_ready():
    print(f"Logged in as {client.user}")
    
    # Set bot status to "Playing Run! Goddess"
    await client.change_presence(activity=discord.Game(name="Run! Goddess"))
    
    # Append Discord mention formats to BOT_NAMES
    BOT_NAMES.extend([
        f"<@{client.user.id}>".lower(),
        f"<@!{client.user.id}>".lower()
    ])
    
    # Send login message to question channel
    if QUESTION_CHANNEL_NAME:
        for guild in client.guilds:
            channel = discord.utils.get(guild.text_channels, name=QUESTION_CHANNEL_NAME)
            if channel:
                try:
                    login_message = f"☀️ Survivors, Commander Dawn Bringer here. Ready to assist with any questions about Run! Goddess.\n`{get_knowledge_string()}`"
                    await channel.send(login_message)
                except Exception as e:
                    print(f"Error sending login message: {e}")
                break


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
            response_text, token_usage, _ = get_ai_response(prompt)
            
            # Check if the bot cannot answer - if response starts with rare prefix, don't send a response
            response_text, is_unimportant = strip_unimportant_response(response_text)
            is_direct = is_direct_question(message)
            
            # If the response is unimportant and not a direct question, don't send a response
            # In case of users asking each other questions, we don't want to respond to them.
            if is_unimportant and not is_direct:
                return
            
            # Send response message
            await send_response_message(message, response_text, token_usage)
        except Exception as e:
            await message.reply(f"Error: {e}")


async def main():
    """Main async function to run the bot."""
    print("\nLogging in..")
    
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
                    print("\nShutdown command received...")
                    # Set shutting down flag to prevent duplicate logout message from on_disconnect
                    set_shutting_down_flag(True)
                    print("Sending logout message...")
                    try:
                        await send_logout_message()
                    except Exception as e:
                        print(f"Error sending logout message: {e}")
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
                print("\nShutting down gracefully...")
                # Set shutting down flag to prevent duplicate logout message from on_disconnect
                set_shutting_down_flag(True)
                print("Sending logout message...")
                try:
                    await send_logout_message()
                except Exception as e:
                    print(f"Error sending logout message: {e}")
                # Re-raise to exit the context manager
                raise
    except (KeyboardInterrupt, asyncio.CancelledError):
        # Already handled above, just exit
        pass


if __name__ == "__main__":
    # Convert SIGTERM to KeyboardInterrupt for consistent handling
    def sigterm_handler(signum, frame):
        raise KeyboardInterrupt
    
    signal.signal(signal.SIGTERM, sigterm_handler)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # This should be handled in main(), but fallback just in case
        pass
