import os
import time
from playwright.sync_api import sync_playwright, expect
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def run_test():
    admin_passcode = os.getenv("ADMIN_PASSCODE")
    if not admin_passcode:
        print("Error: ADMIN_PASSCODE not found in .env file.")
        exit(1)

    print(f"Loaded ADMIN_PASSCODE: {admin_passcode}")

    with sync_playwright() as p:
        # Launch browser
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        try:
            # 1. Navigate to Home Page
            print("Navigating to http://localhost:3000...")
            page.goto("http://localhost:3000")
            
            # Wait for the page to load
            page.wait_for_load_state("networkidle")

            # 2. Click "Administrator Settings"
            print("Looking for 'Administrator Settings' button...")
            # The button text is "Administrator Settings" inside an anchor tag
            admin_btn = page.get_by_role("link", name="Administrator Settings")
            expect(admin_btn).to_be_visible()
            admin_btn.click()
            
            # 3. Verify Admin Login Page
            print("Verifying Admin Login page...")
            # Check for "Admin Login" heading
            expect(page.get_by_role("heading", name="Admin Login")).to_be_visible()
            
            # 4. Enter Passcode
            print("Entering Admin Passcode...")
            passcode_input = page.get_by_placeholder("Enter Admin Passcode")
            passcode_input.fill(admin_passcode)
            
            # 5. Click Login
            print("Clicking Login button...")
            page.get_by_role("button", name="Login").click()
            
            # 6. Verify Admin Dashboard
            print("Verifying Admin Dashboard...")
            # Wait for "Admin Dashboard" heading
            expect(page.get_by_role("heading", name="Admin Dashboard")).to_be_visible()
            
            # Check for tabs (Users / Rooms)
            expect(page.get_by_role("tab", name="Users")).to_be_visible()
            expect(page.get_by_role("tab", name="Rooms")).to_be_visible()
            
            print("Admin Dashboard loaded successfully!")
            
            # Optional: Check if data is loaded (e.g., check for table headers)
            expect(page.get_by_role("columnheader", name="Username")).to_be_visible()

            # 7. Logout
            print("Testing Logout...")
            page.get_by_role("button", name="Logout").click()
            
            # 8. Verify return to Login Page
            print("Verifying return to Login page...")
            expect(page.get_by_role("heading", name="Admin Login")).to_be_visible()
            
            print("Logout successful!")
            print("TEST PASSED: Admin Login/Logout flow verified.")

        except Exception as e:
            print(f"TEST FAILED: {e}")
            # Take screenshot on failure
            page.screenshot(path="testcases/admin_login/output/failure.png")
            exit(1)
        finally:
            browser.close()

if __name__ == "__main__":
    run_test()
