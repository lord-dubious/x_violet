import pytest
import asyncio
import time
from pathlib import Path
from xviolet.agent import Agent
from xviolet.config import config

class DummyTwitter:
    def __init__(self):
        self.login_calls = 0
        self.post_calls = 0
        self.post_media_calls = 0
    async def login(self):
        self.login_calls += 1
        return True
    async def post_tweet(self, text):
        self.post_calls += 1
    async def post_tweet_with_media(self, text, media_path):
        self.post_media_calls += 1

class DummyLLM:
    def __init__(self):
        self.generate_calls = []
        self.analyze_calls = []
    def generate_text(self, prompt, context_type="chat", **kwargs):
        self.generate_calls.append((prompt, context_type))
        return "text"
    def analyze_image(self, image_path, context_type="post", **kwargs):
        self.analyze_calls.append((image_path, context_type))
        return "[analysis]"

def test_agent_schedule_media_and_action(monkeypatch, tmp_path):
    # Configure for test
    config.enable_action_processing = True
    config.enable_twitter_post_generation = True
    config.action_interval = 0         # immediate actions
    config.post_interval_min = 0       # immediate posts
    config.post_interval_max = 0
    config.loop_sleep_interval_min = 0 # no waiting
    config.loop_sleep_interval_max = 0
    config.media_tweet_probability = 1.0  # always media
    config.media_dir = str(tmp_path)
    # Create dummy media
    media_file = tmp_path / "img.png"
    media_file.write_bytes(b'data')
    # Initialize agent and inject dummies
    agent = Agent()
    # Stub run_once to count actions
    agent.run_once_called = 0
    def stub_run_once():
        agent.run_once_called += 1
    agent.run_once = stub_run_once
    dummy_twitter = DummyTwitter()
    dummy_llm = DummyLLM()
    agent.twitter = dummy_twitter
    agent.llm = dummy_llm
    # Patch sleep to avoid real delay
    monkeypatch.setattr(time, 'sleep', lambda x: None)
    # Run limited cycles
    agent.run(max_cycles=4)
    # Since max_cycles breaks before 4th loop processing, expect 3 loops
    assert agent.run_once_called == 3
    # login called each cycle
    assert dummy_twitter.login_calls == 3
    # media analysis and media tweets
    assert len(dummy_llm.analyze_calls) == 3
    assert dummy_twitter.post_media_calls == 3

@pytest.mark.parametrize("prob_text, expected_post, expected_media", [
    (0.0, 3, 0),  # always text
    (1.0, 0, 3),  # always media
])
def test_agent_text_vs_media(monkeypatch, tmp_path, prob_text, expected_post, expected_media):
    # Configure for test
    config.enable_action_processing = False  # skip actions
    config.enable_twitter_post_generation = True
    config.action_interval = 0
    config.post_interval_min = 0
    config.post_interval_max = 0
    config.loop_sleep_interval_min = 0
    config.loop_sleep_interval_max = 0
    config.media_tweet_probability = prob_text
    config.media_dir = str(tmp_path)
    # Create dummy media
    media_file = tmp_path / "img.jpg"
    media_file.write_bytes(b'')
    agent = Agent()
    # Stub run_once (should not be called)
    agent.run_once = lambda: (_ for _ in ()).throw(AssertionError("run_once should not be called"))
    dummy_twitter = DummyTwitter()
    dummy_llm = DummyLLM()
    agent.twitter = dummy_twitter
    agent.llm = dummy_llm
    monkeypatch.setattr(time, 'sleep', lambda x: None)
    agent.run(max_cycles=4)
    # Check posts
    assert dummy_twitter.post_calls == expected_post
    assert dummy_twitter.post_media_calls == expected_media
    # Ensure LLM generate or analyze used
    if expected_media:
        assert len(dummy_llm.analyze_calls) == expected_media
    else:
        assert len(dummy_llm.generate_calls) == expected_post
