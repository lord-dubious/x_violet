"""
Persistent storage helper for tracking tweet interactions.
Stores tweet IDs in data/interactions.json to avoid duplicate actions.
"""
import json
from pathlib import Path

INTERACTIONS_PATH = Path(__file__).resolve().parent.parent / "data" / "interactions.json"

class InteractionStore:
    def __init__(self, path=INTERACTIONS_PATH):
        self.path = Path(path)
        self._ensure_file()
        self.data = self._load()

    def _ensure_file(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            with open(self.path, "w") as f:
                json.dump({"interacted_tweets": []}, f)

    def _load(self):
        with open(self.path, "r") as f:
            return json.load(f)

    def has_interacted(self, tweet_id: str) -> bool:
        return tweet_id in self.data.get("interacted_tweets", [])

    def add_interaction(self, tweet_id: str):
        if not self.has_interacted(tweet_id):
            self.data.setdefault("interacted_tweets", []).append(tweet_id)
            self._save()

    def _save(self):
        with open(self.path, "w") as f:
            json.dump(self.data, f, indent=2)

    def remove_interaction(self, tweet_id: str):
        if self.has_interacted(tweet_id):
            self.data["interacted_tweets"].remove(tweet_id)
            self._save()

    def clear(self):
        self.data["interacted_tweets"] = []
        self._save()
