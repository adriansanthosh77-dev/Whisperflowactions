import rapidfuzz
import logging
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)

# --- High-Performance Semantic Thesaurus ---
# Maps common synonyms to the canonical reflex keywords.
# This provides 80% of the benefit of embeddings with 0% of the latency.
THESAURUS = {
    "open": ["launch", "start", "run", "execute", "go to", "show me", "open up", "bring up", "focus"],
    "close": ["kill", "stop", "exit", "quit", "terminate", "shut down", "close down"],
    "search": ["find", "look up", "google", "query", "research", "hunt for"],
    "type": ["dictate", "write", "enter", "insert", "input", "put"],
    "next": ["forward", "advance", "skip"],
    "previous": ["back", "backward", "return"],
    "minimize": ["hide", "stow", "shrink"],
    "maximize": ["full screen", "expand", "enlarge"],
    "brightness": ["light", "illumination", "dim"],
    "volume": ["sound", "audio", "noise"],
}

class SemanticMatcher:
    """
    Layer 3 Intent Matcher.
    Uses Token Set Ratio + Synonym Expansion for near-semantic matching.
    """
    def __init__(self, threshold: float = 80.0):
        self.threshold = threshold

    def expand_query(self, query: str) -> List[str]:
        """Generates variations of the query based on the thesaurus."""
        words = query.lower().split()
        variations = [query.lower()]
        
        for i, word in enumerate(words):
            for canonical, synonyms in THESAURUS.items():
                if word in synonyms:
                    # Create a copy and swap synonym for canonical
                    new_words = words[:]
                    new_words[i] = canonical
                    variations.append(" ".join(new_words))
        return list(set(variations))

    def find_match(self, query: str, keys: List[str]) -> Optional[str]:
        """
        Tries to match the query against a list of keys using 
        semantic-aware fuzzy matching.
        """
        variations = self.expand_query(query)
        
        best_match = None
        best_score = 0
        
        for v in variations:
            # Token Set Ratio is robust against word order and extra words
            result = rapidfuzz.process.extractOne(
                v, keys, 
                scorer=rapidfuzz.fuzz.token_set_ratio,
                score_cutoff=self.threshold
            )
            if result:
                match, score, index = result
                if score > best_score:
                    best_score = score
                    best_match = match
        
        if best_match:
            logger.info(f"Semantic match found: '{query}' -> '{best_match}' (score: {best_score:.1f})")
            return best_match
            
        return None

_MATCHER = SemanticMatcher()

def semantic_match(query: str, keys: List[str], threshold: float = 80.0) -> Optional[str]:
    _MATCHER.threshold = threshold
    return _MATCHER.find_match(query, keys)
