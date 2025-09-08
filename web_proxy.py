from flask import Flask, request, Response, render_template_string
import requests
import os
from bs4 import BeautifulSoup
from urllib.parse import urljoin, quote_plus, unquote_plus, urlparse
import logging
import re
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

PROXY_BACKEND = {
    "http": "http://127.0.0.1:6767",
    "https": "http://127.0.0.1:6767"
}

# Launch Playwright once for better performance
_playwright = sync_playwright().start()
_browser = _playwright.chromium.launch(headless=False, proxy={"server": "http://127.0.0.1:6767"})

def fetch_with_playwright(url, timeout=15000):
    """Return rendered HTML from Playwright (string) or raise."""
    context = _browser.new_context()
    page = context.new_page()

    try:
        page.goto(url, wait_until="networkidle", timeout=timeout)
        html = page.content()
    finally:
        page.close()
        context.close()
    return html

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
            style_tag.string = re.sub(r"url(['\"]?(.*?)['\"]?)", lambda match: f'url({proxify(match.group(1))})', style_tag.string)

    # Rewrite inline style attributes
    for tag in soup.find_all(style=True):
        tag['style'] = re.sub(r"url(['\"]?(.*?)['\"]?)", lambda match: f'url({proxify(match.group(1))})', tag['style'])

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
                const absolute = new URL(rawUrl, ''' + base_url + ''');
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
    games_html_path = r"C:\Users\Reid am\Desktop\BrowserProxy\games.html"
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
            logging.info(f"[proxy] fetching (playwright) {url}")
            rendered = fetch_with_playwright(url)
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
    port = int(os.environ.get("PORT", 8080))
    host = os.environ.get("HOST", "127.0.0.1")
    try:
        app.run(host=host, port=port, threaded=False)
    finally:
        _playwright.stop()