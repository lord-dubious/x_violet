-- Schema for unified tweet memory + vector db in sqlite-vec

-- Table for tweet/conversation metadata
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

-- Table for conversation chains
CREATE TABLE IF NOT EXISTS conversations (
    conversation_id TEXT PRIMARY KEY,
    root_tweet_id TEXT,
    last_updated TIMESTAMP
);

-- Vector table for tweet embeddings (sqlite-vec)
CREATE VIRTUAL TABLE IF NOT EXISTS tweet_embeddings USING vec(
    id INTEGER PRIMARY KEY,
    tweet_id TEXT,
    embedding BLOB
);

-- Index for fast lookup
CREATE INDEX IF NOT EXISTS idx_tweet_convo ON tweets(conversation_id);
CREATE INDEX IF NOT EXISTS idx_embedding_tweet_id ON tweet_embeddings(tweet_id);
