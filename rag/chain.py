"""LangChain RAG chain setup."""

from typing import Tuple, Optional
from openai import OpenAI
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from rag.retriever import RAGRetriever


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
    
    def _prepare_query(self, user_query: str) -> Tuple[list, str, list]:
        """Prepare query by retrieving documents and building message content.
        
        Args:
            user_query: User's question
            
        Returns:
            Tuple of (retrieved_docs, message_content, sources)
        """
        # Retrieve relevant documents
        retrieved_docs = self.retriever.retrieve(user_query)
        
        # Format context
        context = self.retriever.format_context(retrieved_docs)
        
        # Get sources
        sources = self.retriever.get_sources(retrieved_docs)
        
        # Create message content with documentation context if available
        message_content = (
            f"[Run! Goddess Documentation]\n\n{context}\n\n---\n\n[User Question]\n{user_query}"
            if context
            else user_query
        )
        
        return retrieved_docs, message_content, sources
    
    def query(self, user_query: str) -> Tuple[str, dict]:
        """Query the RAG chain with a user question.
        
        Args:
            user_query: User's question
            
        Returns:
            Tuple of (response_text, metadata_dict)
            metadata_dict contains:
                - sources: List of source documents
                - retrieved_docs: Number of documents retrieved
        """
        retrieved_docs, message_content, sources = self._prepare_query(user_query)
        
        # Build messages for LangChain
        messages = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=message_content)
        ]
        
        # Get response from LLM
        response = self.llm.invoke(messages)
        response_text = response.content
        
        metadata = {
            "sources": sources,
            "retrieved_docs": len(retrieved_docs),
        }
        
        return response_text, metadata
    
    def query_with_usage(self, user_query: str) -> Tuple[str, object, dict]:
        """Query the RAG chain and return usage information.
        
        Args:
            user_query: User's question
            
        Returns:
            Tuple of (response_text, usage_object, metadata_dict)
            usage_object is OpenAI Usage object with token counts
            metadata_dict contains:
                - sources: List of source documents
                - retrieved_docs: Number of documents retrieved
                - full_prompt: Full prompt sent to OpenAI (system + user messages)
                - retrieved_chunks: List of retrieved document chunks with metadata
        """
        retrieved_docs, message_content, sources = self._prepare_query(user_query)
        
        # Build messages for OpenAI API
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": message_content}
        ]
        
        # Format full prompt for debugging (includes system and user messages)
        full_prompt = f"System: {self.system_prompt}\n\nUser: {message_content}"
        
        # Use OpenAI client directly to get usage info
        openai_client = OpenAI()
        response = openai_client.chat.completions.create(
            model=self.model_name,
            max_completion_tokens=self.max_tokens,
            temperature=self.temperature,
            messages=messages
        )
        
        response_text = response.choices[0].message.content
        usage = response.usage
        
        # Format retrieved chunks for debugging
        retrieved_chunks = []
        for doc in retrieved_docs:
            chunk_info = {
                "content": doc.page_content,
                "source": doc.metadata.get("source", "Unknown"),
                "doc_type": doc.metadata.get("doc_type", "general"),
                "metadata": doc.metadata
            }
            retrieved_chunks.append(chunk_info)
        
        metadata = {
            "sources": sources,
            "retrieved_docs": len(retrieved_docs),
            "full_prompt": full_prompt,
            "retrieved_chunks": retrieved_chunks,
        }
        
        return response_text, usage, metadata

