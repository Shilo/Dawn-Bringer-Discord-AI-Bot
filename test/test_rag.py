#!/usr/bin/env python3
"""Standalone RAG testing script for debugging chunk retrieval.

This script allows interactive testing of the RAG system to see what chunks
would be sent to OpenAI for different queries.

Usage:
    Interactive mode:
        python test/test_rag.py
        python test/test_rag.py --verbose
        python test/test_rag.py --rebuild
        python test/test_rag.py --top-k 10

    Non-interactive mode (test specific queries):
        python test/test_rag.py "What Valkyrie Should I Use?"
        python test/test_rag.py "best valks" "What Valkyries Should I Use?" --top-k 10
        python test/test_rag.py "query here" --verbose --rebuild
"""

import os
import sys
from pathlib import Path

# Add parent directory to path so we can import rag modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
from rag.configs import RAGConfig
from rag.document_loader import DocumentLoader
from rag.vector_store import VectorStore
from rag.retriever import RAGRetriever
from rag.chain import RAGChain

# Load environment variables
load_dotenv()


def initialize_rag_system(force_rebuild: bool = False, verbose: bool = False):
    """Initialize the RAG system for testing.
    
    Args:
        force_rebuild: If True, rebuild the vector store
        verbose: If True, enable verbose logging
        
    Returns:
        Tuple of (RAGChain, RAGRetriever) instances
    """
    print("\n🔧 Initializing RAG system...")
    
    # Load documents
    loader = DocumentLoader(RAGConfig.DOCS_DIR)
    documents = loader.load_all_documents()
    
    if not documents:
        print("⚠️ No documents found. RAG system will not work properly.")
        return None, None
    
    print(f"📚 Loaded {len(documents)} documents")
    
    # Initialize vector store
    vector_store = VectorStore(force_rebuild=force_rebuild)
    
    # Check if we need to rebuild
    if vector_store._should_rebuild():
        print("📦 Building vector store from documents...")
        vector_store.build_vector_store(documents)
    else:
        print("📂 Using existing vector store...")
        vector_store.get_vector_store()  # Load existing
    
    # Initialize retriever with verbose logging
    retriever = RAGRetriever(vector_store, verbose=verbose)
    
    # Initialize RAG chain (we won't use it for LLM, just for structure)
    chain = RAGChain(
        retriever=retriever,
        model_name="gpt-4o-mini",  # Not used, just for initialization
        max_tokens=500,
        temperature=0.7,
    )
    
    return chain, retriever


def format_chunk_output(doc, score, index):
    """Format a chunk for display.
    
    Args:
        doc: LangChain Document
        score: Distance score
        index: Chunk index (1-based)
        
    Returns:
        Formatted string
    """
    source = doc.metadata.get("source", "Unknown")
    doc_type = doc.metadata.get("doc_type", "general")
    content = doc.page_content.strip()
    
    # Truncate content for display
    preview = content[:200] + "..." if len(content) > 200 else content
    
    output = f"\n{'='*80}\n"
    output += f"Chunk #{index}\n"
    output += f"{'='*80}\n"
    output += f"Source: {source}\n"
    output += f"Type: {doc_type}\n"
    output += f"Score: {score:.3f} (lower is better)\n"
    output += f"Content Length: {len(content)} chars\n"
    output += f"\nContent Preview:\n{'-'*80}\n{preview}\n"
    if len(content) > 200:
        output += f"\n... ({len(content) - 200} more characters)\n"
    output += f"{'-'*80}\n"
    
    return output


def test_query(retriever, query: str, top_k: int = 5):
    """Test a query and display results.
    
    Args:
        retriever: RAGRetriever instance
        query: Query string
        top_k: Number of chunks to retrieve
    """
    print(f"\n{'#'*80}")
    print(f"# Testing Query: {query}")
    print(f"{'#'*80}")
    
    try:
        # Retrieve chunks with scores
        results = retriever.retrieve_with_scores(query, top_k_override=top_k)
        
        if not results:
            print("\n❌ No chunks retrieved!")
            return
        
        print(f"\n✅ Retrieved {len(results)} chunks\n")
        
        # Display each chunk
        for i, (doc, score) in enumerate(results, 1):
            print(format_chunk_output(doc, score, i))
        
        # Summary
        threshold = retriever.vector_store.config.SCORE_THRESHOLD
        threshold_str = f"{threshold:.3f}" if threshold is not None else "None (no filtering)"
        
        # Get total chunks in vector store
        try:
            vector_store = retriever.vector_store.get_vector_store()
            if vector_store:
                # Get collection from ChromaDB
                collection = vector_store._collection
                total_chunks = collection.count()
            else:
                total_chunks = None
        except Exception:
            total_chunks = None
        
        print(f"\n{'='*80}")
        print("SUMMARY")
        print(f"{'='*80}")
        print(f"Query: {query}")
        if total_chunks is not None:
            print(f"Total Chunks in Vector Store: {total_chunks}")
        print(f"Chunks Retrieved: {len(results)}")
        print(f"Score Threshold: {threshold_str}")
        print(f"Best Score: {results[0][1]:.3f}")
        print(f"Worst Score: {results[-1][1]:.3f}")
        print(f"Average Score: {sum(s for _, s in results) / len(results):.3f}")
        
        # Show sources with scores
        source_chunks = {}  # source -> list of (chunk_index, score)
        for i, (doc, score) in enumerate(results, 1):
            source = doc.metadata.get("source", "Unknown")
            if source not in source_chunks:
                source_chunks[source] = []
            source_chunks[source].append((i, score))
        
        # Calculate total chunks from all sources
        total_chunks_from_sources = sum(len(chunks) for chunks in source_chunks.values())
        
        print(f"\nSources ({len(source_chunks)} unique, {total_chunks_from_sources} total chunks):")
        for source in sorted(source_chunks.keys()):
            chunks = source_chunks[source]
            count = len(chunks)
            scores_str = ", ".join([f"#{idx} ({score:.3f})" for idx, score in chunks])
            print(f"  - {source} ({count} chunk{'s' if count > 1 else ''}): {scores_str}")
        
    except Exception as e:
        print(f"\n❌ Error during retrieval: {e}")
        import traceback
        traceback.print_exc()


def main():
    """Main test loop."""
    import argparse

    parser = argparse.ArgumentParser(description="Test RAG chunk retrieval")
    parser.add_argument("queries", nargs="*", help="Query strings to test (if provided, runs in non-interactive mode)")
    parser.add_argument("--verbose", "-v", action="store_true",
                       help="Enable verbose logging for debugging")
    parser.add_argument("--rebuild", "-r", action="store_true",
                       help="Force rebuild vector store")
    parser.add_argument("--top-k", "-k", type=int, default=5,
                       help="Number of chunks to retrieve (default: 5)")

    args = parser.parse_args()
    
    # Check for OpenAI API key
    if not os.getenv("OPENAI_API_KEY"):
        print("❌ Error: OPENAI_API_KEY environment variable not set!")
        print("Please set it in your .env file or environment.")
        sys.exit(1)
    
    # Initialize RAG system
    chain, retriever = initialize_rag_system(
        force_rebuild=args.rebuild,
        verbose=args.verbose
    )

    if not retriever:
        print("❌ Failed to initialize RAG system")
        sys.exit(1)

    # If queries were provided as arguments, test them and exit
    if args.queries:
        print(f"\n{'='*80}")
        print("RAG Chunk Retrieval Tester - Non-Interactive Mode")
        print(f"{'='*80}")
        print(f"Testing {len(args.queries)} quer{'ies' if len(args.queries) != 1 else 'y'}...")
        if args.verbose:
            print("Verbose logging is ENABLED")

        for query in args.queries:
            test_query(retriever, query, top_k=args.top_k)
        return  # Exit after testing provided queries

    # Interactive mode
    print("\n" + "="*80)
    print("RAG Chunk Retrieval Tester")
    print("="*80)
    print("\nEnter queries to test chunk retrieval.")
    print("Commands:")
    print("  - Type a query and press Enter to test it")
    print("  - Type 'quit' or 'exit' to exit")
    print("  - Type 'help' for more commands")
    print(f"  - Top-K is set to {args.top_k} (use --top-k to change)")
    if args.verbose:
        print("  - Verbose logging is ENABLED")
    print("="*80)

    # Interactive loop
    while True:
        try:
            query = input("\n🔍 Query: ").strip()
            
            if not query:
                continue
            
            if query.lower() in ('quit', 'exit', 'q'):
                print("\n👋 Goodbye!")
                break
            
            if query.lower() == 'help':
                print("\nAvailable commands:")
                print("  quit, exit, q  - Exit the test script")
                print("  help          - Show this help message")
                print("  clear         - Clear screen")
                print("  top-k <num>   - Change top-k value (e.g., 'top-k 10')")
                continue
            
            if query.lower() == 'clear':
                os.system('cls' if os.name == 'nt' else 'clear')
                continue
            
            if query.lower().startswith('top-k '):
                try:
                    new_k = int(query.split()[1])
                    args.top_k = new_k
                    print(f"✅ Top-K set to {new_k}")
                except (IndexError, ValueError):
                    print("❌ Invalid format. Use: top-k <number>")
                continue
            
            # Test the query
            test_query(retriever, query, top_k=args.top_k)
            
        except KeyboardInterrupt:
            print("\n\n👋 Goodbye!")
            break
        except EOFError:
            print("\n\n👋 Goodbye!")
            break
        except Exception as e:
            print(f"\n❌ Unexpected error: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    main()

