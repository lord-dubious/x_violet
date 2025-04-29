"""
TwitterClient scaffold for x_violet

- Uses twikit_ext for all Twitter API actions
- Loads all config from AgentConfig (env-driven, Eliza-style)
- Supports login/session, posting, search, polling, retry, dry run, proxy, and target users
- Ready for further feature expansion (media, DMs, etc.)
"""
from xviolet.config import config
import logging
import asyncio
import os
import json

logger = logging.getLogger("xviolet.twitter_client")

# Guard proxystr import: may be unavailable or broken
try:
    from proxystr import Proxy
    from proxystr.utils import ProxyStringParser
except Exception as e:
    logger.warning(f"Could not import proxystr.Proxy or ProxyStringParser, disabling proxy support: {e}")
    Proxy = None
    ProxyStringParser = None

# Define a minimum buffer for scheduling tweets to avoid API errors
MIN_SCHEDULE_BUFFER_SECONDS = 300  # 5 minutes

class TwitterClient:
    def __init__(self):
        self.config = config
        self.client = None
        self.session = None
        self.proxy = None
        self.proxy_refresh_url = None # Store the refresh URL here
        self.logged_in = False
        # Async lock for lazy initialization and auth
        self._init_lock = asyncio.Lock()

    def _load_proxy(self):
        # Skip proxy and client initialization in dry_run mode
        if self.config.dry_run:
            logger.info("[DRY RUN] Skipping proxy and client setup.")
            self.proxy = None
            self.client = None
            return
        from xviolet.provider.proxy import proxy_manager
        proxy_str = self.config.twitter_proxy or proxy_manager.get_proxy_url()
        if not Proxy or not ProxyStringParser:
            logger.error("Proxy support disabled; proxystr unavailable. Aborting.")
            raise RuntimeError("Proxy support disabled")
        if not proxy_str:
            logger.error("No Twitter proxy configured; proxy required. Aborting.")
            raise RuntimeError("Proxy required but not configured")
        
        # Parse and log proxy details
        try:
            parsed_proxy = ProxyStringParser.from_string(proxy_str)
            self.proxy_refresh_url = parsed_proxy.rotation_url # Store refresh URL
            logger.info("Parsed Proxy Details:")
            logger.info(f"  Protocol: {parsed_proxy.protocol}")
            logger.info(f"  IP:       {parsed_proxy.ip}")
            logger.info(f"  Port:     {parsed_proxy.port}")
            logger.info(f"  Username: {parsed_proxy.username if parsed_proxy.username else 'N/A'}")
            logger.info(f"  Password: {'***' if parsed_proxy.password else 'N/A'}")
            logger.info(f"  Refresh URL: {self.proxy_refresh_url if self.proxy_refresh_url else 'N/A'}")
        except Exception as parse_err:
            logger.error(f"Failed to parse proxy string '{proxy_str}': {parse_err}. Aborting.")
            raise RuntimeError(f"Failed to parse proxy string: {parse_err}")

        logger.info(f"Initializing Proxy object for Twitter client using: {proxy_str}")
        try:
            self.proxy = Proxy(proxy_str) # Create Proxy object using original string
        except Exception as e:
            logger.error(f"Failed to create Proxy({proxy_str}): {e}. Aborting.")
            raise RuntimeError(f"Failed to initialize proxy: {e}")
        
        # Build profile for Twikit client
        profile = {
            "auth_token": self.config.twitter_auth_token,
            "ct0": self.config.twitter_ct0,
            "username": self.config.twitter_username,
            "email": self.config.twitter_email,
            "password": self.config.twitter_password,
            "totp_secret": self.config.twitter_2fa_secret,
            "proxy": self.proxy,
        }
        # Local import of Twikit Client to avoid top-level import issues
        try:
            from twikit_ext.client.client import Client
        except ImportError as e:
            logger.error(f"Could not import twikit_ext.client.client.Client: {e}")
            raise
        # Instantiate Twikit client
        if self.proxy:
            try:
                from httpx_socks import AsyncProxyTransport
                transport = AsyncProxyTransport.from_url(self.proxy.url)
                self.client = Client(profile, proxy=self.proxy, transport=transport, user_agent=self.config.twitter_user_agent)
            except Exception as e:
                logger.warning(f"Proxy transport init failed ({e}); using default client")
                self.client = Client(profile, user_agent=self.config.twitter_user_agent)
        else:
            self.client = Client(profile, user_agent=self.config.twitter_user_agent)

    async def rotate_proxy_if_bad(self):
        """Trigger proxy rotation using refresh URL if the proxy is BAD/unreachable."""
        if not self.proxy:
            logger.warning("No proxy loaded, cannot rotate.")
            return False
        try:
            # First check if the proxy is reachable
            is_good = await self.proxy.check() # Assuming check is async or wrap in thread
            if is_good:
                logger.debug("Proxy check OK, no rotation needed.")
                return True # No rotation needed
            
            # If proxy is bad AND we have a refresh URL, try rotating
            if not is_good and self.proxy_refresh_url:
                logger.info(f"Proxy is BAD, attempting rotation via URL: {self.proxy_refresh_url}")
                try:
                    import httpx
                    async with httpx.AsyncClient(follow_redirects=True) as client:
                        response = await client.get(str(self.proxy_refresh_url))
                        response.raise_for_status() # Raises exception for 4xx/5xx
                    logger.info(f"Proxy refresh request successful (Status: {response.status_code}). Re-checking proxy.")
                    # Optionally re-check proxy after refresh
                    await asyncio.sleep(1) # Give proxy time to update
                    is_good_after_refresh = await self.proxy.check()
                    logger.info(f"Proxy status after refresh: {'GOOD' if is_good_after_refresh else 'BAD'}")
                    return is_good_after_refresh
                except Exception as refresh_err:
                    logger.error(f"Proxy refresh request failed: {refresh_err}")
                    return False # Refresh failed
            elif not is_good:
                logger.warning("Proxy is BAD, but no refresh URL configured or rotation failed.")
                return False # Cannot rotate
            else:
                return True # Was already good
        except Exception as check_err:
             logger.error(f"Error during proxy check/rotation: {check_err}")
             return False

    async def login(self):
        """
        Robust and stealthy login flow for Twitter using twikit_ext:
        1. Try auth_token-only (recommended by twikit_ext docs).
        2. If that fails, try full cookie dict (auth_token, ct0, etc.).
        3. If that fails, try username/password (least stealthy).
        Adds a randomized delay between fallbacks for stealth.
        """
        if self.config.dry_run:
            logger.info("[DRY RUN] Skipping login; marking as logged in.")
            self.logged_in = True
            return True

        import random
        # Helper for strategic delay
        async def strategic_delay():
            delay = random.uniform(self.config.auth_delay_min, self.config.auth_delay_max)
            logger.info(f"Strategic delay: sleeping for {delay:.2f}s before next auth attempt.")
            await asyncio.sleep(delay)

        # Lazy initialize proxy and client if not already done
        if self.client is None:
            try:
                self._load_proxy()
            except RuntimeError as load_err:
                logger.error(f"Failed to load proxy/client during login: {load_err}")
                self.logged_in = False
                return False

        async with self._init_lock:
            # --- Attempt 1: Auth Token Only ---
            auth_token = getattr(self.config, 'twitter_auth_token', None)
            if auth_token:
                logger.info("Attempting login using ONLY auth_token (twikit_ext best practice)...")
                try:
                    await self.rotate_proxy_if_bad()
                    # Re-instantiate client with only auth_token for max stealth
                    from twikit_ext.client.client import Client
                    self.client = Client({'auth_token': auth_token})
                    await self.client.connect()
                    user = await self.client.user()
                    self.logged_in = True
                    logger.info(f"Login successful via auth_token: {user}")
                    return True
                except Exception as token_err:
                    logger.warning(f"Auth_token login failed: {token_err}")
                    await strategic_delay()
            else:
                logger.info("No auth_token provided in config, skipping auth_token login.")

            # --- Attempt 2: Full Cookie Dict ---
            cookies_file = os.getenv("TWITTER_COOKIE_FILE", getattr(self.config, 'cookie_file', None))
            cookies_map = None
            if cookies_file and os.path.exists(cookies_file):
                logger.info(f"Attempting login using cookie file: {cookies_file}")
                try:
                    with open(cookies_file, 'r') as f:
                        raw = json.load(f)
                    if isinstance(raw, list):
                        cookies_map = {c.get('name'): c.get('value') for c in raw if c.get('name') and c.get('value')}
                    elif isinstance(raw, dict):
                        cookies_map = raw
                    else:
                        cookies_map = None
                        logger.warning(f"Unrecognized cookie file format: {cookies_file}")
                    if cookies_map:
                        from twikit_ext.client.client import Client
                        self.client = Client(cookies_map)
                        await self.client.connect()
                        user = await self.client.user()
                        self.logged_in = True
                        logger.info(f"Login successful via cookie dict: {user}")
                        return True
                    else:
                        logger.warning("No valid cookies found in file.")
                except Exception as cookie_err:
                    logger.warning(f"Cookie dict login failed: {cookie_err}")
                    await strategic_delay()
            else:
                logger.info("No cookie file found or specified, skipping cookie login.")

            # --- Attempt 3: Username/Password ---
            username = getattr(self.config, 'twitter_username', None)
            password = getattr(self.config, 'twitter_password', None)
            if username and password:
                logger.info("Attempting login via username/password (least stealthy, last resort)...")
                try:
                    from twikit_ext.client.client import Client
                    self.client = Client()
                    await self.client.login(username, password)
                    user = await self.client.user()
                    self.logged_in = True
                    logger.info(f"Login successful via username/password: {user}")
                    # Save cookies for future stealthier logins
                    cookies_file = os.getenv("TWITTER_COOKIE_FILE", getattr(self.config, 'cookie_file', None))
                    if cookies_file:
                        try:
                            os.makedirs(os.path.dirname(cookies_file), exist_ok=True)
                            with open(cookies_file, 'w') as f:
                                json.dump({n: v for n, v in self.client.http.cookies.items()}, f, indent=2)
                            logger.info(f"Saved session cookies to {cookies_file}")
                        except Exception as save_err:
                            logger.warning(f"Failed saving cookies: {save_err}")
                    return True
                except Exception as cred_err:
                    logger.error(f"Login failed via username/password: {cred_err}")
                    await strategic_delay()
            else:
                logger.info("No username/password provided, skipping credential login.")

            logger.error("All authentication attempts failed.")
            self.logged_in = False
            return False


    async def post_tweet(self, text: str):
        """Post a tweet (text only, async)."""
        if self.config.dry_run:
            logger.info(f"[DRY RUN] Would post tweet: {text}")
            return True
        if len(text) > self.config.max_tweet_length:
            logger.warning("Tweet exceeds max length. Truncating.")
            text = text[:self.config.max_tweet_length]
        # Rotate proxy before posting
        await self.rotate_proxy_if_bad()
        try:
            tweet = await self.client.create_tweet(text=text)
            logger.info(f"Tweet posted: {tweet}")
            return True
        except Exception as e:
            logger.error(f"Failed to post tweet: {e}")
            return False

    async def post_tweet_with_media(self, text: str, media_path: str):
        """Post a tweet with media attachment (async)."""
        if self.config.dry_run:
            logger.info(f"[DRY RUN] Would post media tweet: {text} with media {media_path}")
            return True
        if len(text) > self.config.max_tweet_length:
            logger.warning("Tweet exceeds max length. Truncating.")
            text = text[:self.config.max_tweet_length]
        # Rotate proxy before posting
        await self.rotate_proxy_if_bad()
        try:
            media_id = await self.client.upload_media(media_path)
            media_ids = [media_id]
            tweet = await self.client.create_tweet(text=text, media_ids=media_ids)
            logger.info(f"Media tweet posted: {tweet}")
            return True
        except Exception as e:
            logger.error(f"Failed to post media tweet: {e}")
            return False

    async def quote_tweet(self, tweet_id: str, text: str, media_path: str = None):
        """Quote a tweet with optional media attachment (async)."""
        if self.config.dry_run:
            logger.info(f"[DRY RUN] Would quote tweet {tweet_id} with text: {text} and media: {media_path}")
            return True
        # Rotate proxy before quoting
        await self.rotate_proxy_if_bad()
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
        await self.rotate_proxy_if_bad()
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
        await self.rotate_proxy_if_bad()
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
        await self.rotate_proxy_if_bad()
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
        await self.rotate_proxy_if_bad()
        logger.info(f"Searching Twitter for: {query}")
        # TODO: Implement actual search with twikit_ext
        return []  # Placeholder

    async def poll(self):
        """Main poll loop (timeline, mentions, etc., async)."""
        logger.info(f"Polling Twitter. Interval: {self.config.poll_interval}s")
        tweets = []
        if not self.config.search_enable:
            # Use timeline API, not search
            try:
                logger.info("Fetching home timeline via API (search disabled)")
                # Twikit_ext: use client.v11.onboarding_task or GQL if available
                # This is a placeholder for the correct timeline fetch method
                # Rotate proxy before fetching timeline/search
                await self.rotate_proxy_if_bad()
                result = await self.client.v11.onboarding_task(
                    guest_token=None, token=None, subtask_inputs=None, data=None
                )
                # TODO: Parse tweets from result
                tweets.extend(result.get('data', []) if isinstance(result, dict) else [])
            except Exception as e:
                logger.error(f"Failed to fetch home timeline: {e}")
        else:
            # Poll tweets from target users
            for user in self.config.target_users:
                try:
                    logger.info(f"Fetching tweets from {user}")
                    # Rotate proxy before search
                    await self.rotate_proxy_if_bad()
                    result = await self.client.search_tweet(query=f"from:{user}", product="Latest")
                    tweets.extend(result if isinstance(result, list) else getattr(result, 'data', []))
                except Exception as e:
                    logger.error(f"Failed to fetch tweets from {user}: {e}")
            # Poll mentions
            try:
                username = self.config.twitter_username
                logger.info(f"Fetching mentions for @{username}")
                # Rotate proxy before search
                await self.rotate_proxy_if_bad()
                result = await self.client.search_tweet(query=f"@{username}", product="Latest")
                tweets.extend(result if isinstance(result, list) else getattr(result, 'data', []))
            except Exception as e:
                logger.error(f"Failed to fetch mentions: {e}")
        return tweets

    async def schedule_loop(self):
        """Periodically generate and schedule tweets using Twitter's API."""
        from datetime import datetime, timedelta, timezone # Import here
        import random # Import here
        from xviolet.provider.llm import generate_tweet_text, generate_media_caption # Import here

        if not self.logged_in:
            if not await self.login():
                logger.error("Login failed, cannot start schedule loop.")
                return
        
        logger.info("Starting scheduled tweet loop...")
        total_media_tweets_this_cycle = max(1, int(self.config.max_scheduled_tweets * self.config.media_tweet_probability))

        while True:
            if not self.config.enable_twitter_post_generation:
                logger.info("Twitter post generation is disabled. Schedule loop sleeping.")
                await asyncio.sleep(self.config.poll_interval) # Sleep for poll interval if disabled
                continue

            try:
                now = datetime.now(timezone.utc)
                scheduled_count = 0
                media_tweet_count = 0

                # Determine media files available
                media_files = []
                if self.config.media_dir and os.path.exists(self.config.media_dir):
                    media_files = [os.path.join(self.config.media_dir, f) 
                                 for f in os.listdir(self.config.media_dir) 
                                 if os.path.isfile(os.path.join(self.config.media_dir, f))]
                    random.shuffle(media_files) # Shuffle to vary media selection
                
                total_media_to_schedule = min(len(media_files), total_media_tweets_this_cycle)

                for i in range(self.config.max_scheduled_tweets):
                    await self.rotate_proxy_if_bad() # Check proxy before each schedule attempt
                    
                    # Calculate execution time within the interval
                    delay_seconds = random.randint(self.config.post_interval_min, self.config.post_interval_max)
                    exec_at_dt = now + timedelta(seconds=delay_seconds)
                    
                    # --- Enforce Minimum Schedule Buffer --- 
                    current_timestamp = int(datetime.now(timezone.utc).timestamp())
                    target_timestamp = int(exec_at_dt.timestamp())
                    
                    if target_timestamp < current_timestamp + MIN_SCHEDULE_BUFFER_SECONDS:
                        logger.warning(f"Calculated schedule time {exec_at_dt} is too soon. Adjusting to {MIN_SCHEDULE_BUFFER_SECONDS}s buffer.")
                        target_timestamp = current_timestamp + MIN_SCHEDULE_BUFFER_SECONDS
                        adjusted_dt = datetime.fromtimestamp(target_timestamp, tz=timezone.utc)
                        logger.info(f"Adjusted schedule time: {adjusted_dt.isoformat()}")
                    else:
                        logger.info(f"Calculated schedule time: {exec_at_dt.isoformat()}")
                    # --- End Buffer Enforcement ---

                    # Decide if it's a media tweet
                    is_media_tweet = (media_tweet_count < total_media_to_schedule) and media_files

                    if is_media_tweet:
                        media_path = media_files[media_tweet_count]
                        logger.info(f"Scheduling media tweet {media_tweet_count + 1}/{total_media_to_schedule} using {os.path.basename(media_path)} for {datetime.fromtimestamp(target_timestamp, tz=timezone.utc).isoformat()}")
                        try:
                            media_id = await self.client.upload_media(media_path, wait_for_completion=True)
                            caption = await generate_media_caption(media_path) # LLM call
                            tweet_id = await self.client.create_scheduled_tweet(
                                scheduled_at=target_timestamp, # Use integer timestamp
                                text=caption,
                                media_ids=[media_id]
                            )
                            logger.info(f"Scheduled media tweet with ID: {tweet_id}, Media: {media_id}")
                            media_tweet_count += 1
                            scheduled_count += 1
                        except Exception as e:
                            logger.error(f"Failed to schedule media tweet with {os.path.basename(media_path)}: {e}")
                            # Optionally remove or mark the media file as failed
                    else:
                        # Schedule text tweet
                        logger.info(f"Scheduling text tweet for {datetime.fromtimestamp(target_timestamp, tz=timezone.utc).isoformat()}")
                        try:
                            tweet_text = await generate_tweet_text() # LLM call
                            tweet_id = await self.client.create_scheduled_tweet(
                                scheduled_at=target_timestamp, # Use integer timestamp
                                text=tweet_text
                            )
                            logger.info(f"Scheduled text tweet with ID: {tweet_id}")
                            scheduled_count += 1
                        except Exception as e:
                            logger.error(f"Failed to schedule text tweet: {e}")

                logger.info(f"Finished scheduling cycle. Scheduled {scheduled_count} tweets ({media_tweet_count} media). Waiting...")
            
            except Exception as e:
                logger.exception(f"Error in schedule loop: {e}")

            # Wait before starting the next scheduling cycle
            wait_time = self.config.post_interval_min # Use min interval as base wait
            logger.info(f"Schedule loop waiting for {wait_time} seconds before next cycle.")
            await asyncio.sleep(wait_time)

    async def stop(self):
        pass

    async def run(self):
        await self.login()
        await asyncio.gather(
            self._poll_loop(),
            self.schedule_loop()
        )

    async def _poll_loop(self):
        while True:
            try:
                tweets = await self.poll()
                for tweet in tweets:
                    logger.info(f"Polled tweet: {tweet}")
            except Exception as e:
                logger.error(f"Error during poll loop: {e}")
            await asyncio.sleep(self.config.poll_interval)

# Example usage
if __name__ == "__main__":
    import asyncio
    logging.basicConfig(level=logging.INFO)
    client = TwitterClient()
    asyncio.run(client.run())
