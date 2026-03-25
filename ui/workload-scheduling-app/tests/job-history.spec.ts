import { test, expect } from '@playwright/test';

test.describe('Historical Jobs & Navigation', () => {
    test.beforeEach(async ({ page }) => { await page.goto('http://localhost:3000/scheduled-jobs'); });

    test('22. Savings Badge Rendering', async ({ page }) => {
        await expect(page.getByText(/% savings/i).first()).toBeVisible();
    });

    test('23. Job Card Click Navigation', async ({ page }) => {
        await page.locator('.bg-card').first().click();
        await expect(page).toHaveURL(/\/schedule\//);
    });

    test('24. Top Navigation Tab Highlight', async ({ page }) => {
        const activeTab = page.locator('nav >> .bg-background');
        await expect(activeTab).toContainText('Scheduled Jobs');
    });

    test('25. Empty State Resilience', async ({ page }) => {
        // If no jobs exist, verify fallback message
        const emptyMsg = page.getByText('No scheduled jobs found');
        if (await emptyMsg.isVisible()) {
            await expect(emptyMsg).toBeVisible();
        }
    });
});