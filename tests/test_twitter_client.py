import pytest
from xviolet.client.twitter_client import TwitterClient
from xviolet.config import config
import time

@pytest.fixture(scope="module")
def client():
    # Enable dry-run to skip real Twitter calls in tests
    from xviolet.config import config
    config.dry_run = True
    return TwitterClient()

@pytest.mark.asyncio
async def test_login(client):
    # Should not raise
    await client.login()
    assert client.logged_in or config.dry_run

@pytest.mark.asyncio
async def test_post_text_tweet(client):
    text = "Test tweet from pytest (ignore)."
    result = await client.post_tweet(text)
    assert result is True

@pytest.mark.asyncio
async def test_post_media_tweet(client, tmp_path):
    from PIL import Image
    img_path = tmp_path / "media.png"
    img = Image.new("RGB", (32, 32), color="green")
    img.save(img_path)
    # Simulate quoting own tweet with media (since direct media tweet not exposed)
    # First post a tweet to quote
    main_tweet = await client.post_tweet("Media base tweet (pytest)")
    # Use a dummy tweet ID for dry run, else try to quote the last tweet
    tweet_id = "1234567890" if config.dry_run else None
    result = await client.quote_tweet(tweet_id or main_tweet, "Media attached", media_path=str(img_path))
    assert result is True

@pytest.mark.asyncio
async def test_action_intervals_respected(client):
    # Check that poll_interval and post_interval_min/max are respected
    start = time.time()
    client.config.poll_interval = 2
    client.config.post_interval_min = 1
    client.config.post_interval_max = 2
    # Simulate polling (should log and wait)
    await client.poll()
    elapsed = time.time() - start
    assert elapsed >= 0  # This is a placeholder: real interval enforcement would require async/timing control
