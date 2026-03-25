// playwright.config.ts
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  // ... existing config ...
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        launchOptions: {
          executablePath: '/usr/sbin/chromium', // The "Arch Fix"
        },
      },
    },
    /* You can delete or comment out Firefox/Mobile/Webkit 
       to avoid errors about missing those browsers */
  ],
});