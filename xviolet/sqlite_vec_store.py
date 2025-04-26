import sqlite3
from pathlib import Path
import sqlite_vec
from xviolet.config import config


class VectorInteractionStore:
    """
    SQLite-backed vector store for tweet interactions.
    Uses sqlite-vec for vector indexing and sqlite-rembed for embeddings.
    """
    def __init__(self, path: str = None):
        # Determine DB path
        db_path = Path(path) if path else Path(__file__).resolve().parent.parent / "data" / "interactions.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        # Connect and load extensions
        self.db = sqlite3.connect(str(db_path))
        self.db.enable_load_extension(True)
        try:
            sqlite_vec.load(self.db)
            # Load rembed extension if available
            try:
                # adjust extension name/path as needed
                self.db.load_extension("rembed0")
            except Exception:
                pass
        finally:
            self.db.enable_load_extension(False)
        # Register embedding client and create tables
        self._register_rembed_client()
        self._create_tables()

    def _register_rembed_client(self):
        # Register your Gemini embedder in temp.rembed_clients
        model = config.embedding_model
        api_key = config.gemini_api_key
        self.db.execute(
            """
            INSERT OR IGNORE INTO temp.rembed_clients(name, options)
            VALUES(?, rembed_client_options(
                'format', 'openai',
                'model', ?,
                'key', ?
            ))
            """,
            (model, model, api_key),
        )
        self.db.commit()

    def _create_tables(self):
        # Virtual table for vector search
        dim = config.embedding_dim
        self.db.execute(f"CREATE VIRTUAL TABLE IF NOT EXISTS interactions USING vec0(embedding float[{dim}])")
        # Meta table for ids and content
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS interactions_meta(id TEXT PRIMARY KEY, content TEXT)"
        )
        self.db.commit()

    def has_interacted(self, tweet_id: str) -> bool:
        cur = self.db.execute(
            "SELECT 1 FROM interactions_meta WHERE id = ?", (tweet_id,)
        )
        return cur.fetchone() is not None

    def add_interaction(self, tweet_id: str, content: str):
        if self.has_interacted(tweet_id):
            return
        # Embed and insert vector
        model = config.embedding_model
        self.db.execute(
            "INSERT INTO interactions(rowid, embedding) VALUES(?, rembed(?, ?))",
            (tweet_id, model, content),
        )
        self.db.execute(
            "INSERT INTO interactions_meta(id, content) VALUES(?, ?)",
            (tweet_id, content),
        )
        self.db.commit()

    def remove_interaction(self, tweet_id: str):
        self.db.execute(
            "DELETE FROM interactions_meta WHERE id = ?", (tweet_id,)
        )
        self.db.execute(
            "DELETE FROM interactions WHERE rowid = ?", (tweet_id,)
        )
        self.db.commit()

    def clear(self):
        self.db.execute("DELETE FROM interactions_meta")
        self.db.execute("DELETE FROM interactions")
        self.db.commit()

    def search(self, query: str, k: int = 5) -> list[tuple[str, float]]:
        """
        Return up to k nearest tweet_ids and distances for the given query text.
        """
        # Uses the rembed SQLite function for on-the-fly embedding
        cur = self.db.execute(
            """
            SELECT rowid, distance
            FROM interactions
            WHERE embedding MATCH rembed(?, ?)
            ORDER BY distance
            LIMIT ?
            """,
            (config.embedding_model, query, k),
        )
        return cur.fetchall()
