# Admin Login Test Case

This test case verifies the functionality of the Admin Dashboard login and logout flow.

## Steps
1. Navigate to the home page (`http://localhost:3000`).
2. Click on the "Administrator Settings" button in the top-right corner.
3. Verify that the "Admin Login" panel is displayed.
4. Enter the correct `ADMIN_PASSCODE` (loaded from `.env`).
5. Click the "Login" button.
6. Verify that the "Admin Dashboard" is displayed (checking for the header and tabs).
7. Click the "Logout" button.
8. Verify that the user is redirected back to the "Admin Login" panel.

## Prerequisites
- The Reflex app must be running.
- `ADMIN_PASSCODE` must be set in the `.env` file.
