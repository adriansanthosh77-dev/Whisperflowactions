import json
import os
import time
import logging
import threading
from pathlib import Path
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

MEMORY_PATH = Path(__file__).parent.parent / "data" / "long_term_memory.json"


class LongTermMemory:
    def __init__(self):
        self.memory: List[Dict] = []
        self._lock = threading.Lock()
        self._load()

    def _load(self):
        if MEMORY_PATH.exists():
            try:
                with open(MEMORY_PATH, "r") as f:
                    self.memory = json.load(f)
            except (json.JSONDecodeError, IOError):
                self.memory = []
        else:
            MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
            self.memory = []

    def _save(self):
        try:
            with open(MEMORY_PATH, "w") as f:
                json.dump(self.memory, f, indent=2)
        except IOError as e:
            logger.error(f"Failed to save memory: {e}")

    def add(self, fact: str, category: str = "general"):
        entry = {
            "fact": fact,
            "category": category,
            "timestamp": time.time(),
        }
        with self._lock:
            self.memory.append(entry)
            self._save()
        logger.info(f"Learned new fact: {fact}")

    def recall(self, query: str, limit: int = 3) -> List[str]:
        if not self.memory:
            return []
        words = query.lower().split()
        results = []
        with self._lock:
            for entry in self.memory:
                fact = entry["fact"].lower()
                if any(word in fact for word in words):
                    results.append(entry["fact"])
        return results[:limit]


_MEMORY = None
_MEMORY_LOCK = threading.Lock()


def get_memory() -> LongTermMemory:
    global _MEMORY
    if _MEMORY is None:
        with _MEMORY_LOCK:
            if _MEMORY is None:
                _MEMORY = LongTermMemory()
    return _MEMORY
