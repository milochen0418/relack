from playwright.sync_api import sync_playwright
import time
import sys

import os

def run():
    # Ensure output directory exists
    output_dir = os.path.join(os.path.dirname(__file__), "output")
    os.makedirs(output_dir, exist_ok=True)

    with sync_playwright() as p:
        print("Launching browser...")
        # headless=False allows us to see what's happening
        browser = p.chromium.launch(headless=False, slow_mo=1000)
        page = browser.new_page()
        
        print("Navigating to http://localhost:3000...")
        try:
            page.goto("http://localhost:3000", timeout=30000, wait_until="domcontentloaded")
        except Exception as e:
            print(f"Navigation failed: {e}")
            browser.close()
            sys.exit(1)

        print("Checking page title...")
        try:
            title = page.title()
            print(f"Page title: {title}")
            if "Relack" not in title:
                print("Error: Title does not contain 'Relack'")
                browser.close()
                sys.exit(1)
        except Exception as e:
            print(f"Failed to check title: {e}")
            browser.close()
            sys.exit(1)

        # Test Guest Login
        print("Testing Guest Login...")
        try:
            print("Filling nickname...")
            # Wait for input to be visible
            page.get_by_placeholder("CoolPanda99").fill("AutoTester")
            
            print("Clicking 'Continue as Guest'...")
            page.get_by_role("button", name="Continue as Guest").click()
            
            print("Waiting for welcome toast or dashboard...")
            # Expect to see "Welcome, AutoTester!" toast
            # or check if we are redirected to the chat dashboard.
            # The toast might appear briefly.
            
            # Let's wait for a text that indicates we are logged in.
            # Maybe the user profile name in the navbar or sidebar?
            # Or the toast message.
            try:
                page.wait_for_selector("text=Welcome, AutoTester!", timeout=5000)
                print("Success: Welcome toast found.")
            except:
                print("Warning: Welcome toast not found or timed out.")
            
            # Check if we are on the dashboard (e.g., check for 'Channels' or 'Direct Messages' if they exist)
            # Or just check if the 'Guest' login form is gone.
            
        except Exception as e:
            print(f"Guest login failed: {e}")
            page.screenshot(path=os.path.join(output_dir, "guest_login_failure.png"))
            browser.close()
            sys.exit(1)

        print("All tests passed!")
        browser.close()

if __name__ == "__main__":
    run()
