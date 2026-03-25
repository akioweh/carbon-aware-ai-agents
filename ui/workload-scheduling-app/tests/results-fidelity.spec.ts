import { test, expect } from '@playwright/test';

test.describe('Result Details & Analytics', () => {
    test('13. Toggle Unoptimised vs Optimised Tab', async ({ page }) => {
        await page.goto('http://localhost:3000/schedule/test-id');
        await page.getByRole('button', { name: 'Unoptimised' }).click();
        await expect(page.locator('button[data-state="active"]')).toContainText('Unoptimised');
    });

    test('14. Metric Card Visibility', async ({ page }) => {
        await page.goto('http://localhost:3000/schedule/test-id');
        await expect(page.getByText('Carbon Intensity')).toBeVisible();
        await expect(page.getByText('Total Emissions')).toBeVisible();
    });

    test('15. Data Center Specific Tabs', async ({ page }) => {
        await page.goto('http://localhost:3000/schedule/test-id');
        const dcTab = page.getByRole('tab', { name: /Data Center/i }).nth(1);
        await dcTab.click();
        await expect(dcTab).toHaveAttribute('aria-selected', 'true');
    });

    test('16. Delete Confirmation Logic', async ({ page }) => {
        await page.goto('http://localhost:3000/schedule/test-id');
        await page.locator('.lucide-trash2').click();
        await expect(page.getByRole('alertdialog')).toBeVisible();
    });

    test('17. Chart Tooltip on Hover', async ({ page }) => {
        await page.goto('http://localhost:3000/schedule/test-id');
        await page.locator('.recharts-surface').hover();
        await expect(page.locator('.recharts-tooltip-wrapper')).toBeVisible();
    });
});