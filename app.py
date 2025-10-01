import socket
import threading
import select
import os
from flask import Flask, request, Response, render_template_string
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, quote_plus, unquote_plus, urlparse
import logging
import re
# import playwright.sync_api 
# from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# --- TCP Proxy (from proxy.py) ---

def handle_client(client_socket):
    try:
        request = client_socket.recv(1024)
        if not request:
            client_socket.close()
            return

        first_line = request.split(b'\n')[0]
        try:
            method = first_line.split(b' ')[0]
        except IndexError:
            client_socket.close()
            return

        if method == b'CONNECT':
            handle_https_request(client_socket, request)
        else:
            handle_http_request(client_socket, request)
    except Exception as e:
        logging.error(f"[*] Client handling exception: {e}")
        client_socket.close()

def handle_http_request(client_socket, request):
    try:
        try:
            first_line = request.decode('ascii').split('\n')[0]
            parts = first_line.split(' ')
            if len(parts) != 3:
                client_socket.close()
                return
            method, url, version = parts
        except (UnicodeDecodeError, ValueError):
            client_socket.close()
            return

        http_pos = url.find("://")
        if http_pos == -1:
            temp = url
        else:
            temp = url[(http_pos + 3):]

        port_pos = temp.find(":")
        webserver_pos = temp.find("/")
        if webserver_pos == -1:
            webserver_pos = len(temp)

        webserver = ""
        port = -1
        if port_pos == -1 or webserver_pos < port_pos:
            port = 80
            webserver = temp[:webserver_pos]
        else:
            try:
                port = int(temp[(port_pos + 1):][:webserver_pos - port_pos - 1])
                webserver = temp[:port_pos]
            except ValueError:
                client_socket.close()
                return

        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((webserver, port))
        s.send(request)

        while True:
            data = s.recv(4096)
            if len(data) > 0:
                client_socket.send(data)
            else:
                break
        s.close()
        client_socket.close()
    except Exception as e:
        logging.error(f"[*] HTTP Exception: {e}")
        client_socket.close()

def handle_https_request(client_socket, request):
    try:
        first_line = request.split(b'\n')[0]
        host_port = first_line.split(b' ')[1]
        host, port = host_port.split(b':')

        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((host, int(port)))
        client_socket.send(b"HTTP/1.1 200 OK\r\n\r\n")

        sockets = [client_socket, s]
        while True:
            readable, writable, exceptional = select.select(sockets, [], sockets, 10)
            if exceptional:
                break
            if not readable and not writable:
                continue

            for sock in readable:
                data = sock.recv(4096)
                if not data:
                    break
                if sock is client_socket:
                    s.sendall(data)
                else:
                    client_socket.sendall(data)
            else:
                continue
            break

    except Exception as e:
        logging.error(f"[*] HTTPS Exception: {e}")
        pass
    finally:
        client_socket.close()
        s.close()

def start_proxy_server(local_host="127.0.0.1", local_port=6767):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((local_host, local_port))
    server.listen(5)
    logging.info(f"[*] TCP Proxy listening on {local_host}:{local_port}")

    while True:
        client_socket, addr = server.accept()
        logging.info(f"[*] Accepted connection from {addr[0]}:{addr[1]}")

        client_handler = threading.Thread(target=handle_client, args=(client_socket,))
        client_handler.start()

# --- Flask Web Proxy (from web_proxy.py) ---

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

PROXY_BACKEND = {
    "http": "http://127.0.0.1:6767",
    "https": "http://127.0.0.1:6767"
}

# To enable Playwright, uncomment the following lines and install playwright
# from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
# _playwright = sync_playwright().start()
# _browser = _playwright.chromium.launch(headless=True, proxy={"server": "http://127.0.0.1:6767"})
# _context = _browser.new_context()

def fetch_with_requests(url, timeout=15):
    """Return HTML from Requests (string) or raise."""
    response = requests.get(url, timeout=timeout, proxies=PROXY_BACKEND)
    response.raise_for_status()
    return response.text

def rewrite_html(base_url, html_text):
    soup = BeautifulSoup(html_text, "html.parser")

    def proxify(raw_url, current_base_url=base_url):
        if not raw_url:
            return raw_url
        raw_url = raw_url.strip()
        if raw_url.startswith("#") or raw_url.startswith("mailto:") or raw_url.startswith("javascript:") or raw_url.startswith("data:"):
            return raw_url
        absolute = urljoin(current_base_url, raw_url)
        return f'/proxy?url={quote_plus(absolute)}'

    for tag in soup.find_all(href=True):
        tag['href'] = proxify(tag['href'])

    for tag in soup.find_all(src=True):
        tag['src'] = proxify(tag['src'])

    for tag in soup.find_all(attrs={"srcset": True}):
        raw = tag['srcset']
        parts = []
        for piece in raw.split(","):
            piece = piece.strip()
            if not piece:
                continue
            tokens = piece.split()
            url_part = tokens[0]
            rest = " ".join(tokens[1:]) if len(tokens) > 1 else ""
            newurl = proxify(url_part)
            parts.append(f"{newurl} {rest}".strip())
        tag['srcset'] = ", ".join(parts)

    for tag in soup.find_all("form"): 
        if tag.has_attr('action'):
            tag['action'] = proxify(tag['action'])

    # Rewrite CSS url() in style tags
    for style_tag in soup.find_all("style"):
        if style_tag.string:
            style_tag.string = re.sub(r"url\((['\"]?(.*?)[\'\"]?)\)", lambda match: f'url({proxify(match.group(1))})', style_tag.string)

    # Rewrite inline style attributes
    for tag in soup.find_all(style=True):
        tag['style'] = re.sub(r"url\((['\"]?(.*?)[\'\"]?)\)", lambda match: f'url({proxify(match.group(1))})', tag['style'])

    for base in soup.find_all("base"):
        base.decompose()

    # Inject a script to handle history and location changes
    injection_script = soup.new_tag("script")
    injection_script.string = """
        (function() {
            // Disable service worker registration
            if ('serviceWorker' in navigator) {
                Object.defineProperty(navigator, 'serviceWorker', {
                    get: function() { return undefined; }
                });
            }

            const proxify = (rawUrl) => {
                if (!rawUrl) return rawUrl;
                const absolute = new URL(rawUrl, '""" + base_url + """');
                return `/proxy?url=${encodeURIComponent(absolute.href)}`;
            };

            const originalPushState = history.pushState;
            history.pushState = function(state, title, url) {
                if (url && typeof url === 'string') {
                    originalPushState.apply(this, [state, title, proxify(url)]);
                } else {
                    originalPushState.apply(this, [state, title, url]);
                }
            };

            const originalReplaceState = history.replaceState;
            history.replaceState = function(state, title, url) {
                if (url && typeof url === 'string') {
                    originalReplaceState.apply(this, [state, title, proxify(url)]);
                } else {
                    originalReplaceState.apply(this, [state, title, url]);
                }
            };

            // Intercept direct window.location assignments
            Object.defineProperty(window, 'location', {
                get: function() { return originalLocation; },
                set: function(newValue) {
                    if (typeof newValue === 'string') {
                        originalLocation.href = proxify(newValue);
                    } else {
                        originalLocation = newValue;
                    }
                }
            });

            // Intercept window.location.href assignments
            const originalLocation = window.location;
            Object.defineProperty(originalLocation, 'href', {
                get: function() { return originalLocation.href; },
                set: function(newValue) {
                    originalLocation.href = proxify(newValue);
                }
            });

            // Intercept form submissions that might not have an action attribute
            document.querySelectorAll('form').forEach(form => {
                form.addEventListener('submit', function(e) {
                    // If the form doesn't have an action, it submits to the current URL
                    if (!form.action) {
                        e.preventDefault();
                        const formData = new FormData(form);
                        const params = new URLSearchParams();
                        for (const pair of formData.entries()) {
                            params.append(pair[0], pair[1]);
                        }
                        const currentUrl = new URL(window.location.href);
                        currentUrl.search = params.toString();
                        window.location.href = proxify(currentUrl.href);
                    }
                });
            });

        })();
    """
    if soup.head:
        soup.head.insert(0, injection_script)
    else:
        soup.insert(0, injection_script)

    return str(soup)

@app.route("/", methods=["GET"])
def index():
    games_html_path = os.path.join(os.path.dirname(__file__), 'games.html')
    with open(games_html_path, 'r', encoding='utf-8') as f:
        games_content = f.read()

    soup = BeautifulSoup(games_content, "html.parser")

    def proxify_home_link(relative_path):
        # Base URL for the home screen itself
        base_url_for_home = "http://127.0.0.1:8080/"
        # Construct the absolute URL relative to our Flask server's root
        absolute_url = urljoin(base_url_for_home, relative_path)
        # Then, wrap it in our proxy URL format
        return f"/proxy?url={quote_plus(absolute_url)}"

    # For <a> tags
    for tag in soup.find_all("a", href=True):
        # Only rewrite external links to go through the proxy
        if tag['href'].startswith(('http://', 'https://')):
            tag['href'] = proxify_home_link(tag['href'])
        # For internal relative links, ensure they are absolute paths relative to our Flask server
        elif not tag['href'].startswith(('/', '#')): # Not root-relative or fragment
            tag['href'] = urljoin("/", tag['href']) # Make it root-relative
        # Root-relative links like /storage/js/cloak.js are left as is

    # For <script> tags with src
    for tag in soup.find_all("script", src=True):
        if tag['src'].startswith(('http://', 'https://')):
            tag['src'] = proxify_home_link(tag['src'])
        elif not tag['src'].startswith('/'):
            tag['src'] = urljoin("/", tag['src'])

    # For <img> tags with src
    for tag in soup.find_all("img", src=True):
        if tag['src'].startswith(('http://', 'https://')):
            tag['src'] = proxify_home_link(tag['src'])
        elif not tag['src'].startswith('/'):
            tag['src'] = urljoin("/", tag['src'])

    # For <link> tags (CSS) with href
    for tag in soup.find_all("link", href=True):
        if tag['href'].startswith(('http://', 'https://')):
            tag['href'] = proxify_home_link(tag['href'])
        elif not tag['href'].startswith('/'):
            tag['href'] = urljoin("/", tag['href'])

    return render_template_string(str(soup))

@app.route("/proxy", methods=["GET", "POST"])
def proxy():
    url = None
    if request.method == "POST" and "url" in request.form:
        url = request.form["url"]
    elif "url" in request.args:
        url = request.args.get("url")
    elif "q" in request.args: # Handle Google search queries directly
        search_query = request.args.get("q")
        url = f"https://www.google.com/search?q={quote_plus(search_query)}"
    else:
        return "No URL provided", 400

    url = unquote_plus(url) if "%" in url else url
    if not urlparse(url).scheme:
        url = "http://" + url

    try:
        head = requests.head(url, allow_redirects=True, timeout=6, proxies=PROXY_BACKEND)
        content_type = head.headers.get("content-type", "")
    except Exception:
        head = None
        content_type = ""

    is_html = "text/html" in content_type

    if is_html:
        try:
            logging.info(f"[proxy] fetching (requests) {url}")
            rendered = fetch_with_requests(url)
            rewritten = rewrite_html(url, rendered)
            return Response(rewritten, content_type="text/html; charset=utf-8")
        except Exception as e:
            logging.exception("Error rendering HTML")
            return f"Error rendering: {e}", 500
    else:
        try:
            logging.info(f"[proxy] streaming {url}")
            resp = requests.get(url, stream=True, timeout=20, proxies=PROXY_BACKEND)
            content_type_res = resp.headers.get("content-type", "application/octet-stream")
            return Response(resp.iter_content(chunk_size=8192), content_type=content_type_res)
        except Exception as e:
            logging.exception("Error fetching resource")
            return f"Error fetching resource: {e}", 500

if __name__ == "__main__":
    proxy_port = 6767
    app_port = 8080

    # Start the TCP proxy in a background thread
    proxy_thread = threading.Thread(target=start_proxy_server, args=("127.0.0.1", proxy_port))
    proxy_thread.daemon = True
    proxy_thread.start()

    # Start the Flask app
    try:
        app.run(host="127.0.0.1", port=app_port, threaded=True)
    finally:
        # To enable Playwright, uncomment the following lines
        # _playwright.stop()
        pass
