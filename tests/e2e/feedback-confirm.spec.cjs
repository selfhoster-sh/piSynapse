// @ts-check
const { test, expect } = require('@playwright/test');
const { installBackendStubs, boot } = require('./stubs.cjs');

async function sendTurn(page, text = 'Merhaba') {
  await page.fill('#msg-input', text);
  await page.press('#msg-input', 'Enter');
}

test.describe('tool confirmation flow', () => {
  test('audited call renders real thumbs merged into the message action bar', async ({ page }) => {
    await installBackendStubs(page);
    await boot(page);
    await sendTurn(page);

    const status = page.locator('.tool-status');
    await expect(status).toHaveCount(1);
    await expect(status.locator('.fb-up')).toHaveCount(1);
    await expect(status.locator('.mark-btn')).toHaveCount(1);
    // The copy/listen/regen bar and the thumbs share the SAME row.
    await expect(status.locator('.copy-btn')).toHaveCount(1);
    const sameRow = await page.evaluate(() => {
      const up = document.querySelector('.tool-status .fb-up');
      const copy = document.querySelector('.tool-status .copy-btn');
      return !!up && !!copy && up.parentElement === copy.parentElement;
    });
    expect(sameRow).toBeTruthy();
    await expect(status.locator('.mark-btn')).toHaveAttribute('title', /Yanlış|Wrong/i);
    await expect(status.locator('.fb-up')).toHaveAttribute('title', /Doğru|Correct/i);
  });

  test('thumbs-up posts {audit_id} as a confirmation, no picker is opened', async ({ page }) => {
    const stubs = await installBackendStubs(page);
    await boot(page);
    await sendTurn(page);

    await page.click('.tool-status .fb-up');

    await expect(page.locator('.tool-status .fb-up.active')).toHaveCount(1);
    await expect(page.locator('.group-picker')).toHaveCount(0);
    expect(stubs.sentConfirmations).toHaveLength(1);
    expect(stubs.sentConfirmations[0]).toEqual({ audit_id: 123 });
    expect(stubs.sentCorrections).toHaveLength(0);
  });

  test('confirmation and correction are mutually exclusive in the UI', async ({ page }) => {
    const stubs = await installBackendStubs(page);
    await boot(page);
    await sendTurn(page);

    await page.click('.tool-status .fb-up');
    await expect(page.locator('.tool-status .fb-up.active')).toHaveCount(1);

    // Correct afterwards: the picker re-opens, the correction lands and the
    // up thumb loses its active look.
    await page.click('.tool-status .mark-btn');
    await expect(page.locator('.group-picker')).toHaveCount(1);
    await page.click('.group-picker .gp-opt');
    await page.click('.group-picker .gp-save');
    await expect(page.locator('.mark-btn.marked')).toHaveCount(1);
    await expect(page.locator('.fb-up.active')).toHaveCount(0);
    expect(stubs.sentConfirmations).toHaveLength(1);
    expect(stubs.sentCorrections).toHaveLength(1);

    // Re-confirm: the up thumb lights back up and the down thumb clears.
    await page.click('.tool-status .fb-up');
    await expect(page.locator('.tool-status .fb-up.active')).toHaveCount(1);
    await expect(page.locator('.mark-btn.marked')).toHaveCount(0);
    expect(stubs.sentConfirmations).toHaveLength(2);
  });

  test('confirmation API error surfaces a visible toast and leaves the thumb unlit', async ({ page }) => {
    const stubs = await installBackendStubs(page, { confirmError: true });
    await boot(page);
    await sendTurn(page);

    await page.click('.tool-status .fb-up');

    await expect(page.locator('#toast')).toContainText('500');
    await expect(page.locator('.tool-status .fb-up.active')).toHaveCount(0);
    await expect(page.locator('.tool-status .fb-up')).toBeEnabled(); // retry possible
    expect(stubs.sentConfirmations).toHaveLength(1);
  });

  test('no audit_id: universal thumbs still render as a message-level pair', async ({ page }) => {
    // C-12 feedback: a round with no audited tool call keeps a 👍/👎 pair so
    // it stays markable (the down thumb captures a message-level verdict +
    // optional note instead of a tool correction).
    await installBackendStubs(page, { auditId: null });
    await boot(page);
    await sendTurn(page);

    await expect(page.locator('.tool-status')).toHaveCount(1);
    await expect(page.locator('.tool-status .mark-btn')).toHaveCount(1);
    await expect(page.locator('.tool-status .fb-up')).toHaveCount(1);
  });
});