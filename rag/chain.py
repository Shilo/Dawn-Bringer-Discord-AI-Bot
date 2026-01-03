"""LangChain RAG chain setup."""

from typing import Tuple, Optional, List, Dict, Any
import json
import re
import logging
from datetime import datetime, timezone
from openai import OpenAI
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from rag.retriever import RAGRetriever
from rag.tools import FileSystemTools, get_tools_definitions
from rag.config import RAGConfig

# Set up logger for agent mode
logger = logging.getLogger(__name__)


class RAGChain:
    """Manages the RAG chain for question answering."""
    
    def __init__(
        self,
        retriever: RAGRetriever,
        model_name: str = "gpt-4o-mini",
        max_tokens: int = 500,
        temperature: float = 0.7,
        system_prompt: Optional[str] = None,
    ):
        """Initialize the RAG chain.
        
        Args:
            retriever: RAGRetriever instance
            model_name: OpenAI model name
            max_tokens: Maximum tokens for response
            temperature: LLM temperature (0.0-2.0)
            system_prompt: System prompt for the LLM
        """
        self.retriever = retriever
        self.model_name = model_name
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.system_prompt = system_prompt or "You are Dawn Bringer, a helpful Discord AI assistant."
        
        # Initialize LLM
        # Explicitly get API key from environment to avoid sync/async issues
        import os
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set")
        
        self.llm = ChatOpenAI(
            model=model_name,
            temperature=temperature,
            max_tokens=max_tokens,
            openai_api_key=api_key,
        )
        
        # Initialize file system tools for agent-like behavior
        self.tools = FileSystemTools()
        self.tools_enabled = True  # Enable tools by default
    
    def _prepare_query(self, user_query: str, include_scores: bool = False, top_k_override: Optional[int] = None, additional_context: Optional[str] = None, additional_metadata: Optional[dict] = None) -> Tuple[list, str, list, Optional[list]]:
        """Prepare query by retrieving documents and building message content.
        
        Args:
            user_query: User's question
            include_scores: If True, retrieve documents with scores (single search, more efficient)
            top_k_override: Optional override for top_k retrieval (passed through from query_with_usage)
            additional_context: Optional additional context content to inject as a document
            additional_metadata: Optional metadata dict for the additional context document (e.g., {"source": "...", "doc_type": "...", "channel_id": ...})
            
        Returns:
            Tuple of (retrieved_docs, message_content, sources, scores)
            scores is None if include_scores is False, otherwise list of (doc, score) tuples
        """
        # Check if we should skip RAG retrieval (only use additional context)
        skip_rag_retrieval = additional_metadata and additional_metadata.get("skip_rag_retrieval", False)
        
        # Use single search when scores are needed - more efficient than two separate searches
        scores = None
        threshold = self.retriever.vector_store.config.SCORE_THRESHOLD
        
        if skip_rag_retrieval:
            # Skip RAG retrieval, only use additional context
            retrieved_docs = []
        elif include_scores:
            # Single search that returns both docs and scores
            try:
                scores = self.retriever.retrieve_with_scores(user_query, score_threshold=threshold, top_k_override=top_k_override)
                # Extract documents from scores
                retrieved_docs = [doc for doc, score in scores]
            except Exception as e:
                print(f"⚠️ Warning: Could not retrieve scores: {e}")
                # Fallback to regular retrieve
                retrieved_docs = self.retriever.retrieve(user_query, apply_threshold=True, top_k_override=top_k_override)
                scores = None
        else:
            # Regular search without scores (more efficient)
            retrieved_docs = self.retriever.retrieve(user_query, apply_threshold=True, top_k_override=top_k_override)
        
        # Inject additional context as a document if provided
        if additional_context:
            from langchain_core.documents import Document as LangChainDocument
            # Use provided metadata or default empty dict
            metadata = additional_metadata.copy() if additional_metadata else {}
            # Ensure required fields have defaults
            if "source" not in metadata:
                metadata["source"] = ""
            if "file_path" not in metadata:
                metadata["file_path"] = metadata.get("source", "")
            if "doc_type" not in metadata:
                metadata["doc_type"] = "general"
            
            dynamic_doc = LangChainDocument(
                page_content=additional_context,
                metadata=metadata
            )
            # Insert at the beginning so it's prioritized
            retrieved_docs.insert(0, dynamic_doc)
        
        # Format context with numbered sources for citation tracking
        context = self.retriever.format_context(retrieved_docs, number_sources=True)
        
        # Get sources
        sources = self.retriever.get_sources(retrieved_docs)
        
        # Create message content with documentation context if available
        # Add instruction to cite which sources are used
        citation_instruction = "\n\nIMPORTANT: At the end of your response, on a new line, output only a valid JSON object (no markdown code blocks, no backticks, no formatting) with this exact structure: {\"used_sources\": [1, 2, 3]}. The numbers represent the source indices (Source 1, Source 2, etc.) from the documentation that you actually used to formulate your answer. Only list sources you directly referenced or used."
        message_content = (
            f"[Run! Goddess Documentation]\n\n{context}\n\n---\n\n[User Question]\n{user_query}{citation_instruction}"
            if context
            else user_query
        )
        
        return retrieved_docs, message_content, sources, scores
    
    def query(self, user_query: str, additional_context: Optional[str] = None, additional_metadata: Optional[dict] = None) -> Tuple[str, dict]:
        """Query the RAG chain with a user question.
        
        Args:
            user_query: User's question
            additional_context: Optional additional context content to inject
            additional_metadata: Optional metadata dict for the additional context document
            
        Returns:
            Tuple of (response_text, metadata_dict)
            metadata_dict contains:
                - sources: List of source documents
                - retrieved_docs: Number of documents retrieved
        """
        retrieved_docs, message_content, sources, _ = self._prepare_query(user_query, additional_context=additional_context, additional_metadata=additional_metadata)
        
        # Build messages for LangChain
        messages = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=message_content)
        ]
        
        # Get response from LLM
        response = self.llm.invoke(messages)
        response_text = response.content
        
        # Store raw response before any parsing/modification
        raw_response_text = response_text
        
        # Parse JSON citation from response to extract used source indices (same as query_with_usage)
        used_source_indices = None
        
        # First, try to find JSON inside a code block (```json ... ``` or ``` ... ```)
        code_block_pattern = r'```(?:json)?\s*(\{[^{}]*"used_sources"[^{}]*\[[^\]]*\][^{}]*\})\s*```'
        code_block_match = re.search(code_block_pattern, response_text, re.DOTALL | re.IGNORECASE)
        if code_block_match:
            try:
                citation_json = json.loads(code_block_match.group(1))
                used_source_indices = citation_json.get("used_sources", [])
                # Remove the entire code block from the response text
                response_text = response_text[:code_block_match.start()].rstrip()
            except json.JSONDecodeError:
                pass  # If JSON parsing fails, try plain JSON pattern
        
        # If not found in code block, try plain JSON object pattern
        if used_source_indices is None:
            json_match = re.search(r'\{[^{}]*"used_sources"[^{}]*\[[^\]]*\][^{}]*\}', response_text, re.DOTALL)
            if json_match:
                try:
                    citation_json = json.loads(json_match.group())
                    used_source_indices = citation_json.get("used_sources", [])
                    # Remove the JSON citation from the response text
                    response_text = response_text[:json_match.start()].rstrip()
                except json.JSONDecodeError:
                    pass  # If JSON parsing fails, used_source_indices remains None and all sources will be shown
        
        # Add source indices to chunks for filtering
        retrieved_chunks = []
        for idx, doc in enumerate(retrieved_docs, 1):
            chunk_info = {
                "content": doc.page_content,
                "source": doc.metadata.get("source", "Unknown"),
                "doc_type": doc.metadata.get("doc_type", "general"),
                "metadata": doc.metadata,
                "source_index": idx
            }
            retrieved_chunks.append(chunk_info)
        
        metadata = {
            "sources": sources,
            "retrieved_docs": len(retrieved_docs),
            "retrieved_chunks": retrieved_chunks,
            "used_source_indices": used_source_indices,
            "raw_response": raw_response_text,  # Store raw response before JSON parsing for response.md
        }
        
        return response_text, metadata
    
    def _execute_tool_call(self, function_name: str, arguments: Dict[str, Any]) -> str:
        """Execute a tool call and return the result as a string.
        
        Args:
            function_name: Name of the function to call
            arguments: Function arguments
            
        Returns:
            JSON string of the result
        """
        logger.info(f"🔧 Executing tool: {function_name}")
        logger.debug(f"   Arguments: {json.dumps(arguments, indent=2)}")
        
        start_time = datetime.now()
        
        try:
            if function_name == "list_files":
                result = self.tools.list_files(
                    directory=arguments.get("directory", ""),
                    pattern=arguments.get("pattern", "*.md")
                )
            elif function_name == "find_characters_by_pattern":
                result = self.tools.find_characters_by_pattern(
                    starts_with=arguments.get("starts_with", ""),
                    contains=arguments.get("contains", ""),
                    doc_type=arguments.get("doc_type", "character")
                )
            elif function_name == "read_file":
                result = self.tools.read_file(
                    file_path=arguments.get("file_path"),
                    max_lines=arguments.get("max_lines", 100)
                )
            elif function_name == "search_in_files":
                result = self.tools.search_in_files(
                    search_term=arguments.get("search_term"),
                    directory=arguments.get("directory", ""),
                    file_pattern=arguments.get("file_pattern", "*.md"),
                    max_results=arguments.get("max_results", 10)
                )
            elif function_name == "get_directory_structure":
                result = self.tools.get_directory_structure(
                    directory=arguments.get("directory", ""),
                    max_depth=arguments.get("max_depth", 2)
                )
            else:
                result = {"error": f"Unknown function: {function_name}"}
                logger.warning(f"⚠️ Unknown function called: {function_name}")
            
            elapsed = (datetime.now() - start_time).total_seconds()
            
            # Log result summary
            if isinstance(result, dict):
                if "error" in result:
                    logger.error(f"❌ Tool {function_name} failed: {result['error']}")
                else:
                    # Log summary based on result type
                    if "files" in result:
                        count = result.get("count", len(result.get("files", [])))
                        logger.info(f"✅ Tool {function_name} completed: Found {count} files ({elapsed:.2f}s)")
                    elif "characters" in result:
                        count = result.get("count", len(result.get("characters", [])))
                        logger.info(f"✅ Tool {function_name} completed: Found {count} characters ({elapsed:.2f}s)")
                    elif "results" in result:
                        count = result.get("count", len(result.get("results", [])))
                        logger.info(f"✅ Tool {function_name} completed: Found {count} results ({elapsed:.2f}s)")
                    elif "content" in result:
                        lines = result.get("line_count", 0)
                        truncated = result.get("truncated", False)
                        trunc_msg = " (truncated)" if truncated else ""
                        logger.info(f"✅ Tool {function_name} completed: Read {lines} lines{trunc_msg} ({elapsed:.2f}s)")
                    else:
                        logger.info(f"✅ Tool {function_name} completed ({elapsed:.2f}s)")
            
            return json.dumps(result, indent=2)
        except Exception as e:
            elapsed = (datetime.now() - start_time).total_seconds()
            logger.error(f"❌ Tool {function_name} exception after {elapsed:.2f}s: {e}", exc_info=True)
            return json.dumps({"error": str(e)})
    
    def query_with_usage(self, user_query: str, include_scores: bool = False, max_tokens_override: Optional[int] = None, top_k_override: Optional[int] = None, additional_context: Optional[str] = None, additional_metadata: Optional[dict] = None, enable_tools: bool = True) -> Tuple[str, object, dict]:
        """Query the RAG chain and return usage information.
        
        Args:
            user_query: User's question
            include_scores: If True, retrieve similarity scores (adds overhead - only use for debugging)
            max_tokens_override: Optional override for max_tokens (temporary, doesn't change instance setting)
            top_k_override: Optional override for top_k retrieval (temporary, doesn't change instance setting)
            additional_context: Optional additional context content to inject
            additional_metadata: Optional metadata dict for the additional context document
            enable_tools: If True, enable function calling tools for agent-like behavior
            
        Returns:
            Tuple of (response_text, usage_object, metadata_dict)
            usage_object is OpenAI Usage object with token counts
            metadata_dict contains:
                - sources: List of source documents
                - retrieved_docs: Number of documents retrieved
                - full_prompt: Full prompt sent to OpenAI (system + user messages)
                - retrieved_chunks: List of retrieved document chunks with metadata and similarity scores (if include_scores=True)
                - tool_calls: List of tool calls made during the query (if tools enabled)
        """
        # Check if we should use tools (agent mode) or regular RAG
        use_tools = enable_tools and self.tools_enabled
        
        if use_tools:
            logger.info(f"🤖 Agent mode enabled for query: {user_query[:100]}...")
            # Agent mode: Use function calling to let LLM explore docs
            return self._query_with_tools(user_query, include_scores, max_tokens_override, top_k_override, additional_context, additional_metadata)
        else:
            logger.info(f"📚 Regular RAG mode for query: {user_query[:100]}...")
            # Regular RAG mode: Use existing retrieval
            return self._query_without_tools(user_query, include_scores, max_tokens_override, top_k_override, additional_context, additional_metadata)
    
    def _query_without_tools(self, user_query: str, include_scores: bool, max_tokens_override: Optional[int], top_k_override: Optional[int], additional_context: Optional[str], additional_metadata: Optional[dict]) -> Tuple[str, object, dict]:
        """Query without tools (original RAG behavior)."""
        logger.debug("📚 Regular RAG mode: Retrieving documents...")
        
        retrieved_docs, message_content, sources, scores = self._prepare_query(user_query, include_scores=include_scores, top_k_override=top_k_override, additional_context=additional_context, additional_metadata=additional_metadata)
        
        logger.info(f"📚 RAG retrieved {len(retrieved_docs)} documents from {len(sources)} sources")
        logger.debug(f"   Context length: {len(message_content)} chars")
        
        # Add current date to system prompt so the model knows what today's date is
        current_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        system_prompt_with_date = f"{self.system_prompt}\n\nCurrent date: {current_date} (UTC)"
        
        # Build messages for OpenAI API
        messages = [
            {"role": "system", "content": system_prompt_with_date},
            {"role": "user", "content": message_content}
        ]
        
        # Format full prompt for debugging (includes system and user messages)
        full_prompt = f"System: {system_prompt_with_date}\n\nUser: {message_content}"
        
        # Use OpenAI client directly to get usage info
        # Use override if provided, otherwise use instance setting
        max_tokens_to_use = max_tokens_override if max_tokens_override is not None else self.max_tokens
        openai_client = OpenAI()
        
        logger.debug(f"📤 Sending request to OpenAI (model: {self.model_name}, tokens: {max_tokens_to_use})")
        api_start_time = datetime.now()
        
        response = openai_client.chat.completions.create(
            model=self.model_name,
            max_completion_tokens=max_tokens_to_use,
            temperature=self.temperature,
            messages=messages
        )
        
        api_elapsed = (datetime.now() - api_start_time).total_seconds()
        logger.info(f"📥 Received response ({api_elapsed:.2f}s)")
        logger.debug(f"   Usage: {response.usage.prompt_tokens} prompt + {response.usage.completion_tokens} completion = {response.usage.total_tokens} total")
        
        response_text = response.choices[0].message.content
        usage = response.usage
        
        logger.info(f"📊 Response length: {len(response_text)} chars")
        
        # Store raw response before any parsing/modification
        raw_response_text = response_text
        
        # Parse JSON citation from response to extract used source indices
        used_source_indices = None
        
        # First, try to find JSON inside a code block (```json ... ``` or ``` ... ```)
        code_block_pattern = r'```(?:json)?\s*(\{[^{}]*"used_sources"[^{}]*\[[^\]]*\][^{}]*\})\s*```'
        code_block_match = re.search(code_block_pattern, response_text, re.DOTALL | re.IGNORECASE)
        if code_block_match:
            try:
                citation_json = json.loads(code_block_match.group(1))
                used_source_indices = citation_json.get("used_sources", [])
                # Remove the entire code block from the response text
                response_text = response_text[:code_block_match.start()].rstrip()
            except json.JSONDecodeError:
                pass  # If JSON parsing fails, try plain JSON pattern
        
        # If not found in code block, try plain JSON object pattern
        if used_source_indices is None:
            json_match = re.search(r'\{[^{}]*"used_sources"[^{}]*\[[^\]]*\][^{}]*\}', response_text, re.DOTALL)
            if json_match:
                try:
                    citation_json = json.loads(json_match.group())
                    used_source_indices = citation_json.get("used_sources", [])
                    # Remove the JSON citation from the response text
                    response_text = response_text[:json_match.start()].rstrip()
                except json.JSONDecodeError:
                    pass  # If JSON parsing fails, used_source_indices remains None and all sources will be shown
        
        # Format retrieved chunks for debugging
        retrieved_chunks = []
        
        # Build a map of documents with scores (by source) for quick lookup
        scored_docs_map = {}
        if scores:
            for doc, score in scores:
                source = doc.metadata.get("source", "Unknown")
                scored_docs_map[source] = score
        
        # Process ALL retrieved_docs (including dynamically injected ones)
        # This ensures dynamically injected documents (like gift codes) are included
        # Also track source index for filtering
        for idx, doc in enumerate(retrieved_docs, 1):  # Start from 1 to match Source 1, Source 2, etc.
            source = doc.metadata.get("source", "Unknown")
            score = scored_docs_map.get(source)  # Get score if available, None otherwise
            
            chunk_info = {
                "content": doc.page_content,
                "source": source,
                "doc_type": doc.metadata.get("doc_type", "general"),
                "metadata": doc.metadata,
                "distance_score": score,
                "source_index": idx  # Add source index (1-based) for filtering
            }
            retrieved_chunks.append(chunk_info)
        
        metadata = {
            "sources": sources,
            "retrieved_docs": len(retrieved_docs),
            "full_prompt": full_prompt,
            "retrieved_chunks": retrieved_chunks,
            "used_source_indices": used_source_indices,  # Store used source indices for filtering
            "raw_response": raw_response_text,  # Store raw response before JSON parsing for response.md
        }
        
        return response_text, usage, metadata
    
    def _query_with_tools(self, user_query: str, include_scores: bool, max_tokens_override: Optional[int], top_k_override: Optional[int], additional_context: Optional[str], additional_metadata: Optional[dict]) -> Tuple[str, object, dict]:
        """Query with tools enabled (agent mode)."""
        logger.info("=" * 80)
        logger.info(f"🤖 AGENT MODE: Starting query processing")
        logger.info(f"📝 Query: {user_query}")
        logger.info("=" * 80)
        
        # Add current date to system prompt
        current_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        # Enhanced system prompt for agent mode
        tools_info = f"""
You have access to tools to explore the documentation directory. The documentation is located at: {RAGConfig.DOCS_DIR}

Available tools:
- list_files: List files in directories
- find_characters_by_pattern: Find characters matching patterns (e.g., "starts with S", "contains SP")
- read_file: Read specific documentation files
- search_in_files: Search for terms across files
- get_directory_structure: Get directory structure

When users ask pattern-based questions like "find valks that start with S" or "SP valk that starts with S", use the find_characters_by_pattern tool first to discover matching characters, then read those files to get detailed information.

You can also use regular RAG retrieval by including relevant context in your response. Use tools when you need to explore or discover information, especially for pattern-based queries.
"""
        
        system_prompt_with_tools = f"{self.system_prompt}\n\nCurrent date: {current_date} (UTC)\n\n{tools_info}"
        logger.debug(f"📋 System prompt length: {len(system_prompt_with_tools)} chars")
        
        # Get tools definitions
        tools = get_tools_definitions()
        logger.info(f"🛠️ Loaded {len(tools)} tools: {[t['function']['name'] for t in tools]}")
        
        # Build initial messages
        messages = [
            {"role": "system", "content": system_prompt_with_tools},
            {"role": "user", "content": user_query}
        ]
        
        # Also try RAG retrieval first to provide initial context
        retrieved_docs = []
        sources = []
        scores = None
        try:
            logger.info("📚 Attempting initial RAG retrieval...")
            retrieved_docs, rag_context, sources, scores = self._prepare_query(
                user_query, 
                include_scores=include_scores, 
                top_k_override=top_k_override,
                additional_context=additional_context,
                additional_metadata=additional_metadata
            )
            if rag_context:
                logger.info(f"✅ RAG retrieved {len(retrieved_docs)} documents, context length: {len(rag_context)} chars")
                messages.append({
                    "role": "assistant",
                    "content": f"[Initial RAG Context]\n{rag_context}\n\nI can also use tools to explore the documentation if needed."
                })
            else:
                logger.info("ℹ️ No RAG context retrieved")
        except Exception as e:
            logger.warning(f"⚠️ RAG retrieval failed in agent mode: {e}", exc_info=True)
        
        max_tokens_to_use = max_tokens_override if max_tokens_override is not None else self.max_tokens
        openai_client = OpenAI()
        
        tool_calls_made = []
        max_iterations = 5  # Prevent infinite loops
        iteration = 0
        
        logger.info(f"🔄 Starting tool calling loop (max {max_iterations} iterations)")
        
        # Tool calling loop
        while iteration < max_iterations:
            iteration += 1
            logger.info(f"\n--- Iteration {iteration}/{max_iterations} ---")
            
            # Make API call with tools
            logger.info(f"📤 Sending request to OpenAI (model: {self.model_name}, tokens: {max_tokens_to_use})")
            logger.debug(f"   Message count: {len(messages)}")
            
            api_start_time = datetime.now()
            response = openai_client.chat.completions.create(
                model=self.model_name,
                max_completion_tokens=max_tokens_to_use,
                temperature=self.temperature,
                messages=messages,
                tools=tools,
                tool_choice="auto"
            )
            api_elapsed = (datetime.now() - api_start_time).total_seconds()
            
            message = response.choices[0].message
            messages.append(message)
            
            logger.info(f"📥 Received response ({api_elapsed:.2f}s)")
            logger.debug(f"   Response finish_reason: {response.choices[0].finish_reason}")
            logger.debug(f"   Usage: {response.usage.prompt_tokens} prompt + {response.usage.completion_tokens} completion = {response.usage.total_tokens} total")
            
            # Check if model wants to call tools
            if message.tool_calls:
                tool_call_count = len(message.tool_calls)
                logger.info(f"🔧 Model requested {tool_call_count} tool call(s):")
                
                # Execute all tool calls
                for idx, tool_call in enumerate(message.tool_calls, 1):
                    function_name = tool_call.function.name
                    logger.info(f"   [{idx}/{tool_call_count}] {function_name}")
                    
                    try:
                        arguments = json.loads(tool_call.function.arguments)
                        logger.debug(f"      Arguments: {json.dumps(arguments, indent=6)}")
                    except json.JSONDecodeError as e:
                        logger.error(f"      ❌ Failed to parse arguments: {e}")
                        arguments = {}
                    
                    # Execute tool
                    tool_result = self._execute_tool_call(function_name, arguments)
                    
                    # Log result summary
                    try:
                        result_data = json.loads(tool_result)
                        if "error" in result_data:
                            logger.error(f"      ❌ Tool returned error: {result_data['error']}")
                        else:
                            # Log key metrics from result
                            if "count" in result_data:
                                logger.info(f"      ✅ Result: {result_data['count']} items found")
                            elif "content" in result_data:
                                content_len = len(result_data.get("content", ""))
                                logger.info(f"      ✅ Result: {content_len} chars read")
                            else:
                                logger.info(f"      ✅ Tool completed successfully")
                    except:
                        result_len = len(tool_result)
                        logger.info(f"      ✅ Result: {result_len} chars")
                    
                    # Track tool call
                    tool_calls_made.append({
                        "function": function_name,
                        "arguments": arguments,
                        "result": tool_result
                    })
                    
                    # Add tool result to messages
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": tool_result
                    })
                
                logger.info(f"🔄 Continuing to next iteration...")
            else:
                # Model is done, return final response
                logger.info("✅ Model finished (no more tool calls)")
                response_text = message.content
                usage = response.usage
                
                logger.info(f"📊 Final response length: {len(response_text)} chars")
                logger.info(f"📊 Total tool calls made: {len(tool_calls_made)}")
                logger.info(f"📊 Total iterations: {iteration}")
                
                # Build metadata
                metadata = {
                    "sources": sources,
                    "retrieved_docs": len(retrieved_docs),
                    "full_prompt": f"System: {system_prompt_with_tools}\n\nUser: {user_query}",
                    "retrieved_chunks": [],
                    "tool_calls": tool_calls_made,
                    "raw_response": response_text,
                }
                
                logger.info("=" * 80)
                logger.info("✅ AGENT MODE: Query completed successfully")
                logger.info("=" * 80)
                
                return response_text, usage, metadata
        
        # If we hit max iterations, return last response
        logger.warning(f"⚠️ Hit max iterations ({max_iterations}), stopping tool loop")
        
        if messages:
            last_message = messages[-1]
            if last_message.get("role") == "assistant" and last_message.get("content"):
                response_text = last_message["content"]
                logger.info("📝 Using last assistant message as response")
            else:
                response_text = "I encountered an issue processing your request. Please try again."
                logger.warning("⚠️ No valid response found, using fallback message")
        else:
            response_text = "I encountered an issue processing your request. Please try again."
            logger.error("❌ No messages found, using fallback message")
        
        usage = response.usage if 'response' in locals() else None
        metadata = {
            "sources": sources,
            "retrieved_docs": len(retrieved_docs),
            "full_prompt": f"System: {system_prompt_with_tools}\n\nUser: {user_query}",
            "retrieved_chunks": [],
            "tool_calls": tool_calls_made,
            "raw_response": response_text,
        }
        
        logger.info("=" * 80)
        logger.warning("⚠️ AGENT MODE: Query completed with max iterations reached")
        logger.info("=" * 80)
        
        return response_text, usage, metadata

