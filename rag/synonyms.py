"""Query synonym and abbreviation expansions for improved retrieval."""

# Common abbreviations and their expansions
# Used to expand queries so that searches with abbreviations also find content using full terms
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
    "event": ["banner", "roulette"],
    "roulette": ["banner", "event"],
    
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

    # Currency
    "money": ["cash", "dollar", "currency"],
    "diamond": ["gem"],
    "shard": ["Valkyrie Shard"]
}

