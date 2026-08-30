// @ts-check
// C-7 multi-tool feedback: ONE 👍/👎 pair per message no matter how many tools
// ran. 👎 opens a chip strip of the tools that ACTUALLY ran; each chip opens the
// group picker bound to that tool's audit_id; 👍 confirms every ran tool at
// once (single decision). Un-fixed tools stay unreviewed by design.
const { test, expect } = require('@playwright/test');
const { installBackendStubs, boot } = require('./stubs.cjs');

async function sendSimple(page, text = 'Merhaba') {
  await page.fill('#msg-input', text);
  await page.press('#msg-input', 'Enter');
}

const twoTools = () => [
  { tool: { name: 'list_calendar_events', phase: 'start' } },
  { tool: { name: 'list_calendar_events', phase: 'end', ok: true, audit_id: 111 } },
  { tool: { name: 'search_tasks', phase: 'start' } },
  { tool: { name: 'search_tasks', phase: 'end', ok: true, audit_id: 222 } },
  { token: 'Yanıt geldi.' },
  { done: true },
];

test.describe('multi-tool feedback (C-7)', () => {
  test('two audited tools settle ONE pair with the merged action bar', async ({ page }) => {
    await installBackendStubs(page, { stream: twoTools });
    await boot(page);
    await sendSimple(page);

    const status = page.locator('.tool-status');
    await expect(status).toHaveCount(1); // one row, not one per tool
    await expect(status.locator('.fb-up')).toHaveCount(1);
    await expect(status.locator('.mark-btn')).toHaveCount(1);
    // Copy/listen/regen share that exact row.
    await expect(status.locator('.copy-btn')).toHaveCount(1);
    const auditList = await page.evaluate(() =>
      document.querySelector('.tool-status')?.getAttribute('data-audits'));
    expect(auditList).toBe('111,222');
    await expect(status).toHaveAttribute('data-audit', '111'); // first audit (e2e contract)
  });

  test('single-tool round still opens the picker DIRECTLY (no chip strip)', async ({ page }) => {
    await installBackendStubs(page); // default stubs: one audited tool (123)
    await boot(page);
    await sendSimple(page);

    await page.click('.tool-status .mark-btn');
    await expect(page.locator('.group-picker')).toHaveCount(1);
    await expect(page.locator('.fb-tabs')).toHaveCount(0);
  });

  test('down-thumb shows a chip per audited tool (refused tools excluded)', async ({ page }) => {
    const stream = () => [
      { tool: { name: 'search_tasks', phase: 'start' } },
      { tool: { name: 'search_tasks', phase: 'end', ok: true, audit_id: 222 } },
      { tool: { name: 'list_calendar_events', phase: 'start' } },
      { tool: { name: 'list_calendar_events', phase: 'end', ok: true, audit_id: 111 } },
      { tool: { name: 'list_emails', phase: 'start' } },
      { tool: { name: 'list_emails', phase: 'refused', ok: false, audit_id: null, attempt: 1, max: 1 } },
      { token: 'Yanıt geldi.' },
      { done: true },
    ];
    await installBackendStubs(page, { stream });
    await boot(page);
    await sendSimple(page);

    await page.click('.tool-status .mark-btn');
    await expect(page.locator('.fb-tabs')).toHaveCount(1);
    await expect(page.locator('.fb-tab')).toHaveCount(2); // email refused → no chip
    await expect(page.locator('.fb-tab[data-tool="list_emails"]')).toHaveCount(0);
    await expect(page.locator('.fb-tab[data-audit="222"]')).toHaveText(/Görevler|Tasks/);
    await expect(page.locator('.fb-tab[data-audit="111"]')).toHaveText(/Takvim|Calendar/);
  });

  test('a chip opens the picker bound to THAT tool only; others stay available', async ({ page }) => {
    const stubs = await installBackendStubs(page, { stream: twoTools });
    await boot(page);
    await sendSimple(page);

    await page.click('.tool-status .mark-btn');
    // Fix the SECOND tool → posts its own audit_id.
    await page.click('.fb-tab[data-audit="222"]');
    await expect(page.locator('.group-picker')).toHaveCount(1);
    await page.click('.group-picker .gp-opt'); // calendar
    await page.click('.group-picker .gp-save');
    await expect(page.locator('.fb-tab[data-audit="222"].done')).toHaveCount(1);
    // Chip strip stays open; the other chip stays actionable.
    await expect(page.locator('.fb-tabs')).toHaveCount(1);
    await expect(page.locator('.fb-tab[data-audit="111"].done')).toHaveCount(0);

    // Fix the FIRST tool next → different audit_id to a different group.
    await page.click('.fb-tab[data-audit="111"]');
    await expect(page.locator('.group-picker')).toHaveCount(1);
    await page.click('.group-picker .gp-opt:nth-child(5)'); // tasks
    await page.click('.group-picker .gp-save');
    await expect(page.locator('.fb-tab[data-audit="111"].done')).toHaveCount(1);

    expect(stubs.sentCorrections).toHaveLength(2);
    expect(stubs.sentCorrections[0]).toEqual({ audit_id: 222, expected_group: 'calendar' });
    expect(stubs.sentCorrections[1]).toEqual({ audit_id: 111, expected_group: 'tasks' });
    // Chip corrections do NOT confirm the round — unreviewed stays unreviewed.
    expect(stubs.sentConfirmations).toHaveLength(0);
  });

  test('thumbs-up confirms EVERY audited tool and drops the chip strip', async ({ page }) => {
    const stubs = await installBackendStubs(page, { stream: twoTools });
    await boot(page);
    await sendSimple(page);

    await page.click('.tool-status .mark-btn'); // open the chooser first…
    await expect(page.locator('.fb-tabs')).toHaveCount(1);

    await page.click('.tool-status .fb-up'); // …then confirm-all

    await expect.poll(() => stubs.sentConfirmations.length).toBe(2);
    expect(stubs.sentConfirmations[0]).toEqual({ audit_id: 111 });
    expect(stubs.sentConfirmations[1]).toEqual({ audit_id: 222 });
    await expect(page.locator('.tool-status .fb-up.active')).toHaveCount(1);
    await expect(page.locator('.fb-tabs')).toHaveCount(0); // the decision supersedes the chooser
  });
});