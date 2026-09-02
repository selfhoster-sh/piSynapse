// @ts-check
// D-1: a scope tool whose run could not be backend-verified (verification_status
// unverified | verification_failed) must settle as an amber "could not verify"
// warning WITHOUT the 👍/👎 pair — the ok flag alone is no longer ground truth
// for these tools. A verified status keeps the ordinary audit-bound thumbs.
const { test, expect } = require('@playwright/test');
const { installBackendStubs, boot } = require('./stubs.cjs');

async function sendTurn(page, text = 'notumu kaydet') {
  await page.fill('#msg-input', text);
  await page.press('#msg-input', 'Enter');
}

function scopedTool(status, ok = true) {
  return [
    { tool: { name: 'create_note', phase: 'start' } },
    { tool: { name: 'create_note', phase: 'end', ok, audit_id: 501, verification_status: status } },
    { token: 'Yanıt geldi.' },
    { done: true },
  ];
}

test.describe('verification_status warn state', () => {
  for (const status of ['unverified', 'verification_failed']) {
    test(`${status}: warning shown, no confirmation pair`, async ({ page }) => {
      await installBackendStubs(page, { auditId: 501, stream: () => scopedTool(status) });
      await boot(page);
      await sendTurn(page);

      const row = page.locator('.tool-status.done');
      await expect(row).toHaveCount(1);
      await expect(row).toHaveClass(/warn/);
      await expect(row).not.toHaveClass(/ok/);
      await expect(row.locator('.fb-state')).toHaveText(/doğrulanamadı|verification|check/i);
      await expect(row.locator('.fb-up')).toHaveCount(0);
      await expect(row.locator('.mark-btn')).toHaveCount(0);
    });
  }

  test('verified: the audit-bound confirmation pair still renders', async ({ page }) => {
    await installBackendStubs(page, { auditId: 501, stream: () => scopedTool('verified') });
    await boot(page);
    await sendTurn(page);

    const row = page.locator('.tool-status.done');
    await expect(row).toHaveCount(1);
    await expect(row).toHaveClass(/ok/);
    await expect(row.locator('.fb-up')).toHaveCount(1);
    await expect(row.locator('.mark-btn')).toHaveCount(1);
  });

  test('no status (non-scope tool): unchanged thumbs', async ({ page }) => {
    await installBackendStubs(page, { auditId: 501, stream: () => scopedTool(null) });
    await boot(page);
    await sendTurn(page);

    const row = page.locator('.tool-status.done');
    await expect(row).toHaveCount(1);
    await expect(row).toHaveClass(/ok/);
    await expect(row.locator('.fb-up')).toHaveCount(1);
    await expect(row.locator('.mark-btn')).toHaveCount(1);
  });

  test('noop (target already gone): neutral info, not red, no audit-bound thumbs', async ({ page }) => {
    await installBackendStubs(page, {
      auditId: 501,
      stream: () => [
        { tool: { name: 'delete_note', phase: 'start' } },
        { tool: { name: 'delete_note', phase: 'end', ok: false, audit_id: 501, verification_status: null, noop: true } },
        { token: 'Yanıt geldi.' },
        { done: true },
      ],
    });
    await boot(page);
    await sendTurn(page);

    const row = page.locator('.tool-status.done');
    await expect(row).toHaveCount(1);
    await expect(row).toHaveClass(/noop/);
    await expect(row).not.toHaveClass(/warn/);
    await expect(row).not.toHaveClass(/ok/);
    await expect(row.locator('.tlab')).toHaveText(/yok|nothing|noop/i);
    await expect(row.locator('.mark-btn')).toHaveCount(0);
    await expect(row.locator('.fb-up')).toHaveCount(0);
  });
});