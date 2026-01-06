#!/usr/bin/env python3
"""Test script to check GPT-5-mini model responses and markdown formatting.

This script allows testing response formatting for different queries.

Usage:
    Interactive mode:
        python test/test_response.py
        python test/test_response.py --verbose

    Non-interactive mode (test specific queries):
        python test/test_response.py "What are some good Valkyrie builds?"
        python test/test_response.py "best valks" "What Valkyries Should I Use?"
        python test/test_response.py "query here" --verbose
"""

import os
import sys
from pathlib import Path

# Add parent directory to path so we can import rag modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()
from configs import Config
from rag.openai_client import prompt_openai

# Load environment variables
load_dotenv()


def load_system_prompt():
    """Load the system prompt from file."""
    try:
        with open('system_prompt.txt', 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        print("Error: system_prompt.txt not found!")
        sys.exit(1)
    except UnicodeDecodeError as e:
        print(f"Error reading system_prompt.txt: {e}")
        sys.exit(1)


def load_rag_system():
    """Load the full RAG system for testing Discord-like behavior."""
    try:
        from dotenv import load_dotenv
        load_dotenv()
        from configs import Config
        from rag.document_loader import DocumentLoader
        from rag.vector_store import VectorStore
        from rag.retriever import RAGRetriever
        from rag.chain import RAGChain

        # Initialize RAG system
        loader = DocumentLoader(Config.DOCS_DIR)
        documents = loader.load_all_documents()

        if not documents:
            print("Error: No documents found for RAG system")
            return None

        vector_store = VectorStore(force_rebuild=False)
        vector_store.get_vector_store()
        retriever = RAGRetriever(vector_store)

        chain = RAGChain(
            retriever=retriever,
            model_name=Config.MODEL,
            max_tokens=Config.MAX_TOKENS,
            temperature=Config.TEMPERATURE,
            system_prompt=load_system_prompt()
        )

        return chain

    except Exception as e:
        print(f"Error loading RAG system: {e}")
        return None


def test_query(system_prompt: str, query: str, verbose: bool = False, rag_chain: object = None):
    """Test a query and display response formatting results.

    Args:
        system_prompt: The system prompt to use
        query: Query string to test
        verbose: If True, show additional debug info
    """
    print(f"\n{'#'*80}")
    print(f"# Testing Query: {query}")
    print(f"{'#'*80}")

    try:
        if rag_chain is not None:
            # Use RAG chain like Discord bot does
            if verbose:
                print(f"\nUsing RAG chain (like Discord bot)...")
                print(f"   Query: {query}")

            response, usage, metadata = rag_chain.query_with_usage(
                query,
                max_tokens_override=Config.MAX_TOKENS
            )
        else:
            # Use direct OpenAI call like simple test
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": query}
            ]

            if verbose:
                print(f"\nSending to {Config.MODEL}...")
                print(f"   System prompt length: {len(system_prompt)} chars")
                print(f"   Query: {query}")

            # Get response
            response, usage = prompt_openai(messages, Config.MAX_TOKENS)

        # Handle encoding issues for display - try UTF-8 first, fallback to ASCII replacement
        try:
            # Try to display with proper Unicode support
            display_response = response
            # Test if it can be encoded/decoded as UTF-8
            display_response.encode('utf-8').decode('utf-8')
        except (UnicodeEncodeError, UnicodeDecodeError):
            # Fallback: convert Unicode chars to ASCII equivalents using unidecode if available
            try:
                import unidecode
                display_response = unidecode.unidecode(response)
            except ImportError:
                # Final fallback: replace with ASCII equivalents
                display_response = response.encode('ascii', 'replace').decode('ascii')

        print(f'\n{"="*50}')
        print('RESPONSE:')
        print('='*50)
        print(display_response)

        if verbose:
            print(f'\n{"="*50}')
            print('USAGE INFO:')
            print('='*50)
            print(f'Tokens used: {usage.total_tokens}')
            print(f'Prompt tokens: {usage.prompt_tokens}')
            print(f'Completion tokens: {usage.completion_tokens}')
            print(f'Model: {Config.MODEL}')
            print(f'GPT-5 verbosity: {Config.GPT5_VERBOSITY}')

        # Check for markdown
        has_bold = '**' in response
        has_code = '`' in response
        has_lists = '- ' in response or '• ' in response or any(str(i) + '. ' in response for i in range(1, 10))
        has_underline = '__' in response

        print(f'\n{"="*50}')
        print('MARKDOWN CHECK:')
        print('='*50)
        print(f'Bold text (**) found: {has_bold}')
        print(f'Code blocks/backticks (`) found: {has_code}')
        print(f'Lists (- or • or numbered) found: {has_lists}')
        print(f'Underline (__) found: {has_underline}')
        print(f'Overall markdown usage: {"Good" if any([has_bold, has_code, has_lists, has_underline]) else "None detected"}')

        if verbose and '{"used_sources":' in response:
            print(f'\nCitation JSON detected in response')

        return True

    except Exception as e:
        print(f"\nError during testing: {e}")
        if verbose:
            import traceback
            traceback.print_exc()
        return False


def main():
    """Main test loop."""
    import argparse

    parser = argparse.ArgumentParser(description="Test GPT-5 response formatting")
    parser.add_argument("queries", nargs="*", help="Query strings to test (if provided, runs in non-interactive mode)")
    parser.add_argument("--verbose", "-v", action="store_true",
                       help="Enable verbose logging and debug info")
    parser.add_argument("--rag", "-r", action="store_true",
                       help="Use full RAG system like Discord bot (includes document retrieval)")

    args = parser.parse_args()

    # Check for OpenAI API key
    if not os.getenv("OPENAI_API_KEY"):
        print("Error: OPENAI_API_KEY environment variable not set!")
        print("Please set it in your .env file or environment.")
        sys.exit(1)

    # Load system prompt
    system_prompt = load_system_prompt()
    print(f"Testing with model: {Config.MODEL}")
    print(f"GPT-5 verbosity: {Config.GPT5_VERBOSITY}")

    # Load RAG system if requested
    rag_chain = None
    if args.rag:
        print("Loading RAG system...")
        rag_chain = load_rag_system()
        if rag_chain is None:
            print("Failed to load RAG system, falling back to direct API calls")
        else:
            print("RAG system loaded successfully")

    mode_name = "RAG Mode (Discord-like)" if rag_chain else "Direct API Mode"

    # If queries were provided as arguments, test them and exit
    if args.queries:
        print(f"\n{'='*80}")
        print(f"Response Formatting Tester - Non-Interactive Mode ({mode_name})")
        print(f"{'='*80}")
        print(f"Testing {len(args.queries)} quer{'ies' if len(args.queries) != 1 else 'y'}...")
        if args.verbose:
            print("Verbose logging is ENABLED")

        success_count = 0
        for query in args.queries:
            if test_query(system_prompt, query, verbose=args.verbose, rag_chain=rag_chain):
                success_count += 1

        print(f"\n{'='*80}")
        print(f"Results: {success_count}/{len(args.queries)} queries tested successfully")
        return  # Exit after testing provided queries

    # Interactive mode
    mode_name = "RAG Mode (Discord-like)" if rag_chain else "Direct API Mode"
    print("\n" + "="*80)
    print(f"Response Formatting Tester ({mode_name})")
    print("="*80)
    print("\nEnter queries to test response formatting.")
    print("Commands:")
    print("  - Type a query and press Enter to test it")
    print("  - Type 'quit' or 'exit' to exit")
    print("  - Type 'help' for more commands")
    print("  - Type 'mode' to toggle between Direct API and RAG modes")
    if args.verbose:
        print("  - Verbose logging is ENABLED")
    print("="*80)

    # Interactive loop
    while True:
        try:
            query = input("\nQuery: ").strip()

            if not query:
                continue

            if query.lower() in ('quit', 'exit', 'q'):
                print("\nGoodbye!")
                break

            if query.lower() == 'help':
                print("\nAvailable commands:")
                print("  quit, exit, q  - Exit the test script")
                print("  help          - Show this help message")
                print("  clear         - Clear screen")
                print("  verbose       - Toggle verbose mode")
                print("  mode          - Toggle between Direct API and RAG modes")
                continue

            if query.lower() == 'clear':
                os.system('cls' if os.name == 'nt' else 'clear')
                continue

            if query.lower() == 'verbose':
                args.verbose = not args.verbose
                print(f"Verbose mode {'ENABLED' if args.verbose else 'DISABLED'}")
                continue

            if query.lower() == 'mode':
                if rag_chain is None:
                    print("Loading RAG system...")
                    rag_chain = load_rag_system()
                    if rag_chain:
                        print("Switched to RAG Mode (Discord-like)")
                    else:
                        print("Failed to load RAG system")
                else:
                    rag_chain = None
                    print("Switched to Direct API Mode")

                mode_name = "RAG Mode (Discord-like)" if rag_chain else "Direct API Mode"
                print(f"Current mode: {mode_name}")
                continue

            # Test the query
            test_query(system_prompt, query, verbose=args.verbose, rag_chain=rag_chain)

        except KeyboardInterrupt:
            print("\n\nGoodbye!")
            break
        except EOFError:
            print("\n\nGoodbye!")
            break
        except Exception as e:
            print(f"\nUnexpected error: {e}")
            if args.verbose:
                import traceback
                traceback.print_exc()


if __name__ == "__main__":
    main()
