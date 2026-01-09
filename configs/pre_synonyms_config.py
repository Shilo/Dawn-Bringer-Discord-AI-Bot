"""PRE-PROCESSING: Query synonym and abbreviation expansions for improved retrieval.

This file contains mappings from abbreviations/short forms to their full expansions.
PROCESSED BEFORE vector search to expand abbreviations so abbreviated searches find full-term content.

Format: "abbreviation": ["full_term_1", "full_term_2", ...]

Processing timing: EARLY (before vector search) - expands abbreviations within queries

Examples:
    # Character abbreviations
    "valk": ["valkyrie"]  # "best valk" finds content about "best valkyrie"

    # Game terms
    "pve": ["player versus environment"]  # "pve guide" finds "player versus environment guide"

    # Multiple expansions for context
    "db": ["dawn bringer", "dawnbringer"]  # Handles both variations

    # Rarity abbreviations
    "ur": ["ultra rare", "gold"]  # "ur valkyrie" finds both "ultra rare valkyrie" and "gold valkyrie"

How it works:
    - Word boundary matching: "valk" in "best valk" becomes "best valkyrie"
    - Partial matching: "valk" in "valkyries" becomes "valkyries" (no change)
    - Multiple expansions: Each abbreviation can expand to multiple full forms

To add new synonyms:
    1. Identify common abbreviations users type
    2. Add full forms that appear in your documents
    3. Consider multiple variations (e.g., "defense" vs "defence")
    4. Test that expansions improve search results

Example additions:
    "char": ["character"]                    # Game character references
    "lvl": ["level", "leveling"]            # Level/leveling content
    "mat": ["material", "materials"]        # Resource/crafting materials
    "crit": ["critical", "critical hit"]    # Already exists, but shows multiple expansions
"""

SYNONYMS = {
    # Character/Class abbreviations
    "valk": ["valkyrie"],
    "db": ["dawn bringer", "dawnbringer"],
    "emi": ["emilius"],
    "yu": ["yusheng"],

    # Rarity terms
    "sp": ["special"],
    "ur": ["ultra rare", "gold"],
    "sr": ["super rare", "blue"],
    "ssr": ["super super rare", "purple"],
    "ul": ["ultimate"],
    "orange": ["yellow"], # Orange = Yellow armaments
    "gold": ["yellow"], # Gold = Yellow armaments

    # Player types
    "f2p": ["free to play"],
    "p2w": ["pay to win"],

    # Game modes
    "pve": ["player versus environment"],
    "pvp": ["player versus player", "arena"],

    # Game mechanics
    "rng": ["random number generator", "random", "luck"],
    "exp": ["experience", "xp"],
    "xp": ["experience", "exp"],
    "hp": ["health", "health points"],
    "atk": ["attack"],
    "def": ["defense", "defence"],
    "dps": ["damage per second", "damage"],
    "aoe": ["area of effect"],
    "cc": ["crowd control"],
    "crit": ["critical", "critical hit"],
    "dmg": ["damage"],
    "mult": ["multiplier"],
    "factor": ["multiplier"], # Pierce factor = Multiplier
    "mod": ["modifier", "multiplier"],

    # Game modes/locations
    "sim": ["simulation", "digital simulation"],
    "corr": ["corridor", "dimensional corridor"],
    "lts": ["limited time sprint", "sprint"],
    "sprint": ["limited time sprint", "lts"],
    "bio": ["bio beast", "bio-beast"],
    "frenzy": ["bio beast frenzy", "bio-beast frenzy"],
    "intercept": ["intercept supply"],
    "supply": ["intercept supply"],
    "guild": ["alliance"],
    "story": ["stage"],
    "bp": ["backpack"],
    "dimentional": ["dimensional"], # Typo from TG: Dimentional Arena = Dimensional Arena
    "event": ["banner", "roulette"],
    "roulette": ["banner", "event"],

    # Currency
    "money": ["cash", "dollar", "currency"],
    "diamond": ["gem"],
    "shard": ["Valkyrie Shard"],
    "core": ["crystal"], # Tech Crystal/Core
}
