import os
import json
import pytest
import tempfile

from xviolet.client.twitter_client import TwitterClient
from xviolet.config import config

# Dummy client to simulate twikit_ext.Client
class DummyClient:
    def __init__(self):
        self.http = type('H', (), {'cookies': {}})()
    async def user(self):
        # Simulate user fetch success
        return {'id': 'dummy_user'}
    async def connect(self):
        # Simulate credential-connect success
        return {'id': 'dummy_user'}

@pytest.fixture(autouse=True)
def reset_config(monkeypatch):
    # Reset config attributes for tests
    config.twitter_ct0 = os.getenv('TWITTER_CT0', '')
    config.twitter_auth_token = os.getenv('TWITTER_AUTH_TOKEN', '')
    config.use_cookies = True
    yield
    # Clean up env vars
    monkeypatch.delenv('TWITTER_COOKIE_FILE', raising=False)
    monkeypatch.delenv('TWITTER_CT0', raising=False)
    monkeypatch.delenv('TWITTER_AUTH_TOKEN', raising=False)

@pytest.mark.asyncio
async def test_cookie_first_login(tmp_path, monkeypatch):
    # Write a valid cookies.json for cookie-first
    cookies = [{'name': 'session', 'value': 'abc'}]
    cookies_file = tmp_path / 'cookies.json'
    cookies_file.write_text(json.dumps(cookies))
    monkeypatch.setenv('TWITTER_COOKIE_FILE', str(cookies_file))
    config.use_cookies = True

    client = TwitterClient()
    # Inject dummy backend
    client.client = DummyClient()
    success = await client.login()
    assert success is True
    assert client.logged_in is True
    # Cookies loaded into http.cookies
    assert client.client.http.cookies.get('session') == 'abc'

@pytest.mark.asyncio
async def test_token_auth_login(monkeypatch):
    # No cookies, use token auth
    monkeypatch.delenv('TWITTER_COOKIE_FILE', raising=False)
    monkeypatch.setenv('TWITTER_CT0', 'tok')
    monkeypatch.setenv('TWITTER_AUTH_TOKEN', 'tokval')
    config.twitter_ct0 = 'tok'
    config.twitter_auth_token = 'tokval'
    config.use_cookies = False

    client = TwitterClient()
    client.client = DummyClient()
    success = await client.login()
    assert success is True
    assert client.logged_in is True

@pytest.mark.asyncio
async def test_credential_login_fallback(monkeypatch):
    # No cookies file, no token auth => credentials
    monkeypatch.delenv('TWITTER_COOKIE_FILE', raising=False)
    config.twitter_ct0 = ''
    config.twitter_auth_token = ''
    config.use_cookies = True

    client = TwitterClient()
    client.client = DummyClient()
    success = await client.login()
    assert success is True
    assert client.logged_in is True
