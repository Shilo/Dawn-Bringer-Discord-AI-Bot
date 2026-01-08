"""
Main entry point for Railway deployment.
Exports the FastAPI app as 'app' for Railway's ASGI server.
Also starts the Discord bot in the background when running on Railway.
"""

import os
import asyncio
import threading
from web_server import web_app

# Export as 'app' for Railway's ASGI server
app = web_app

# Start the Discord bot in the background when running on Railway
# Railway sets RAILWAY_ENVIRONMENT, so we can detect if we're on Railway
if os.getenv("RAILWAY_ENVIRONMENT"):
    def start_bot():
        """Start the bot in a separate thread with its own event loop."""
        import bot
        # Create a new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            # Set up the event loop policy to ensure proper task context
            asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())
            loop.run_until_complete(bot.main())
        except Exception as e:
            print(f"❌ Error starting bot: {e}")
            import traceback
            print(traceback.format_exc())
        finally:
            loop.close()

    # Start bot in background thread
    print("🤖 Discord bot starting in background thread...")
    bot_thread = threading.Thread(target=start_bot, daemon=True)
    bot_thread.start()

