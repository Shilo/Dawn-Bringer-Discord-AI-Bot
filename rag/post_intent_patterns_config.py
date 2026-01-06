"""POST-PROCESSING: FAQ intent pattern recognition.

This file contains patterns that map query keywords to specific FAQ content.
PROCESSED AFTER vector search to boost relevant FAQ entries based on exact keyword matching.

Format: frozenset(["keyword1", "keyword2", ...]): ["target_faq_title_1", "target_faq_title_2", ...]

Processing timing: LATE (after vector search) - boosts retrieved documents higher in results

Examples:
    # All keywords must be present in query for the pattern to match
    frozenset(['best', 'valk', 'valkyrie']): ['what valkyrie should i use']
    # Query: "what's the best valkyrie" -> MATCHES (boosts "What Valkyrie Should I Use?" FAQ)
    # Query: "best valk" -> NO MATCH (missing "valkyrie")

    # Multiple FAQs can be boosted for the same pattern
    frozenset(['best', 'team']): ['what team should i use', 'recommended team']
    # Boosts both the main team FAQ and recommended team content

    # Specific intent patterns for precise matching
    frozenset(['weapon', 'level']): ['how should i level valkyrie weapons']
    # Query: "how do I level weapons" -> MATCHES and boosts weapon leveling FAQ

To add new patterns:
    1. Identify keywords that indicate specific user intent
    2. Find the exact FAQ title(s) that should be boosted
    3. Use frozenset() to ensure all keywords must be present
    4. Test with queries containing those exact keywords

Example addition:
    frozenset(['new', 'player', 'help']): ['beginner guide', 'getting started']
    # Would boost beginner content when users ask for "new player help"
"""

from typing import Dict, List, FrozenSet

# Intent patterns for FAQ boosting
# Maps sets of keywords to FAQ titles that should be boosted for those queries
INTENT_PATTERNS: Dict[FrozenSet[str], List[str]] = {
    # Valkyrie-related intents
    frozenset(['best', 'valk', 'valkyrie']): ['what valkyrie should i use', 'valkyrie recommendations'],
    frozenset(['good', 'valk', 'valkyrie']): ['what valkyrie should i use', 'valkyrie recommendations'],
    frozenset(['top', 'valk', 'valkyrie']): ['valkyrie tier list', 'what valkyrie should i use'],
    frozenset(['valkyrie', 'tier', 'list']): ['valkyrie tier list'],
    frozenset(['valkyrie', 'recommend']): ['what valkyrie should i use'],

    # Team-related intents
    frozenset(['best', 'team']): ['what team should i use', 'recommended team'],
    frozenset(['good', 'team']): ['what team should i use', 'recommended team'],
    frozenset(['f2p', 'team']): ['free to play team', 'f2p valkyrie lineup'],
    frozenset(['team', 'recommend']): ['what team should i use', 'recommended team'],

    # Weapon-related intents
    frozenset(['best', 'weapon']): ['what valkyrie ur weapons should i equip', 'weapon recommendations'],
    frozenset(['good', 'weapon']): ['what valkyrie ur weapons should i equip', 'weapon guide'],
    frozenset(['weapon', 'equip']): ['what valkyrie ur weapons should i equip'],
    frozenset(['weapon', 'level']): ['what valkyrie skills should i level', 'how should i level valkyrie weapons'],

    # Skill-related intents
    frozenset(['skill', 'level']): ['what valkyrie skills should i level'],
    frozenset(['skill', 'upgrade']): ['what valkyrie skills should i level'],
    frozenset(['valkyrie', 'skill']): ['what valkyrie skills should i level'],

    # SP Valkyrie intents
    frozenset(['sp', 'valkyrie']): ['should i spend money for sp valkyries'],
    frozenset(['sp', 'worth']): ['should i spend money for sp valkyries'],
    frozenset(['buy', 'sp']): ['should i spend money for sp valkyries'],

    # Flame intents
    frozenset(['flame', 'worth']): ['should i spend money for flame'],
    frozenset(['buy', 'flame']): ['should i spend money for flame'],
    frozenset(['flame', 'recommend']): ['should i spend money for flame'],

    # Beginner intents
    frozenset(['beginner', 'guide']): ['beginner guide', 'getting started'],
    frozenset(['new', 'player']): ['beginner guide', 'getting started'],
    frozenset(['getting', 'started']): ['beginner guide', 'tutorial'],

    # Game mode intents
    frozenset(['raid', 'guide']): ['raid guide', 'raid valkyries'],
    frozenset(['arena', 'guide']): ['arena guide', 'arena valkyries'],
    frozenset(['pvp', 'guide']): ['arena guide', 'arena valkyries'],
    frozenset(['corridor', 'guide']): ['corridor guide', 'dimensional corridor'],
}
