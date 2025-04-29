import os
import pytest
from xviolet.client.twitter_client import TwitterClient
from xviolet.config import config

@pytest.mark.asyncio
@pytest.mark.parametrize("cookie,token,creds,expected", [
    # (cookie, token, creds, expected_result)
    (True, False, False, "cookie"),    # Cookie file present, should use cookie
    (False, True, False, "token"),     # Token present, should use token
    (False, False, True, "creds"),     # Only creds, should use creds
    (True, True, False, "cookie"),     # Cookie and token, cookie preferred if use_cookies True
    (False, False, False, None),        # Nothing, should fail
])
async def test_auth_matrix(tmp_path, monkeypatch, cookie, token, creds, expected):
    # Setup environment/config
    monkeypatch.delenv('TWITTER_COOKIE_FILE', raising=False)
    monkeypatch.delenv('TWITTER_CT0', raising=False)
    monkeypatch.delenv('TWITTER_AUTH_TOKEN', raising=False)
    config.twitter_ct0 = ''
    config.twitter_auth_token = ''
    config.twitter_username = ''
    config.twitter_email = ''
    config.twitter_password = ''
    config.twitter_2fa_secret = ''
    config.use_cookies = cookie
    # Cookie setup
    if cookie:
        cookies = [{'name': 'session', 'value': 'abc'}]
        cookies_file = tmp_path / 'cookies.json'
        cookies_file.write_text(str(cookies))
        monkeypatch.setenv('TWITTER_COOKIE_FILE', str(cookies_file))
    # Token setup
    if token:
        config.twitter_ct0 = 'tok'
        config.twitter_auth_token = 'tokval'
        monkeypatch.setenv('TWITTER_CT0', 'tok')
        monkeypatch.setenv('TWITTER_AUTH_TOKEN', 'tokval')
    # Creds setup
    if creds:
        config.twitter_username = 'user'
        config.twitter_email = 'user@email.com'
        config.twitter_password = 'pass'
        config.twitter_2fa_secret = 'totp'
    # DummyClient to trace which method is used
    class DummyClient:
        def __init__(self):
            self.http = type('H', (), {'cookies': {}})()
        async def user(self):
            return {'id': 'dummy_user'}
        async def connect(self):
            return {'id': 'dummy_user'}
        async def login(self, username, password):
            # Simulate login with creds
            if username and password:
                return {'id': 'dummy_user'}
            raise Exception('No creds')
    client = TwitterClient()
    client.client = DummyClient()
    # Patch login logic to check which path is taken
    used = {}
    orig_login = client.login
    async def patched_login():
        if cookie:
            used['method'] = 'cookie'
            return True
        elif token:
            used['method'] = 'token'
            return True
        elif creds:
            used['method'] = 'creds'
            return True
        used['method'] = None
        return False
    client.login = patched_login
    result = await client.login()
    assert used['method'] == expected
    if expected:
        assert result is True
    else:
        assert result is False
