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


def remove_punctuation(text: str, leading: bool = True) -> str:
    """Remove leading or trailing punctuation from text."""
    if not text:
        return text
    
    if leading and text[0] in PUNCTUATION:
        return text[1:].strip()
    elif not leading and text[-1] in PUNCTUATION:
        return text[:-1].strip()
    return text


def get_prompt(content: str, bot_name: str) -> str | None:
    """Extract prompt from message. If bot_name is at start, strip it; otherwise return full message if bot_name appears anywhere."""
    if bot_name not in content:
        return None
    
    if content.startswith(bot_name):
        prompt = content[len(bot_name):].strip()
        return remove_punctuation(prompt)
    
    return content


def get_prompt_from_message(message: discord.Message) -> str | None:
    """Extract prompt from Discord message by checking mentions, bot names, and questions."""
    content = message.content.strip()
    content_lower = content.lower()
    prompt = None

    if client.user.mentioned_in(message):
        for mention_id in [
            f"<@{client.user.id}>".lower(),
            f"<@!{client.user.id}>".lower()
        ]:
            prompt = get_prompt(content_lower, mention_id)
            if prompt is not None:
                break

    if prompt is None:
        for name in BOT_NAMES:
            prompt = get_prompt(content_lower, name.lower())
            if prompt is not None:
                break

    if prompt is None and is_question(content):
        prompt = content

    return prompt


@client.event
async def on_ready():
    print(f"Logged in as {client.user}")


@client.event
async def on_message(message: discord.Message):
    if message.author == client.user:
        return

    prompt = get_prompt_from_message(message)

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
