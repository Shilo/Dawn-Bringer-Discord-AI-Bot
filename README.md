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

# Optional Configuration
# Web server port (defaults to 8000)
PORT=8000

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

# Optional Railway Configuration
# Set RAILWAY_VOLUME_PATH to customize the persistent volume path for vector store on Railway
# Defaults to /data if not set and RAILWAY_ENVIRONMENT is detected
RAILWAY_VOLUME_PATH=/data
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

The RAG system uses configuration files in the `configs/` directory. Current settings include:

- **Embedding Model**: `text-embedding-3-small` (1536 dimensions)
- **Retrieval**: Top 5 most relevant chunks, similarity threshold 1.2
- **Chunking**: 1000 words per chunk with 200 word overlap
- **Model**: `gpt-5-mini` with 500 max tokens, temperature 0.1 (GPT-5 models use default temperature, configurable reasoning effort and verbosity)

#### Advanced Configuration Files

The RAG system includes three specialized configuration files for improved search:

1. **`configs/pre_synonyms_config.py`** - Expands abbreviations before search
   - "valk" → "valkyrie", "db" → "dawn bringer"

2. **`configs/pre_query_expansion_config.py`** - Maps short queries to full topics
   - "best valk" → ["what valkyrie should i use", "valkyrie tier list"]

3. **`configs/post_intent_patterns_config.py`** - Boosts FAQ results based on patterns
   - Keywords like "best valkyrie" boost relevant FAQ entries

#### GitHub Repository URL (Optional)

Set the `GITHUB_REPO_URL` environment variable to enable source links:
```bash
# Format: https://github.com/username/repo or https://github.com/username/repo/tree/branch
GITHUB_REPO_URL=https://github.com/yourusername/your-repo-name
```

If not set, source links will not be generated in normal responses (debug command always shows sources).

### Documentation

For detailed RAG system documentation, see [rag/README.md](rag/README.md).

## Project Structure

```
.
├── bot.py                 # Main bot entry point
├── commands.py           # Bot command handlers
├── configs/               # Configuration files
│   ├── __init__.py        # Main configuration class
│   ├── post_intent_patterns_config.py  # FAQ intent recognition
│   ├── pre_query_expansion_config.py   # Query expansion mappings
│   └── pre_synonyms_config.py          # Synonym and abbreviation expansions
├── rag/                  # RAG system implementation
│   ├── __init__.py        # Module exports
│   ├── chain.py           # LangChain RAG chain setup
│   ├── chunking.py        # Smart document chunking
│   ├── document_loader.py # Document loading and parsing
│   ├── retriever.py       # Semantic retrieval logic
│   ├── utils.py           # Utility functions
│   └── vector_store.py    # ChromaDB vector store management
├── docs/                 # Documentation files (markdown)
├── chroma_db/            # Vector store database (auto-generated, local dev only)
├── public/               # Web interface static files
├── shares.db             # Shared conversations database (local dev only)
├── /data/                # Persistent storage on Railway (contains chroma_db/, shares.db)
├── system_prompt.txt     # Bot personality and rules
├── views.py              # Web interface views
├── web_server.py        # Web server implementation
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
- Edit `configs/__init__.py` and increase `TOP_K` value to retrieve more chunks
- Verify documents are properly formatted in `docs/`
- Check that vector store was built successfully (check `chroma_db/` directory)
- Consider adjusting `SCORE_THRESHOLD` (lower values = more strict filtering)

For more troubleshooting, see [rag/README.md](rag/README.md#troubleshooting).

## Railway Deployment

### Persistent Storage Setup

**Important**: Railway uses ephemeral filesystems by default, which means the `chroma_db` directory gets wiped on each deployment. This causes the vector store to rebuild every time, which is slow and expensive.

To fix this, you need to set up a **persistent volume** for the vector store:

1. **Create a Volume in Railway:**
   - Go to your Railway project
   - Click "New" → "Volume"
   - Name it `dawn-bringer-data` (or any name you prefer)
   - Set the mount path to `/data`

2. **Note**: The vector store automatically detects Railway deployments and uses the persistent volume path. You can customize the volume path by setting the `RAILWAY_VOLUME_PATH` environment variable if needed.

3. **Redeploy:**
   - The vector store will be built once and persist across deployments
   - Subsequent deployments will reuse the existing vector store (much faster!)

### Railway Volume Configuration

The application automatically detects Railway deployments (via `RAILWAY_ENVIRONMENT` env var) and uses `/data` as the base persistent storage path. It will create:
- `/data/chroma_db/` for the vector store
- `/data/shares.db` for shared conversation data

If you need to use a different volume mount path, set the `RAILWAY_VOLUME_PATH` environment variable in your Railway service variables.

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

### Share System

The bot includes a **conversation sharing system** that allows users to create permanent, shareable links to specific bot conversations. This is useful for sharing interesting answers, saving conversations for later reference, or discussing bot responses in other channels/forums.

#### Features

- **Persistent Links**: Share links are permanent and persist across deployments when using Railway persistent volumes
- **Rich Interface**: Shared conversations include the full chat interface for continued interaction
- **Source Citations**: Shows source links and citations (if configured)
- **View Tracking**: Tracks how many times each share has been viewed
- **Privacy**: Only the original conversation is shared (no user identification)
- **Persistence**: Shares are stored in persistent storage on Railway deployments (requires volume setup)

#### Creating Share Links

**From Discord:**
- React with any emoji to any bot response
- The bot will automatically create a share link and send it in a follow-up message

**From Web Interface:**
- Click the "Share" button after any bot response
- A shareable link will be copied to your clipboard

#### Share URLs

Share links use a clean, direct format:
- **Format**: `https://your-domain.com/ABC123`
- **Example**: `https://dawn-bringer.railway.app/X7K9M2`

Each share ID is a unique 6-character alphanumeric code that directly maps to a stored conversation.

#### How It Works

1. **Storage**: Conversations are stored in a SQLite database (`shares.db`) with:
   - Original prompt and response
   - Timestamp and metadata
   - View count tracking

2. **Access**: When someone visits a share link:
   - The conversation is displayed in the web interface
   - Users can continue the conversation from that point
   - The shared header shows creation date and view count

3. **API Endpoints**:
   - `POST /api/share` - Create a new share (internal use)
   - `GET /api/share/{short_id}` - Retrieve share data
   - `GET /{short_id}` - Access shared conversation page

#### Privacy & Security

- **No Personal Data**: Share links contain only the conversation content
- **No Tracking**: No user identification or tracking beyond view counts
- **Public Access**: Anyone with the link can view and continue the conversation

#### Clear Preview Cache

The bot caches Discord preview images for shared conversations to improve performance. Use the `clear_preview_cache.py` script to clear cached images when needed.

##### What It Does

The script clears cached preview images from the database, forcing the bot to regenerate Discord preview images on the next access. This is useful when:

- **Font rendering changes** (like the recent Unicode symbol fixes)
- **Layout or styling updates** to preview images
- **Debugging preview image issues**
- **Wanting to refresh all preview images** with updated rendering logic

##### What Gets Deleted

**Database Data Deleted:**
- **Binary image data** stored in the `preview_image` column (PNG image blobs)
- **Generation timestamp** in the `preview_generated_at` column

**No Files or Folders Deleted:**
- ❌ No filesystem files are touched
- ❌ No folders are deleted
- ❌ No disk storage is freed

**What Stays Intact:**
- ✅ Original conversation data (questions, answers, timestamps)
- ✅ Share URLs and short IDs remain functional
- ✅ View counts and metadata preserved
- ✅ Database structure unchanged
- ✅ All other database columns remain untouched

**Important: Database-Only Operation**
The script **only modifies the SQLite database** (`shares.db`). It does not:
- Delete any files from your computer or Railway server
- Remove any folders or directories
- Free up disk space (database size remains the same)
- Affect your code, fonts, or configuration files

The cached images are stored as **binary data directly in the database**, not as separate image files on disk. When you clear the cache, you're only removing stored data from the database - the actual PNG images get regenerated on-demand when someone visits a share URL.

##### Usage

**Clear All Cached Images:**
```bash
python clear_preview_cache.py --all
```

**Clear Specific Share Caches:**
```bash
python clear_preview_cache.py ABC123 XYZ789
```

**On Railway:**
```bash
railway run python clear_preview_cache.py --all
```

##### When to Use

- **After Font Updates:** After deploying font fixes (like adding `DejaVuSans.ttf` for Unicode symbols)
- **After Preview Image Changes:** When modifying `preview_image_generator.py` (colors, layout, text rendering)
- **Debugging Specific Shares:** If a particular share URL shows incorrect preview image

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