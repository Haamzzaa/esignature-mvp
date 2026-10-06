import { test as setup, expect } from '@playwright/test';
import path from 'path';

const authFile = 'e2e/.auth/user.json';

setup('authenticate user and save storage state', async ({ page }) => {
  const username = process.env.E2E_USERNAME;
  const password = process.env.E2E_PASSWORD;

  if (!username || !password) {
    throw new Error('E2E_USERNAME and E2E_PASSWORD environment variables are required for E2E authentication setup.');
  }

  // Navigate to login
  await page.goto('/login');

  // Fill in credentials
  await page.getByPlaceholder('enter username').fill(username);
  await page.getByPlaceholder('enter password').fill(password);

  // Click Sign In and wait for redirect to root
  const submitButton = page.locator('button[type="submit"]');
  await Promise.all([
    page.waitForURL(/\/$/),
    submitButton.click(),
  ]);

  // Assert successful landing on home page
  await expect(page).toHaveURL(/\/$/);
  const dashboardHeading = page.locator('text=E-Sign Workspace');
  await expect(dashboardHeading).toBeVisible();

  // Assert token exists in localStorage
  const tokenExists = await page.evaluate(() => {
    const token = localStorage.getItem('token');
    return !!token;
  });
  expect(tokenExists).toBe(true);

  // Save storage state to file
  await page.context().storageState({ path: authFile });
});
