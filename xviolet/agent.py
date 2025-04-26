"""
Main agent loop for x_violet: integrates LLM, persona, ActionManager, and TwitterClient.
- Handles polling, LLM-driven action selection, and dispatch.
- Avoids duplicate interactions using interactions.json
"""
import logging
from xviolet.config import config
from xviolet.provider.llm import LLMManager
from xviolet.actions import ActionManager
from xviolet.client.twitter_client import TwitterClient

logger = logging.getLogger("xviolet.agent")

class XVioletAgent:
    def __init__(self):
        self.config = config
        self.llm = LLMManager()
        self.twitter = TwitterClient()
        self.actions = ActionManager(self.twitter)

    def run_once(self):
        # 1. Fetch timeline/tweets to consider
        timeline = self.twitter.poll()  # TODO: Should return a list of tweet dicts
        if not timeline:
            logger.info("No tweets to process.")
            return
        for tweet in timeline:
            tweet_id = tweet["id"]
            text = tweet["text"]
            user = tweet["user"]
            media_path = tweet.get("media_path")
            conversation = tweet.get("conversation", False)

            # 2. Build LLM prompt (persona, tweet, context, available actions)
            prompt = self.llm.build_action_prompt(
                persona_path=self.config.character_file,
                tweet=text,
                user=user,
                available_actions=self.actions.SUPPORTED_ACTIONS,
                context=tweet
            )
            # 3. Ask LLM to select action and generate text (if needed)
            llm_result = self.llm.generate_structured_output(prompt)
            action = llm_result.get("action")
            generated_text = llm_result.get("text")

            # 4. Dispatch action (quote, reply, like, retweet)
            self.actions.dispatch(
                action=action,
                tweet_id=tweet_id,
                text=generated_text,
                media_path=media_path,
                conversation=conversation
            )

    def run(self):
        logger.info("Starting agent loop...")
        while True:
            self.run_once()
            # TODO: Respect config intervals, sleep, etc.
            break  # Remove this break for real agent loop

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    agent = XVioletAgent()
    agent.run()
