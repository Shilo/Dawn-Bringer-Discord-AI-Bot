"""LangChain RAG chain setup."""

from typing import Tuple, Optional, List
import json
import re
from datetime import datetime, timezone
from openai import OpenAI
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from rag.retriever import RAGRetriever
from rag.openai_client import prompt_openai


class RAGChain:
    """Manages the RAG chain for question answering."""
    
    def __init__(
        self,
        retriever: RAGRetriever,
        model_name: str = "gpt-4o-mini",
        max_tokens: int = 500,
        temperature: float = 0.7,
        system_prompt: Optional[str] = None,
        verbosity: Optional[str] = None,
        reasoning_effort: Optional[str] = None,
        status_updater = None,
    ):
        """Initialize the RAG chain.

        Args:
            retriever: RAGRetriever instance
            model_name: OpenAI model name
            max_tokens: Maximum tokens for response
            temperature: LLM temperature (0.0-2.0)
            system_prompt: System prompt for the LLM
            verbosity: GPT-5 verbosity level ("low", "medium", "high")
            reasoning_effort: GPT-5 reasoning effort ("minimal", "medium", "high")
            status_updater: Optional callback function to update status messages
        """
        self.retriever = retriever
        self.model_name = model_name
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.system_prompt = system_prompt or "You are Dawn Bringer, a helpful Discord AI assistant."
        self.verbosity = verbosity
        self.reasoning_effort = reasoning_effort
        self.status_updater = status_updater
        
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
    
    def _prepare_query(self, user_query: str, include_scores: bool = False, top_k_override: Optional[int] = None, score_threshold_override: Optional[float] = None, additional_context: Optional[str] = None, additional_metadata: Optional[dict] = None) -> Tuple[list, str, list, Optional[list]]:
        """Prepare query by retrieving documents and building message content.
        
        Args:
            user_query: User's question
            include_scores: If True, retrieve documents with scores (single search, more efficient)
            top_k_override: Optional override for top_k retrieval (passed through from query_with_usage)
            score_threshold_override: Optional override for score threshold (temporary, doesn't change global setting)
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
        threshold = score_threshold_override if score_threshold_override is not None else self.retriever.vector_store.config.SCORE_THRESHOLD
        
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
            retrieved_docs = self.retriever.retrieve(user_query, apply_threshold=True, top_k_override=top_k_override, score_threshold_override=score_threshold_override)
        
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
        message_content = (
            f"[Run! Goddess Documentation]\n\n{context}\n\n---\n\n[User Question]\n{user_query}"
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
    
    async def query_with_usage(self, user_query: str, include_scores: bool = False, max_tokens_override: Optional[int] = None, top_k_override: Optional[int] = None, score_threshold_override: Optional[float] = None, additional_context: Optional[str] = None, additional_metadata: Optional[dict] = None, status_updater=None) -> Tuple[str, object, dict]:
        """Query the RAG chain and return usage information.

        Args:
            user_query: User's question
            include_scores: If True, retrieve similarity scores (adds overhead - only use for debugging)
            max_tokens_override: Optional override for max_tokens (temporary, doesn't change instance setting)
            top_k_override: Optional override for top_k retrieval (temporary, doesn't change instance setting)
            score_threshold_override: Optional override for score threshold (temporary, doesn't change global setting)
            additional_context: Optional additional context content to inject
            additional_metadata: Optional metadata dict for the additional context document
            status_updater: Optional callback function to update status messages (overrides instance setting)

        Returns:
            Tuple of (response_text, usage_object, metadata_dict)
            usage_object is OpenAI Usage object with token counts
            metadata_dict contains:
                - sources: List of source documents
                - retrieved_docs: Number of documents retrieved
                - full_prompt: Full prompt sent to OpenAI (system + user messages)
                - retrieved_chunks: List of retrieved document chunks with metadata and similarity scores (if include_scores=True)
        """
        # Use provided status_updater or fall back to instance variable
        current_status_updater = status_updater if status_updater is not None else self.status_updater

        # Update status to show we're retrieving documents
        if current_status_updater:
            await current_status_updater("Retrieving documents...")

        retrieved_docs, message_content, sources, scores = self._prepare_query(user_query, include_scores=include_scores, top_k_override=top_k_override, score_threshold_override=score_threshold_override, additional_context=additional_context, additional_metadata=additional_metadata)
        
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
        
        # Use override if provided, otherwise use instance setting
        max_tokens_to_use = max_tokens_override if max_tokens_override is not None else self.max_tokens

        # Update status to show we're generating the response
        if current_status_updater:
            await current_status_updater("Generating response...")

        # Call the LLM using the unified function
        response_text, usage = prompt_openai(messages, max_tokens_to_use)
        
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

