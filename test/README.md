# RAG Testing Script

This directory contains a standalone test script for debugging and tuning the RAG chunk retrieval system.

## Usage

### Basic Usage
```bash
python test/test_rag.py
```

### With Verbose Logging
```bash
python test/test_rag.py --verbose
```

### Force Rebuild Vector Store
```bash
python test/test_rag.py --rebuild
```

### Change Top-K Value
```bash
python test/test_rag.py --top-k 10
```

### Combined Options
```bash
python test/test_rag.py --verbose --top-k 10
```

## Interactive Commands

Once the script is running, you can:

- **Enter a query** - Type any query and press Enter to test it
- **`quit` or `exit`** - Exit the test script
- **`help`** - Show available commands
- **`clear`** - Clear the screen
- **`top-k <number>`** - Change the top-k value (e.g., `top-k 10`)

## What It Shows

For each query, the script displays:

1. **Query Expansion Details** (if `--verbose` is used):
   - Plural normalization
   - Synonym expansion
   - Word order variations
   - Search parameters

2. **Retrieved Chunks**:
   - Source file
   - Document type
   - Distance score (lower is better)
   - Content preview

3. **Summary**:
   - Number of chunks retrieved
   - Best/worst/average scores
   - Unique sources

## Example Session

```
🔍 Query: what valks should i use?

================================================================================
# Testing Query: what valks should i use?
================================================================================

✅ Retrieved 5 chunks

================================================================================
Chunk #1
================================================================================
Source: faq/FAQ - 2. Player
Type: faq
Score: 0.663 (lower is better)
Content Length: 1234 chars

Content Preview:
What Valkyrie Should I Use?  > There is no "single best" for all modes for all Dawnbringer Classes. ...
--------------------------------------------------------------------------------
...
```

## Notes

- The script uses the same RAG system as production, but with verbose logging enabled
- Verbose logging is **disabled by default** in production (`bot.py`)
- The script only shows what chunks would be retrieved, not the final LLM response
- This is useful for debugging why certain chunks are or aren't being retrieved

