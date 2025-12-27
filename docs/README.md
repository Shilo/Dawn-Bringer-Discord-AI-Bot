# Game Documentation

This directory contains all game documentation files that the Dawn Bringer Discord bot uses to answer questions. The bot automatically loads all `.txt` and `.md` files on startup and uses keyword matching to find relevant sections when answering user queries.

**Note:** `README.md` files are ignored and will not be loaded as documentation.

## How it works

- The bot recursively searches through all `.txt` and `.md` files in this directory and subdirectories
- When a user asks a question, it finds relevant documentation based on keyword matching
- The bot prioritizes files whose names contain query keywords
- Relevant documentation is included as context for the AI response (up to 1000 characters per query)
- The bot uses paragraph-level extraction by default to provide the most relevant snippets

## Documentation Structure

The documentation is organized into the following categories:

### Core Guides
- **`all-the-guides-topic/`** - Comprehensive game guides covering:
  - Star Rank and Shards
  - F2P Gem Spending
  - Purchase and Spending
  - Classes
  - Armaments
  - Stats
  - Builds
  - Shop Purchases
  - Tech Tree

### Valkyries
- **`valkyries/`** - Individual character profiles for all Valkyries (Miranda, Nicole, Emily, Elia, Aurora, Sophia, Madison, Kiki, Chika Shiraishi, Kanade, Rina, Flame, Gabrielle, Zoe, Audrey, Diva, Poposha, Wendy, Emilius, Hecate_SP, Alicia, Milena, Anna, Rika, YuSheng, Misty, Ophelia, Lynn, Niya, Yonai, Vila, Irene, Liz, Mina, Ruby_SP, Elaris, Katherine_SP, Loranna, Sasha, Haruka Mizuhara, Eve & Ashe_SP, Nova_SP, Sylvia_SP, Lunaverre_SP, Kotsuba Yoshikawa, Hoshimi Oozora, Charlene, Violetta, Gabrielle (Researcher), Audrey (Flamebearer), and Special Valkyries)

### Tier Lists & Rankings
- **`valkyrie-tier-list/`** - Tier list information for:
  - Overview
  - Raids
  - Corridor Simulation
  - Stages and Other Content

### Game Mechanics
- **`bluestacks-game-guides/`** - Gameplay mechanics and guides:
  - Beginners Guide – Core Mechanics
  - Combat Mechanics
  - Team Composition
  - Install and Play Run! Goddess on PC with BlueStacks

### Events & Sprints
- **`limited-time-sprints/`** - Information about limited-time events:
  - Overview
  - Schedule
  - Sprint Types
  - History
  - Tips

### Frequently Asked Questions
- **`faq-frequently-asked-questions/`** - FAQ sections covering:
  - Player questions
  - Gameplay questions
  - Event questions
  - Cash Shop questions
  - System questions
  - Support questions

### Specialized Guides
- **`backpack-tech/`** - Backpack specialization guides
- **`citrine-miner/`** - Citrine mining patterns and strategies
- **`game-strat-wiki/`** - Strategic gameplay guides
- **`new-features/`** - Information about new game features:
  - New Features List
  - Radar Expedition

### Official Content
- **`official-website/`** - Content from the official website:
  - About
  - FAQ

### Additional Directories
- **`bluestacks-beginners-guide/`** - Beginner guides for BlueStacks
- **`mining/`** - Mining-related documentation
- **`sprints/`** - Sprint-related documentation
- **`tier-lists/`** - Additional tier list information

## File Naming Conventions

- Files are organized by topic in subdirectories
- Individual Valkyrie files use the format: `{ID}-{Name}.md` (e.g., `100001-Miranda.md`)
- Guide files use descriptive names with numbers for ordering (e.g., `1. Star Rank and Shards.md`)
- The filename (without extension and relative path) is shown in the context when the bot references documentation

## Tips for Adding Documentation

- **Keep files organized by topic** - Use subdirectories to group related content
- **Use clear headings and sections** - This helps the bot extract relevant paragraphs
- **Include specific details** - Stats, mechanics, and specific information improve answer quality
- **Descriptive filenames** - Files with keywords in their names are prioritized by the bot
- **Markdown formatting** - Use proper markdown headings (`#`, `##`, `###`) to structure content
- **Avoid README.md** - These files are automatically ignored

## How the Bot Finds Relevant Documentation

1. **Keyword Matching** - The bot extracts keywords from user queries
2. **Filename Priority** - Files whose names contain query keywords get bonus points
3. **Content Matching** - The bot scores files based on keyword frequency in content
4. **Top Results** - The top 3 most relevant files are selected
5. **Paragraph Extraction** - Relevant paragraphs are extracted from selected files (default mode)
6. **Context Limit** - Up to 1000 characters of documentation are included per query
