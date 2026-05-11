/**
 * 共享认证 Fixtures
 * 所有需要认证的测试都应使用此 fixtures 进行登录
 */
import { test as base } from '@playwright/test';

const TEST_EMAIL = process.env.TEST_EMAIL || 'mr_yang@example.com';
const TEST_PASSWORD = process.env.TEST_PASSWORD || '12345678';

async function apiLogin(page, email = TEST_EMAIL, password = TEST_PASSWORD) {
  await page.goto('/');
  await page.waitForLoadState('domcontentloaded');
  await page.waitForTimeout(500);

  // Check if already logged in
  const existingToken = await page.evaluate(() => localStorage.getItem('access_token'));
  if (existingToken) return true;

  // Click login button in sidebar
  const loginBtn = page.locator('.login-prompt button');
  const loginVisible = await loginBtn.isVisible({ timeout: 5000 }).catch(() => false);
  if (!loginVisible) {
    // Might already be logged in
    const token = await page.evaluate(() => localStorage.getItem('access_token'));
    return !!token;
  }

  await loginBtn.click();
  await page.waitForTimeout(500);

  // Wait for modal inputs
  await page.waitForSelector('input[type="email"]', { timeout: 3000 }).catch(() => {});

  // Fill credentials
  const emailInput = page.locator('input[type="email"]').first();
  const passwordInput = page.locator('input[type="password"]').first();

  try {
    await emailInput.fill(email);
    await passwordInput.fill(password);
  } catch {
    // Fallback: find all inputs in the modal
    const inputs = page.locator('[class*="modal"] input, [class*="dialog"] input');
    const count = await inputs.count();
    if (count >= 2) {
      await inputs.nth(0).fill(email);
      await inputs.nth(1).fill(password);
    }
  }

  // Click login
  const submitBtn = page.locator('button[class*="btn-login"], button:has-text("登录")').first();
  await submitBtn.click();
  await page.waitForTimeout(2000);

  const token = await page.evaluate(() => localStorage.getItem('access_token'));
  return !!token;
}

async function logout(page) {
  // Navigate to the app page first, then clear storage
  await page.goto('/');
  await page.waitForLoadState('domcontentloaded');

  // Clear storage from within the same origin
  await page.evaluate(() => {
    localStorage.clear();
    sessionStorage.clear();
  });

  // Clear cookies
  const context = page.context();
  await context.clearCookies();

  // Reload to apply state
  await page.reload({ waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(500);
}

export const test = base.extend({
  authenticatedPage: async ({ page }, use) => {
    await apiLogin(page);
    await use(page);
  },
});

export { apiLogin, logout, TEST_EMAIL, TEST_PASSWORD };
