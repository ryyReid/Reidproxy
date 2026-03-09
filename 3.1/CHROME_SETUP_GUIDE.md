# ReidProxy with Headless Chrome - Setup Guide

## Overview

This enhanced version of ReidProxy uses **Selenium with headless Chrome** to render JavaScript-heavy websites. This is perfect for sites like Twitter, Facebook, Reddit, YouTube, and modern web apps that rely heavily on JavaScript.

## How It Works

The proxy intelligently decides which rendering method to use:

1. **Regular Sites** → Uses `requests` library (fast, lightweight)
2. **JavaScript-Heavy Sites** → Uses headless Chrome (slower, but renders everything)

You can configure which domains trigger Chrome rendering.

## Prerequisites

### 1. Python 3.8+
Already installed from your original setup.

### 2. Google Chrome or Chromium

**Windows:**
- Download from: https://www.google.com/chrome/
- Or use Edge (Chromium-based)

**macOS:**
```bash
brew install --cask google-chrome
```

**Linux (Ubuntu/Debian):**
```bash
# Install Chrome
wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
sudo dpkg -i google-chrome-stable_current_amd64.deb
sudo apt-get install -f

# Or install Chromium
sudo apt-get update
sudo apt-get install chromium-browser chromium-chromedriver
```

### 3. ChromeDriver

**Option A: Automatic (Recommended)**
The `webdriver-manager` package will handle this automatically.

**Option B: Manual**
- Download from: https://chromedriver.chromium.org/
- Match your Chrome version
- Add to PATH

## Installation

### 1. Install Dependencies

```bash
pip install -r requirements_chrome.txt
```

This installs:
- `selenium` - Browser automation
- `webdriver-manager` - Automatic ChromeDriver management
- All previous dependencies

### 2. Verify Chrome Installation

```bash
# Check Chrome version
google-chrome --version  # Linux
"C:\Program Files\Google\Chrome\Application\chrome.exe" --version  # Windows
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --version  # macOS
```

### 3. Test Setup

Create a test script:

```python
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

options = Options()
options.add_argument('--headless')
options.add_argument('--no-sandbox')

driver = webdriver.Chrome(options=options)
driver.get('https://www.google.com')
print(f"Title: {driver.title}")
driver.quit()

print("✅ Chrome setup successful!")
```

Run it:
```bash
python test_chrome.py
```

## Configuration

### Basic Setup

Edit `app_with_chrome.py`:

```python
class Config:
    # Enable/disable Chrome
    USE_HEADLESS_CHROME = True
    
    # Time to wait for pages to load (seconds)
    CHROME_WAIT_TIME = 10
    
    # Number of Chrome instances to keep ready
    CHROME_POOL_SIZE = 3
    
    # Domains that should use Chrome
    USE_CHROME_FOR_DOMAINS = {
        'twitter.com', 'x.com',
        'facebook.com',
        'instagram.com',
        'reddit.com',
        'youtube.com'
    }
```

### Adding More Domains

To render a site with Chrome, add its domain:

```python
USE_CHROME_FOR_DOMAINS = {
    'twitter.com',
    'x.com',
    'mysite.com',  # Add your domain here
    'another-site.com'
}
```

### Performance Tuning

**For Fast Browsing (less Chrome):**
```python
CHROME_POOL_SIZE = 1  # Fewer instances
CHROME_WAIT_TIME = 5  # Shorter wait
USE_CHROME_FOR_DOMAINS = {'twitter.com'}  # Only essential sites
```

**For Full JavaScript Support (more Chrome):**
```python
CHROME_POOL_SIZE = 5  # More instances
CHROME_WAIT_TIME = 15  # Longer wait for complex sites
USE_CHROME_FOR_DOMAINS = {
    # Add many domains
}
```

**Disable Images (Faster Loading):**
```python
# In _create_driver() method, uncomment:
prefs = {"profile.managed_default_content_settings.images": 2}
chrome_options.add_experimental_option("prefs", prefs)
```

### Memory Optimization

Chrome uses significant memory. For low-memory systems:

```python
CHROME_POOL_SIZE = 1  # Only 1 instance
# Add to chrome_options in _create_driver():
chrome_options.add_argument('--disable-extensions')
chrome_options.add_argument('--disable-plugins')
chrome_options.add_argument('--disable-images')  # If uncommented above
```

## Running the Application

### Development Mode

```bash
python app_with_chrome.py
```

You'll see:
```
Starting ReidProxy with Chrome support...
Initializing Chrome driver pool with 3 instances...
Created new Chrome driver instance
Created new Chrome driver instance
Created new Chrome driver instance
Chrome driver pool ready with 3 instances
TCP Proxy listening on 127.0.0.1:6767
Web interface on http://127.0.0.1:5000
Chrome rendering enabled for 6 domains
```

### Production Mode

```bash
gunicorn -w 4 -b 0.0.0.0:5000 --timeout 120 app_with_chrome:app
```

**Note:** Each Gunicorn worker will have its own Chrome pool, so memory usage increases with workers.

## Usage

### Web Interface

1. Navigate to http://127.0.0.1:5000
2. Enter a URL (e.g., `twitter.com`)
3. If the domain is in `USE_CHROME_FOR_DOMAINS`, Chrome will render it
4. Otherwise, the fast `requests` method is used

### How to Tell What's Being Used

Check the terminal logs:
```
INFO - Proxying: https://twitter.com
INFO - Using Chrome for: https://twitter.com
INFO - Fetching with Chrome: https://twitter.com
```

vs

```
INFO - Proxying: https://wikipedia.org
INFO - Using requests for: https://wikipedia.org
```

## Troubleshooting

### "ChromeDriver not found"

**Solution 1:** Install webdriver-manager
```bash
pip install webdriver-manager
```

Then modify `_create_driver()`:
```python
from webdriver_manager.chrome import ChromeDriverManager

driver = webdriver.Chrome(
    service=Service(ChromeDriverManager().install()),
    options=chrome_options
)
```

**Solution 2:** Manual ChromeDriver
- Download from https://chromedriver.chromium.org/
- Place in PATH or specify path:
```python
service = Service('/path/to/chromedriver')
driver = webdriver.Chrome(service=service, options=chrome_options)
```

### "Chrome version mismatch"

Chrome and ChromeDriver versions must match.

**Check versions:**
```bash
google-chrome --version
chromedriver --version
```

**Fix:** Update both to latest:
```bash
# Update Chrome (varies by OS)
# Then update ChromeDriver
pip install --upgrade webdriver-manager
```

### "Chrome failed to start"

**On Linux:**
```bash
# Install dependencies
sudo apt-get install -y \
  libnss3 libgconf-2-4 libxi6 libxcursor1 libxss1 \
  libxcomposite1 libasound2 libxtst6 libxrandr2 \
  fonts-liberation libappindicator3-1 libatk-bridge2.0-0 \
  libgtk-3-0
```

**Check permissions:**
```bash
chmod +x /path/to/chromedriver
```

**Try running Chrome manually:**
```bash
google-chrome --headless --disable-gpu --dump-dom https://www.google.com
```

### "Too Many Open Files"

Chrome uses many file descriptors.

**Increase limit (Linux/macOS):**
```bash
ulimit -n 4096
```

Make permanent:
```bash
# Add to ~/.bashrc or ~/.zshrc
ulimit -n 4096
```

### High Memory Usage

Each Chrome instance uses ~100-200MB RAM.

**Solutions:**
1. Reduce `CHROME_POOL_SIZE`
2. Use fewer Gunicorn workers
3. Disable images (see Configuration)
4. Limit domains in `USE_CHROME_FOR_DOMAINS`

### Slow Performance

**Speed up Chrome:**
```python
# Add to chrome_options:
chrome_options.add_argument('--disable-extensions')
chrome_options.add_argument('--disable-plugins')
chrome_options.add_argument('--disable-software-rasterizer')
chrome_options.add_argument('--disable-dev-shm-usage')

# Disable images
prefs = {"profile.managed_default_content_settings.images": 2}
chrome_options.add_experimental_option("prefs", prefs)
```

**Reduce wait time:**
```python
CHROME_WAIT_TIME = 5  # Instead of 10
```

### "Session not created"

Chrome crashed or didn't start properly.

**Debug:**
```python
# Remove --headless to see what's happening
# chrome_options.add_argument('--headless')  # Comment out
```

## Advanced Features

### Screenshots

Add screenshot capability:

```python
def fetch_with_chrome(url):
    # ... existing code ...
    
    # Take screenshot before returning
    screenshot_path = f"/tmp/screenshot_{time.time()}.png"
    driver.screenshot(screenshot_path)
    logger.info(f"Screenshot saved: {screenshot_path}")
    
    # ... rest of code ...
```

### Wait for Specific Elements

For sites that load slowly:

```python
def fetch_with_chrome(url):
    driver.get(url)
    
    # Wait for specific element
    try:
        element = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, "main-content"))
        )
    except TimeoutException:
        logger.warning("Element not found")
    
    # ... rest of code ...
```

### Execute JavaScript

Interact with the page:

```python
# Scroll to bottom (load lazy content)
driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
time.sleep(2)

# Click a button
button = driver.find_element(By.ID, "load-more")
button.click()
time.sleep(1)

# Get the updated HTML
html_content = driver.page_source
```

### Capture Network Requests

Use Chrome DevTools Protocol:

```python
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities

caps = DesiredCapabilities.CHROME
caps['goog:loggingPrefs'] = {'performance': 'ALL'}

driver = webdriver.Chrome(options=chrome_options, desired_capabilities=caps)

# After page load
logs = driver.get_log('performance')
# Process network logs...
```

## Docker Deployment

Create `Dockerfile`:

```dockerfile
FROM python:3.11-slim

# Install Chrome
RUN apt-get update && apt-get install -y \
    wget gnupg2 \
    && wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements_chrome.txt .
RUN pip install --no-cache-dir -r requirements_chrome.txt

COPY . .

EXPOSE 5000

CMD ["python", "app_with_chrome.py"]
```

Build and run:
```bash
docker build -t reidproxy-chrome .
docker run -p 5000:5000 reidproxy-chrome
```

## Performance Comparison

| Site Type | Requests Method | Chrome Method |
|-----------|----------------|---------------|
| Static HTML | 50-200ms | 2-5 seconds |
| JavaScript Site | May not work | 3-8 seconds |
| Memory Usage | ~10MB | ~150MB per instance |

**Recommendation:** Only use Chrome for sites that actually need it.

## Security Considerations

Chrome adds attack surface:

1. **Keep Chrome Updated** - Security patches
2. **Sandbox Chrome** - Use Docker/containers
3. **Limit Pool Size** - Reduce resource exhaustion
4. **Monitor Resources** - Watch memory/CPU usage
5. **Add Timeouts** - Prevent hanging processes

## Best Practices

1. **Test First** - Try without Chrome, add if needed
2. **Start Small** - Begin with 1 Chrome instance
3. **Monitor Logs** - Watch for errors/crashes
4. **Profile Performance** - Find bottlenecks
5. **Gradual Rollout** - Add domains slowly

## Getting Help

If you have issues:

1. Check Chrome is installed: `google-chrome --version`
2. Check ChromeDriver: `chromedriver --version`
3. Check logs: Look for error messages
4. Test manually: Run the test script above
5. Reduce complexity: Set `CHROME_POOL_SIZE = 1`

## Summary

You now have a proxy that can handle:
- ✅ Static websites (fast)
- ✅ JavaScript-heavy sites (Chrome)
- ✅ AJAX/dynamic content
- ✅ Modern web apps
- ✅ Sites with complex interactions

The proxy automatically chooses the best method for each site!
