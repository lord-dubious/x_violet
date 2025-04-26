"""
TwitterClient scaffold for x_violet

- Uses twikit_ext for all Twitter API actions
- Loads all config from AgentConfig (env-driven, Eliza-style)
- Supports login/session, posting, search, polling, retry, dry run, proxy, and target users
- Ready for further feature expansion (media, DMs, etc.)
"""
from xviolet.config import config
import logging
from twikit_ext.client.client import Client
from proxystr import Proxy
import asyncio
import os
import json

logger = logging.getLogger("xviolet.twitter_client")

class TwitterClient:
    def __init__(self):
        self.config = config
        self.client = None
        self.session = None
        self.logged_in = False
        self._load_proxy()
        # Async client initialization
        self._init_lock = asyncio.Lock()

    def _load_proxy(self):
        # Use Twitter-specific proxy if set, else fallback to generic SOCKS5_PROXY
        proxy_str = self.config.twitter_proxy or self.config.socks5_proxy
        if proxy_str:
            logger.info(f"Initializing proxy for Twitter client: {proxy_str}")
            self.proxy = Proxy(proxy_str)
            # Optional: Show proxy details and check status
            try:
                info = self.proxy.get_info()
                logger.info(f"Proxy details: {info}")
                blacklist = info.get('blacklist', None)
                if blacklist:
                    logger.warning(f"Proxy is blacklisted: {blacklist}")
                else:
                    logger.info("Proxy is not blacklisted.")
            except Exception as e:
                logger.error(f"Failed to get proxy info: {e}")
            try:
                is_good = self.proxy.check()
                if is_good:
                    logger.info("Proxy is GOOD.")
                else:
                    logger.warning("Proxy is BAD or unreachable.")
            except Exception as e:
                logger.error(f"Proxy check failed: {e}")
            # Build profile for twikit_ext with auth token and ct0
            profile = {
                "auth_token": self.config.twitter_auth_token,
                "ct0": self.config.twitter_ct0,
                "username": self.config.twitter_username,
                "email": self.config.twitter_email,
                "password": self.config.twitter_password,
                "totp_secret": self.config.twitter_2fa_secret,
                "proxy": self.proxy,
            }
            # Instantiate extended Twikit client with Proxy instance
            self.client = Client(profile, proxy=self.proxy, user_agent=self.config.twitter_user_agent)
        else:
            logger.warning("No Twitter proxy configured (TWITTER_PROXY or SOCKS5_PROXY). Proceeding without proxy.")
            self.proxy = None
            profile = {
                "auth_token": self.config.twitter_auth_token,
                "ct0": self.config.twitter_ct0,
                "username": self.config.twitter_username,
                "email": self.config.twitter_email,
                "password": self.config.twitter_password,
                "totp_secret": self.config.twitter_2fa_secret,
                "proxy": None,
            }
            # Instantiate extended Twikit client without proxy
            self.client = Client(profile, user_agent=self.config.twitter_user_agent)

    def rotate_proxy_if_bad(self):
        """Trigger proxy rotation if the proxy is BAD/unreachable."""
        if not self.proxy:
            logger.warning("No proxy loaded, cannot rotate.")
            return False
        try:
            is_good = self.proxy.check()
            if not is_good and hasattr(self.proxy, 'refresh'):
                logger.info("Proxy is BAD, attempting rotation...")
                result = self.proxy.refresh()
                logger.info(f"Proxy rotation triggered. Result: {result}")
                return result
            elif not is_good:
                logger.warning("Proxy is BAD, but rotation not supported.")
                return False
            else:
                logger.info("Proxy is still GOOD, no rotation needed.")
                return True
        except Exception as e:
            logger.error(f"Proxy rotation check/attempt failed: {e}")
            return False

    async def login(self):
        # Throttle login to avoid bans
        import random
        delay = random.uniform(self.config.auth_delay_min, self.config.auth_delay_max)
        logger.info(f"Sleeping for {delay:.2f}s before login to avoid rate limits.")
        await asyncio.sleep(delay)
        logger.info("Authenticating with Twitter via twikit_ext...")
        async with self._init_lock:
            # Attempt to load existing cookies for reuse
            cookies_file = self.config.cookie_file
            if cookies_file and os.path.exists(cookies_file):
                try:
                    with open(cookies_file, 'r') as f:
                        cookies_dict = json.load(f)
                    # Update client HTTP cookies
                    self.client.http.cookies.update(cookies_dict)
                    logger.info(f"Loaded cookies from {cookies_file}")
                    # Validate session via user fetch
                    user = await self.client.user()
                    self.logged_in = True
                    logger.info(f"Session validated via cookies: {user}")
                    return
                except Exception as e:
                    logger.warning(f"Cookie load or validation failed: {e}, falling back to full login")
                    # Clear invalid cookies
                    self.client.http.cookies.clear()
            # Ensure proxy is rotated before login
            self.rotate_proxy_if_bad()
            try:
                user = await self.client.connect()
                self.logged_in = True
                logger.info(f"Login successful: {user}")
                # Save cookies to file for next time
                try:
                    os.makedirs(os.path.dirname(cookies_file), exist_ok=True)
                    with open(cookies_file, 'w') as f:
                        json.dump(dict(self.client.http.cookies), f)
                    logger.info(f"Saved cookies to {cookies_file}")
                except Exception as se:
                    logger.warning(f"Failed saving cookies: {se}")
            except Exception as e:
                self.logged_in = False
                logger.error(f"Twitter login failed: {e}")

    async def post_tweet(self, text: str):
        """Post a tweet (text only, async)."""
        if self.config.dry_run:
            logger.info(f"[DRY RUN] Would post tweet: {text}")
            return True
        if len(text) > self.config.max_tweet_length:
            logger.warning("Tweet exceeds max length. Truncating.")
            text = text[:self.config.max_tweet_length]
        # Rotate proxy before posting
        self.rotate_proxy_if_bad()
        try:
            tweet = await self.client.create_tweet(text=text)
            logger.info(f"Tweet posted: {tweet}")
            return True
        except Exception as e:
            logger.error(f"Failed to post tweet: {e}")
            return False

    async def quote_tweet(self, tweet_id: str, text: str, media_path: str = None):
        """Quote a tweet with optional media attachment (async)."""
        if self.config.dry_run:
            logger.info(f"[DRY RUN] Would quote tweet {tweet_id} with text: {text} and media: {media_path}")
            return True
        # Rotate proxy before quoting
        self.rotate_proxy_if_bad()
        try:
            attachment_url = f"https://twitter.com/i/web/status/{tweet_id}"
            media_ids = None
            if media_path:
                media_id = await self.client.upload_media(media_path)
                media_ids = [media_id]
            await self.client.create_tweet(text=text, media_ids=media_ids, attachment_url=attachment_url)
            logger.info(f"Quoted tweet {tweet_id} with text: {text} and media: {media_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to quote tweet: {e}")
            return False

    async def reply(self, tweet_id: str, text: str):
        """Reply to a tweet (async)."""
        if self.config.dry_run:
            logger.info(f"[DRY RUN] Would reply to tweet {tweet_id} with: {text}")
            return True
        # Rotate proxy before replying
        self.rotate_proxy_if_bad()
        try:
            await self.client.create_tweet(text=text, reply_to=tweet_id)
            logger.info(f"Replied to tweet {tweet_id} with: {text}")
            return True
        except Exception as e:
            logger.error(f"Failed to reply to tweet: {e}")
            return False

    async def like(self, tweet_id: str):
        """Like a tweet (async)."""
        if self.config.dry_run:
            logger.info(f"[DRY RUN] Would like tweet {tweet_id}")
            return True
        # Rotate proxy before liking
        self.rotate_proxy_if_bad()
        try:
            await self.client.like_tweet(tweet_id)
            logger.info(f"Liked tweet {tweet_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to like tweet: {e}")
            return False

    async def retweet(self, tweet_id: str):
        """Retweet a tweet (async)."""
        if self.config.dry_run:
            logger.info(f"[DRY RUN] Would retweet tweet {tweet_id}")
            return True
        # Rotate proxy before retweeting
        self.rotate_proxy_if_bad()
        try:
            await self.client.retweet(tweet_id)
            logger.info(f"Retweeted tweet {tweet_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to retweet: {e}")
            return False

    async def search(self, query: str):
        """Perform a Twitter search if enabled (async)."""
        if not self.config.search_enable:
            logger.info("Search is disabled by config.")
            return []
        # Rotate proxy before search
        self.rotate_proxy_if_bad()
        logger.info(f"Searching Twitter for: {query}")
        # TODO: Implement actual search with twikit_ext
        return []  # Placeholder

    async def poll(self):
        """Main poll loop (timeline, mentions, etc., async)."""
        logger.info(f"Polling every {self.config.poll_interval} seconds...")
        # TODO: Implement polling logic, timeline fetch, etc.

    async def run(self):
        await self.login()
        await self.poll()

# Example usage
if __name__ == "__main__":
    import asyncio
    logging.basicConfig(level=logging.INFO)
    client = TwitterClient()
    asyncio.run(client.run())
