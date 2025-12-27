import os
import discord
from openai import OpenAI
from dotenv import load_dotenv
from pathlib import Path
import re
import signal
import asyncio
import sys

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


def load_documentation() -> dict[str, str]:
    """Load all documentation files from the docs directory.
    
    Supports .txt and .md files, but ignores README.md files.
    Returns a dictionary mapping filename (without extension) to file content.
    """
    docs = {}
    docs_path = Path(DOCS_DIR)
    
    if not docs_path.exists():
        print(f"Warning: {DOCS_DIR} directory not found. Documentation will not be available.")
        return docs
    
    # Load both .txt and .md files, but skip README.md
    for pattern in ["*.txt", "*.md"]:
        for file_path in docs_path.glob(pattern):
            # Skip README.md files (case-insensitive)
            if file_path.stem == "README":
                continue
            
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if content:
                        docs[file_path.stem] = content
                        print(f"Loaded documentation: {file_path.name}")
            except Exception as e:
                print(f"Error loading {file_path}: {e}")
    
    return docs


def find_relevant_docs(query: str, docs: dict[str, str]) -> str:
    """Find relevant documentation sections based on the user's query.
    
    Uses simple keyword matching to find the most relevant documentation.
    Returns a formatted string with relevant context (up to MAX_DOC_CONTEXT chars).
    """
    if not docs:
        return ""
    
    query_lower = query.lower()
    query_words = set(re.findall(r'\b\w+\b', query_lower))
    
    # Score each doc by keyword matches
    scored_docs = []
    for name, content in docs.items():
        content_lower = content.lower()
        score = sum(1 for word in query_words if word in content_lower and len(word) > 2)
        if score > 0:
            scored_docs.append((score, name, content))
    
    # Sort by score and get top matches
    scored_docs.sort(reverse=True, key=lambda x: x[0])
    
    # Build context from top matches
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
DOCUMENTATION = load_documentation()


intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
openai_client = OpenAI()


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


def is_question(text: str) -> bool:
    """Check if text is a question."""
    if text.endswith("?"):
        return True
    space_idx = text.find(" ")
    first_word = text[:space_idx].lower() if space_idx != -1 else text.lower()
    return first_word in QUESTION_STARTERS


def remove_start_mention(content: str, name: str) -> str:
    """Remove mention/name from start of content and strip leading punctuation."""
    content = content[len(name):].strip()
    if content and content[0] in PUNCTUATION:
        content = content[1:].strip()
    return content


def get_prompt(message: discord.Message) -> str | None:
    """Extract prompt from Discord message.
    
    Checks for bot names or mentions in the message. If found at the start (index 0),
    strips the name/mention and leading punctuation from the content.
    
    Returns the processed content if:
    - Bot name or mention is found anywhere in the message
    - Bot is mentioned via Discord's mention system
    - Message is a question (only in QUESTION_CHANNEL_NAME if set)
    
    Returns None if none of the above conditions are met.
    """
    content = message.content.strip()
    content_lower = content.lower()

    bot_names = BOT_NAMES + [
        f"<@{client.user.id}>".lower(),
        f"<@!{client.user.id}>".lower()
    ]

    for name in bot_names:
        index = content_lower.find(name)
        if index != -1:
            if index == 0:
                content = remove_start_mention(content, name)
            return content

    if client.user.mentioned_in(message):
        return content

    if QUESTION_CHANNEL_NAME and message.channel.name == QUESTION_CHANNEL_NAME and is_question(content):
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


@client.event
async def on_ready():
    print(f"Logged in as {client.user}")
    
    # Send login message to question channel
    if QUESTION_CHANNEL_NAME:
        for guild in client.guilds:
            channel = discord.utils.get(guild.text_channels, name=QUESTION_CHANNEL_NAME)
            if channel:
                try:
                    await channel.send("☀️ Survivors, Commander Dawn Bringer here. Ready to assist with any questions about Run! Goddess.")
                except Exception as e:
                    print(f"Error sending login message: {e}")
                break


@client.event
async def on_disconnect():
    # Send logout message to question channel
    await send_logout_message()


@client.event
async def on_message(message: discord.Message):
    if message.author == client.user:
        return

    prompt = get_prompt(message)

    if prompt:
        async with message.channel.typing():
            try:
                response_text, token_usage, full_prompt = get_ai_response(prompt)
                full_prompt = f"**Prompt:** {full_prompt}"
                response_text = f"**Response:** {response_text}"
                token_info = get_token_info(token_usage, MODEL)
                
                # Combine all parts
                full_message = full_prompt + "\n\n" + response_text + "\n\n" + token_info
                
                # Split into chunks if too long
                message_chunks = split_message(full_message)
                
                # Send first chunk as reply, rest as follow-ups
                for i, chunk in enumerate(message_chunks):
                    if i == 0:
                        await message.reply(chunk)
                    else:
                        await message.channel.send(chunk)
            except Exception as e:
                await message.reply(f"Error: {e}")


async def main():
    """Main async function to run the bot."""
    try:
        async with client:
            try:
                await client.start(os.getenv("DISCORD_TOKEN"))
            except (KeyboardInterrupt, asyncio.CancelledError):
                # Send logout message before context manager closes the client
                print("\nShutting down gracefully...")
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
