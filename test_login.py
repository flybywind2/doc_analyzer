#!/usr/bin/env python3
"""
Test login flow with Playwright
"""
from playwright.sync_api import sync_playwright
import time

def test_login():
    with sync_playwright() as p:
        # Launch browser
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        
        # Enable console logging
        page.on("console", lambda msg: print(f"[BROWSER] {msg.type}: {msg.text}"))
        
        # Go to login page
        print("📍 Navigating to login page...")
        page.goto("https://8000-i1e7ru3hdap3doc8e20t8-a402f90a.sandbox.novita.ai/auth/login")
        time.sleep(2)
        
        # Take screenshot
        page.screenshot(path="/home/user/webapp/screenshot_login.png")
        print("✅ Login page loaded")
        
        # Fill login form
        print("📝 Filling login form...")
        page.fill('input[name="username"]', "admin")
        page.fill('input[name="password"]', "admin123!")
        
        # Take screenshot before submit
        page.screenshot(path="/home/user/webapp/screenshot_before_submit.png")
        
        # Submit form
        print("🚀 Submitting form...")
        page.click('button[type="submit"]')
        
        # Wait for response
        time.sleep(3)
        
        # Check current URL
        current_url = page.url
        print(f"📍 Current URL: {current_url}")
        
        # Take screenshot after login
        page.screenshot(path="/home/user/webapp/screenshot_after_login.png")
        
        # Check cookies
        cookies = context.cookies()
        print(f"\n🍪 Cookies ({len(cookies)}):")
        for cookie in cookies:
            print(f"  - {cookie['name']}: {cookie['value'][:50]}..." if len(cookie['value']) > 50 else f"  - {cookie['name']}: {cookie['value']}")
        
        # Check local storage
        print("\n💾 Local Storage:")
        local_storage = page.evaluate("() => Object.entries(localStorage)")
        for key, value in local_storage:
            print(f"  - {key}: {value[:50]}..." if len(value) > 50 else f"  - {key}: {value}")
        
        # Try to access dashboard
        print("\n📍 Navigating to dashboard...")
        page.goto("https://8000-i1e7ru3hdap3doc8e20t8-a402f90a.sandbox.novita.ai/dashboard")
        time.sleep(2)
        
        # Check if redirected or authenticated
        final_url = page.url
        print(f"📍 Final URL: {final_url}")
        
        # Get page content
        content = page.content()
        if "Not authenticated" in content:
            print("❌ Authentication failed - 'Not authenticated' found in page")
        elif "Dashboard" in content or "dashboard" in content.lower():
            print("✅ Successfully authenticated - Dashboard loaded")
        else:
            print("⚠️  Unknown state - checking page content...")
            print(f"Page title: {page.title()}")
        
        # Take final screenshot
        page.screenshot(path="/home/user/webapp/screenshot_dashboard.png")
        
        # Close
        browser.close()
        
        print("\n✅ Test completed. Screenshots saved.")

if __name__ == "__main__":
    test_login()
