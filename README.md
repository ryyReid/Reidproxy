# Reidproxy
um i did it

## How to Use

This guide will walk you through setting up and using the BrowserProxy.

### Prerequisites

Before you begin, ensure you have the following installed:

*   **Python 3**: Download and install from [python.org](https://www.python.org/downloads/).
*   **pip**: Python's package installer, usually comes with Python.

### Installation

1.  **Navigate to the project directory**:
    ```bash
    cd C:\Users\Reid am\Desktop\BrowserProxy
    ```

2.  **Install dependencies**:
    The project relies on several Python libraries. Install them using `pip`:
    ```bash
    pip install -r requirements.txt
    ```

### Running the Proxy

To start the web proxy server, execute the `proxy.py and web_proxy.py` script:

```bash
python proxy.py
```

```bash
python web_proxy.py
```

By default, the web proxy will run on `http://127.0.0.1:8080`. You will see output in your terminal indicating that the server is running.
and the proxy runs on 'http:127.0.0.1:6767"
### Browser Configuration

To use the proxy, you need to configure your web browser to direct its traffic through `http://127.0.0.1:6767`. The exact steps vary slightly depending on your browser.

#### General Steps (Example for Chrome/Firefox):

1.  **Open your browser's settings/preferences.**
2.  **Search for "Proxy" settings.**
3.  **Select "Manual proxy configuration" or similar.**
4.  **Enter the following details:**
    *   **HTTP Proxy**: `127.0.0.1`
    *   **Port**: `6767`
5.  **Save your changes.**

Now, all your browser's web traffic should be routed through the local proxy. Remember to disable the proxy settings in your browser when you no longer need it, or your internet access might be affected.