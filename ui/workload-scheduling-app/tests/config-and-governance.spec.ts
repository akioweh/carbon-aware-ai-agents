import { test, expect } from '@playwright/test';

test.describe('Data Center Configuration & Map', () => {
    test.beforeEach(async ({ page }) => { await page.goto('http://localhost:3000/config'); });

    test('01. Toggle DC and Verify Change State', async ({ page }) => {
        const saveBtn = page.getByRole('button', { name: 'Save Configuration' });
        await expect(saveBtn).toBeDisabled();
        await page.getByRole('switch').first().click();
        await expect(saveBtn).toBeEnabled();
    });

    test('02. Zero-Active State Error Visibility', async ({ page }) => {
        const switches = await page.getByRole('switch', { checked: true }).all();
        for (const s of switches) { await s.click(); }
        await expect(page.getByText(/at least one data centre must be active/i)).toBeVisible();
        await expect(page.getByRole('button', { name: 'Save Configuration' })).toBeDisabled();
    });

    test('03. Map Marker Tooltip Display', async ({ page }) => {
        await page.locator('.leaflet-marker-icon').first().hover();
        await expect(page.locator('.leaflet-tooltip')).toBeVisible();
    });

    test('04. Map Selection Syncs with List', async ({ page }) => {
        await page.locator('.leaflet-interactive').first().click();
        await expect(page.locator('li.bg-muted\\/50')).toBeVisible();
    });

    test('05. Persistence Handshake on Success', async ({ page }) => {
        await page.getByRole('switch').first().click();
        await page.getByRole('button', { name: 'Save Configuration' }).click();
        await expect(page.getByText('Configuration saved')).toBeVisible();
    });

    test('06. Back Button Navigation', async ({ page }) => {
        await page.getByRole('button', { name: 'Back' }).click();
        await expect(page).toHaveURL('http://localhost:3000/');
    });
});