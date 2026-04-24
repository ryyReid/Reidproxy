import pytest
from unittest.mock import MagicMock, patch
import sys
import os

# Mock all dependencies that might be missing
for module in ['flask', 'requests', 'bs4', 'selenium', 'selenium.webdriver',
               'selenium.webdriver.chrome.options', 'selenium.webdriver.chrome.service',
               'selenium.webdriver.common.by', 'selenium.webdriver.support.ui',
               'selenium.webdriver.support', 'selenium.common.exceptions']:
    sys.modules[module] = MagicMock()

# Mock specific attributes needed for imports and decorators
import flask
flask.Flask = MagicMock()
mock_app = MagicMock()
flask.Flask.return_value = mock_app
# Mock decorators
mock_app.route.return_value = lambda f: f
flask.request = MagicMock()
flask.Response = MagicMock
flask.render_template_string = MagicMock
flask.abort = MagicMock

# Mock BeautifulSoup
import bs4
bs4.BeautifulSoup = MagicMock()

# Add 3.1 to sys.path
sys.path.append(os.path.join(os.getcwd(), '3.1'))

# Now import the components we want to test
import app_with_chrome
from app_with_chrome import normalize_url, should_use_chrome, is_domain_allowed, rewrite_html, RateLimiter, Config

def test_normalize_url():
    assert normalize_url("http://example.com\\path") == "http://example.com/path"
    assert normalize_url("http://example.com//path") == "http://example.com/path"
    assert normalize_url("https://example.com/path//subpath") == "https://example.com/path/subpath"
    assert normalize_url(None) is None

def test_should_use_chrome():
    original_use = Config.USE_HEADLESS_CHROME
    original_domains = Config.USE_CHROME_FOR_DOMAINS

    Config.USE_HEADLESS_CHROME = True
    Config.USE_CHROME_FOR_DOMAINS = {'twitter.com', 'x.com'}

    assert should_use_chrome("https://twitter.com/home") is True
    assert should_use_chrome("https://www.twitter.com/home") is True
    assert should_use_chrome("https://google.com") is False

    Config.USE_HEADLESS_CHROME = False
    assert should_use_chrome("https://twitter.com/home") is False

    Config.USE_HEADLESS_CHROME = original_use
    Config.USE_CHROME_FOR_DOMAINS = original_domains

def test_is_domain_allowed():
    Config.BLOCKED_DOMAINS = {'malicious.com'}
    Config.ALLOWED_DOMAINS = set()

    assert is_domain_allowed("https://google.com") is True
    assert is_domain_allowed("https://malicious.com") is False

    Config.ALLOWED_DOMAINS = {'trusted.com'}
    assert is_domain_allowed("https://trusted.com") is True
    assert is_domain_allowed("https://google.com") is False

    Config.ALLOWED_DOMAINS = set()

def test_rate_limiter():
    limiter = RateLimiter(max_requests=2, window=60)
    assert limiter.is_allowed("user1") is True
    assert limiter.is_allowed("user1") is True
    assert limiter.is_allowed("user1") is False
    assert limiter.is_allowed("user2") is True

@patch('app_with_chrome.BeautifulSoup')
def test_rewrite_html(mock_bs):
    base_url = "https://example.com/"
    html = '<html></html>'
    rewrite_html(base_url, html)
    mock_bs.assert_called_once()
