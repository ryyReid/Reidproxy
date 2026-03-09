#!/usr/bin/env python3
"""
Installation and verification script for ReidProxy with Chrome support
"""

import sys
import subprocess
import platform
import importlib.util
import os

def print_step(step, message):
    """Print formatted step message"""
    print(f"\n{'='*60}")
    print(f"Step {step}: {message}")
    print('='*60)

def check_python_version():
    """Check if Python version is 3.8+"""
    print_step(1, "Checking Python Version")
    version = sys.version_info
    print(f"Python version: {version.major}.{version.minor}.{version.micro}")
    
    if version.major < 3 or (version.major == 3 and version.minor < 8):
        print("❌ Python 3.8 or higher is required!")
        return False
    
    print("✅ Python version OK")
    return True

def check_chrome_installed():
    """Check if Chrome/Chromium is installed"""
    print_step(2, "Checking for Chrome/Chromium")
    
    system = platform.system()
    chrome_commands = []
    
    if system == "Windows":
        chrome_commands = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
        ]
    elif system == "Darwin":  # macOS
        chrome_commands = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        ]
    else:  # Linux
        chrome_commands = [
            "google-chrome",
            "google-chrome-stable",
            "chromium",
            "chromium-browser"
        ]
    
    chrome_found = False
    for cmd in chrome_commands:
        try:
            if os.path.exists(cmd) or subprocess.run(
                [cmd if not os.path.exists(cmd) else cmd, "--version"],
                capture_output=True,
                timeout=5
            ).returncode == 0:
                print(f"✅ Chrome found: {cmd}")
                chrome_found = True
                break
        except (subprocess.TimeoutExpired, FileNotFoundError, PermissionError):
            continue
    
    if not chrome_found:
        print("❌ Chrome/Chromium not found!")
        print("\nInstallation instructions:")
        if system == "Windows":
            print("  Download from: https://www.google.com/chrome/")
        elif system == "Darwin":
            print("  Run: brew install --cask google-chrome")
        else:
            print("  Ubuntu/Debian: sudo apt-get install chromium-browser")
            print("  Or download from: https://www.google.com/chrome/")
        return False
    
    return True

def install_requirements():
    """Install Python requirements"""
    print_step(3, "Installing Python Dependencies")
    
    requirements_file = "requirements_chrome.txt"
    if not os.path.exists(requirements_file):
        print(f"❌ {requirements_file} not found!")
        return False
    
    try:
        print(f"Installing from {requirements_file}...")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", requirements_file],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            print("✅ Dependencies installed successfully")
            return True
        else:
            print(f"❌ Installation failed:\n{result.stderr}")
            return False
            
    except Exception as e:
        print(f"❌ Error installing dependencies: {e}")
        return False

def verify_packages():
    """Verify required packages are installed"""
    print_step(4, "Verifying Package Installation")
    
    required_packages = {
        'selenium': 'selenium',
        'flask': 'flask',
        'requests': 'requests',
        'bs4': 'beautifulsoup4',
    }
    
    all_found = True
    for import_name, package_name in required_packages.items():
        spec = importlib.util.find_spec(import_name)
        if spec is None:
            print(f"❌ {package_name} not found")
            all_found = False
        else:
            print(f"✅ {package_name} installed")
    
    return all_found

def test_selenium():
    """Test Selenium with headless Chrome"""
    print_step(5, "Testing Selenium with Chrome")
    
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        
        print("Creating headless Chrome instance...")
        options = Options()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        
        driver = webdriver.Chrome(options=options)
        
        print("Navigating to Google...")
        driver.get('https://www.google.com')
        
        title = driver.title
        print(f"Page title: {title}")
        
        driver.quit()
        
        if "Google" in title:
            print("✅ Selenium test successful!")
            return True
        else:
            print("❌ Unexpected page title")
            return False
            
    except Exception as e:
        print(f"❌ Selenium test failed: {e}")
        print("\nTroubleshooting:")
        print("1. Install webdriver-manager: pip install webdriver-manager")
        print("2. Ensure Chrome/Chromium is in PATH")
        print("3. Check ChromeDriver version matches Chrome version")
        return False

def create_config():
    """Create a basic config file"""
    print_step(6, "Creating Configuration")
    
    config_content = """# ReidProxy Configuration

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
"""
    
    config_file = "proxy_config.py"
    if not os.path.exists(config_file):
        try:
            with open(config_file, 'w') as f:
                f.write(config_content)
            print(f"✅ Created {config_file}")
            print("   You can customize settings in this file")
        except Exception as e:
            print(f"⚠️  Could not create config file: {e}")
    else:
        print(f"ℹ️  {config_file} already exists, skipping")
    
    return True

def main():
    """Run all installation steps"""
    print("""
    ╔═══════════════════════════════════════════════════════╗
    ║  ReidProxy Chrome Setup & Verification               ║
    ╚═══════════════════════════════════════════════════════╝
    """)
    
    steps = [
        ("Python Version", check_python_version),
        ("Chrome Installation", check_chrome_installed),
        ("Python Dependencies", install_requirements),
        ("Package Verification", verify_packages),
        ("Selenium Test", test_selenium),
        ("Configuration", create_config),
    ]
    
    results = {}
    for name, func in steps:
        try:
            results[name] = func()
        except Exception as e:
            print(f"❌ Error in {name}: {e}")
            results[name] = False
    
    # Summary
    print("\n" + "="*60)
    print("INSTALLATION SUMMARY")
    print("="*60)
    
    for name, success in results.items():
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} - {name}")
    
    all_passed = all(results.values())
    
    print("\n" + "="*60)
    if all_passed:
        print("🎉 SUCCESS! Everything is ready!")
        print("\nNext steps:")
        print("1. Review proxy_config.py and customize settings")
        print("2. Run the proxy: python app_with_chrome.py")
        print("3. Open browser: http://127.0.0.1:5000")
        print("4. Test with a JavaScript-heavy site like twitter.com")
    else:
        print("⚠️  INCOMPLETE - Please fix the issues above")
        print("\nCommon solutions:")
        print("- Install Chrome: https://www.google.com/chrome/")
        print("- Update pip: python -m pip install --upgrade pip")
        print("- Install webdriver-manager: pip install webdriver-manager")
    
    print("="*60 + "\n")
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())
