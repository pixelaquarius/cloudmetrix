
from playwright.sync_api import sync_playwright
import time
import os

profile_dir = os.path.abspath(os.path.join('data', 'browser_profiles', 'Primaty'))
with sync_playwright() as p:
    browser = p.chromium.launch_persistent_context(
        user_data_dir=profile_dir,
        headless=False,
        channel="chrome"
    )
    page = browser.pages[0]
    page.goto('https://www.facebook.com/')
    print("Please login. The window will close in 3 minutes.")
    time.sleep(180)
    browser.close()
