# Logging Guide for Agent Mode

This guide explains the logging system added to track how the bot handles prompts and tool calls.

## Logging Levels

### INFO Level (Default)
Shows important events and flow:
- When agent mode is enabled/disabled
- Tool calls being made
- API request/response times
- Summary of results
- Final response statistics

### DEBUG Level
Shows detailed information:
- Full tool call arguments
- Complete API request details
- Message counts and content lengths
- Detailed tool results

## Enabling Debug Logging

Run the bot with the `--debug-rag` flag:

```bash
python bot.py --debug-rag
```

Or for both rebuild and debug:

```bash
python bot.py --rebuild --debug-rag
```

## Log Format

Logs follow this format:
```
YYYY-MM-DD HH:MM:SS - rag.chain - LEVEL - message
```

## What Gets Logged

### 1. Mode Selection
```
🤖 Agent mode enabled for query: find valks that start with S...
```
or
```
📚 Regular RAG mode for query: what are Sylvia's skills...
```

### 2. Agent Mode Flow

#### Initial Setup
```
================================================================================
🤖 AGENT MODE: Starting query processing
📝 Query: find valks that start with S
================================================================================
📋 System prompt length: 1234 chars
🛠️ Loaded 5 tools: ['list_files', 'find_characters_by_pattern', 'read_file', 'search_in_files', 'get_directory_structure']
```

#### RAG Retrieval (if attempted)
```
📚 Attempting initial RAG retrieval...
✅ RAG retrieved 3 documents, context length: 1234 chars
```
or
```
ℹ️ No RAG context retrieved
```

#### Tool Calling Loop
```
🔄 Starting tool calling loop (max 5 iterations)

--- Iteration 1/5 ---
📤 Sending request to OpenAI (model: gpt-4o-mini, tokens: 500)
📥 Received response (1.23s)
   Response finish_reason: tool_calls
   Usage: 456 prompt + 78 completion = 534 total
🔧 Model requested 1 tool call(s):
   [1/1] find_characters_by_pattern
      Arguments: {
        "starts_with": "S",
        "contains": "SP"
      }
🔧 Executing tool: find_characters_by_pattern
   Arguments: {
     "starts_with": "S",
     "contains": "SP"
   }
✅ Tool find_characters_by_pattern completed: Found 1 characters (0.05s)
      ✅ Result: 1 items found
🔄 Continuing to next iteration...

--- Iteration 2/5 ---
📤 Sending request to OpenAI (model: gpt-4o-mini, tokens: 500)
📥 Received response (1.45s)
   Response finish_reason: tool_calls
   Usage: 1234 prompt + 45 completion = 1279 total
🔧 Model requested 1 tool call(s):
   [1/1] read_file
      Arguments: {
        "file_path": "character/100044-Sylvia_SP.md"
      }
🔧 Executing tool: read_file
   Arguments: {
     "file_path": "character/100044-Sylvia_SP.md",
     "max_lines": 100
   }
✅ Tool read_file completed: Read 37 lines (0.02s)
      ✅ Result: 2345 chars read
🔄 Continuing to next iteration...

--- Iteration 3/5 ---
📤 Sending request to OpenAI (model: gpt-4o-mini, tokens: 500)
📥 Received response (0.89s)
   Response finish_reason: stop
   Usage: 2345 prompt + 234 completion = 2579 total
✅ Model finished (no more tool calls)
📊 Final response length: 456 chars
📊 Total tool calls made: 2
📊 Total iterations: 3
================================================================================
✅ AGENT MODE: Query completed successfully
================================================================================
```

### 3. Tool Execution Details

Each tool call logs:
- **Start**: Tool name and arguments
- **Execution**: What the tool is doing
- **Result**: Summary of what was found/returned
- **Timing**: How long it took

Example:
```
🔧 Executing tool: find_characters_by_pattern
   Arguments: {
     "starts_with": "S",
     "contains": "SP"
   }
✅ Tool find_characters_by_pattern completed: Found 1 characters (0.05s)
```

### 4. Error Handling

If a tool fails:
```
❌ Tool find_characters_by_pattern failed: Directory not found: invalid_path
```

If max iterations reached:
```
⚠️ Hit max iterations (5), stopping tool loop
⚠️ AGENT MODE: Query completed with max iterations reached
```

### 5. Regular RAG Mode

For non-agent queries:
```
📚 Regular RAG mode: Retrieving documents...
📚 RAG retrieved 5 documents from 3 sources
   Context length: 3456 chars
📤 Sending request to OpenAI (model: gpt-4o-mini, tokens: 500)
📥 Received response (0.67s)
   Usage: 1234 prompt + 234 completion = 1468 total
📊 Response length: 456 chars
```

## Log Examples by Scenario

### Scenario 1: Pattern Query
**Query**: "find valks that start with S"

**Expected Logs**:
1. Agent mode enabled
2. RAG retrieval (may find nothing)
3. Tool call: `find_characters_by_pattern(starts_with="S")`
4. Tool call: `read_file` for each matching character
5. Final response

### Scenario 2: Direct Question
**Query**: "What are Sylvia's skills?"

**Expected Logs**:
1. Regular RAG mode (or agent mode with RAG first)
2. RAG retrieval finds Sylvia document
3. Direct response (no tools needed)

### Scenario 3: Exploration Query
**Query**: "What files are in the character directory?"

**Expected Logs**:
1. Agent mode enabled
2. Tool call: `list_files(directory="character")`
3. Response with file list

## Debug Mode Details

With `--debug-rag`, you'll also see:

### Full Tool Arguments
```json
   Arguments: {
     "starts_with": "S",
     "contains": "SP",
     "doc_type": "character"
   }
```

### Complete Tool Results
```
   Result: {
     "characters": [
       {
         "name": "Sylvia_SP",
         "file": "character/100044-Sylvia_SP.md",
         "filename": "100044-Sylvia_SP.md"
       }
     ],
     "count": 1
   }
```

### Message Details
```
   Message count: 5
   Context length: 3456 chars
```

## Performance Metrics

Logs include timing information:
- **API calls**: Time to get response from OpenAI
- **Tool execution**: Time to execute each tool
- **Total iterations**: How many tool call rounds were needed

Example:
```
📥 Received response (1.23s)
✅ Tool find_characters_by_pattern completed: Found 1 characters (0.05s)
📊 Total iterations: 3
```

## Troubleshooting

### No Tool Calls Made
If you see "Model finished (no more tool calls)" on first iteration:
- The model decided tools weren't needed
- Check if RAG retrieval already provided enough context

### Max Iterations Reached
If you see "Hit max iterations (5)":
- The model is making too many tool calls
- May indicate a loop or inefficient tool usage
- Check tool results to see if they're providing useful information

### Tool Errors
If you see "❌ Tool X failed":
- Check the error message
- Verify file paths and arguments
- Check if DOCS_DIR is correctly configured

## Log File Output

To save logs to a file, modify the logging configuration:

```python
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
```

This will log to both console and `bot.log` file.

