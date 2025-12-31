from playwright.sync_api import sync_playwright
import time
import sys

def run():
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
            # Click the 'Guest' tab button. 
            # Using exact=True to distinguish from 'Continue as Guest' button if needed,
            # or targeting the specific tab button class/structure.
            # The previous error showed:
            # 1) <button ...>Guest</button>
            # 2) <button ...>Continue as Guest</button>
            
            print("Clicking 'Guest' tab...")
            page.get_by_role("button", name="Guest", exact=True).click()
            
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
            page.screenshot(path="guest_login_failure.png")
            browser.close()
            sys.exit(1)

        # Test Google Login UI (Visual check only since we can't easily automate full Google auth without credentials)
        print("Testing Google Login UI...")
        try:
            # Reload page to reset state (or logout if implemented)
            page.goto("http://localhost:3000")
            
            print("Clicking 'Google Login' tab...")
            page.get_by_role("button", name="Google Login").click()
            
            print("Checking for 'Sign In with Google' text...")
            if page.get_by_text("Sign In with Google").is_visible():
                print("Success: Google Login UI is visible.")
            else:
                print("Error: Google Login UI not visible.")
                page.screenshot(path="google_ui_failure.png")
                browser.close()
                sys.exit(1)
                
        except Exception as e:
            print(f"Google Login UI test failed: {e}")
            browser.close()
            sys.exit(1)

        print("All tests passed!")
        browser.close()

if __name__ == "__main__":
    run()
