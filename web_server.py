"""
FastAPI web server for Dawn Bringer Discord AI Bot.
Provides a web interface for users to interact with the bot without Discord.
"""

import os
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import asyncio
from typing import Optional


# Initialize FastAPI app
web_app = FastAPI(title="Dawn Bringer - Run! Goddess AI Assistant")

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


@web_app.post("/api/query")
async def query_api(request: Request):
    """Handle query requests from the web interface."""
    try:
        # Lazy import to avoid circular dependency
        import bot
        
        data = await request.json()
        question = data.get("question", "").strip()
        
        if not question:
            raise HTTPException(status_code=400, detail="No question provided")
        
        # Check if RAG system is initialized
        if bot.get_rag_chain() is None:
            raise HTTPException(
                status_code=503, 
                detail="RAG system is still initializing. Please try again in a moment."
            )
        
        # Use the existing RAG system from bot.py
        response_text, token_usage, _, metadata = await bot.get_ai_response(question)
        response_text, _ = bot.strip_unimportant_response(response_text)
        
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
                
                # Try to get URL
                url = None
                file_path = chunk.get("file_path")
                if file_path:
                    chunk_metadata = chunk.get("metadata", {})
                    from rag.utils import generate_github_link
                    start_line = chunk_metadata.get("start_line") if isinstance(chunk_metadata, dict) else None
                    end_line = chunk_metadata.get("end_line") if isinstance(chunk_metadata, dict) else None
                    # Normalize path
                    normalized_path = str(file_path).replace("\\", "/")
                    from rag.config import RAGConfig
                    docs_dir_name = RAGConfig.DOCS_DIR.name
                    github_file_path = f"{docs_dir_name}/{normalized_path}" if not normalized_path.startswith(f"{docs_dir_name}/") else normalized_path
                    url = generate_github_link(github_file_path, start_line, end_line)
                
                # Format source name
                if "/" in str(file_path):
                    name = str(file_path).split("/")[-1]
                else:
                    name = str(file_path) if file_path else source
                
                sources.append({
                    "source": source,
                    "name": name,
                    "url": url
                })
        
        # Calculate stats
        stats = None
        if token_usage:
            cost = bot.calculate_cost(token_usage.prompt_tokens, token_usage.completion_tokens, bot.MODEL)
            stats = {
                "cost": cost,
                "tokens": token_usage.total_tokens,
                "prompt_tokens": token_usage.prompt_tokens,
                "completion_tokens": token_usage.completion_tokens
            }
        
        return JSONResponse({
            "response": response_text,
            "sources": sources,
            "stats": stats,
            "metadata": {
                "retrieved_docs": metadata.get("retrieved_docs", 0) if metadata else 0
            }
        })
        
    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"⚠️ Error in query_api: {e}")
        import traceback
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Internal server error: {e}")


@web_app.get("/api/stats")
async def stats_api():
    """Get bot knowledge base statistics."""
    try:
        # Lazy import to avoid circular dependency
        import bot
        
        # Check rag_chain directly via module attribute (most reliable)
        rag_chain_value = bot.get_rag_chain()
        
        # If rag_chain is None, return initializing message
        if rag_chain_value is None:
            return JSONResponse({"stats": "📚 Initializing knowledge base..."})
        
        # Get stats using the existing function
        stats_string = bot.get_knowledge_stats_string()
        
        return JSONResponse({"stats": stats_string})
        
    except Exception as e:
        # Log error but don't expose details to client
        print(f"⚠️ Error in stats_api: {e}")
        return JSONResponse({"stats": "📚 Knowledge base unavailable"})


@web_app.get("/health")
async def health_check():
    """Health check endpoint for Railway."""
    return JSONResponse({"status": "ok", "service": "Dawn Bringer Web Interface"})


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
