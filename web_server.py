"""
FastAPI web server for Dawn Bringer Discord AI Bot.
Provides a web interface for users to interact with the bot without Discord.
"""

import os
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException
from fastapi import Path as FastAPIPath
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import asyncio
from typing import Optional


# Initialize FastAPI app
web_app = FastAPI(title="Dawn Bringer - Run! Goddess AI")

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


@web_app.get("/", response_class=HTMLResponse)
async def home():
    """Serve the main web interface."""
    html_file = PUBLIC_DIR / "index.html"
    if not html_file.exists():
        raise HTTPException(status_code=500, detail="HTML file not found")
    return FileResponse(html_file)


def format_web_api_response(response_text: str, token_usage, metadata: dict = None, client_ip: str = "unknown") -> dict:
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
    cost = calculate_cost(token_usage.prompt_tokens, token_usage.completion_tokens, Config.MODEL)
    
    # Log response information (same format as Discord responses)
    print(f"📤 Response sent | User: Web API ({client_ip}) | Channel: Web Interface | Cost: ${cost:.6f} | Tokens: {token_usage.total_tokens} ({token_usage.prompt_tokens} prompt + {token_usage.completion_tokens} completion) | Response length: {len(response_text)} chars")
    
    # Format sources for the web interface
    sources = []
    if metadata:
        from rag.utils import format_source_links
        # Get source links (returns markdown formatted strings)
        source_links = format_source_links(metadata, max_sources=5, show_without_links=True)
        
        # Parse sources from retrieved_chunks
        retrieved_chunks = metadata.get("retrieved_chunks", [])
        used_source_indices = metadata.get("used_source_indices")
        
        # If we have used_source_indices, only show those sources
        if used_source_indices is not None:
            used_indices_set = set(used_source_indices)
            chunks_to_show = [chunk for chunk in retrieved_chunks 
                             if chunk.get("source_index") in used_indices_set]
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
                channel_id = int(channel_id) if isinstance(channel_id, str) and channel_id.isdigit() else channel_id
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
                github_file_path = f"{docs_dir_name}/{normalized_path}" if not normalized_path.startswith(f"{docs_dir_name}/") else normalized_path
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
                file_path_str = str(file_path).replace("\\", "/")  # Normalize to forward slashes
                if "/" in file_path_str:
                    name = file_path_str.split("/")[-1]
                else:
                    name = file_path_str
                # Remove .md extension if present
                if name.endswith('.md'):
                    name = name[:-3]
            else:
                # Fallback: extract from source
                source_str = str(source).replace("\\", "/")  # Normalize to forward slashes
                if "/" in source_str:
                    name = source_str.split("/")[-1]
                    if name.endswith('.md'):
                        name = name[:-3]
                else:
                    name = str(source)
            
            # Try to read external link from .meta file (Discord/website)
            external_link_info = None
            if file_path and not is_channel_id:
                from rag.utils import read_external_link_from_meta
                external_link_info = read_external_link_from_meta(file_path)
            
            sources.append({
                "source": source,
                "name": name,
                "url": url,
                "external_link": external_link_info,  # Tuple of (ref_name, external_url) or None
                "start_line": start_line,
                "end_line": end_line
            })
    
    # Calculate stats (cost already calculated above for logging)
    stats = None
    if token_usage:
        stats = {
            "cost": cost,
            "tokens": token_usage.total_tokens,
            "prompt_tokens": token_usage.prompt_tokens,
            "completion_tokens": token_usage.completion_tokens
        }
    
    return {
        "response": response_text,
        "sources": sources,
        "stats": stats,
        "metadata": {
            "retrieved_docs": metadata.get("retrieved_docs", 0) if metadata else 0
        }
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
                detail="RAG system is still initializing. Please try again in a moment."
            )

        # Lazy import to avoid circular dependency - only import when RAG is ready
        try:
            from bot import process_user_prompt
        except Exception as import_error:
            print(f"⚠️ Failed to import bot functions: {import_error}")
            raise HTTPException(
                status_code=503,
                detail="Bot dependencies are not properly initialized. Please ensure the bot has been started and the RAG system is ready."
            )

        # Use the same processing logic as Discord messages
        # This ensures gift code requests work the same way
        result = await process_user_prompt(question, is_direct=True)
        if result is None:
            raise HTTPException(
                status_code=400,
                detail="Unable to process question"
            )
        
        response_text, token_usage, metadata = result
        
        # Get client IP address if available
        client_ip = request.client.host if request.client else "unknown"
        
        # Format response for web API
        response_data = format_web_api_response(response_text, token_usage, metadata, client_ip)
        
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
                detail="RAG system is still initializing. Please try again in a moment."
            )

        # Lazy import to avoid circular dependency - only import when RAG is ready
        try:
            from bot import process_user_prompt
        except Exception as import_error:
            print(f"⚠️ Failed to import bot functions: {import_error}")
            raise HTTPException(
                status_code=503,
                detail="Bot dependencies are not properly initialized. Please ensure the bot has been started and the RAG system is ready."
            )

        # Regenerate with same parameters
        result = await process_user_prompt(prompt, is_direct=True)
        if result is None:
            raise HTTPException(
                status_code=400,
                detail="Unable to process prompt"
            )
        
        response_text, token_usage, metadata = result
        
        # Get client IP address if available
        client_ip = request.client.host if request.client else "unknown"
        
        # Format response for web API
        response_data = format_web_api_response(response_text, token_usage, metadata, client_ip)
        
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
                detail="RAG system is still initializing. Please try again in a moment."
            )

        # Lazy import to avoid circular dependency - only import when RAG is ready
        try:
            from bot import SYSTEM_PROMPT, get_ai_response, strip_unimportant_response, GIFT_CODE_SERVER_ID
        except Exception as import_error:
            print(f"⚠️ Failed to import bot functions: {import_error}")
            raise HTTPException(
                status_code=503,
                detail="Bot dependencies are not properly initialized. Please ensure the bot has been started and the RAG system is ready."
            )

        # Get extended system prompt (detailed and comprehensive with higher token limit)
        base_system_prompt = SYSTEM_PROMPT
        extended_system_prompt = base_system_prompt.replace(
            "Concise and direct.",
            "Detailed and comprehensive."
        )
        # Use same token limit logic as Discord bot
        from configs import Config
        extended_system_prompt = extended_system_prompt.replace(
            "Maximum length: 500 tokens.",
            f"Maximum length: {max(Config.MAX_TOKENS, 1000)} tokens."
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
            system_prompt_override=extended_system_prompt
        )
        
        # Check if the bot cannot answer
        response_text, is_unimportant = strip_unimportant_response(response_text)
        if is_unimportant:
            raise HTTPException(
                status_code=400,
                detail="Unable to extend response"
            )
        
        # Get client IP address if available
        client_ip = request.client.host if request.client else "unknown"
        
        # Format response for web API (with max_sources=10 for extended)
        response_data = format_web_api_response(response_text, token_usage, metadata, client_ip)
        
        # Update sources to show up to 10 for extended responses
        if metadata:
            from rag.utils import format_source_links
            source_links = format_source_links(metadata, max_sources=10, show_without_links=True)
            
            # Rebuild sources list with up to 10 sources
            retrieved_chunks = metadata.get("retrieved_chunks", [])
            used_source_indices = metadata.get("used_source_indices")
            
            if used_source_indices is not None:
                used_indices_set = set(used_source_indices)
                chunks_to_show = [chunk for chunk in retrieved_chunks 
                                 if chunk.get("source_index") in used_indices_set]
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
                    channel_id = int(channel_id) if isinstance(channel_id, str) and channel_id.isdigit() else channel_id
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
                    github_file_path = f"{docs_dir_name}/{normalized_path}" if not normalized_path.startswith(f"{docs_dir_name}/") else normalized_path
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
                    file_path_str = str(file_path).replace("\\", "/")  # Normalize to forward slashes
                    if "/" in file_path_str:
                        name = file_path_str.split("/")[-1]
                    else:
                        name = file_path_str
                    # Remove .md extension if present
                    if name.endswith('.md'):
                        name = name[:-3]
                else:
                    # Fallback: extract from source
                    source_str = str(source).replace("\\", "/")  # Normalize to forward slashes
                    if "/" in source_str:
                        name = source_str.split("/")[-1]
                        if name.endswith('.md'):
                            name = name[:-3]
                    else:
                        name = str(source)
                
                # Try to read external link from .meta file (Discord/website)
                external_link_info = None
                if file_path and not is_channel_id:
                    from rag.utils import read_external_link_from_meta
                    external_link_info = read_external_link_from_meta(file_path)
                
                sources.append({
                    "source": source,
                    "name": name,
                    "url": url,
                    "external_link": external_link_info,  # Tuple of (ref_name, external_url) or None
                    "start_line": start_line,
                    "end_line": end_line
                })
            
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
        
        rag_chain = get_rag_chain()
        
        if rag_chain is None:
            return JSONResponse({"stats": "Initializing knowledge base..."})
        
        # Get stats directly from the rag_chain
        stats = rag_chain.retriever.vector_store.get_stats()
        doc_count = stats.get("document_count", 0)
        estimated_words = estimate_words_from_chunks(doc_count)
        word_display = format_word_count(estimated_words)
        stats_string = f"My game knowledge: ~{word_display} words from {doc_count:,} articles"
        
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
            raise HTTPException(status_code=400, detail="Prompt and response are required")
        
        # Create share and get short ID
        short_id = share_db.create_share(prompt, response, metadata)
        
        # Get the base URL
        railway_public_domain = os.getenv("RAILWAY_PUBLIC_DOMAIN")
        if railway_public_domain:
            base_url = f"https://{railway_public_domain}"
        else:
            # Fallback to request host
            host = request.headers.get("host", "localhost:8000")
            scheme = "https" if request.url.scheme == "https" or "railway" in host else "http"
            base_url = f"{scheme}://{host}"
        
        short_url = f"{base_url}/{short_id}"
        
        return JSONResponse({
            "short_id": short_id,
            "url": short_url
        })
        
    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"⚠️ Error in create_share_api: {e}")
        import traceback
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Internal server error: {e}")


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


@web_app.get("/{short_id}", response_class=HTMLResponse)
async def share_page(short_id: str = FastAPIPath(..., pattern=r"^[a-zA-Z0-9]{6}$")):
    """Serve the shared conversation page with chat interface."""
    try:
        import share_db

        # Check if share exists (don't increment view count here - JavaScript API will do it)
        # The JavaScript will call /api/share/{short_id} which increments the count
        # We just need to check if it exists to show 404 or serve the page
        conn = share_db.get_db_connection()
        cursor = conn.execute(
            "SELECT id FROM shares WHERE id = ?",
            (short_id,)
        )
        share_exists = cursor.fetchone() is not None
        conn.close()

        if not share_exists:
            # Return 404 page
            html_content = """
            <!DOCTYPE html>
            <html lang="en">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Share Not Found - Dawn Bringer</title>
                <link rel="icon" type="image/png" href="/static/icon.png">
                <link rel="stylesheet" href="/static/style.css">
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <div class="header-icon"><img src="/static/icon.png" alt="Dawn Bringer"></div>
                        <div class="header-text"><h1>Dawn Bringer</h1></div>
                        <div class="header-subtitle">Run! Goddess AI</div>
                    </div>
                    <div style="text-align: center; padding: 2rem;">
                        <h2>Share Not Found</h2>
                        <p>This shared conversation could not be found. It may have expired or the link is invalid.</p>
                        <a href="/" style="color: #4a9eff;">Return to home</a>
                    </div>
                </div>
            </body>
            </html>
            """
            return HTMLResponse(content=html_content, status_code=404)

        # Serve the main index.html page (it will detect the share URL and show share UI)
        html_file = PUBLIC_DIR / "index.html"
        if not html_file.exists():
            raise HTTPException(status_code=500, detail="Page template not found")

        # Read and return the HTML (it will load the share data via JavaScript)
        return FileResponse(html_file)

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
        log_level="info",
        access_log=False  # Reduce noise in logs
    )
    server = uvicorn.Server(config)
    
    return asyncio.create_task(server.serve())
