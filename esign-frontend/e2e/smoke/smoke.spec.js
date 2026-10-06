import { test, expect } from '@playwright/test';

// Reset storage state for smoke tests so they start unauthenticated
test.use({ storageState: { cookies: [], origins: [] } });

test.describe('E-Sign Frontend Smoke Test', () => {
  test('should load the gateway page and show the login form', async ({ page }) => {
    // Navigate to the root page (which redirects to /login)
    await page.goto('/');

    // Check that we are redirected to /login (or URL contains /login)
    await expect(page).toHaveURL(/.*\/login/);

    // Verify E-Sign Security Gateway banner is visible
    const banner = page.locator('text=E-Sign Security Gateway');
    await expect(banner).toBeVisible();

    // Verify welcome text is visible
    const heading = page.locator('text=Welcome back');
    await expect(heading).toBeVisible();
  });
});
