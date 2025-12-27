# Dawn Bringer Discord AI Bot

> Survivor, I'm here to help. As your Dawn Bringer, I've seen what this world can throw at us—infected, mad scientists, and everything in between. Need answers? Strategy? Just want to chat? @Mention me or say my name (DB, Dawn, Dawnbringer) and I'll be there. Let's go—no challenge is too great when we face it together.

A Discord bot for the Run! Goddess community, powered by OpenAI.

## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Create a `.env` file with your API keys:
   ```bash
   cp .env.example .env
   ```

3. Edit `.env` with your tokens:
   ```
   DISCORD_TOKEN=your_discord_bot_token_here
   OPENAI_API_KEY=your_openai_api_key_here
   ```

4. Run the bot:
   ```bash
   python bot.py
   ```

## Usage

Prompt the bot by:
- Mentioning it: `@DawnBringer what is the meaning of life?`
- Using a trigger name: `dawn tell me a joke`

### Trigger Names

The bot responds to:
- `@Dawn Bringer` (mention/tag)
- `db`
- `dawn`
- `dawnbringer`
- `dawn bringer`

Edit the `BOT_NAMES` list in `bot.py` to customize the text prefixes.
