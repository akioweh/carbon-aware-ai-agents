import { test, expect } from '@playwright/test';

test.describe('Global Workload Calendar', () => {
    test.beforeEach(async ({ page }) => { await page.goto('http://localhost:3000/workload-calendar'); });

    test('18. Toggle Carbon-Intensity Layer', async ({ page }) => {
        await page.getByText('Carbon-Intensity').click();
        await expect(page.locator('.recharts-line')).toHaveCount(1);
    });

    test('19. Toggle Capacity Layer', async ({ page }) => {
        await page.getByText('Capacity').click();
        await expect(page.locator('.recharts-line')).toHaveCount(2);
    });

    test('20. Now Reference Line Orientation', async ({ page }) => {
        await expect(page.locator('text=Now')).toBeVisible();
    });

    test('21. Responsive Scroll Check', async ({ page }) => {
        const container = page.locator('.overflow-x-auto');
        await expect(container).toBeVisible();
    });
});