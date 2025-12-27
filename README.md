# Dawn Bringer Discord AI Bot

> Survivor, I'm here to help! As your Dawn Bringer, I've seen what this world can throw at us—infected, mad scientists, and everything in between. Need answers? Strategy? Just want to chat? Let's go—no challenge is too great when we face it together.
> - Mention me (@Dawn Bringer)
> - Say my name (DB, Dawn, Dawnbringer)
> - Ask a relevant game question

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
- Mentioning it: `@Dawn Bringer what is the meaning of life?`
- Using a trigger name: `dawn tell me a joke`
- Asking a question in #👧ask-dawn-bringer: `Why is the sky blue?`

### Trigger Names

The bot responds to:
- `@Dawn Bringer` (mention/tag)
- `db`
- `dawn`
- `dawnbringer`
- `dawn bringer`
- Any question in `#👧ask-dawn-bringer`

Edit the `BOT_NAMES` list in `bot.py` to customize the text prefixes.
