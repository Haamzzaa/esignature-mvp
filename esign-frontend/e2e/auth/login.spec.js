import { test, expect } from '@playwright/test';

// Reset storage state for login tests so they start unauthenticated
test.use({ storageState: { cookies: [], origins: [] } });

test.describe('E-Sign Authentication Flow', () => {
  // Console logging auditor
  let appConsoleMessages = [];
  
  test.beforeEach(async ({ page }) => {
    appConsoleMessages = [];
    page.on('console', msg => {
      const text = msg.text();
      // Detect specific application log formats that we audited
      if (
        text.includes('VITE_API_URL') ||
        text.includes('API_REQUEST_PAYLOAD') ||
        text.includes('Failed to load user with current token') ||
        text.includes('Logout error on server') ||
        text.includes('[Camera Debug]') ||
        text.includes('Auto draft/analysis failed')
      ) {
        appConsoleMessages.push({ type: msg.type(), text });
      }
    });
  });

  test('should fail login with invalid credentials and show error', async ({ page }) => {
    await page.goto('/login');

    // Verify fields are visible
    const usernameInput = page.getByPlaceholder('enter username');
    const passwordInput = page.getByPlaceholder('enter password');
    const submitButton = page.locator('button[type="submit"]');

    await expect(usernameInput).toBeVisible();
    await expect(passwordInput).toBeVisible();

    // Fill invalid credentials
    await usernameInput.fill('invalid_e2e_user');
    await passwordInput.fill('invalid_e2e_password');

    // Click Sign In
    await submitButton.click();

    // Verify error is shown in the UI
    const errorAlert = page.locator('text=Invalid credentials.');
    await expect(errorAlert).toBeVisible();

    // Verify URL remains on login page
    await expect(page).toHaveURL(/.*\/login/);

    // Verify no application-generated console output was leaked
    expect(appConsoleMessages).toHaveLength(0);
  });

  test('should login successfully with valid credentials and redirect to dashboard', async ({ page }) => {
    // Read credentials from environment variables
    const username = process.env.E2E_USERNAME;
    const password = process.env.E2E_PASSWORD;

    // Check if credentials are provided in env, else skip
    if (!username || !password) {
      console.warn('E2E_USERNAME and E2E_PASSWORD are not defined. Skipping success login test.');
      test.skip();
      return;
    }

    await page.goto('/login');

    const usernameInput = page.getByPlaceholder('enter username');
    const passwordInput = page.getByPlaceholder('enter password');
    const submitButton = page.locator('button[type="submit"]');

    // Fill valid credentials
    await usernameInput.fill(username);
    await passwordInput.fill(password);

    // Click Sign In and wait for navigation
    await Promise.all([
      page.waitForURL(/\/$/), // Wait for redirect to root
      submitButton.click(),
    ]);

    // Verify we landed on the home page (dashboard)
    await expect(page).toHaveURL(/\/$/);

    // Assert that the main dashboard heading is visible
    const heading = page.locator('text=E-Sign Workspace');
    await expect(heading).toBeVisible();
    
    // Check that localStorage now contains the authentication token
    const tokenExists = await page.evaluate(() => {
      const token = localStorage.getItem('token');
      return !!token; // Returns true/false without exposing the actual token value
    });
    expect(tokenExists).toBe(true);

    // Verify no application-generated console output was leaked
    expect(appConsoleMessages).toHaveLength(0);
  });
});
