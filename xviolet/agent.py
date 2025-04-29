"""
Main agent loop for x_violet: integrates LLM, persona, ActionManager, and TwitterClient.
- Handles polling, LLM-driven action selection, and dispatch.
- Avoids duplicate interactions using interactions.json
"""
import logging
import asyncio
import time
import random
from pathlib import Path
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
        # Use dedicated event loop to avoid nested asyncio.run issues
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    def run_once(self):
        # 1. Fetch timeline/tweets to consider
        # Execute the async poll() coroutine to get timeline
        # Authenticate before polling
        self.loop.run_until_complete(self.twitter.login())
        timeline = self.loop.run_until_complete(self.twitter.poll())  # TODO: Should return a list of tweet dicts
        # Limit number of tweets processed per cycle
        limit = self.config.max_actions_processing
        timeline = timeline[:limit]
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

    def run(self, max_cycles: int = None):
        logger.info("Starting unified agent scheduler...")
        # Initialize next run times
        now = time.time()
        # Counter for test loop breaking
        cycles = 0
        next_action = now
        # Post scheduling: immediate first run or randomized interval
        if self.config.post_immediately:
            next_post = now
            # disable immediate flag for subsequent runs
            self.config.post_immediately = False
        else:
            next_post = now + random.uniform(self.config.post_interval_min, self.config.post_interval_max)
        while True:
            now = time.time()
            # Increment cycle and check max_cycles
            cycles += 1
            if max_cycles is not None and cycles >= max_cycles:
                logger.info(f"Reached max_cycles={max_cycles}, exiting loop.")
                break
            # Action processing (poll & dispatch) at configured interval
            if self.config.enable_action_processing and now >= next_action:
                logger.info("Running action processing cycle...")
                # Ensure authenticated before polling
                self.loop.run_until_complete(self.twitter.login())
                self.run_once()
                next_action = now + self.config.action_interval
            # Post generation at configured interval
            if self.config.enable_twitter_post_generation and now >= next_post:
                logger.info("Generating and posting a scheduled tweet...")
                # Decide between media or text tweet
                if random.random() < self.config.media_tweet_probability:
                    # Media tweet flow
                    media_dir = Path(self.config.media_dir)
                    media_files = [p for p in media_dir.iterdir() if p.suffix.lower() in ('.jpg','.jpeg','.png','.gif')]
                    if media_files:
                        media_path = str(random.choice(media_files))
                        tweet_text = self.llm.analyze_image(media_path, context_type="post")
                        if tweet_text:
                            self.loop.run_until_complete(
                                self.twitter.post_tweet_with_media(tweet_text, media_path)
                            )
                        else:
                            text = self.llm.generate_text("Automated tweet from x_violet", context_type="post")
                            if text:
                                self.loop.run_until_complete(self.twitter.post_tweet(text))
                    else:
                        logger.warning(f"No media files found in {self.config.media_dir}; posting text tweet.")
                        text = self.llm.generate_text("Automated tweet from x_violet", context_type="post")
                        if text:
                            self.loop.run_until_complete(self.twitter.post_tweet(text))
                else:
                    # Text tweet flow
                    text = self.llm.generate_text("Automated tweet from x_violet", context_type="post")
                    if text:
                        self.loop.run_until_complete(self.twitter.post_tweet(text))
                next_post = now + random.uniform(self.config.post_interval_min, self.config.post_interval_max)
            sleep_interval = random.uniform(
                self.config.loop_sleep_interval_min,
                self.config.loop_sleep_interval_max
            )
            time.sleep(sleep_interval)

Agent = XVioletAgent  # Alias for compatibility

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    agent = Agent()
    agent.run()
