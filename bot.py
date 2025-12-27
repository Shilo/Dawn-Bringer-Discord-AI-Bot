import os
import discord
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# Configuration
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Names the bot will respond to (case-insensitive)
BOT_NAMES = ["dawn", "dawnbringer", "dawn bringer"]

# Initialize clients
client = discord.Client(intents=discord.Intents.default() | discord.Intents.message_content)
openai_client = OpenAI(api_key=OPENAI_API_KEY)


def get_ai_response(prompt: str) -> str:
    """Get a response from OpenAI."""
    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=500
    )
    return response.choices[0].message.content


@client.event
async def on_ready():
    print(f"Logged in as {client.user}")


@client.event
async def on_message(message: discord.Message):
    # Ignore messages from the bot itself
    if message.author == client.user:
        return

    content = message.content.strip()
    prompt = None

    # Check if bot is mentioned
    if client.user.mentioned_in(message):
        prompt = content.replace(f"<@{client.user.id}>", "").strip()

    # Check if message starts with any of the bot names
    if prompt is None:
        content_lower = content.lower()
        for name in BOT_NAMES:
            if content_lower.startswith(name):
                prompt = content[len(name):].strip()
                # Remove leading punctuation like comma or colon
                if prompt and prompt[0] in ",:-":
                    prompt = prompt[1:].strip()
                break

    # If we found a prompt, respond
    if prompt:
        async with message.channel.typing():
            try:
                response = get_ai_response(prompt)
                await message.reply(response)
            except Exception as e:
                await message.reply(f"Error: {e}")


if __name__ == "__main__":
    client.run(DISCORD_TOKEN)
