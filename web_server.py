"""
FastAPI web server for Dawn Bringer Discord AI Bot.
Provides a web interface for users to interact with the bot without Discord.
"""

import os
import re
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException
from fastapi import Path as FastAPIPath
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import asyncio
from typing import Optional


# Initialize FastAPI app
web_app = FastAPI(title="Run! Goddess AI - Dawn Bringer")

# Add CORS middleware
web_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Get the public directory path
PUBLIC_DIR = Path(__file__).parent / "public"

# Mount static files
web_app.mount("/static", StaticFiles(directory=str(PUBLIC_DIR)), name="static")


def sanitize_text_for_preview(text: str) -> str:
    """Sanitize text for Discord preview by removing markdown formatting and normalizing whitespace.

    Args:
        text: Raw text that may contain markdown formatting and newlines

    Returns:
        Cleaned text suitable for Discord preview meta tags
    """
    if not text:
        return ""

    # Remove markdown formatting
    # Remove code blocks (```code```)
    text = re.sub(r"```[\s\S]*?```", "", text, flags=re.DOTALL)
    # Remove inline code (`code`)
    text = re.sub(r"`([^`\n]+)`", r"\1", text)
    # Remove bold/italic (**text**, *text*, ***text***, __text__, _text_)
    text = re.sub(r"\*\*\*([^*\n]+)\*\*\*", r"\1", text)  # ***bold italic***
    text = re.sub(r"\*\*([^*\n]+)\*\*", r"\1", text)  # **bold**
    text = re.sub(r"__([^_\n]+)__", r"\1", text)  # __bold__
    text = re.sub(r"\*([^*\n]+)\*", r"\1", text)  # *italic*
    text = re.sub(r"_([^_\n]+)_", r"\1", text)  # _italic_
    # Remove headers (# ## ### etc.)
    text = re.sub(r"^#+\s+", "", text, flags=re.MULTILINE)
    # Remove links [text](url) but keep the text
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    # Remove strikethrough (~~text~~)
    text = re.sub(r"~~([^~\n]+)~~", r"\1", text)
    # Remove spoilers ||text||
    text = re.sub(r"\|\|([^\|\n]+)\|\|", r"\1", text)
    # Remove list markers (-, *, +, numbers)
    text = re.sub(r"^[\s]*[-\*\+]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^[\s]*\d+\.\s+", "", text, flags=re.MULTILINE)

    # Normalize whitespace
    # Replace newlines with spaces
    text = text.replace("\n", " ").replace("\r", " ")
    # Remove extra spaces and tabs
    text = re.sub(r"\s+", " ", text)
    # Strip leading/trailing whitespace
    text = text.strip()

    return text


@web_app.get("/", response_class=HTMLResponse)
async def home():
    """Serve the main web interface."""
    html_file = PUBLIC_DIR / "index.html"
    if not html_file.exists():
        raise HTTPException(status_code=500, detail="HTML file not found")
    return FileResponse(html_file)


def format_web_api_response(
    response_text: str, token_usage, metadata: dict = None, client_ip: str = "unknown"
) -> dict:
    """Format the response for the web API.

    This function extracts the response formatting logic so it can be reused.

    Args:
        response_text: The AI response text
        token_usage: Token usage object from OpenAI
        metadata: Optional metadata dict containing sources and retrieved_chunks
        client_ip: Client IP address for logging (default: "unknown")

    Returns:
        Dictionary with response, sources, stats, and metadata
    """
    from configs import Config
    from bot import calculate_cost, GIFT_CODE_SERVER_ID

    # Calculate cost (used for both logging and stats)
    cost = calculate_cost(
        token_usage.prompt_tokens, token_usage.completion_tokens, Config.MODEL
    )

    # Log response information (same format as Discord responses)
    print(
        f"📤 Response sent | User: Web API ({client_ip}) | Channel: Web Interface | Cost: ${cost:.6f} | Tokens: {token_usage.total_tokens} ({token_usage.prompt_tokens} prompt + {token_usage.completion_tokens} completion) | Response length: {len(response_text)} chars"
    )

    # Format sources for the web interface
    sources = []
    if metadata:
        from rag.utils import format_source_links

        # Get source links (returns markdown formatted strings)
        source_links = format_source_links(
            metadata, max_sources=5, show_without_links=True
        )

        # Parse sources from retrieved_chunks
        retrieved_chunks = metadata.get("retrieved_chunks", [])
        used_source_indices = metadata.get("used_source_indices")

        # If we have used_source_indices, only show those sources
        if used_source_indices is not None:
            used_indices_set = set(used_source_indices)
            chunks_to_show = [
                chunk
                for chunk in retrieved_chunks
                if chunk.get("source_index") in used_indices_set
            ]
        else:
            chunks_to_show = retrieved_chunks[:5]  # Show top 5 if no specific indices

        seen_sources = set()
        for chunk in chunks_to_show:
            source = chunk.get("source", "Unknown")
            if source in seen_sources:
                continue
            seen_sources.add(source)

            # Get metadata and file_path
            chunk_metadata = chunk.get("metadata", {})
            if isinstance(chunk_metadata, dict):
                file_path = chunk_metadata.get("file_path") or chunk.get("file_path")
                channel_id = chunk_metadata.get("channel_id")
            else:
                file_path = chunk.get("file_path")
                channel_id = None

            # If file_path is not set, use source as file_path (source often contains the path)
            if not file_path:
                file_path = source

            # Check if this is a channel ID (gift code document)
            # Channel IDs are stored as integers or numeric strings
            is_channel_id = False
            if channel_id is not None:
                is_channel_id = True
                channel_id = (
                    int(channel_id)
                    if isinstance(channel_id, str) and channel_id.isdigit()
                    else channel_id
                )
            elif isinstance(file_path, str) and file_path.isdigit():
                is_channel_id = True
                channel_id = int(file_path)

            # Try to get URL
            url = None
            start_line = None
            end_line = None
            if is_channel_id:
                # Generate Discord channel link
                server_id = GIFT_CODE_SERVER_ID
                if server_id and channel_id:
                    # Convert server_id to int if it's a string
                    if isinstance(server_id, str) and server_id.isdigit():
                        server_id = int(server_id)
                    url = f"https://discord.com/channels/{server_id}/{channel_id}"
            elif file_path:
                if isinstance(chunk_metadata, dict):
                    start_line = chunk_metadata.get("start_line")
                    end_line = chunk_metadata.get("end_line")
                    # Convert string to int if needed (ChromaDB may store as strings)
                    try:
                        start_line = int(start_line) if start_line else None
                    except (ValueError, TypeError):
                        start_line = None
                    try:
                        end_line = int(end_line) if end_line else None
                    except (ValueError, TypeError):
                        end_line = None

                from rag.utils import generate_github_link

                # Normalize path
                normalized_path = str(file_path).replace("\\", "/")
                from configs import Config

                docs_dir_name = Config.DOCS_DIR.name
                github_file_path = (
                    f"{docs_dir_name}/{normalized_path}"
                    if not normalized_path.startswith(f"{docs_dir_name}/")
                    else normalized_path
                )
                url = generate_github_link(github_file_path, start_line, end_line)

            # Format source name (just the MD file name, remove .md extension if present)
            # Handle both forward slashes and backslashes (Windows paths)
            if is_channel_id:
                # For channel IDs, try to get the channel name from shared state
                from shared_state import get_gift_code_channel

                channel = get_gift_code_channel()
                if channel and channel.id == channel_id:
                    # Use channel name with emoji if available (Discord format)
                    name = f"#{channel.name}"
                else:
                    # Fallback: use channel mention format
                    name = f"#{channel_id}"
            elif file_path:
                file_path_str = str(file_path).replace(
                    "\\", "/"
                )  # Normalize to forward slashes
                if "/" in file_path_str:
                    name = file_path_str.split("/")[-1]
                else:
                    name = file_path_str
                # Remove .md extension if present
                if name.endswith(".md"):
                    name = name[:-3]
            else:
                # Fallback: extract from source
                source_str = str(source).replace(
                    "\\", "/"
                )  # Normalize to forward slashes
                if "/" in source_str:
                    name = source_str.split("/")[-1]
                    if name.endswith(".md"):
                        name = name[:-3]
                else:
                    name = str(source)

            # Try to read external link from .meta file (Discord/website)
            external_link_info = None
            if file_path and not is_channel_id:
                from rag.utils import read_external_link_from_meta

                external_link_info = read_external_link_from_meta(file_path)

            sources.append(
                {
                    "source": source,
                    "name": name,
                    "url": url,
                    "external_link": external_link_info,  # Tuple of (ref_name, external_url) or None
                    "start_line": start_line,
                    "end_line": end_line,
                }
            )

    # Calculate stats (cost already calculated above for logging)
    stats = None
    if token_usage:
        stats = {
            "cost": cost,
            "tokens": token_usage.total_tokens,
            "prompt_tokens": token_usage.prompt_tokens,
            "completion_tokens": token_usage.completion_tokens,
        }

    return {
        "response": response_text,
        "sources": sources,
        "stats": stats,
        "metadata": {
            "retrieved_docs": metadata.get("retrieved_docs", 0) if metadata else 0
        },
    }


@web_app.post("/api/query")
async def query_api(request: Request):
    """Handle query requests from the web interface."""
    try:
        data = await request.json()
        question = data.get("question", "").strip()

        if not question:
            raise HTTPException(status_code=400, detail="No question provided")

        # Check if RAG system is initialized
        from shared_state import get_rag_chain

        if get_rag_chain() is None:
            raise HTTPException(
                status_code=503,
                detail="RAG system is still initializing. Please try again in a moment.",
            )

        # Lazy import to avoid circular dependency - only import when RAG is ready
        try:
            from bot import process_user_prompt
        except Exception as import_error:
            print(f"⚠️ Failed to import bot functions: {import_error}")
            raise HTTPException(
                status_code=503,
                detail="Bot dependencies are not properly initialized. Please ensure the bot has been started and the RAG system is ready.",
            )

        # Use the same processing logic as Discord messages
        # This ensures gift code requests work the same way
        result = await process_user_prompt(question, is_direct=True)
        if result is None:
            raise HTTPException(status_code=400, detail="Unable to process question")

        response_text, token_usage, metadata = result

        # Get client IP address if available
        client_ip = request.client.host if request.client else "unknown"

        # Format response for web API
        response_data = format_web_api_response(
            response_text, token_usage, metadata, client_ip
        )

        return JSONResponse(response_data)

    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"⚠️ Error in query_api: {e}")
        import traceback

        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Internal server error: {e}")


@web_app.post("/api/regenerate")
async def regenerate_api(request: Request):
    """Handle regenerate requests from the web interface."""
    try:
        data = await request.json()
        prompt = data.get("prompt", "").strip()

        if not prompt:
            raise HTTPException(status_code=400, detail="No prompt provided")

        # Check if RAG system is initialized
        from shared_state import get_rag_chain

        if get_rag_chain() is None:
            raise HTTPException(
                status_code=503,
                detail="RAG system is still initializing. Please try again in a moment.",
            )

        # Lazy import to avoid circular dependency - only import when RAG is ready
        try:
            from bot import process_user_prompt
        except Exception as import_error:
            print(f"⚠️ Failed to import bot functions: {import_error}")
            raise HTTPException(
                status_code=503,
                detail="Bot dependencies are not properly initialized. Please ensure the bot has been started and the RAG system is ready.",
            )

        # Regenerate with same parameters
        result = await process_user_prompt(prompt, is_direct=True)
        if result is None:
            raise HTTPException(status_code=400, detail="Unable to process prompt")

        response_text, token_usage, metadata = result

        # Get client IP address if available
        client_ip = request.client.host if request.client else "unknown"

        # Format response for web API
        response_data = format_web_api_response(
            response_text, token_usage, metadata, client_ip
        )

        return JSONResponse(response_data)

    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"⚠️ Error in regenerate_api: {e}")
        import traceback

        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Internal server error: {e}")


@web_app.post("/api/extend")
async def extend_api(request: Request):
    """Handle extend (more) requests from the web interface."""
    try:
        data = await request.json()
        prompt = data.get("prompt", "").strip()

        if not prompt:
            raise HTTPException(status_code=400, detail="No prompt provided")

        # Check if RAG system is initialized
        from shared_state import get_rag_chain

        if get_rag_chain() is None:
            raise HTTPException(
                status_code=503,
                detail="RAG system is still initializing. Please try again in a moment.",
            )

        # Lazy import to avoid circular dependency - only import when RAG is ready
        try:
            from bot import (
                SYSTEM_PROMPT,
                get_ai_response,
                strip_unimportant_response,
                GIFT_CODE_SERVER_ID,
            )
        except Exception as import_error:
            print(f"⚠️ Failed to import bot functions: {import_error}")
            raise HTTPException(
                status_code=503,
                detail="Bot dependencies are not properly initialized. Please ensure the bot has been started and the RAG system is ready.",
            )

        # Get extended system prompt (detailed and comprehensive with higher token limit)
        base_system_prompt = SYSTEM_PROMPT
        extended_system_prompt = base_system_prompt.replace(
            "Concise and direct.", "Detailed and comprehensive."
        )

        # Use same token limit logic as Discord bot
        from configs import Config

        extended_system_prompt = extended_system_prompt.replace(
            "Maximum length: 500 tokens.",
            f"Maximum length: {max(Config.MAX_TOKENS, 1000)} tokens.",
        )

        # Calculate extended threshold (25% increase from default 1.2 = 1.5)
        # This allows more chunks that are slightly less relevant but still useful for comprehensive answers
        from configs import Config

        base_threshold = Config.SCORE_THRESHOLD or 1.2
        extended_threshold = base_threshold * 1.25

        # Get AI response with extended parameters (same as Discord bot)
        response_text, token_usage, _, metadata = await get_ai_response(
            prompt,
            max_tokens_override=Config.MAX_TOKENS * 2,
            top_k_override=10,
            score_threshold_override=extended_threshold,
            system_prompt_override=extended_system_prompt,
        )

        # Check if the bot cannot answer
        response_text, _ = strip_unimportant_response(response_text)

        # Get client IP address if available
        client_ip = request.client.host if request.client else "unknown"

        # Format response for web API (with max_sources=10 for extended)
        response_data = format_web_api_response(
            response_text, token_usage, metadata, client_ip
        )

        # Update sources to show up to 10 for extended responses
        if metadata:
            from rag.utils import format_source_links

            source_links = format_source_links(
                metadata, max_sources=10, show_without_links=True
            )

            # Rebuild sources list with up to 10 sources
            retrieved_chunks = metadata.get("retrieved_chunks", [])
            used_source_indices = metadata.get("used_source_indices")

            if used_source_indices is not None:
                used_indices_set = set(used_source_indices)
                chunks_to_show = [
                    chunk
                    for chunk in retrieved_chunks
                    if chunk.get("source_index") in used_indices_set
                ]
            else:
                chunks_to_show = retrieved_chunks[:10]

            seen_sources = set()
            sources = []
            for chunk in chunks_to_show:
                source = chunk.get("source", "Unknown")
                if source in seen_sources:
                    continue
                seen_sources.add(source)

                # Get metadata and file_path
                chunk_metadata = chunk.get("metadata", {})
                if isinstance(chunk_metadata, dict):
                    file_path = chunk_metadata.get("file_path") or chunk.get(
                        "file_path"
                    )
                    channel_id = chunk_metadata.get("channel_id")
                else:
                    file_path = chunk.get("file_path")
                    channel_id = None

                # If file_path is not set, use source as file_path (source often contains the path)
                if not file_path:
                    file_path = source

                # Check if this is a channel ID (gift code document)
                # Channel IDs are stored as integers or numeric strings
                is_channel_id = False
                if channel_id is not None:
                    is_channel_id = True
                    channel_id = (
                        int(channel_id)
                        if isinstance(channel_id, str) and channel_id.isdigit()
                        else channel_id
                    )
                elif isinstance(file_path, str) and file_path.isdigit():
                    is_channel_id = True
                    channel_id = int(file_path)

                # Try to get URL
                url = None
                start_line = None
                end_line = None
                if is_channel_id:
                    # Generate Discord channel link
                    server_id = GIFT_CODE_SERVER_ID
                    if server_id and channel_id:
                        # Convert server_id to int if it's a string
                        if isinstance(server_id, str) and server_id.isdigit():
                            server_id = int(server_id)
                        url = f"https://discord.com/channels/{server_id}/{channel_id}"
                elif file_path:
                    # Get line numbers from metadata
                    if isinstance(chunk_metadata, dict):
                        start_line = chunk_metadata.get("start_line")
                        end_line = chunk_metadata.get("end_line")
                        # Convert string to int if needed (ChromaDB may store as strings)
                        try:
                            start_line = int(start_line) if start_line else None
                        except (ValueError, TypeError):
                            start_line = None
                        try:
                            end_line = int(end_line) if end_line else None
                        except (ValueError, TypeError):
                            end_line = None

                    # Generate GitHub link
                    from rag.utils import generate_github_link

                    normalized_path = str(file_path).replace("\\", "/")
                    from configs import Config

                    docs_dir_name = Config.DOCS_DIR.name
                    github_file_path = (
                        f"{docs_dir_name}/{normalized_path}"
                        if not normalized_path.startswith(f"{docs_dir_name}/")
                        else normalized_path
                    )
                    url = generate_github_link(github_file_path, start_line, end_line)

                # Format source name (just the MD file name, remove .md extension if present)
                # Handle both forward slashes and backslashes (Windows paths)
                if is_channel_id:
                    # For channel IDs, try to get the channel name from shared state
                    from shared_state import get_gift_code_channel

                    channel = get_gift_code_channel()
                    if channel and channel.id == channel_id:
                        # Use channel name with emoji if available (Discord format)
                        name = f"#{channel.name}"
                    else:
                        # Fallback: use channel mention format
                        name = f"#{channel_id}"
                elif file_path:
                    file_path_str = str(file_path).replace(
                        "\\", "/"
                    )  # Normalize to forward slashes
                    if "/" in file_path_str:
                        name = file_path_str.split("/")[-1]
                    else:
                        name = file_path_str
                    # Remove .md extension if present
                    if name.endswith(".md"):
                        name = name[:-3]
                else:
                    # Fallback: extract from source
                    source_str = str(source).replace(
                        "\\", "/"
                    )  # Normalize to forward slashes
                    if "/" in source_str:
                        name = source_str.split("/")[-1]
                        if name.endswith(".md"):
                            name = name[:-3]
                    else:
                        name = str(source)

                # Try to read external link from .meta file (Discord/website)
                external_link_info = None
                if file_path and not is_channel_id:
                    from rag.utils import read_external_link_from_meta

                    external_link_info = read_external_link_from_meta(file_path)

                sources.append(
                    {
                        "source": source,
                        "name": name,
                        "url": url,
                        "external_link": external_link_info,  # Tuple of (ref_name, external_url) or None
                        "start_line": start_line,
                        "end_line": end_line,
                    }
                )

            response_data["sources"] = sources

        return JSONResponse(response_data)

    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"⚠️ Error in extend_api: {e}")
        import traceback

        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Internal server error: {e}")


@web_app.get("/api/stats")
async def stats_api():
    """Get bot knowledge base statistics."""
    try:
        # Use shared state (simple and reliable)
        from shared_state import get_rag_chain
        from rag.utils import estimate_words_from_chunks, format_word_count
        from configs import Config

        rag_chain = get_rag_chain()

        if rag_chain is None:
            return JSONResponse({"stats": "Initializing knowledge base..."})

        # Get stats directly from the rag_chain
        stats = rag_chain.retriever.vector_store.get_stats()
        doc_count = stats.get("document_count", 0)
        estimated_words = estimate_words_from_chunks(doc_count)
        word_display = format_word_count(estimated_words)

        # Format model name nicely (uppercase GPT prefix, title case the rest)
        model_name = re.sub(
            r"\b([a-zA-Z]+)\b",
            lambda m: m.group(1).title(),
            Config.MODEL.replace("-", " "),
        )
        if model_name.startswith("Gpt"):
            model_name = "GPT" + model_name[3:]

        stats_string = f"🧠 AI Model: {model_name} | 📚 Knowledge: ~{word_display} words, {doc_count:,} articles"

        return JSONResponse({"stats": stats_string})

    except Exception as e:
        # Log error but don't expose details to client
        print(f"⚠️ Error in stats_api: {e}")
        import traceback

        print(traceback.format_exc())
        return JSONResponse({"stats": "Knowledge base unavailable"})


@web_app.get("/health")
async def health_check():
    """Health check endpoint for Railway."""
    return JSONResponse({"status": "ok", "service": "Dawn Bringer Web Interface"})


@web_app.post("/api/share")
async def create_share_api(request: Request):
    """Create a new share and return the short URL."""
    try:
        import share_db

        data = await request.json()
        prompt = data.get("prompt", "").strip()
        response = data.get("response", "").strip()
        metadata = data.get("metadata")  # Optional metadata

        if not prompt or not response:
            raise HTTPException(
                status_code=400, detail="Prompt and response are required"
            )

        # Validate data sizes
        if len(prompt) > 10000:  # Reasonable limit for prompts
            raise HTTPException(status_code=400, detail="Prompt too long")
        if len(response) > 50000:  # Reasonable limit for responses
            raise HTTPException(status_code=400, detail="Response too long")

        # Create share and get short ID
        short_id = share_db.create_share(prompt, response, metadata)

        # Get the base URL
        railway_public_domain = os.getenv("RAILWAY_PUBLIC_DOMAIN")
        if railway_public_domain:
            base_url = f"https://{railway_public_domain}"
        else:
            # Fallback to request host
            host = request.headers.get("host", "localhost:8000")
            scheme = (
                "https"
                if request.url.scheme == "https" or "railway" in host
                else "http"
            )
            base_url = f"{scheme}://{host}"

        short_url = f"{base_url}/{short_id}"

        return JSONResponse({"short_id": short_id, "url": short_url})

    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"⚠️ Error in create_share_api: {e}")
        import traceback

        print(traceback.format_exc())
        # Return more detailed error for debugging
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@web_app.get("/api/share/{short_id}")
async def get_share_api(short_id: str):
    """Get share data by short ID."""
    try:
        import share_db

        share = share_db.get_share(short_id)
        if share is None:
            raise HTTPException(status_code=404, detail="Share not found")

        return JSONResponse(share)

    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"⚠️ Error in get_share_api: {e}")
        import traceback

        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Internal server error: {e}")


@web_app.api_route("/api/preview/{short_id}.png", methods=["GET", "HEAD"])
async def get_share_preview_image(short_id: str, request: Request):
    """Generate and serve a Discord preview image for a shared conversation."""
    try:
        import share_db
        from preview_image_generator import generate_conversation_preview

        # Validate short_id format
        import re

        if not re.match(r"^[a-zA-Z0-9]{6}$", short_id):
            raise HTTPException(status_code=404, detail="Invalid share ID format")

        # For HEAD requests, we need to generate/check the image exists but return empty content
        is_head_request = request.method == "HEAD"

        # Check for cached preview image first
        cached_image = share_db.get_preview_image(short_id)
        if cached_image is not None:
            # Return cached image
            return Response(
                content=cached_image if not is_head_request else b"",
                media_type="image/png",
                headers={
                    "Cache-Control": "public, max-age=86400",  # Cache for 24 hours (longer for cached images)
                    "Content-Length": str(len(cached_image)),
                    "X-Image-Source": "cache",
                },
            )

        # Get share data
        share = share_db.get_share(short_id)
        if share is None:
            raise HTTPException(status_code=404, detail="Share not found")

        # Sanitize text for image generation (same as Discord preview)
        sanitized_question = sanitize_text_for_preview(share["prompt"])
        sanitized_answer = sanitize_text_for_preview(share["response"])

        # Generate preview image
        image_data = generate_conversation_preview(
            question=sanitized_question,
            answer=sanitized_answer,
            bot_name="Dawn Bringer",
        )

        # Cache the generated image
        share_db.store_preview_image(short_id, image_data)

        # Return image with appropriate headers
        return Response(
            content=image_data if not is_head_request else b"",
            media_type="image/png",
            headers={
                "Cache-Control": "public, max-age=3600",  # Cache for 1 hour
                "Content-Length": str(len(image_data)),
                "X-Image-Source": "generated",
            },
        )

    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"⚠️ Error generating preview image: {e}")
        import traceback

        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Internal server error: {e}")


@web_app.get("/{short_id}", response_class=HTMLResponse)
async def share_page(short_id: str):
    """Serve the shared conversation page with chat interface."""
    try:
        import share_db

        # Check if short_id matches the expected pattern (6 alphanumeric characters)
        import re

        if not re.match(r"^[a-zA-Z0-9]{6}$", short_id):
            # Invalid share ID format - redirect to homepage
            from starlette.responses import RedirectResponse

            return RedirectResponse(url="/", status_code=302)

        # Get share data for meta tags (don't increment view count here - JavaScript API will do it)
        share = share_db.get_share(short_id)
        share_exists = share is not None

        if not share_exists:
            # Return 404 page
            return FileResponse(PUBLIC_DIR / "share-not-found.html", status_code=404)

        # Generate dynamic meta tags for Discord preview
        # Sanitize and truncate question as title, and answer as description
        sanitized_question = sanitize_text_for_preview(share["prompt"])
        sanitized_answer = sanitize_text_for_preview(share["response"])

        question = (
            sanitized_question[:400] + "…"
            if len(sanitized_question) > 400
            else sanitized_question
        )
        # Truncate answer to ~400 characters for Discord preview
        answer = (
            sanitized_answer[:400] + "…"
            if len(sanitized_answer) > 400
            else sanitized_answer
        )
        # Escape HTML entities for meta tags
        question_escaped = (
            question.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )
        answer_escaped = (
            answer.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

        # Get the base URL for og:url
        railway_public_domain = os.getenv("RAILWAY_PUBLIC_DOMAIN")
        if railway_public_domain:
            base_url = f"https://{railway_public_domain}"
        else:
            # Fallback to request host
            base_url = "https://your-domain.railway.app"  # User will need to set RAILWAY_PUBLIC_DOMAIN

        share_url = f"{base_url}/{short_id}"
        preview_image_url = f"{base_url}/api/preview/{short_id}.png"

        # Read the base HTML template
        html_file = PUBLIC_DIR / "index.html"
        if not html_file.exists():
            raise HTTPException(status_code=500, detail="Page template not found")

        with open(html_file, "r", encoding="utf-8") as f:
            html_content = f.read()

        # Replace the static meta tags with dynamic ones for share pages
        # Keep default title, use user question as description
        html_content = html_content.replace(
            '<meta property="og:description" content="Ask anything about Run! Goddess - Your AI companion">',
            f'<meta property="og:description" content="{question_escaped}">',
        )
        html_content = html_content.replace(
            '<meta property="og:image" content="/static/discord-preview.png">',
            f'<meta property="og:image" content="{preview_image_url}">',
        )
        html_content = html_content.replace(
            '<meta property="og:url" content="/">',
            f'<meta property="og:url" content="{share_url}">',
        )

        # Also update Twitter Card meta tags
        # Keep default title, use user question as description
        html_content = html_content.replace(
            '<meta name="twitter:description" content="Ask anything about Run! Goddess - Your AI companion">',
            f'<meta name="twitter:description" content="{question_escaped}">',
        )
        html_content = html_content.replace(
            '<meta name="twitter:image" content="/static/discord-preview.png">',
            f'<meta name="twitter:image" content="{preview_image_url}">',
        )

        # Keep default page title for consistency

        return HTMLResponse(content=html_content)

    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"⚠️ Error in share_page: {e}")
        import traceback

        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Internal server error: {e}")


def create_web_server_task(port: Optional[int] = None):
    """Create a task to run the web server.

    Args:
        port: Port to run on (defaults to PORT env var or 8000)

    Returns:
        asyncio.Task for the web server
    """
    import uvicorn

    if port is None:
        port = int(os.getenv("PORT", 8000))

    config = uvicorn.Config(
        web_app,
        host="0.0.0.0",
        port=port,
        log_level="warning",
        access_log=False,  # Reduce noise in logs
    )
    server = uvicorn.Server(config)

    return asyncio.create_task(server.serve())
