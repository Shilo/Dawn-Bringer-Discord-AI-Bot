import os
import discord
from openai import OpenAI
from dotenv import load_dotenv
from pathlib import Path
import re

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


def load_documentation() -> dict[str, str]:
    """Load all documentation files from the docs directory.
    
    Returns a dictionary mapping filename (without extension) to file content.
    """
    docs = {}
    docs_path = Path(DOCS_DIR)
    
    if not docs_path.exists():
        print(f"Warning: {DOCS_DIR} directory not found. Documentation will not be available.")
        return docs
    
    for file_path in docs_path.glob("*.txt"):
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


@client.event
async def on_ready():
    print(f"Logged in as {client.user}")


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
                token_usage = f"`🪙 {token_usage.total_tokens} total ({token_usage.prompt_tokens} prompt + {token_usage.completion_tokens} completion)`"
                await message.reply(full_prompt + "\n\n" + response_text + "\n\n" + token_usage)
            except Exception as e:
                await message.reply(f"Error: {e}")


if __name__ == "__main__":
    client.run(os.getenv("DISCORD_TOKEN"))
