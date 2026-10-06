import { test, expect } from '@playwright/test';
import path from 'path';

test.describe('E-Sign Document Upload and Envelope Creation Workflow', () => {
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

  test('should successfully upload a document, place signature, and dispatch envelope', async ({ page }) => {
    // 1. Start on the authenticated workspace homepage
    await page.goto('/');
    
    // Assert dashboard loaded successfully
    await expect(page.locator('text=E-Sign Workspace')).toBeVisible();

    // 2. Click "Create New Request" CTA button
    const createRequestCta = page.locator('text=Create New Request').first();
    await createRequestCta.click();

    // Verify redirect to /create-request
    await expect(page).toHaveURL(/.*\/create-request/);

    // 3. Document Tab: Upload approved test PDF
    const fileInput = page.locator('#pdf-upload');
    await expect(fileInput).toBeVisible();

    const pdfPath = '../esign-backend/tests/عقد عميل.pdf';
    await fileInput.setInputFiles(pdfPath);

    // Wait for upload/validation & Gemini contract authority analysis to finish
    // This makes the "Continue to Recipients" button active.
    const continueRecipientsBtn = page.locator('button:has-text("Continue to Recipients")');
    await expect(continueRecipientsBtn).toBeEnabled({ timeout: 60000 });
    await continueRecipientsBtn.click();

    // 4. Recipients Tab: Configure signing workflow
    // Fill full name and email address for the first signer in the step
    const nameInput = page.getByPlaceholder('Full Name').first();
    const emailInput = page.getByPlaceholder('Email Address').first();

    await expect(nameInput).toBeVisible();
    await nameInput.fill('Alice Signer');
    await emailInput.fill('alice@example.com');

    // Click "Continue to Prepare"
    const continuePrepareBtn = page.locator('button:has-text("Continue to Prepare")');
    await expect(continuePrepareBtn).toBeVisible();
    await continuePrepareBtn.click();

    // 5. Prepare Tab: Place target signature zone on the PDF page
    // Wait for the PDF document preview viewport to load
    const pdfPage = page.locator('.react-pdf__Page').first();
    await expect(pdfPage).toBeVisible({ timeout: 20000 });

    // Click on the center of the first page to place a signature zone coordinates
    await pdfPage.click({ position: { x: 150, y: 150 } });

    // Click "Continue to Settings"
    const continueSettingsBtn = page.locator('button:has-text("Continue to Settings")');
    await expect(continueSettingsBtn).toBeEnabled();
    await continueSettingsBtn.click();

    // 6. Settings Tab: Proceed with default options
    const continueReviewBtn = page.locator('button:has-text("Continue to Review")');
    await expect(continueReviewBtn).toBeVisible();
    await continueReviewBtn.click();

    // 7. Review Tab: Validate checklist summary and dispatch package
    const sendPackageBtn = page.locator('button:has-text("Send Package")');
    await expect(sendPackageBtn).toBeEnabled();
    
    // Dispatch and monitor network response
    await Promise.all([
      page.waitForResponse(resp => resp.url().includes('/api/v1/envelopes/') && resp.url().includes('/send/') && resp.status() === 200, { timeout: 30000 }),
      sendPackageBtn.click(),
    ]);

    // 8. Verify Successful Dispatch page
    await expect(page.locator('text=Workflow Dispatched')).toBeVisible({ timeout: 20000 });
    await expect(page.locator('text=عقد عميل.pdf')).toBeVisible();

    // 9. Verify no application-generated console output was leaked
    expect(appConsoleMessages).toHaveLength(0);
  });
});
