from playwright.sync_api import sync_playwright
import sys
import time
import select

def run():
    with sync_playwright() as p:
        print("Launching browser with persistent context...")
        # Use a persistent context to avoid Incognito mode and save login state
        # This allows Google Login to work and persist across runs if needed
        user_data_dir = "./playwright_user_data"
        context = p.chromium.launch_persistent_context(
            user_data_dir,
            headless=False,
            slow_mo=1000,
            args=["--disable-blink-features=AutomationControlled"]
        )
        
        if len(context.pages) > 0:
            page = context.pages[0]
        else:
            page = context.new_page()
        
        print("Navigating to http://localhost:3000...")
        try:
            page.goto("http://localhost:3000", timeout=30000, wait_until="domcontentloaded")
        except Exception as e:
            print(f"Navigation failed: {e}")
            context.close()
            sys.exit(1)

        print("Testing Google Login UI...")
        try:
            # Click the 'Google Login' tab button.
            print("Clicking 'Google Login' tab...")
            page.get_by_role("button", name="Google Login").click()
            
            print("Checking for 'Sign In with Google' text...")
            # Wait for the text to appear
            page.wait_for_selector("text=Sign In with Google", timeout=5000)
            
            print("Success: Google Login UI is visible.")
            
            # Setup auto-fill for Google Login popup
            target_email = "joanmirochen@gmail.com"
            
            def handle_popup(popup):
                print(f"New window detected: {popup.url}")
                if "accounts.google.com" in popup.url:
                    print("Google Login popup detected.")
                    try:
                        popup.wait_for_load_state("domcontentloaded")
                        print(f"Auto-filling email: {target_email}")
                        popup.wait_for_selector("input[type='email']", timeout=10000).fill(target_email)
                        print("Email filled. Clicking Next...")
                        popup.get_by_role("button", name="Next").click()
                    except Exception as e:
                        print(f"Could not auto-fill email: {e}")

            context.on("page", handle_popup)

            print("\n" + "="*60)
            print("USER ACTION REQUIRED:")
            print("1. Please manually click the 'Sign in with Google' button in the browser.")
            print(f"2. The script will attempt to fill '{target_email}' for you.")
            print("3. Enter your password manually.")
            print("4. Complete the login process.")
            print("Waiting 60 seconds for login to complete...")
            print("="*60 + "\n")

            # Wait for login success (either Registration form or Dashboard)
            # We look for "Finish Profile" (registration) or "Channels"/"Direct Messages" (dashboard)
            # or the welcome toast.
            
            try:
                # Wait up to 60 seconds for the user to log in
                # We look for the "Finish Profile" header which appears for new users
                # OR a known element from the dashboard/navbar for existing users
                # For now, let's look for the registration header or the user profile link/avatar
                
                # Note: We use a predicate or multiple selectors if possible, but wait_for_selector takes one.
                # We'll try to wait for the registration form first, as that's the likely next step for a new test user.
                # If the user is already registered, they might go straight to dashboard.
                
                # Let's wait for *any* change that indicates auth success.
                # The "Sign In with Google" text should disappear or we navigate away.
                
                print("Waiting for 'Finish Profile' screen or Dashboard...")
                print("(Tip: Press ENTER 3 times in the terminal to abort waiting immediately)")
                
                # We can loop and check multiple conditions
                start_time = time.time()
                logged_in = False
                enter_presses = 0

                while time.time() - start_time < 60:
                    # Check for manual abort via stdin (Enter key)
                    # select.select([sys.stdin], [], [], 0) checks if stdin has data waiting
                    if sys.stdin in select.select([sys.stdin], [], [], 0)[0]:
                        _ = sys.stdin.readline()
                        enter_presses += 1
                        print(f"Abort counter: {enter_presses}/3")
                        if enter_presses >= 3:
                             raise Exception("Manual abort: User pressed Enter 3 times.")

                    if page.get_by_text("Finish Profile").is_visible():
                        print("Detected Registration Screen ('Finish Profile').")
                        
                        # Auto-fill registration if we are here
                        print("Auto-filling registration form...")
                        page.get_by_placeholder("Choose a display name").fill("ManualTestUser")
                        page.get_by_role("button", name="Create Profile").click()
                        logged_in = True
                        break
                        
                    if page.get_by_text("Welcome back").is_visible():
                        print("Detected 'Welcome back' toast.")
                        logged_in = True
                        break
                        
                    # Check for dashboard elements (e.g. if we have a logout button or profile)
                    # Assuming 'Guest' tab is gone is also a sign, but let's look for positive confirmation.
                    # If we are logged in, the auth_container is replaced by chat_dashboard.
                    # Let's look for something unique to chat_dashboard.
                    # Based on index.py: rx.cond(AuthState.user, chat_dashboard(), welcome_hero())
                    # If chat_dashboard is active, welcome_hero is gone.
                    if not page.get_by_text("Relack: Real-Time Chat Evolved.").is_visible():
                         # Double check we are not just loading
                         if page.get_by_text("Channels").is_visible() or page.get_by_text("Direct Messages").is_visible():
                             print("Detected Dashboard.")
                             logged_in = True
                             break
                    
                    page.wait_for_timeout(1000)
                
                if not logged_in:
                    raise Exception("Timeout waiting for login.")
                
                print("Login flow completed successfully!")
                
                # Optional: Take a screenshot of the result
                page.wait_for_timeout(2000) # Wait for animations
                page.screenshot(path="google_login_success.png")
                
            except Exception as e:
                print(f"Login wait failed: {e}")
                page.screenshot(path="google_login_timeout.png")
                # Don't fail the test hard if it's just a manual timeout, 
                # but strictly speaking the test failed to verify login.
                sys.exit(1)
            
        except Exception as e:
            print(f"Google Login UI test failed: {e}")
            page.screenshot(path="google_login_failure.png")
            context.close()
            sys.exit(1)

        print("Google Login Test passed!")
        context.close()

if __name__ == "__main__":
    run()
