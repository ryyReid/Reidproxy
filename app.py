# app.py - Stealth Proxy Server (merged improvements 2025/2026)
from flask import Flask, request, Response, send_from_directory, jsonify
from urllib.parse import urlparse, unquote
import requests
import re
import os
import logging
import traceback
from ipaddress import ip_address

# Optional brotli (pip install brotli if you want it)
try:
    import brotli
except ImportError:
    brotli = None

# ────────────────────────────────────────────────
# Logging ─ very verbose for development
# ────────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s | %(levelname)-7s | %(name)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['PROPAGATE_EXCEPTIONS'] = True

# ────────────────────────────────────────────────
# SSRF / private network protection
# ────────────────────────────────────────────────
DENY_LIST_SUBSTRINGS = [
    "localhost", "127.0.0.1", "0.0.0.0", "::1",
    "192.168.", "10.", "172.16.", "172.17.", "172.18.", "172.19.",
    "172.20.", "172.21.", "172.22.", "172.23.", "172.24.", "172.25.",
    "172.26.", "172.27.", "172.28.", "172.29.", "172.30.", "172.31.",
    "169.254.",
]

def is_dangerous_url(url_str: str) -> bool:
    parsed = urlparse(url_str)
    host = (parsed.hostname or "").lower()

    for block in DENY_LIST_SUBSTRINGS:
        if block in host:
            return True

    try:
        ip = ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local:
            return True
    except ValueError:
        pass

    return False

# ────────────────────────────────────────────────
# Debug endpoint
# ────────────────────────────────────────────────
@app.route("/debug")
def debug_info():
    info = {
        "request": {
            "method": request.method,
            "url": request.url,
            "path": request.path,
            "args": dict(request.args),
            "remote_addr": request.remote_addr,
            "user_agent": request.user_agent.string,
            "headers_count": len(request.headers),
        },
        "flask": {
            "debug": app.debug,
            "server_name": app.config.get("SERVER_NAME"),
        },
        "python": {
            "version": os.sys.version.splitlines()[0],
        }
    }
    return jsonify(info), 200

# ────────────────────────────────────────────────
# Static file serving
# ────────────────────────────────────────────────
@app.route("/")
def index():
    return send_from_directory(".", "games.html")

@app.route("/assets/<path:filename>")
def serve_assets(filename):
    return send_from_directory("static/img", filename)

@app.route("/static/<path:filename>")
def serve_static_files(filename):
    return send_from_directory("static", filename)

# ────────────────────────────────────────────────
# Sub-resource proxy   /p/example.com/style.css   →   https://example.com/style.css
# MUST COME BEFORE the main /p/<path> route
# ────────────────────────────────────────────────
@app.route("/p/<netloc>/<path:subpath>")
def sub_resource_proxy(netloc, subpath):
    if is_dangerous_url(f"https://{netloc}"):
        return "Access to this domain blocked", 403

    target_url = f"https://{netloc}/{subpath}"
    if request.query_string:
        target_url += "?" + request.query_string.decode()

    logger.info(f"Sub-resource: {request.url} → {target_url}")

    try:
        headers = {
            "User-Agent": request.headers.get("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"),
            "Accept": request.headers.get("Accept", "*/*"),
            "Referer": request.headers.get("Referer", f"https://{netloc}/"),
            "Accept-Encoding": "gzip, deflate, br",
        }

        resp = requests.get(
            target_url,
            headers=headers,
            timeout=15,
            stream=True,
            allow_redirects=True
        )
        resp.raise_for_status()

        excluded = ["content-encoding", "content-length", "transfer-encoding", "connection"]
        out_headers = {k: v for k, v in resp.headers.items() if k.lower() not in excluded}

        def generate():
            for chunk in resp.iter_content(8192):
                yield chunk

        return Response(generate(), status=resp.status_code, headers=out_headers)

    except Exception as e:
        logger.error(f"Sub-resource failed {target_url}: {str(e)}")
        if request.args.get("debug") == "1":
            return f"<pre>Sub-resource error:\n{traceback.format_exc()}</pre>", 502
        return "Failed to load resource", 502

# ────────────────────────────────────────────────
# Main proxy route   /p/https://example.com/path   or   /p/example.com
# ────────────────────────────────────────────────
@app.route("/p/<path:encoded_url>")
def stealth_proxy(encoded_url):
    debug_mode = request.args.get("debug", "0") == "1"

    try:
        target_url = unquote(encoded_url).strip()

        # Auto-add https:// if missing protocol
        if not target_url.lower().startswith(("http://", "https://")):
            target_url = "https://" + target_url

        logger.info(f"Main proxy → {target_url}")

        if is_dangerous_url(target_url):
            return "Blocked: internal / private address", 403

        headers = {
            "User-Agent": request.headers.get("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"),
            "Accept": request.headers.get("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"),
            "Accept-Language": request.headers.get("Accept-Language", "en-US,en;q=0.9"),
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": request.headers.get("Referer", ""),
            "Connection": "keep-alive",
        }

        resp = requests.get(
            target_url,
            headers=headers,
            timeout=25,
            allow_redirects=True,
            stream=True
        )
        resp.raise_for_status()

        content_type = resp.headers.get("Content-Type", "").lower()

        content = b""
        if "text/html" in content_type:
            try:
                html = resp.content.decode("utf-8", errors="replace")
                parsed = urlparse(target_url)
                netloc = parsed.netloc
                proxy_prefix = f"/p/{netloc}"

                # Rewrite root-relative, protocol-relative, same-domain absolute
                for attr in ['href', 'src', 'action', 'data-src', 'poster', 'data-background', 'data-lazy-src', 'data-poster']:
                    html = re.sub(
                        rf'({attr})=["\']/(?!/)',
                        rf'\1="{proxy_prefix}/',
                        html, flags=re.IGNORECASE
                    )
                    html = re.sub(
                        rf'({attr})=["\']//',
                        rf'\1="{proxy_prefix}/',
                        html, flags=re.IGNORECASE
                    )
                    html = re.sub(
                        rf'({attr})=["\']https?://{re.escape(netloc)}',
                        rf'\1="{proxy_prefix}',
                        html, flags=re.IGNORECASE
                    )

                # Basic inline style url(/path) → url(/p/netloc/path)
                html = re.sub(
                    r'url\(\s*["\']?/(?!/)',
                    f'url({proxy_prefix}/',
                    html, flags=re.IGNORECASE
                )

                content = html.encode("utf-8")
            except Exception as e:
                logger.error(f"HTML rewrite failed: {e}")
                content = resp.content
        else:
            # Stream non-HTML directly
            def stream_content():
                for chunk in resp.iter_content(chunk_size=8192):
                    yield chunk

            return Response(
                stream_content(),
                status=resp.status_code,
                headers={k: v for k, v in resp.headers.items() if k.lower() not in [
                    "content-encoding", "content-length", "transfer-encoding", "connection"
                ]},
                content_type=content_type
            )

        # Final headers
        out_headers = {
            k: v for k, v in resp.headers.items()
            if k.lower() not in ["content-encoding", "content-length", "transfer-encoding", "connection"]
        }
        out_headers["Content-Type"] = content_type

        return Response(content, status=resp.status_code, headers=out_headers)

    except requests.RequestException as e:
        logger.error(f"Fetch failed {target_url}: {str(e)}")
        msg = f"Could not reach target ({str(e)})"
        if debug_mode:
            return f"<pre>{msg}\n{traceback.format_exc()}</pre>", 502
        return msg, 502

    except Exception as e:
        logger.exception("Unexpected proxy error")
        msg = "Internal proxy error"
        if debug_mode:
            return f"<pre>{msg}\n{traceback.format_exc()}</pre>", 500
        return msg, 500

# ────────────────────────────────────────────────
# 404
# ────────────────────────────────────────────────
@app.errorhandler(404)
def page_not_found(e):
    return "<h2>404 - Not Found</h2><p>Try /debug or check URL format</p>", 404


if __name__ == "__main__":
    # For HTTPS (recommended for crypto.subtle / secure context):
    #   1. mkcert -install
    #   2. mkcert 192.168.40.76 localhost 127.0.0.1
    #   3. Uncomment and adjust filenames below
    #
    # import ssl
    # context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    # context.load_cert_chain("192.168.40.76+3.pem", "192.168.40.76+3-key.pem")
    # app.run(host="0.0.0.0", port=8080, ssl_context=context, debug=True)

    # Plain HTTP (current default)
    app.run(host="0.0.0.0", port=8080, debug=True)