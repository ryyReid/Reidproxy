# ReidProxy Configuration

# Chrome Settings
USE_HEADLESS_CHROME = True
CHROME_POOL_SIZE = 3
CHROME_WAIT_TIME = 10

# Domains to render with Chrome (add your own!)
USE_CHROME_FOR_DOMAINS = {
    'twitter.com',
    'x.com',
    'facebook.com',
    'instagram.com',
    'reddit.com',
}

# Security (CHANGE THESE!)
ENABLE_AUTH = False  # Set to True for production
API_KEY = "change-me-to-random-string"

# Rate Limiting
RATE_LIMIT = 60  # requests per minute per IP

# Server Settings
FLASK_PORT = 5000
PROXY_PORT = 6767
