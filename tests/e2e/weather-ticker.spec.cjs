// @ts-check
const { test, expect } = require('@playwright/test');
const { installBackendStubs, boot } = require('./stubs.cjs');

const ticker = page => page.locator('#ticker-text-inner');

test.describe('weather ticker widget', () => {
  test('condition label is localized when the UI language changes', async ({ page }) => {
    await installBackendStubs(page); // stub: temp 22, wmo_code 0 ("Açık"/clear)
    await boot(page);

    // Playwright boots with en-US locale → app defaults to English.
    await expect(ticker(page)).toContainText('22°C · Clear');
    // Clear-condition icon: a sun (has a <circle>), distinct from the generic sun-cloud.
    expect(await ticker(page).locator('svg circle').count()).toBeGreaterThan(0);

    await page.evaluate(() => applyLang('tr'));

    await expect(ticker(page)).toContainText('22°C · Açık');

    await page.evaluate(() => applyLang('en'));
    await expect(ticker(page)).toContainText('22°C · Clear');
  });

  test('icon and label follow the reported condition kind (storm)', async ({ page }) => {
    await installBackendStubs(page);
    await boot(page);

    // Re-route the weather widget to a thunderstorm payload and refresh.
    await page.route('**/widget/weather', route => route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ ok: true, city: 'Akşehir', temp_c: 18, feels_c: 17,
        condition: 'Gök gürültülü', wmo_code: 95, kind: 'storm',
        summary: 'Akşehir: 18°C, Gök gürültülü, feels like 17°C' }),
    }));
    await page.evaluate(async () => { await refreshTicker(); });

    await expect(ticker(page)).toContainText('18°C · Thunderstorm');
    // Lightning bolt path (storm icon) is rendered.
    expect(await ticker(page).locator("svg path[d='m13 12-3 5h4l-3 5']").count()).toBeGreaterThan(0);

    await page.evaluate(() => applyLang('tr'));
    await expect(ticker(page)).toContainText('18°C · Gök gürültülü');
  });
});