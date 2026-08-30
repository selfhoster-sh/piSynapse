// @ts-check
const { test, expect } = require('@playwright/test');
const { installBackendStubs, boot } = require('./stubs.cjs');

test.describe('new-chat button press feedback (sticky-hover leak)', () => {
  test('touch + glass: tapping the top new-chat button leaves it at rest scale', async ({ browser }) => {
    const page = await browser.newPage({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });
    await installBackendStubs(page);
    await boot(page);
    await page.evaluate(() => applyGlass(true));

    const btn = page.locator('.top-new-btn');
    const box = await btn.boundingBox();
    await page.touchscreen.tap(box.x + box.width / 2, box.y + box.height / 2);

    // Regression: an ungated :hover{transform:scale(1.02)} made touch :hover
    // sticky, so a tap left the CTA permanently enlarged and the press effect
    // looked broken. The resting transform must return to none.
    await expect(btn).toHaveCSS('transform', 'none');
  });

  test('desktop: hover still enlarges the CTA (hover effect preserved)', async ({ page }) => {
    await installBackendStubs(page);
    await boot(page);

    const btn = page.locator('#btn-new');
    const box = await btn.boundingBox();
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);

    await expect(btn).toHaveCSS('transform', /matrix\(1\.0[1-9]/);
  });
});