"""Shared state for RAG chain access across modules."""

import asyncio
from typing import Any, Optional

rag_chain = None
client_ready = False
gift_code_channel = None
_discord_loop: Optional[asyncio.AbstractEventLoop] = None


def get_rag_chain():
    return rag_chain


def set_rag_chain(value):
    global rag_chain
    rag_chain = value


def get_client_ready(client=None):
    if client is not None:
        try:
            if client.is_ready():
                return True
        except Exception:
            pass
    return client_ready


def set_client_ready(value):
    global client_ready
    client_ready = value


def get_gift_code_channel():
    return gift_code_channel


def set_gift_code_channel(value):
    global gift_code_channel
    gift_code_channel = value


def set_discord_loop(loop: asyncio.AbstractEventLoop):
    """Set the Discord client's event loop for cross-thread operations."""
    global _discord_loop
    _discord_loop = loop


def get_discord_loop() -> Optional[asyncio.AbstractEventLoop]:
    """Get the Discord client's event loop."""
    return _discord_loop


async def run_in_discord_loop(coro) -> Any:
    """Run a coroutine in the Discord client's event loop from another thread."""
    loop = get_discord_loop()
    if loop is None:
        raise RuntimeError("Discord event loop not available")

    # If we're already in the Discord loop, just await the coroutine
    current_loop = asyncio.get_running_loop()
    if current_loop is loop:
        return await coro

    # Otherwise, use run_coroutine_threadsafe
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return await asyncio.wrap_future(future)
