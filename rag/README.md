# RAG (Retrieval-Augmented Generation) System

This directory contains the RAG system implementation for the Dawn Bringer Discord Bot. The RAG system provides semantic search capabilities using LangChain, OpenAI embeddings, and ChromaDB vector database.

## Overview

The RAG system replaces the previous keyword-based documentation search with a semantic search approach that:

- **Understands context**: Uses embeddings to find relevant content based on meaning, not just keywords
- **Handles stop words**: Embeddings naturally ignore common words like "how", "what", "the", "and"
- **No character limits**: Retrieves top K most relevant chunks regardless of size
- **Better accuracy**: Context-aware retrieval reduces hallucinations and improves answer quality

## Architecture

```
rag/
├── __init__.py          # Module exports and imports
├── chain.py             # LangChain RAG chain setup
├── chunking.py          # Smart document chunking strategies
├── document_loader.py   # Load and parse documentation files
├── retriever.py         # Semantic retrieval logic
├── utils.py             # Utility functions for RAG system
└── vector_store.py      # ChromaDB vector store management

configs/
├── __init__.py          # Main configuration class and settings
├── post_intent_patterns_config.py  # FAQ intent pattern recognition (post-processing)
├── pre_query_expansion_config.py   # Semantic query expansion mappings (pre-processing)
└── pre_synonyms_config.py          # Query synonym and abbreviation expansions (pre-processing)
```

## Components

### `configs/` Directory

Configuration settings for the RAG system:

#### `configs/__init__.py` - Main Configuration
- **Embedding settings**: `text-embedding-3-small` model, 1536 dimensions
- **Chunking settings**: 1000 words per chunk (default), 200 overlap, 4000 characters fallback
- **Retrieval settings**: Top K=5, similarity threshold=1.2
- **Vector store**: ChromaDB path, collection name
- **Model settings**: `gpt-4o-mini`, max tokens, temperature

#### `configs/pre_synonyms_config.py` - Query Preprocessing
- **Purpose**: Expands abbreviations and synonyms before vector search
- **Examples**: "valk" → "valkyrie", "db" → "dawn bringer"
- **Processing**: Early (before vector search)

#### `configs/pre_query_expansion_config.py` - Semantic Expansion
- **Purpose**: Maps short queries to expanded semantic searches
- **Examples**: "best valk" → ["what valkyrie should i use", "valkyrie tier list"]
- **Processing**: Early (before vector search)

#### `configs/post_intent_patterns_config.py` - FAQ Boosting
- **Purpose**: Boosts relevant FAQ entries based on keyword patterns
- **Examples**: frozenset(['best', 'valk']) → ['what valkyrie should i use']
- **Processing**: Late (after vector search)

### `document_loader.py`

Loads and parses documentation files:
- Recursively loads `.md` and `.txt` files from `docs/`
- Skips `README.md` files
- Detects document types: `faq`, `guide`, `character`, `general`
- Preserves file metadata (path, type, character name)

**Document Type Detection:**
- **FAQ**: Files in `faq-*` or `frequently-asked-*` directories
- **Character**: Files in `valkyries/` or matching pattern `\d+-[Name].md`
- **Guide**: Files in `guide*` or `guides*` directories
- **General**: All other files

### `chunking.py`

Smart document chunking with different strategies per document type:

**FAQ Documents:**
- Chunks by question-answer pairs
- Preserves markdown headers as questions
- Metadata includes question text and section

**Guide Documents:**
- Chunks by markdown sections (`##`, `###`)
- Preserves section hierarchy
- Uses 1000 character chunks with 200 overlap

**Character Documents:**
- Chunks by sections (bio, skills, etc.)
- Uses smaller chunks (800 chars) for focused content
- Includes character name in metadata

### `vector_store.py`

Manages ChromaDB vector store:
- Initializes ChromaDB collection on startup
- Embeds document chunks using OpenAI embeddings
- Handles persistence (works with Railway's filesystem)
- Detects when vector store needs rebuilding
- Provides retriever interface for LangChain

**Vector Store Lifecycle:**
1. On first run: Builds vector store from all documents
2. On subsequent runs: Loads existing vector store
3. Rebuilds automatically if documents change (detected by empty collection)

### `retriever.py`

Semantic retrieval logic:
- Uses LangChain's ChromaDB retriever
- Performs similarity search with configurable top K
- Formats retrieved context with source citations
- Handles empty results gracefully

### `chain.py`

LangChain RAG chain setup:
- Creates retrieval chain using LangChain
- Integrates with OpenAI chat model (`gpt-4o-mini`)
- Supports configurable temperature and max tokens
- Formats retrieved context for prompt
- Returns response with usage information

### `utils.py`

Utility functions for the RAG system:
- **Word count estimation**: Converts document chunks to estimated word counts
- **CJK detection**: Identifies cross-language queries (Chinese/Japanese/Korean)
- **Threshold adjustment**: Increases similarity threshold for cross-language searches
- **GitHub link generation**: Creates source links for documentation
- **File text extraction**: Retrieves exact text from original files for citations
- **Source link formatting**: Formats citations with GitHub links and external references

## Usage

### Initialization

The RAG system is automatically initialized when the bot starts:

```python
from configs import Config
from rag.chain import RAGChain
from rag.vector_store import VectorStore
from rag.retriever import RAGRetriever
from rag.document_loader import DocumentLoader

# Load documents
loader = DocumentLoader(Config.DOCS_DIR)
documents = loader.load_all_documents()

# Initialize vector store
vector_store = VectorStore(force_rebuild=False)
if vector_store._should_rebuild():
    vector_store.build_vector_store(documents)
else:
    vector_store.get_vector_store()  # Load existing

# Initialize retriever (verbose=False for production)
retriever = RAGRetriever(vector_store, verbose=False)

# Initialize RAG chain
chain = RAGChain(
    retriever=retriever,
    model_name=Config.MODEL,
    max_tokens=Config.MAX_TOKENS,
    temperature=Config.TEMPERATURE,
    system_prompt="You are Dawn Bringer..."
)
```

### Querying

```python
# Get response with usage info
response_text, usage, metadata = chain.query_with_usage("What is the best class?")

# metadata contains:
# - sources: List of source document paths
# - retrieved_docs: Number of documents retrieved
```

## Configuration

Environment variables (optional, defaults provided):

```bash
# Embedding model (default: text-embedding-3-small)
EMBEDDING_MODEL=text-embedding-3-small

# Number of chunks to retrieve (default: 5)
RAG_TOP_K=5

# Vector store path (default: ./chroma_db)
CHROMA_DB_PATH=./chroma_db
```

## Railway Deployment

The RAG system is fully compatible with Railway:

- **No external services**: File-based ChromaDB requires no additional database setup
- **Automatic initialization**: Vector store builds automatically on first deployment
- **Efficient updates**: Only rebuilds when documents change

### ⚠️ Important: Persistent Storage Required

**Railway uses ephemeral filesystems by default**, which means the `chroma_db` directory gets wiped on each deployment. To prevent rebuilding the vector store every time:

1. **Create a persistent volume** in Railway (mount path: `/data/chroma_db`)
2. **Set environment variable**: `CHROMA_DB_PATH=/data/chroma_db`
3. The vector store will persist across deployments

See the main [README.md](../README.md#railway-deployment) for detailed setup instructions.

## Document Format Support

The system supports various document formats:

### Q&A Format (FAQ)
```markdown
## :crossed_swords: [What is the Best Class?](link)
> Answer content here...
```

### Guide Format
```markdown
# Guide Title

## Section 1
Content here...

## Section 2
More content...
```

### Character Format
```markdown
# Character Name - Title

> Bio description...

## Skills

### Skill Name
Skill description...
```

## Performance

- **Embedding cost**: ~$0.02 per 1M tokens (text-embedding-3-small)
- **Query latency**: ~1-2 seconds (embedding + retrieval + LLM)
- **Vector store size**: ~1-5 MB per 1000 document chunks
- **Memory usage**: Minimal (ChromaDB is file-based)

## Troubleshooting

### Vector Store Not Building

If the vector store fails to build:
1. Check that `docs/` directory exists and contains files
2. Verify `OPENAI_API_KEY` is set in environment
3. Check file permissions for `chroma_db/` directory

### Poor Retrieval Results

If retrieval results are poor:
1. Increase `RAG_TOP_K` to retrieve more chunks
2. Check document chunking (may need to adjust chunk sizes)
3. Verify documents are properly formatted

### Railway Deployment Issues

If vector store doesn't persist on Railway:
1. Ensure `chroma_db/` is not in `.gitignore`
2. Check Railway filesystem persistence settings
3. Verify write permissions in deployment environment

## Future Enhancements

Potential improvements:
- Incremental updates (only re-embed changed documents)
- Hybrid search (combine semantic + keyword search)
- Query expansion (improve query understanding)
- Multi-query retrieval (generate multiple queries for better results)
- Re-ranking (improve result ordering)

