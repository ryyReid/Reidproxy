import socket
import threading
import select
import os
from flask import Flask, request, Response, render_template_string
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, quote_plus, unquote_plus, urlparse, urlunparse
import logging
import re

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
        if raw_url.startswith("/proxy?url="):
            return raw_url
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

    def css_url_replacer(match):
        url = match.group(1).strip()
        if (url.startswith("'") and url.endswith("'")) or \
           (url.startswith('"') and url.endswith('"')):
            url = url[1:-1]
        
        if url.startswith('data:'):
            return f"url('{url}')"
            
        return f"url('{proxify(url)}')"

    for style_tag in soup.find_all("style"):
        if style_tag.string:
            style_tag.string = re.sub(r"url\((.*?)\)", css_url_replacer, style_tag.string)

    for tag in soup.find_all(style=True):
        tag['style'] = re.sub(r"url\((.*?)\)", css_url_replacer, tag['style'])

    for base in soup.find_all("base"):
        base.decompose()

    injection_script = soup.new_tag("script")
    injection_script.string = '''
        (function() {
            const base_url = \' ''' + base_url + '''';

            const proxify = (rawUrl) => {
                if (!rawUrl || typeof rawUrl !== 'string' || rawUrl.startsWith('/proxy?url=')) return rawUrl;

                let absoluteUrl;
                try {
                    absoluteUrl = new URL(rawUrl, base_url);
                } catch (e) {
                    return rawUrl;
                }

                if (absoluteUrl.origin === new URL(window.location.href).origin && absoluteUrl.pathname === window.location.pathname && absoluteUrl.hash) {
                    return rawUrl;
                }

                return `/proxy?url=${encodeURIComponent(absoluteUrl.href)}`;
            };

            const rewriteElement = (element) => {
                if (element.hasAttribute('href') && !element.hasAttribute('data-proxified')) {
                    element.href = proxify(element.getAttribute('href'));
                    element.setAttribute('data-proxified', 'true');
                }
                if (element.hasAttribute('src') && !element.hasAttribute('data-proxified')) {
                    element.src = proxify(element.getAttribute('src'));
                    element.setAttribute('data-proxified', 'true');
                }
                if (element.hasAttribute('action') && !element.hasAttribute('data-proxified')) {
                    element.action = proxify(element.getAttribute('action'));
                    element.setAttribute('data-proxified', 'true');
                }
            };

            const observer = new MutationObserver((mutations) => {
                mutations.forEach((mutation) => {
                    mutation.addedNodes.forEach((node) => {
                        if (node.nodeType === Node.ELEMENT_NODE) {
                            rewriteElement(node);
                            node.querySelectorAll('[href], [src], [action]').forEach(rewriteElement);
                        }
                    });
                });
            });

            observer.observe(document.documentElement, {
                childList: true,
                subtree: true,
            });

            document.querySelectorAll('[href], [src], [action]').forEach(rewriteElement);

            setInterval(() => {
                document.querySelectorAll('[href]:not([data-proxified]), [src]:not([data-proxified]), [action]:not([data-proxified])').forEach(element => {
                    rewriteElement(element);
                });
            }, 500);

        })();
    '''
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

    base_game_url = "https://ryyreid.github.io/Reidweb_v3vv/"

    def proxify_all_links(link):
        if not link:
            return link
        
        link = link.strip()
        if (link.startswith("'") and link.endswith("'")) or \
           (link.startswith('"') and link.endswith('"')):
            link = link[1:-1]

        if link.startswith("#") or link.startswith("mailto:") or link.startswith("javascript:") or link.startswith("data:"):
            return link
        
        absolute_url = urljoin(base_game_url, link)
        
        return f"/proxy?url={quote_plus(absolute_url)}"

    for tag in soup.find_all("a", href=True):
        tag['href'] = proxify_all_links(tag['href'])

    for tag in soup.find_all("script", src=True):
        tag['src'] = proxify_all_links(tag['src'])

    for tag in soup.find_all("img", src=True):
        tag['src'] = proxify_all_links(tag['src'])

    for tag in soup.find_all("link", href=True):
        tag['href'] = proxify_all_links(tag['href'])

    return render_template_string(str(soup))

def rewrite_text_based_content(base_url, content, proxify_func):
    """
    Generic function to rewrite URLs in text-based content (CSS, JS).
    """
    def repl(match):
        url = match.group(1).strip()
        if (url.startswith("'") and url.endswith("'")) or \
           (url.startswith('"') and url.endswith('"')):
            url = url[1:-1]
        
        if url.startswith('data:'):
            return f"url('{url}')"
            
        return f"url('{proxify_func(url)}')"

    content = re.sub(r"url\((.*?)\)", repl, content)
    return content

@app.route("/proxy", methods=["GET", "POST"])
def proxy():
    url = None
    if request.method == "POST" and "url" in request.form:
        url = request.form["url"]
    elif "url" in request.args:
        url = request.args.get("url")
    elif "q" in request.args:
        search_query = request.args.get("q")
        url = f"https://www.google.com/search?q={quote_plus(search_query)}"
    else:
        return "No URL provided", 400

    url = unquote_plus(url) if "%" in url else url
    
    # Normalize the URL
    url = url.replace('\\', '/')
    
    if not urlparse(url).scheme:
        url = "http://" + url

    try:
        resp = requests.get(url, stream=True, timeout=20, proxies=PROXY_BACKEND, allow_redirects=True)
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "").lower()
        
        def proxify(raw_url, current_base_url=url):
            if not raw_url:
                return raw_url
            raw_url = raw_url.strip()
            if raw_url.startswith("#") or raw_url.startswith("mailto:") or raw_url.startswith("javascript:") or raw_url.startswith("data:"):
                return raw_url
            absolute = urljoin(current_base_url, raw_url)
            return f'/proxy?url={quote_plus(absolute)}'

        if "text/html" in content_type:
            html_content = resp.content.decode('utf-8', errors='replace')
            
            # Get the directory of the URL
            parsed_url = urlparse(url)
            path_dir = os.path.dirname(parsed_url.path)
            base_url = urlunparse((parsed_url.scheme, parsed_url.netloc, path_dir, '', '', ''))

            rewritten_html = rewrite_html(base_url, html_content)
            return Response(rewritten_html, content_type="text/html; charset=utf-8")

        elif "text/css" in content_type or url.endswith(".glsl"):
            text_content = resp.content.decode('utf-8', errors='replace')
            rewritten_content = rewrite_text_based_content(url, text_content, proxify)
            return Response(rewritten_content, content_type=content_type)
            
        elif "application/javascript" in content_type or "text/javascript" in content_type:
            text_content = resp.content.decode('utf-8', errors='replace')
            rewritten_content = rewrite_text_based_content(url, text_content, proxify)
            return Response(rewritten_content, content_type=content_type)

        else:
            return Response(resp.iter_content(chunk_size=8192), content_type=content_type)

    except requests.exceptions.RequestException as e:
        return f"Error fetching resource: {e}", 500
    except Exception as e:
        return f"An unexpected error occurred: {e}", 500

if __name__ == "__main__":
    proxy_port = 6767
    app_port = 8080

    proxy_thread = threading.Thread(target=start_proxy_server, args=("127.0.0.1", proxy_port))
    proxy_thread.daemon = True
    proxy_thread.start()

    try:
        app.run(host="127.0.0.1", port=app_port, threaded=True)
    finally:
        pass
