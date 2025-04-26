"""
Action Manager for x_violet agent.
Supports: quote, reply, like, retweet, and persistent interaction tracking.
LLM/persona-driven selection and dispatch. Uses twikit/twikit_ext for all actions.
"""
from xviolet.storage import InteractionStore
import logging

# Import the Twitter client (twikit/twikit_ext)
from xviolet.client.twitter_client import TwitterClient

logger = logging.getLogger("xviolet.actions")

SUPPORTED_ACTIONS = [
    "QUOTE_TWEET",
    "REPLY",
    "LIKE",
    "RETWEET",
]

class ActionManager:
    def __init__(self, twitter_client=None, interaction_store=None):
        self.twitter = twitter_client or TwitterClient()
        self.store = interaction_store or InteractionStore()

    def should_interact(self, tweet_id: str, conversation: bool = False) -> bool:
        """
        Returns True if the tweet should be interacted with.
        Allows ongoing replies in a conversation (conversation=True).
        """
        if conversation:
            return True
        return not self.store.has_interacted(tweet_id)

    def record_interaction(self, tweet_id: str):
        self.store.add_interaction(tweet_id)

    def quote_tweet(self, tweet_id: str, text: str, media_path: str = None):
        if not self.should_interact(tweet_id):
            logger.info(f"Already quoted tweet {tweet_id}, skipping.")
            return False
        self.twitter.quote_tweet(tweet_id, text, media_path)
        self.record_interaction(tweet_id)
        return True

    def reply(self, tweet_id: str, text: str, conversation: bool = False):
        if not self.should_interact(tweet_id, conversation=conversation):
            logger.info(f"Already replied to tweet {tweet_id}, skipping.")
            return False
        self.twitter.reply(tweet_id, text)
        self.record_interaction(tweet_id)
        return True

    def like(self, tweet_id: str):
        if not self.should_interact(tweet_id):
            logger.info(f"Already liked tweet {tweet_id}, skipping.")
            return False
        self.twitter.like(tweet_id)
        self.record_interaction(tweet_id)
        return True

    def retweet(self, tweet_id: str):
        if not self.should_interact(tweet_id):
            logger.info(f"Already retweeted tweet {tweet_id}, skipping.")
            return False
        self.twitter.retweet(tweet_id)
        self.record_interaction(tweet_id)
        return True

    def dispatch(self, action: str, tweet_id: str, text: str = None, media_path: str = None, conversation: bool = False):
        if action == "QUOTE_TWEET":
            return self.quote_tweet(tweet_id, text, media_path)
        elif action == "REPLY":
            return self.reply(tweet_id, text, conversation=conversation)
        elif action == "LIKE":
            return self.like(tweet_id)
        elif action == "RETWEET":
            return self.retweet(tweet_id)
        else:
            logger.warning(f"Action '{action}' not supported.")
            return False
