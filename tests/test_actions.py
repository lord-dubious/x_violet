import pytest
from xviolet.actions import ActionManager
from xviolet.storage import InteractionStore

class DummyTwitterClient:
    def __init__(self):
        self.actions = []
    def quote_tweet(self, tweet_id, text, media_path=None):
        self.actions.append(("QUOTE_TWEET", tweet_id, text, media_path))
    def reply(self, tweet_id, text):
        self.actions.append(("REPLY", tweet_id, text))
    def like(self, tweet_id):
        self.actions.append(("LIKE", tweet_id))
    def retweet(self, tweet_id):
        self.actions.append(("RETWEET", tweet_id))

@pytest.fixture
def store(tmp_path):
    path = tmp_path / "interactions.json"
    path.write_text('{"interacted_tweets": []}')
    return InteractionStore(path)

@pytest.fixture
def manager(store):
    return ActionManager(DummyTwitterClient(), store)

def test_quote_tweet(manager):
    assert manager.quote_tweet("1", "text")
    assert manager.store.has_interacted("1")
    assert not manager.quote_tweet("1", "text")  # No duplicate

def test_reply(manager):
    assert manager.reply("2", "reply")
    assert manager.store.has_interacted("2")
    assert not manager.reply("2", "reply")
    # Conversation override
    assert manager.reply("2", "reply", conversation=True)

def test_like(manager):
    assert manager.like("3")
    assert manager.store.has_interacted("3")
    assert not manager.like("3")

def test_retweet(manager):
    assert manager.retweet("4")
    assert manager.store.has_interacted("4")
    assert not manager.retweet("4")
