# Dawn Bringer Discord AI Bot

A simple Discord bot that uses OpenAI to respond to prompts.

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
- `@DawnBringer` (mention/tag)
- `dawn`
- `dawnbringer`
- `dawn bringer`

Edit the `BOT_NAMES` list in `bot.py` to customize the text prefixes.
