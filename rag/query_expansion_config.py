"""Configuration for semantic query expansion mappings.

This file contains mappings from short/informal queries to more complete questions and topics.
Used by the RAG retriever to improve retrieval by expanding user queries semantically.

Format: "query_pattern": ["expanded_query_1", "expanded_query_2", ...]

Examples:
    # Basic expansion: short query -> related topics
    "best valk": ["what valkyrie should i use", "valkyrie tier list", "best valkyrie"]

    # Multiple expansions for broader coverage
    "f2p": ["free to play guide", "free to play valkyries", "free to play team"]

    # Context-specific expansions
    "raid": ["raid guide", "raid valkyries"]  # Expands to both guide and character recommendations

To add new mappings:
    1. Choose a common short query users might type
    2. Add expanded versions that match actual document content
    3. Test that the expansions improve retrieval results

Example addition:
    "new feature": ["new feature guide", "new feature tutorial", "how to use new feature"]
"""

from typing import Dict, List

# Semantic query mappings - maps short queries to more complete questions/topics
# This helps bridge the gap between how users ask questions and how documentation is structured
SEMANTIC_MAPPINGS: Dict[str, List[str]] = {
    # Valkyrie-related queries
    "best valk": ["what valkyrie should i use", "valkyrie tier list", "best valkyrie"],
    "good valk": ["what valkyrie should i use", "valkyrie recommendations"],
    "valk tier": ["valkyrie tier list"],
    "top valk": ["valkyrie tier list", "best valkyrie"],

    # Team-related queries
    "best team": ["what team should i use", "recommended team", "best lineup"],
    "good team": ["what team should i use", "recommended team"],
    "f2p team": ["free to play team", "f2p valkyrie lineup"],

    # General game queries
    "beginner": ["beginner guide", "getting started"],
    "new player": ["beginner guide", "new player guide"],
    "f2p": ["free to play guide", "free to play valkyries"],
    "p2w": ["pay to win guide", "pay to win valkyries"],

    # Specific game modes
    "raid": ["raid guide", "raid valkyries"],
    "arena": ["arena guide", "arena valkyries", "pvp guide"],
    "corridor": ["corridor guide", "dimensional corridor"],
    "simulation": ["simulation guide", "digital simulation"],

    # Character queries
    "db": ["dawn bringer guide", "dawnbringer"],
    "dawnbringer": ["dawn bringer guide", "db guide"],

    # Weapon queries
    "best weapon": ["what valkyrie weapons should i use", "weapon recommendations"],
    "good weapon": ["what valkyrie weapons should i use", "weapon guide"],
    "weapon tier": ["weapon tier list", "best weapons"],

    # Other common queries
    "how to play": ["beginner guide", "getting started guide"],
    "getting started": ["beginner guide", "tutorial"],
    "tutorial": ["beginner guide", "getting started"],
    "guide": ["complete guide", "beginner guide"],
}
