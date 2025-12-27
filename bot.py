import os
import discord
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

BOT_NAMES = ["db", "dawn bringer", "dawn", "dawnbringer"]
QUESTION_STARTERS = ["who", "what", "when", "where", "why", "how", "is", "are", "can", "could",
                     "would", "should", "do", "does", "did", "will", "has", "have", "which"]
PUNCTUATION = ",.!?:;-"
MODEL = "gpt-4o-mini" #"gpt-5-mini"
MAX_TOKENS = 500


intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
openai_client = OpenAI()


def get_ai_response(prompt: str) -> str:
    """Get a response from OpenAI."""
    response = openai_client.chat.completions.create(
        model=MODEL,
        max_completion_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content


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
    - Message is a question
    
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

    if is_question(content):
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
                response = get_ai_response(prompt)
                full_response = f"**Prompt:** {prompt}\n\n**Response:** {response}"
                await message.reply(full_response)
            except Exception as e:
                await message.reply(f"Error: {e}")


if __name__ == "__main__":
    client.run(os.getenv("DISCORD_TOKEN"))
