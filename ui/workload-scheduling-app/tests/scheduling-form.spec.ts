import { test, expect } from '@playwright/test';

test.describe('Scheduling Form Inputs', () => {
    test.beforeEach(async ({ page }) => { await page.goto('http://localhost:3000/'); });

    test('07. Job Type Selection State', async ({ page }) => {
        await page.getByLabel('Job Type').selectOption('inference');
        await expect(page.getByLabel('Job Type')).toHaveValue('inference');
    });

    test('08. GPU Count Numeric Boundary', async ({ page }) => {
        await page.getByLabel('GPU Count').fill('999');
        await expect(page.getByLabel('GPU Count')).toHaveValue('999');
    });

    test('09. Preferred DC Filter Logic', async ({ page }) => {
        const select = page.getByLabel(/Preferred Data Center/i);
        await select.selectOption({ index: 1 });
        await expect(select).not.toHaveValue('none');
    });

    test('10. Loading Spinner on Submit', async ({ page }) => {
        await page.getByRole('button', { name: 'Schedule Job' }).click();
        await expect(page.locator('.animate-spin')).toBeVisible();
    });

    test('11. Form Validation Alert', async ({ page }) => {
        await page.getByLabel('GPU Count').fill('');
        await page.getByRole('button', { name: 'Schedule Job' }).click();
        await expect(page.locator('role=alert')).toBeVisible();
    });

    test('12. Navigation to Results Page', async ({ page }) => {
        await page.getByRole('button', { name: 'Schedule Job' }).click();
        await page.waitForURL(/\/schedule\/.+/);
        await expect(page).toHaveURL(/\/schedule\//);
    });
});