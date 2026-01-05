# Dawn Bringer Discord AI Bot

> Survivor, I am here to help! As your Dawn Bringer, I have seen what this world can throw at us—infected, mad scientists, and everything in between. Need answers? Strategy? Just want to chat? Let us go—no challenge is too great when we face it together.
> - Mention me (@Dawn Bringer)
> - Say my name (DB, Dawn, Dawnbringer)
> - Ask a relevant game question

A Discord bot for the Run! Goddess community, powered by OpenAI and RAG (Retrieval-Augmented Generation) for intelligent documentation search.

## Requirements

- **Python 3.11** (recommended) or Python 3.10
- Discord Bot Token
- OpenAI API Key

## Setup

### 1. Create Virtual Environment

Create and activate a virtual environment with Python 3.11:

**Windows (PowerShell):**
```bash
python3.11 -m venv venv
.\venv\Scripts\Activate.ps1
```

**Windows (CMD):**
```bash
python3.11 -m venv venv
.\venv\Scripts\activate.bat
```

**Linux/Mac:**
```bash
python3.11 -m venv venv
source venv/bin/activate
```

### 2. Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Configure Environment Variables

Create a `.env` file with your API keys:

**Option 1: Copy example file**
```bash
cp .env.example .env
```

**Option 2: Create manually**
Create a `.env` file in the project root:
```
# Required
DISCORD_TOKEN=your_discord_bot_token_here
OPENAI_API_KEY=your_openai_api_key_here

# Optional RAG Configuration (defaults shown)
EMBEDDING_MODEL=text-embedding-3-small
RAG_TOP_K=5
RAG_SCORE_THRESHOLD=1.2
CHROMA_DB_PATH=./chroma_db

# Optional GitHub Repository URL for source links
# Format: https://github.com/username/repo or https://github.com/username/repo/tree/branch
# If not set, source links will not be generated in normal responses (debug command always shows sources)
GITHUB_REPO_URL=https://github.com/yourusername/your-repo-name

# Optional Gift Code Channel Configuration
# Set GIFT_CODE_SERVER_ID to the Discord server (guild) ID where the gift code channel is located
# Set GIFT_CODE_CHANNEL_NAME to the name of the channel to search for gift codes
# If not set, gift code search feature will be disabled
GIFT_CODE_SERVER_ID=
GIFT_CODE_CHANNEL_NAME=gift-codes
```

### 4. Run the Bot

```bash
python bot.py
```

The bot will automatically:
- Initialize the RAG system
- Build the vector store from documentation (first run only)
- Connect to Discord

## Usage

### Interacting with the Bot

Prompt the bot by:
- Mentioning it: `@Dawn Bringer what is the best class?`
- Using a trigger name: `dawn how do I upgrade my character?`
- Asking a question in `#👧ask-dawn-bringer`: `What are the best builds?`

### Trigger Names

The bot responds to:
- `@Dawn Bringer` (mention/tag)
- `db`
- `dawn`
- `dawnbringer`
- `dawn bringer`
- Any question in `#👧ask-dawn-bringer`

Edit the `BOT_NAMES` list in `bot.py` to customize the text prefixes.

## RAG System

The bot uses a **Retrieval-Augmented Generation (RAG)** system for intelligent documentation search:

### Features

- **Semantic Search**: Understands context and meaning, not just keywords
- **Smart Chunking**: Automatically chunks documentation by type (FAQ, guides, characters)
- **Context-Aware**: Retrieves the most relevant documentation chunks for each query
- **Source Citations**: Provides source references for answers
- **Automatic Updates**: Rebuilds vector store when documentation changes

### How It Works

1. **Document Loading**: Recursively loads all `.md` and `.txt` files from `docs/`
2. **Smart Chunking**: Chunks documents based on type (FAQ, guide, character, general)
3. **Embedding**: Creates vector embeddings using OpenAI's `text-embedding-3-small`
4. **Vector Store**: Stores embeddings in ChromaDB for fast similarity search
5. **Retrieval**: Finds top K most relevant chunks for each query
6. **Generation**: Uses retrieved context to generate accurate, cited answers

### Configuration

Optional environment variables (defaults provided):

```bash
# Embedding model (default: text-embedding-3-small)
EMBEDDING_MODEL=text-embedding-3-small

# Number of chunks to retrieve (default: 5)
RAG_TOP_K=5

# Relevance threshold for filtering chunks (distance score, lower = more relevant)
# Chunks with distance > this value will be filtered out
# Set to "None" or empty string to disable filtering
# Typical values: 1.0-1.5, default: 1.2
RAG_SCORE_THRESHOLD=1.2

# Vector store path (default: ./chroma_db)
CHROMA_DB_PATH=./chroma_db

# GitHub repository URL for source links (optional)
# Format: https://github.com/username/repo or https://github.com/username/repo/tree/branch
# If not set, source links will not be generated in normal responses
# Debug command (!! or !debug) always shows sources even without GitHub URL
GITHUB_REPO_URL=https://github.com/yourusername/your-repo-name
```

### Documentation

For detailed RAG system documentation, see [rag/README.md](rag/README.md).

## Project Structure

```
.
├── bot.py                 # Main bot entry point
├── commands.py           # Bot command handlers
├── rag/                  # RAG system implementation
│   ├── config.py         # Configuration settings
│   ├── document_loader.py # Document loading and parsing
│   ├── chunking.py       # Smart document chunking
│   ├── vector_store.py   # ChromaDB vector store
│   ├── retriever.py      # Semantic retrieval
│   └── chain.py          # LangChain RAG chain
├── docs/                 # Documentation files (markdown)
├── chroma_db/            # Vector store database (auto-generated)
└── requirements.txt      # Python dependencies
```

## Troubleshooting

### Virtual Environment Issues

If you encounter Python version issues:
- Ensure Python 3.11 is installed: `python3.11 --version`
- Use the correct Python version when creating venv: `python3.11 -m venv venv`

### RAG System Issues

**Vector store not building:**
- Check that `docs/` directory exists and contains files
- Verify `OPENAI_API_KEY` is set in `.env`
- Check file permissions for `chroma_db/` directory

**Poor retrieval results:**
- Increase `RAG_TOP_K` environment variable to retrieve more chunks
- Verify documents are properly formatted in `docs/`
- Check that vector store was built successfully (check `chroma_db/` directory)

For more troubleshooting, see [rag/README.md](rag/README.md#troubleshooting).

## Railway Deployment

### Persistent Storage Setup

**Important**: Railway uses ephemeral filesystems by default, which means the `chroma_db` directory gets wiped on each deployment. This causes the vector store to rebuild every time, which is slow and expensive.

To fix this, you need to set up a **persistent volume** for the vector store:

1. **Create a Volume in Railway:**
   - Go to your Railway project
   - Click "New" → "Volume"
   - Name it `chroma-db` (or any name you prefer)
   - Set the mount path to `/data/chroma_db` (or your preferred path)

2. **Update Environment Variable:**
   - In your Railway service settings, add/update the `CHROMA_DB_PATH` environment variable:
   ```
   CHROMA_DB_PATH=/data/chroma_db
   ```
   - This points to the persistent volume mount path

3. **Redeploy:**
   - The vector store will be built once and persist across deployments
   - Subsequent deployments will reuse the existing vector store (much faster!)

### Alternative: Use Railway's Data Directory

If you prefer, you can also use Railway's recommended data directory:
```
CHROMA_DB_PATH=/tmp/chroma_db
```

However, `/tmp` is still ephemeral on Railway, so **you must use a persistent volume** for the vector store to persist between deployments.

### Verifying Persistence

After setting up the persistent volume, you should see:
- First deployment: `📦 Building vector store from documents...` (takes ~10-30 seconds)
- Subsequent deployments: `📂 Using existing vector store...` (instant)

If you see "Building vector store" on every deployment, the persistent volume is not configured correctly.

## Web Interface

The bot includes a **web interface** that allows users to interact with the bot via a browser, even on Discord servers where the bot cannot join.

### Features

- **Discord-like UI**: Beautiful, modern interface that mimics Discord's design
- **Real-time Chat**: Interactive chat interface with the bot
- **Source Citations**: Shows source links for answers (if GitHub repo is configured)
- **Token Usage**: Displays cost and token usage for each query
- **Mobile Friendly**: Responsive design that works on all devices

### Accessing the Web Interface

When the bot is running, the web interface is automatically available at:

- **Local Development**: `http://localhost:8000` (or the port specified by `PORT` environment variable)
- **Railway Deployment**: Railway automatically provides a public URL (check your Railway project's networking settings)

### Railway Configuration

The web server automatically starts alongside the Discord bot when deployed to Railway:

1. **Automatic Detection**: Railway automatically detects the web server and provides a public URL
2. **Port Configuration**: The web server uses the `PORT` environment variable (Railway sets this automatically)
3. **No Additional Setup**: No Procfile or special configuration needed - it just works!

### Sharing the Web Interface

Once deployed on Railway:

1. Go to your Railway project → **Networking** tab
2. Click **Generate Domain** to get a public URL
3. Share this URL with users on Discord servers where the bot can't join
4. Users can access the bot through their web browser

### Web Interface API

The web interface also exposes a REST API for programmatic access:

- `POST /api/query` - Send a question and get a response
  ```json
  {
    "question": "What is the best class?"
  }
  ```
  
- `GET /api/stats` - Get knowledge base statistics
- `GET /health` - Health check endpoint

### Example Response

```json
{
  "response": "Based on the documentation...",
  "sources": [
    {
      "source": "guide/classes.md",
      "name": "classes.md",
      "url": "https://github.com/user/repo/blob/main/docs/guide/classes.md#L10"
    }
  ],
  "stats": {
    "cost": 0.000123,
    "tokens": 456,
    "prompt_tokens": 300,
    "completion_tokens": 156
  }
}
```