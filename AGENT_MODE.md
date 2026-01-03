# Agent Mode - Function Calling System

The bot now supports an **agent-like mode** where it can explore its own documentation directory using function calling, similar to how Cursor works.

## Overview

Instead of hardcoding pattern matching logic, the bot can now:
1. **Discover** files and directories in its docs
2. **Search** for characters matching patterns
3. **Read** specific files when needed
4. **Explore** the documentation structure dynamically

## How It Works

When a user asks a query like "find valks that start with S", the bot:

1. **Receives the query** and recognizes it needs to explore files
2. **Calls `find_characters_by_pattern`** tool with `starts_with="S"`
3. **Gets a list** of matching characters (e.g., "Sylvia_SP", "Sophia", etc.)
4. **Calls `read_file`** for each relevant character to get details
5. **Formats a response** with the information found

## Available Tools

### 1. `list_files`
List files in a directory with optional pattern matching.

**Example Usage:**
- List all markdown files: `list_files(directory="character", pattern="*.md")`
- Find specific files: `list_files(directory="guide", pattern="*raid*")`

### 2. `find_characters_by_pattern`
Find character files matching patterns (perfect for "starts with X" queries).

**Example Usage:**
- Find characters starting with S: `find_characters_by_pattern(starts_with="S")`
- Find SP characters starting with S: `find_characters_by_pattern(starts_with="S", contains="SP")`
- Find UR characters: `find_characters_by_pattern(contains="UR")`

### 3. `read_file`
Read a specific documentation file.

**Example Usage:**
- Read a character file: `read_file(file_path="character/100044-Sylvia_SP.md")`
- Read first 50 lines: `read_file(file_path="guide/raids.md", max_lines=50)`

### 4. `search_in_files`
Search for a term across multiple files.

**Example Usage:**
- Search for "Infernal Queen": `search_in_files(search_term="Infernal Queen")`
- Search in character directory: `search_in_files(search_term="Pierce", directory="character")`

### 5. `get_directory_structure`
Get the directory structure to understand organization.

**Example Usage:**
- Get root structure: `get_directory_structure()`
- Get character directory: `get_directory_structure(directory="character")`

## Enabling Agent Mode

Agent mode is **enabled by default** but can be controlled:

```python
# In rag/chain.py, the query_with_usage method accepts:
enable_tools=True  # Enable agent mode (default)
enable_tools=False # Use traditional RAG only
```

## Example Queries

### Pattern-Based Queries
- "find valks that start with S"
- "what SP characters start with S?"
- "show me all UR valkyries"
- "characters that contain SP"

### Exploration Queries
- "what files are in the character directory?"
- "list all guide files"
- "show me the docs structure"

### Combined Queries
- "find valks starting with S and tell me about their skills"
  - Bot will: find characters → read their files → extract skill info

## Benefits

1. **No Hardcoding**: Pattern matching logic is handled by the LLM, not hardcoded
2. **Flexible**: Can handle new query patterns without code changes
3. **Exploratory**: Bot can discover and explore its own knowledge base
4. **Transparent**: Tool calls are logged in metadata for debugging

## Tool Call Tracking

All tool calls are tracked in the response metadata:

```python
metadata = {
    "tool_calls": [
        {
            "function": "find_characters_by_pattern",
            "arguments": {"starts_with": "S", "contains": "SP"},
            "result": {...}
        },
        {
            "function": "read_file",
            "arguments": {"file_path": "character/100044-Sylvia_SP.md"},
            "result": {...}
        }
    ]
}
```

## Hybrid Approach

The bot uses a **hybrid approach**:
1. **First**: Tries traditional RAG retrieval for initial context
2. **Then**: Uses tools if needed for pattern-based or exploratory queries
3. **Finally**: Combines both sources for the final response

This gives the best of both worlds:
- Fast semantic search for direct questions
- Flexible tool-based exploration for pattern queries

## Performance Considerations

- **Tool calls add latency**: Each tool call is an additional API round-trip
- **Max iterations**: Limited to 5 iterations to prevent infinite loops
- **Caching**: Consider caching tool results for repeated queries

## Future Enhancements

Potential improvements:
- Cache tool results
- Parallel tool execution
- Tool result summarization
- Selective tool enabling based on query type

