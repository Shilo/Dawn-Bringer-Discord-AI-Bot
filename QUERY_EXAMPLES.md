# Query Processing Examples

This document explains how different types of queries are processed by the Dawn Bringer Discord Bot's RAG system.

## Table of Contents
1. [Pattern-Based Character Queries](#pattern-based-character-queries)
2. [Synonym Expansion](#synonym-expansion)
3. [Character-Specific Queries](#character-specific-queries)
4. [General Game Questions](#general-game-questions)
5. [Gift Code Queries](#gift-code-queries)
6. [Newcomer Code Detection](#newcomer-code-detection)
7. [FAQ/Guide Queries](#faqguide-queries)

---

## Pattern-Based Character Queries

These queries ask about characters using patterns like "starts with X" or "name starts with X".

### Example 1: "What are the skills of the new SP valk that starts with S?"

**Processing Steps:**
1. **Pattern Detection**: Detects "starts with S" pattern → extracts letter "S"
2. **Context Extraction**: Detects "SP" context from "SP valk"
3. **Character Search**: Searches `docs/character/` for files matching:
   - Name starts with "S" (case-insensitive)
   - Contains "SP" in filename or character name
   - Finds: `100044-Sylvia_SP.md` → "Sylvia_SP"
4. **Query Expansion**: Adds query variations:
   - Original: "what are the skills of the new SP valk that starts with S?"
   - "Sylvia_SP"
   - "what are the skills of the new SP valk that starts with S? Sylvia_SP"
   - "what are the skills of the new SP valk Sylvia_SP"
5. **Retrieval**: Searches vector store with all variations
6. **Result**: Retrieves Sylvia document chunks with high relevance

**Other Pattern Examples:**
- "valk that starts with M" → Finds characters like "Miranda", "Madison", "Misty"
- "UR character beginning with E" → Finds UR characters starting with E
- "name starts with A valkyrie" → Finds characters starting with A

---

## Synonym Expansion

The system automatically expands abbreviations and synonyms to improve retrieval.

### Example 2: "What is the best DB class?"

**Processing Steps:**
1. **Synonym Detection**: Detects "DB" abbreviation
2. **Expansion**: Expands "DB" → ["dawn bringer", "dawnbringer"]
3. **Query Variations Created**:
   - Original: "what is the best DB class?"
   - "what is the best dawn bringer class?"
   - "what is the best dawnbringer class?"
   - "what is the best DB dawn bringer class?"
4. **Word Order Expansion**: For each variation, tries different word orders:
   - "best class DB"
   - "class best DB"
   - "DB best class"
   - etc.
5. **Retrieval**: Searches with all variations
6. **Result**: Finds relevant documentation about Dawn Bringer classes

**Common Synonym Mappings:**
- `valk` → `valkyrie`
- `sp` → `special`
- `ur` → `ultra rare`, `gold`
- `sr` → `super rare`, `blue`
- `ssr` → `super super rare`, `purple`
- `pve` → `player versus environment`
- `pvp` → `player versus player`, `arena`
- `f2p` → `free to play`
- `atk` → `attack`
- `def` → `defense`, `defence`
- `hp` → `health`, `health points`
- `dps` → `damage per second`, `damage`
- `aoe` → `area of effect`
- `cc` → `crowd control`
- `crit` → `critical`, `critical hit`
- `lts` → `limited time sprint`, `sprint`
- `sim` → `simulation`, `digital simulation`
- `corr` → `corridor`, `dimensional corridor`
- `bio` → `bio beast`, `bio-beast`
- `guild` → `alliance`

### Example 3: "How do I get more exp?"

**Processing Steps:**
1. **Synonym Detection**: Detects "exp" abbreviation
2. **Expansion**: Expands "exp" → ["experience", "xp"]
3. **Query Variations**:
   - "how do I get more exp?"
   - "how do I get more experience?"
   - "how do I get more xp?"
4. **Retrieval**: Finds guides about gaining experience/XP

---

## Character-Specific Queries

Direct queries about specific characters.

### Example 4: "Tell me about Sylvia's skills"

**Processing Steps:**
1. **Direct Character Match**: Query contains character name "Sylvia"
2. **Retrieval**: Searches for documents containing "Sylvia"
3. **Document Matching**: Finds `docs/character/100044-Sylvia_SP.md`
4. **Chunk Expansion**: If small chunks are retrieved, expands to include full sections
5. **Result**: Returns comprehensive information about Sylvia's skills

### Example 5: "What are Miranda's star upgrades?"

**Processing Steps:**
1. **Character Detection**: "Miranda" identified
2. **Specific Topic**: "star upgrades" narrows the search
3. **Retrieval**: Finds relevant sections from Miranda's character document
4. **Section Expansion**: Expands header-only chunks to include full upgrade information
5. **Result**: Returns star upgrade details for Miranda

---

## General Game Questions

Questions about game mechanics, features, or general information.

### Example 6: "How does the corridor simulation work?"

**Processing Steps:**
1. **Synonym Expansion**: "corridor" → ["corridor", "dimensional corridor"]
2. **Query Variations**:
   - "how does the corridor simulation work?"
   - "how does the dimensional corridor simulation work?"
3. **Document Type Detection**: Searches across all document types
4. **Retrieval**: Finds relevant guides and FAQ entries
5. **Result**: Returns information about corridor simulation mechanics

### Example 7: "What is a limited time sprint?"

**Processing Steps:**
1. **Synonym Expansion**: "sprint" → ["limited time sprint", "lts"]
2. **Query Variations**:
   - "what is a limited time sprint?"
   - "what is a lts?"
   - "what is a limited time sprint lts?"
3. **Document Matching**: Finds `docs/general/limited-time-sprints/` documents
4. **Result**: Returns comprehensive sprint information

---

## Gift Code Queries

Queries about gift codes or redemption codes.

### Example 8: "What gift codes are available?"

**Processing Steps:**
1. **Gift Code Detection**: Detects keywords: "code", "gift", "redemption", "redeem", "promo", "coupon"
2. **Channel Search**: Searches configured Discord channel (`gift-codes` by default)
3. **Code Extraction**: Extracts gift codes from recent messages (last 7 days)
4. **Document Generation**: Creates dynamic document with:
   - Active gift codes
   - Posting dates
   - Redemption instructions
5. **Context Injection**: Injects this document as additional context (prioritized)
6. **RAG Retrieval**: May also search static documentation about gift codes
7. **Result**: Returns both active codes and general information

**Note**: Gift code documents are dynamically generated and expire after 1 week.

---

## Newcomer Code Detection

Automatic detection when users share newcomer invite codes publicly.

### Example 9: User sends: "ABCDEFGHIJ" (10 uppercase letters)

**Processing Steps:**
1. **Pattern Detection**: Detects 10-character uppercase code pattern
2. **Newcomer Document Loading**: Loads `docs/general/new-features/newcomer-invitation.md`
3. **Context Injection**: Injects document with special instruction to explain why codes should be shared privately
4. **RAG Retrieval**: Skips normal RAG retrieval (uses only newcomer document)
5. **Response**: Bot explains mutual trading benefits and privacy importance

**Note**: This is a special case that bypasses normal RAG retrieval to provide targeted education.

---

## FAQ/Guide Queries

Questions that match FAQ or guide content.

### Example 10: "How do I upgrade my backpack?"

**Processing Steps:**
1. **Synonym Expansion**: Checks for relevant synonyms
2. **Document Type Search**: Searches FAQ and guide documents
3. **Retrieval**: Finds relevant guides about backpack upgrades
4. **Chunk Prioritization**: If multiple chunks from same document, prefers:
   - Earlier chunks (likely headers/main content)
   - Larger chunks (more comprehensive)
   - Better similarity scores
5. **Result**: Returns guide information about backpack upgrades

### Example 11: "What are the best valkyries for raids?"

**Processing Steps:**
1. **Synonym Expansion**: "valkyries" → ["valkyrie", "valk"]
2. **Query Variations**: Multiple word order variations
3. **Document Matching**: Finds tier list documents in `docs/general/valkyrie-tier-list/`
4. **Section Expansion**: Expands to include full raid tier list sections
5. **Result**: Returns comprehensive raid tier list information

---

## Cross-Language Queries

Queries in languages without word boundaries (Chinese, Japanese, Korean).

### Example 12: Japanese query about a character

**Processing Steps:**
1. **CJK Detection**: Detects CJK characters (Chinese, Japanese, Korean)
2. **Threshold Adjustment**: Increases score threshold by 25% (cross-language queries have higher distances)
3. **Search Expansion**: Doubles the search_k parameter (gets more results)
4. **Retrieval**: Searches with adjusted parameters
5. **Fallback**: If threshold filters all results, returns top K anyway
6. **Result**: Returns best matches even with higher distance scores

---

## Query Processing Flow Summary

For any query, the system:

1. **Preprocessing**:
   - Detects pattern-based queries (e.g., "starts with X")
   - Detects gift code requests
   - Detects newcomer codes
   - Detects CJK characters

2. **Query Expansion**:
   - Synonym expansion (abbreviations → full terms)
   - Pattern-based character name expansion
   - Word order variations (for multi-word queries)

3. **Retrieval**:
   - Searches vector store with all query variations
   - Tracks best scores for each document
   - Filters by relevance threshold (adjusted for cross-language)

4. **Post-Processing**:
   - Expands header-only chunks to include full sections
   - Expands small chunks within sections
   - Prioritizes comprehensive chunks when multiple from same document
   - Replaces small chunks with better ones from same document if available

5. **Context Building**:
   - Formats retrieved chunks with source citations
   - Injects additional context (gift codes, newcomer docs) if applicable
   - Numbers sources for citation tracking

6. **Response Generation**:
   - Sends context to LLM with user query
   - LLM generates response using retrieved documentation
   - Extracts used source indices from response
   - Formats response with source links

---

## Tips for Better Queries

1. **Be Specific**: "Sylvia skills" is better than "valk skills"
2. **Use Abbreviations**: The system expands them automatically (e.g., "SP valk", "UR character")
3. **Pattern Queries Work**: "starts with S" will find matching characters
4. **Ask Direct Questions**: "What are X's skills?" works well
5. **Context Helps**: "SP valk that starts with S" is better than just "starts with S"

---

## Technical Details

- **Embedding Model**: `text-embedding-3-small` (OpenAI)
- **Chunk Size**: 1000 chars (default), 800 chars (characters)
- **Top K Retrieval**: 5 chunks per query (configurable)
- **Score Threshold**: 1.2 (configurable, filters low-relevance chunks)
- **Vector Store**: ChromaDB with persistent storage
- **Query Variations**: Typically 5-20 variations per query (depends on synonyms and patterns)

