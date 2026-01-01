from playwright.sync_api import sync_playwright
import time
import sys
import os

def run():
    # Ensure output directory exists
    output_dir = os.path.join(os.path.dirname(__file__), "output")
    os.makedirs(output_dir, exist_ok=True)

    with sync_playwright() as p:
        print("Launching browser with persistent context...")
        user_data_dir = os.path.abspath("playwright_user_data")
        context = p.chromium.launch_persistent_context(
            user_data_dir,
            headless=False,
            slow_mo=1000,
            args=["--disable-blink-features=AutomationControlled"]
        )
        
        # Clear cookies to ensure a fresh login session for testing
        print("Clearing cookies to force fresh login...")
        context.clear_cookies()
        
        page = context.pages[0] if context.pages else context.new_page()
        
        print("Navigating to http://localhost:3000...")
        try:
            page.goto("http://localhost:3000", timeout=30000, wait_until="domcontentloaded")
        except Exception as e:
            print(f"Navigation failed: {e}")
            context.close()
            sys.exit(1)

        print("Checking page title...")
        try:
            title = page.title()
            print(f"Page title: {title}")
            if "Relack" not in title:
                print("Error: Title does not contain 'Relack'")
                context.close()
                sys.exit(1)
        except Exception as e:
            print(f"Failed to check title: {e}")
            context.close()
            sys.exit(1)
        # Check if already logged in
        print("Checking if already logged in...")
        try:
            logout_btn = page.get_by_text("Logout")
            if logout_btn.is_visible(timeout=3000):
                print("User is already logged in. Logging out to test login flow...")
                logout_btn.click()
                # Wait for logout to complete
                logout_btn.wait_for(state="hidden", timeout=5000)
                print("Logged out successfully.")
                
                # Reload the page to ensure the Google button script re-initializes correctly
                print("Reloading page to reset Google Sign-In state...")
                page.reload()
                page.wait_for_load_state("domcontentloaded")
                time.sleep(2) # Give GSI script time to load
                
        except Exception as e:
            print(f"User is not logged in or logout failed: {e}")

        # Test Google Login Button Presence
        print("Looking for Google Sign-In button...")
        try:
            # The Google button is usually in an iframe rendered by the GSI library.
            # We will look for it in frames, but also check the main page just in case.
            
            google_button = None
            
            # Retry loop to find the button
            for i in range(15):
                # Check frames for GSI button
                for frame in page.frames:
                    if "gsi/button" in frame.url:
                        # Found the GSI iframe
                        btn = frame.locator("[role='button']").first
                        if btn.is_visible():
                            google_button = btn
                            print("Found Google Sign-In button (in GSI iframe).")
                            break
                
                if google_button:
                    break
                    
                time.sleep(1)
                print(f"Waiting for Google button... ({i+1}/15)")
            
            if google_button:
                print("Attempting to click Google Sign-In button...")
                # Setup a listener for the popup before clicking
                with page.expect_popup() as popup_info:
                    google_button.click()

                popup = popup_info.value
                print("Popup opened successfully!")
                
                # Wait for the popup to load content
                try:
                    popup.wait_for_load_state("domcontentloaded")
                    print(f"Popup title: {popup.title()}")
                    print(f"Popup URL: {popup.url}")
                    
                    if "accounts.google.com" in popup.url:
                        print("Verified: Popup is a Google login page.")
                        
                        print("Filling email 'joanmirochen@gmail.com'...")
                        # Wait for the email input field
                        email_input = popup.locator("input[type='email']")
                        email_input.wait_for()
                        email_input.fill("joanmirochen@gmail.com")
                        print("Email filled successfully.")
                        
                        # Click Next button automatically
                        print("Attempting to click Next button...")
                        try:
                            # Try specific ID first (common in Google login)
                            next_btn = popup.locator("#identifierNext")
                            if next_btn.is_visible():
                                next_btn.click()
                                print("Clicked Next button (by ID).")
                            else:
                                # Fallback to finding button by text
                                popup.get_by_role("button").filter(has_text="Next").first.click()
                                print("Clicked Next button (by text).")
                        except Exception as e:
                            print(f"Could not click Next button automatically: {e}")

                        # Take a screenshot of the filled popup
                        popup.screenshot(path=os.path.join(output_dir, "google_popup_filled.png"))
                        
                        print("\n" + "="*60)
                        print("MANUAL INTERACTION REQUIRED")
                        print("Please complete the Google login process in the popup window.")
                        print("Enter password, handle 2FA, etc.")
                        print("="*60 + "\n")
                        
                        input("Press Enter AFTER you have successfully logged in and the popup has closed...")

                    else:
                        print("Warning: Popup URL does not look like Google login.")
                        
                except Exception as e:
                    print(f"Error inspecting popup: {e}")
                finally:
                    print("Closing popup handle (if still open)...")
                    try:
                        popup.close()
                    except:
                        pass

                # Verify Login Success
                print("Verifying login success...")
                try:
                    # Wait for the main page to update. It might take a few seconds after popup closes.
                    # Check for Logout button which appears in Navbar when logged in
                    print("Waiting for 'Logout' button...")
                    page.get_by_text("Logout").wait_for(timeout=15000)
                    print("Success: 'Logout' button found.")
                    
                    # Check for Rooms list (e.g. "General")
                    if page.get_by_text("General").is_visible():
                        print("Success: 'General' room found.")
                    
                    page.screenshot(path=os.path.join(output_dir, "login_success.png"))
                    print("Login verification passed!")
                    
                except Exception as e:
                    print(f"Login verification failed: {e}")
                    page.screenshot(path=os.path.join(output_dir, "login_verification_failed.png"))
                    raise e

            else:
                # It might be the One Tap or the button might be rendered differently.
                # Let's try to find the button by text in the main page or frames.
                pass

            # Taking a screenshot to verify the button is visible
            page.screenshot(path=os.path.join(output_dir, "google_login_page.png"))
            print("Screenshot taken.")

            # Note: Clicking the button and logging in is complex due to security protections and 2FA.
            # For this test case, we verify the page loads and the auth container is present.
            
            # Verify the "OR" separator is present, which confirms the auth container structure
            # Use exact=True to avoid matching other text containing "OR"
            if page.get_by_text("OR", exact=True).is_visible():
                print("Auth container structure verified (OR separator found).")
            else:
                print("Warning: 'OR' separator not found.")

        except Exception as e:
            print(f"Google login test failed: {e}")
            page.screenshot(path=os.path.join(output_dir, "google_login_failure.png"))
            context.close()
            sys.exit(1)

        print("Test finished (Button presence check).")
        context.close()

if __name__ == "__main__":
    run()
