"""
ReidProxy - Enhanced Version with Headless Chrome Support
A web proxy with JavaScript rendering capabilities using Selenium
"""

import socket
import threading
import select
import os
import re
from flask import Flask, request, Response, render_template_string, abort
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, quote_plus, unquote_plus, urlparse, parse_qs
import logging
from functools import wraps
import time
from collections import defaultdict

# Selenium imports for headless Chrome
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
import tempfile
import shutil

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
class Config:
    PROXY_HOST = "127.0.0.1"
    PROXY_PORT = 6767
    FLASK_HOST = "127.0.0.1"
    FLASK_PORT = 5000
    
    # Chrome/Selenium settings
    USE_HEADLESS_CHROME = True  # Enable/disable Chrome rendering
    CHROME_WAIT_TIME = 10  # Seconds to wait for page load
    CHROME_POOL_SIZE = 3  # Number of Chrome instances to keep ready
    
    # Triggers for using Chrome (instead of requests)
    USE_CHROME_FOR_DOMAINS = {
        # Add domains that require JavaScript
        'twitter.com', 'x.com',
        'facebook.com',
        'instagram.com',
        'reddit.com',
        'youtube.com'
    }
    
    # Security settings
    ENABLE_AUTH = False
    API_KEY = "your-secret-key-here"
    RATE_LIMIT = 2000
    
    # Domain filtering
    BLOCKED_DOMAINS = set(['malicious.com', 'spam.com'])
    ALLOWED_DOMAINS = set()
    
    # Timeouts
    REQUEST_TIMEOUT = 20
    SOCKET_TIMEOUT = 10


# ---------------- CHROME DRIVER POOL ----------------

class ChromeDriverPool:
    """Manages a pool of Chrome WebDriver instances for better performance"""
    
    def __init__(self, pool_size=3):
        self.pool_size = pool_size
        self.drivers = []
        self.lock = threading.Lock()
        self._initialize_pool()
    
    def _create_driver(self):
        """Create a new Chrome WebDriver instance"""
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        
        try:
            driver = webdriver.Chrome(options=chrome_options)
            driver.set_page_load_timeout(Config.CHROME_WAIT_TIME)
            logger.info("Created new Chrome driver instance")
            return driver
        except Exception as e:
            logger.error(f"Failed to create Chrome driver: {e}")
            return None
    
    def _initialize_pool(self):
        """Initialize the driver pool"""
        logger.info(f"Initializing Chrome driver pool with {self.pool_size} instances...")
        for i in range(self.pool_size):
            driver = self._create_driver()
            if driver:
                self.drivers.append(driver)
        logger.info(f"Chrome driver pool ready with {len(self.drivers)} instances")
    
    def get_driver(self):
        """Get a driver from the pool and verify it is alive"""
        with self.lock:
            while self.drivers:
                driver = self.drivers.pop()
                try:
                    # Quick check to see if driver is still responsive
                    driver.current_url
                    return driver
                except WebDriverException:
                    logger.warning("Found dead driver in pool, discarding.")
                    try:
                        driver.quit()
                    except:
                        pass
            
            # Pool is empty or all drivers were dead, create a new one
            logger.warning("Driver pool empty (or dead), creating new instance")
            return self._create_driver()
    
    def return_driver(self, driver):
        """Return a driver to the pool"""
        with self.lock:
            if len(self.drivers) < self.pool_size:
                self.drivers.append(driver)
            else:
                # Pool is full, quit this driver
                try:
                    driver.quit()
                except:
                    pass
    
    def shutdown(self):
        """Shutdown all drivers in the pool"""
        logger.info("Shutting down Chrome driver pool...")
        with self.lock:
            for driver in self.drivers:
                try:
                    driver.quit()
                except:
                    pass
            self.drivers.clear()


# Initialize Chrome driver pool if enabled
chrome_pool = None
if Config.USE_HEADLESS_CHROME:
    chrome_pool = ChromeDriverPool(Config.CHROME_POOL_SIZE)


# ---------------- CHROME RENDERING ----------------

def fetch_with_chrome(url):
    """
    Fetch a URL using headless Chrome for JavaScript rendering
    Returns: (html_content, status_code, content_type)
    """
    if not chrome_pool:
        raise Exception("Chrome driver pool not initialized")
    
    driver = chrome_pool.get_driver()
    if not driver:
        raise Exception("Failed to get Chrome driver")
    
    try:
        logger.info(f"Fetching with Chrome: {url}")
        
        # Navigate to URL
        driver.get(url)
        
        # Wait for page to load (wait for body element)
        try:
            WebDriverWait(driver, Config.CHROME_WAIT_TIME).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
        except TimeoutException:
            logger.warning(f"Timeout waiting for page load: {url}")
        
        # Optional: Wait for specific elements or AJAX to complete
        time.sleep(1)  # Give dynamic content time to render
        
        # Get the rendered HTML
        html_content = driver.page_source
        
        # Get final URL (in case of redirects)
        final_url = driver.current_url
        
        chrome_pool.return_driver(driver)
        
        return html_content, 200, "text/html", final_url
        
    except WebDriverException as e:
        logger.error(f"Chrome WebDriver error: {e}")
        try:
            chrome_pool.return_driver(driver)
        except:
            pass
        raise Exception(f"Chrome rendering failed: {str(e)}")
    
    except Exception as e:
        logger.error(f"Chrome fetch error: {e}")
        try:
            chrome_pool.return_driver(driver)
        except:
            pass
        raise


def fetch_with_requests(url):
    """
    Fetch a URL using requests library (no JavaScript)
    Returns: (content, status_code, content_type, final_url)
    """
    PROXY_BACKEND = {
        "http": f"http://{Config.PROXY_HOST}:{Config.PROXY_PORT}",
        "https": f"http://{Config.PROXY_HOST}:{Config.PROXY_PORT}"
    }
    
    resp = requests.get(
        url,
        stream=True,
        timeout=Config.REQUEST_TIMEOUT,
        proxies=PROXY_BACKEND,
        allow_redirects=True,
        headers={'User-Agent': 'Mozilla/5.0 (compatible; ReidProxy/2.0)'}
    )
    resp.raise_for_status()
    
    content_type = resp.headers.get("content-type", "").lower()
    
    if "text/html" in content_type:
        content = resp.content.decode("utf-8", errors="replace")
    else:
        content = resp.content
    
    return content, resp.status_code, content_type, resp.url


def should_use_chrome(url):
    """Determine if URL should be rendered with Chrome"""
    if not Config.USE_HEADLESS_CHROME:
        return False
    
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    
    # Remove 'www.' prefix
    if domain.startswith('www.'):
        domain = domain[4:]
    
    # Check if domain is in the Chrome list
    for chrome_domain in Config.USE_CHROME_FOR_DOMAINS:
        if chrome_domain in domain:
            return True
    
    return False


# ---------------- RATE LIMITING ----------------

class RateLimiter:
    def __init__(self, max_requests=60, window=60):
        self.max_requests = max_requests
        self.window = window
        self.requests = defaultdict(list)
    
    def is_allowed(self, identifier):
        now = time.time()
        self.requests[identifier] = [
            req_time for req_time in self.requests[identifier]
            if now - req_time < self.window
        ]
        
        if len(self.requests[identifier]) >= self.max_requests:
            return False
        
        self.requests[identifier].append(now)
        return True


rate_limiter = RateLimiter(Config.RATE_LIMIT)


# ---------------- SECURITY HELPERS ----------------

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not Config.ENABLE_AUTH:
            return f(*args, **kwargs)
        
        api_key = request.headers.get('X-API-Key') or request.args.get('api_key')
        if api_key != Config.API_KEY:
            abort(401, "Unauthorized: Invalid or missing API key")
        return f(*args, **kwargs)
    return decorated


def is_domain_allowed(url):
    try:
        domain = urlparse(url).netloc.lower()
        if ':' in domain:
            domain = domain.split(':')[0]
        
        if domain in Config.BLOCKED_DOMAINS:
            logger.warning(f"Blocked domain: {domain}")
            return False
        
        if Config.ALLOWED_DOMAINS and domain not in Config.ALLOWED_DOMAINS:
            logger.warning(f"Domain not in whitelist: {domain}")
            return False
        
        return True
    except Exception as e:
        logger.error(f"Domain validation error: {e}")
        return False


# ---------------- TCP PROXY ----------------

def handle_client(client_socket):
    try:
        request_data = client_socket.recv(1024)
        if not request_data:
            client_socket.close()
            return

        first_line = request_data.split(b'\n')[0]
        method = first_line.split(b' ')[0]

        if method == b'CONNECT':
            handle_https_request(client_socket, request_data)
        else:
            handle_http_request(client_socket, request_data)
    except Exception as e:
        logger.error(f"Client handling error: {e}")
    finally:
        try:
            client_socket.close()
        except:
            pass


def handle_http_request(client_socket, request_data):
    try:
        first_line = request_data.decode('ascii', errors='ignore').split('\n')[0]
        parts = first_line.split(' ')
        
        if len(parts) < 3:
            raise ValueError("Invalid HTTP request")
        
        method, url, _ = parts
        http_pos = url.find("://")
        temp = url if http_pos == -1 else url[http_pos + 3:]

        port_pos = temp.find(":")
        webserver_pos = temp.find("/")
        if webserver_pos == -1:
            webserver_pos = len(temp)

        if port_pos == -1 or webserver_pos < port_pos:
            port = 80
            webserver = temp[:webserver_pos]
        else:
            webserver = temp[:port_pos]
            port = int(temp[port_pos + 1:webserver_pos])

        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(Config.SOCKET_TIMEOUT)
        s.connect((webserver, port))
        s.sendall(request_data)

        while True:
            data = s.recv(4096)
            if not data:
                break
            client_socket.sendall(data)

        s.close()
    except Exception as e:
        logger.error(f"HTTP proxy error: {e}")
    finally:
        try:
            client_socket.close()
        except:
            pass


def handle_https_request(client_socket, request_data):
    s = None
    try:
        first_line = request_data.split(b'\n')[0]
        parts = first_line.split(b' ')
        
        if len(parts) < 2:
            raise ValueError("Invalid CONNECT request")
        
        host_port = parts[1]
        if b':' not in host_port:
            raise ValueError("Invalid host:port format")
        
        host, port = host_port.split(b':')
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(Config.SOCKET_TIMEOUT)
        s.connect((host.decode(), int(port)))
        
        client_socket.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        sockets = [client_socket, s]
        
        while True:
            try:
                readable, _, exceptional = select.select(sockets, [], sockets, Config.SOCKET_TIMEOUT)
                
                if exceptional:
                    break
                
                if not readable:
                    continue
                
                for sock in readable:
                    data = sock.recv(4096)
                    if not data:
                        return
                    
                    other_sock = s if sock is client_socket else client_socket
                    other_sock.sendall(data)
                    
            except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
                logger.debug("Connection closed by peer")
                break
                
    except Exception as e:
        logger.error(f"HTTPS proxy error: {e}")
    finally:
        try:
            client_socket.close()
        except:
            pass
        if s:
            try:
                s.close()
            except:
                pass


def start_proxy_server(host, port):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((host, port))
    server.listen(5)
    logger.info(f"TCP Proxy listening on {host}:{port}")

    while True:
        try:
            client_socket, addr = server.accept()
            logger.debug(f"Connection from {addr}")
            
            threading.Thread(
                target=handle_client,
                args=(client_socket,),
                daemon=True
            ).start()
        except Exception as e:
            logger.error(f"Server accept error: {e}")


# ---------------- FLASK WEB PROXY ----------------

app = Flask(__name__)


def normalize_url(url):
    """
    Normalize URLs to fix common issues:
    - Replace backslashes with forward slashes
    - Handle spaces properly
    - Remove duplicate slashes
    """
    if not url:
        return url
    
    # Replace backslashes with forward slashes
    url = url.replace('\\', '/')
    
    # Remove duplicate slashes (except after http:// or https://)
    url = re.sub(r'(?<!:)//+', '/', url)
    
    return url


def rewrite_html(base_url, html_text):
    """Rewrite HTML links to route through proxy"""
    try:
        soup = BeautifulSoup(html_text, "html.parser")

        def proxify(raw_url):
            if not raw_url:
                return raw_url
            raw_url = raw_url.strip()
            
            skip_prefixes = ("#", "mailto:", "javascript:", "data:", "tel:", "/proxy?url=")
            if raw_url.startswith(skip_prefixes):
                return raw_url
            
            # Normalize the URL (fix backslashes, etc.)
            raw_url = normalize_url(raw_url)
            
            absolute = urljoin(base_url, raw_url)
            
            # Normalize again after joining
            absolute = normalize_url(absolute)
            
            return f"/proxy?url={quote_plus(absolute)}"

        for tag in soup.find_all(href=True):
            tag["href"] = proxify(tag["href"])
        
        for tag in soup.find_all(src=True):
            tag["src"] = proxify(tag["src"])
        
        for tag in soup.find_all("form", action=True):
            tag["action"] = proxify(tag["action"])

        return str(soup)
    except Exception as e:
        logger.error(f"HTML rewrite error: {e}")
        return html_text


@app.route("/")
def index():
    """Serve the main page"""
    games_html_path = os.path.join(os.path.dirname(__file__), "games.html")
    try:
        with open(games_html_path, "r", encoding="utf-8") as f:
            content = f.read()
        return render_template_string(content)
    except FileNotFoundError:
        logger.error("games.html not found")
        return "games.html not found", 404


@app.route("/health")
def health():
    """Health check endpoint"""
    status = {
        "status": "ok",
        "proxy": "running",
        "chrome_enabled": Config.USE_HEADLESS_CHROME
    }
    if chrome_pool:
        status["chrome_pool_size"] = len(chrome_pool.drivers)
    return status, 200


@app.route('/<path:path>')
def catch_all_assets(path):
    """
    Dynamically route relative asset requests using the HTTP Referer header.
    This replaces the hardcoded game URL and works for any proxied site.
    """
    referer = request.headers.get('Referer')
    
    if not referer:
        logger.warning(f"Orphaned asset request (No Referer): /{path}")
        abort(404)

    # We extract the 'url' parameter from the referer's query string
    parsed_referer = urlparse(referer)
    query_params = parse_qs(parsed_referer.query)
    
    if 'url' not in query_params:
        logger.warning(f"Referer missing 'url' parameter: {referer}")
        abort(404)
        
    original_base_url = query_params['url'][0]
    
    # Ensure the base URL is treated correctly as a directory for urljoin
    if not original_base_url.endswith('/') and not '.' in original_base_url.split('/')[-1]:
        original_base_url += '/'
    elif not original_base_url.endswith('/'):
         # If it's a file like index.html, get the parent directory
         parsed_base = urlparse(original_base_url)
         base_path = os.path.dirname(parsed_base.path)
         if not base_path.endswith('/'):
             base_path += '/'
         original_base_url = f"{parsed_base.scheme}://{parsed_base.netloc}{base_path}"

    target_url = urljoin(original_base_url, path)
    
    logger.info(f"Dynamic Asset Routing: /{path} -> {target_url}")
    
    try:
        resp = requests.get(target_url, stream=True, timeout=Config.REQUEST_TIMEOUT)
        resp.raise_for_status()
        
        # Exclude hop-by-hop headers before returning the proxy response
        excluded_headers = ['content-encoding', 'content-length', 'transfer-encoding', 'connection']
        headers = [(name, value) for (name, value) in resp.raw.headers.items()
                   if name.lower() not in excluded_headers]
        
        return Response(resp.content, resp.status_code, headers)
    except requests.exceptions.RequestException as e:
        logger.warning(f"Asset not found or connection failed: {target_url} - {e}")
        abort(404)


@app.route("/performance")
def performance_dummy():
    return "", 204


@app.route("/proxy", methods=["GET", "POST"])
@require_auth
def proxy():
    """Main proxy endpoint with Chrome support"""
    # Rate limiting
    client_ip = request.remote_addr
    if not rate_limiter.is_allowed(client_ip):
        abort(429, "Rate limit exceeded")
    
    # Get URL
    if request.method == "POST" and "url" in request.form:
        url = request.form["url"]
    elif "url" in request.args:
        url = request.args.get("url")
    elif "q" in request.args:
        query = request.args.get('q')
        url = f"https://www.google.com/search?q={quote_plus(query)}"
    else:
        abort(400, "No URL provided")

    url = unquote_plus(url)
    
    # Normalize URL - fix backslashes and path issues
    url = normalize_url(url)
    
    if not urlparse(url).scheme:
        url = "http://" + url
    
    # Security check
    if not is_domain_allowed(url):
        abort(403, "Access to this domain is not allowed")
    
    logger.info(f"Proxying: {url}")
    
    try:
        # Decide whether to use Chrome or requests
        use_chrome = should_use_chrome(url)
        
        if use_chrome:
            logger.info(f"Using Chrome for: {url}")
            html, status_code, content_type, final_url = fetch_with_chrome(url)
        else:
            logger.info(f"Using requests for: {url}")
            content, status_code, content_type, final_url = fetch_with_requests(url)
            html = content if isinstance(content, str) else content.decode('utf-8', errors='replace')
        
        # Rewrite HTML content
        if "text/html" in content_type:
            parsed = urlparse(final_url)
            
            path = parsed.path
            if path and not path.endswith('/'):
                path = os.path.dirname(path)
            if not path.endswith('/'):
                path += '/'
            
            base_url = f"{parsed.scheme}://{parsed.netloc}{path}"
            
            return Response(
                rewrite_html(base_url, html),
                content_type="text/html; charset=utf-8"
            )
        
        # Return non-HTML content as-is
        return Response(html if isinstance(html, bytes) else html.encode(), content_type=content_type)

    except requests.Timeout:
        abort(504, "Request timeout")
    except requests.RequestException as e:
        logger.error(f"Proxy error: {e}")
        abort(502, f"Proxy error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        abort(500, f"Internal error: {str(e)}")


# ---------------- ENTRY POINT ----------------

def main():
    """Start both proxy server and Flask app"""
    logger.info("Starting ReidProxy with Chrome support...")
    
    # Start TCP proxy
    proxy_thread = threading.Thread(
        target=start_proxy_server,
        args=(Config.PROXY_HOST, Config.PROXY_PORT),
        daemon=True
    )
    proxy_thread.start()
    
    time.sleep(0.5)
    
    # Start Flask
    logger.info(f"Web interface on http://{Config.FLASK_HOST}:{Config.FLASK_PORT}")
    if Config.USE_HEADLESS_CHROME:
        logger.info(f"Chrome rendering enabled for {len(Config.USE_CHROME_FOR_DOMAINS)} domains")
    
    try:
        app.run(
            host=Config.FLASK_HOST,
            port=Config.FLASK_PORT,
            threaded=True,
            use_reloader=False,
            debug=False
        )
    finally:
        # Cleanup Chrome drivers
        if chrome_pool:
            chrome_pool.shutdown()


if __name__ == "__main__":
    main()