# Game Documentation

Place your game documentation files here as `.txt` or `.md` files. The bot will automatically load them on startup and use them to answer questions.

**Note:** `README.md` files are ignored and will not be loaded as documentation.

## How it works

- The bot searches through all `.txt` and `.md` files in this directory
- When a user asks a question, it finds relevant sections based on keywords
- Relevant documentation is included as context for the AI response

## File naming

Name your files descriptively (e.g., `valkyries.txt`, `combat_mechanics.md`, `events.txt`). The filename (without extension) will be shown in the context.

## Example structure

```
docs/
  ├── valkyries.txt          # Information about all Valkyries
  ├── combat_mechanics.txt   # Combat system details
  ├── base_building.txt      # Base building guide
  ├── events.txt             # Event information
  └── weapons.txt            # Weapons and equipment
```

## Tips

- Keep files organized by topic
- Use clear headings and sections
- Include specific details, stats, and mechanics
- The bot will automatically find relevant sections based on user questions

