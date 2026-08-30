// @ts-check
// C-8 feedback persistence: the C-7 thumbs pair must survive a chat switch /
// page refresh. GET /chat/history now carries per-assistant-message audits
// (audit_id, tool_name, confirmed_at, corrected_at, expected_group); addMsg
// rebuilds the exact live row (below the bubble) and re-applies persisted
// state: all audits confirmed → 👍 lit, any audit corrected → 👎 marked.
const { test, expect } = require('@playwright/test');
const { installBackendStubs, boot } = require('./stubs.cjs');

const ROW = '.msg-group.assistant .tool-status.done';

const historyWithAudits = [
  {
    role: 'user', content: 'test', timestamp: '2026-08-30T10:00:00Z',
    images: null, reasoning: null,
  },
  {
    role: 'assistant', content: 'çoktan yapıldı', timestamp: '2026-08-30T10:00:01Z',
    images: null, reasoning: null,
    audits: [
      { audit_id: 1, tool_name: 'get_weather', confirmed_at: null, corrected_at: null, expected_group: null },
      { audit_id: 2, tool_name: 'list_emails', confirmed_at: '2026-08-30T10:00:05Z', corrected_at: null, expected_group: null },
    ],
  },
  {
    role: 'assistant', content: 'düzeltip onayladım', timestamp: '2026-08-30T10:00:02Z',
    images: null, reasoning: null,
    audits: [
      { audit_id: 3, tool_name: 'get_weather', confirmed_at: '2026-08-30T10:00:04Z', corrected_at: '2026-08-30T10:00:03Z', expected_group: 'weather' },
    ],
  },
];

async function loadHistory(page, sid = 'hist1') {
  await page.evaluate((s) => window.loadSession(s), sid);
}

test.describe('feedback persistence (C-8)', () => {
  test('history restores ONE pair per audited assistant message + merged bar', async ({ page }) => {
    await installBackendStubs(page, { history: historyWithAudits });
    await boot(page);
    await loadHistory(page);

    await expect(page.locator(ROW)).toHaveCount(2);
    // Copy/listen merge into the pair rows behind a hairline divider.
    await expect(page.locator(ROW).nth(0).locator('.bar-divider')).toHaveCount(1);
    await expect(page.locator(ROW).nth(0).locator('.copy-btn')).toHaveCount(1);
    // data-audits carries ALL ran audits (not just the first).
    await expect(page.locator(ROW).nth(0)).toHaveAttribute('data-audits', '1,2');
    await expect(page.locator(ROW).nth(0)).toHaveAttribute('data-audit', '1');
  });

  test('persisted signals re-light the thumbs (👍 lit, 👎 marked)', async ({ page }) => {
    await installBackendStubs(page, { history: historyWithAudits });
    await boot(page);
    await loadHistory(page);

    const row0 = page.locator(ROW).nth(0);
    const row1 = page.locator(ROW).nth(1);
    // Mixed round (one confirmed, one not) → no confirmation, no correction.
    await expect(row0.locator('.fb-up.active')).toHaveCount(0);
    await expect(row0.locator('.mark-btn.marked')).toHaveCount(0);
    // Fully settled second round → both thumbs carry their live outcome.
    await expect(row1.locator('.fb-up.active')).toHaveCount(1);
    await expect(row1.locator('.mark-btn.marked')).toHaveCount(1);
  });

  test('historical thumbs stay live: confirm-all and correction round-trip', async ({ page }) => {
    const stubs = await installBackendStubs(page, { history: historyWithAudits });
    await boot(page);
    await loadHistory(page);

    const row0 = page.locator(ROW).nth(0);
    const row1 = page.locator(ROW).nth(1);

    // 👍 on the mixed row confirms EVERY audited tool of that message.
    await row0.locator('.fb-up').click();
    await expect.poll(() => stubs.sentConfirmations.length).toBe(2);
    expect(stubs.sentConfirmations[0]).toEqual({ audit_id: 1 });
    expect(stubs.sentConfirmations[1]).toEqual({ audit_id: 2 });
    await expect(row0.locator('.fb-up.active')).toHaveCount(1);

    // 👎 on the single-tool row opens the picker directly, bound to its audit.
    await row1.locator('.mark-btn').click();
    await expect(page.locator('.group-picker')).toHaveCount(1);
    await expect(page.locator('.fb-tabs')).toHaveCount(0);
    await page.click('.group-picker .gp-opt'); // calendar
    await page.click('.group-picker .gp-save');
    await expect(row1.locator('.mark-btn.marked')).toHaveCount(1);
    expect(stubs.sentCorrections).toHaveLength(1);
    expect(stubs.sentCorrections[0]).toEqual({ audit_id: 3, expected_group: 'calendar' });
  });
});