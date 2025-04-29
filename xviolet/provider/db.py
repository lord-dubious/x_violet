import os
import sqlite3
import logging

logger = logging.getLogger(__name__)

DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../data'))
DB_PATH = os.path.join(DATA_DIR, 'twitter_memory.sqlite')

# SQL schema for regular and vector tables
SCHEMA = """
CREATE TABLE IF NOT EXISTS tweets (
    tweet_id TEXT PRIMARY KEY,
    user_id TEXT,
    username TEXT,
    created_at TIMESTAMP,
    conversation_id TEXT,
    in_reply_to_status_id TEXT,
    text TEXT,
    processed INTEGER DEFAULT 0,
    embedding_id INTEGER,
    UNIQUE(tweet_id)
);

CREATE TABLE IF NOT EXISTS conversations (
    conversation_id TEXT PRIMARY KEY,
    root_tweet_id TEXT,
    last_updated TIMESTAMP
);

CREATE VIRTUAL TABLE IF NOT EXISTS tweet_embeddings USING vec(
    id INTEGER PRIMARY KEY,
    tweet_id TEXT,
    embedding BLOB
);

CREATE INDEX IF NOT EXISTS idx_tweet_convo ON tweets(conversation_id);
CREATE INDEX IF NOT EXISTS idx_embedding_tweet_id ON tweet_embeddings(tweet_id);
"""

# Example seed data (for dev/testing)
SEED_TWEETS = [
    ("seed1", "u123", "tester", "2025-04-27T20:00:00", "conv1", None, "Hello world!", 1, 1),
    ("seed2", "u456", "tester2", "2025-04-27T20:01:00", "conv1", "seed1", "Reply to hello", 1, 2),
]
SEED_CONVOS = [
    ("conv1", "seed1", "2025-04-27T20:01:00"),
]
SEED_EMBEDDINGS = [
    (1, "seed1", b"\x00"*768),
    (2, "seed2", b"\x01"*768),
]

def ensure_data_dir():
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)
        logger.info(f"Created data directory at {DATA_DIR}")

def get_connection():
    ensure_data_dir()
    conn = sqlite3.connect(DB_PATH)
    # Load extensions if available
    try:
        conn.enable_load_extension(True)
        conn.execute("SELECT load_extension('vec')")
        conn.execute("SELECT load_extension('rembed')")
        logger.info("Loaded sqlite-vec and sqlite-rembed extensions.")
    except Exception as e:
        logger.warning(f"Could not load vector/embedding extensions: {e}")
    return conn

def initialize_db(seed=False):
    conn = get_connection()
    with conn:
        for stmt in SCHEMA.split(';'):
            if stmt.strip():
                conn.execute(stmt)
        logger.info("Database tables ensured.")
        if seed:
            try:
                conn.executemany("INSERT OR IGNORE INTO tweets VALUES (?,?,?,?,?,?,?,?,?)", SEED_TWEETS)
                conn.executemany("INSERT OR IGNORE INTO conversations VALUES (?,?,?)", SEED_CONVOS)
                conn.executemany("INSERT OR IGNORE INTO tweet_embeddings VALUES (?,?,?)", SEED_EMBEDDINGS)
                logger.info("Seed data inserted.")
            except Exception as e:
                logger.warning(f"Seed data insertion failed: {e}")
    conn.close()

def upsert_tweet(tweet):
    conn = get_connection()
    with conn:
        conn.execute("""
        INSERT OR REPLACE INTO tweets (tweet_id, user_id, username, created_at, conversation_id, in_reply_to_status_id, text, processed, embedding_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, tweet)
    conn.close()

def upsert_conversation(convo):
    conn = get_connection()
    with conn:
        conn.execute("""
        INSERT OR REPLACE INTO conversations (conversation_id, root_tweet_id, last_updated)
        VALUES (?, ?, ?)
        """, convo)
    conn.close()

def upsert_embedding(embedding):
    conn = get_connection()
    with conn:
        conn.execute("""
        INSERT OR REPLACE INTO tweet_embeddings (id, tweet_id, embedding)
        VALUES (?, ?, ?)
        """, embedding)
    conn.close()

# Call this on startup
if __name__ == "__main__":
    initialize_db(seed=True)
