// @ts-check
const { test, expect } = require('@playwright/test');
const { installBackendStubs, boot, GROUPS } = require('./stubs.cjs');

const GROUP_COUNT = GROUPS.length;

async function sendTurn(page, text = 'Merhaba') {
  await page.fill('#msg-input', text);
  await page.press('#msg-input', 'Enter');
}

async function markOnce(page) {
  await page.click('.mark-btn');
  await page.click('.group-picker .gp-opt'); // select first group
  await page.click('.group-picker .gp-save');
}

test.describe('tool marking flow', () => {
  test('mark button appears only for an audited tool call', async ({ page }) => {
    await installBackendStubs(page);
    await boot(page);
    await sendTurn(page);

    await expect(page.locator('.tool-status')).toHaveCount(1);
    const pill = page.locator('.tool-status').first();
    await expect(pill.locator('.mark-btn')).toHaveCount(1);
    expect(await pill.getAttribute('data-audit')).toBe('123');
    await expect(pill.locator('.mark-btn')).toHaveAttribute('title', /Yanlış|Wrong/i);
  });

  test('no mark button when audit_id is null', async ({ page }) => {
    await installBackendStubs(page, { auditId: null });
    await boot(page);
    await sendTurn(page);

    await expect(page.locator('.tool-status')).toHaveCount(1);
    await expect(page.locator('.tool-status .mark-btn')).toHaveCount(0);
  });

  test('picker renders all tool groups', async ({ page }) => {
    await installBackendStubs(page);
    await boot(page);
    await sendTurn(page);

    await page.click('.mark-btn');
    await expect(page.locator('.group-picker .gp-opt')).toHaveCount(GROUP_COUNT);
    const labels = await page.locator('.group-picker .gp-opt').allTextContents();
    expect(labels.every(t => t.trim().length > 0)).toBeTruthy();
  });

  test('correction posts {audit_id, expected_group}', async ({ page }) => {
    const stubs = await installBackendStubs(page);
    await boot(page);
    await sendTurn(page);

    await markOnce(page);

    await expect(page.locator('.group-picker')).toHaveCount(0);
    await expect(page.locator('.mark-btn.marked')).toHaveCount(1);
    expect(stubs.sentCorrections).toHaveLength(1);
    expect(stubs.sentCorrections[0].audit_id).toBe(123);
    expect(GROUPS).toContain(stubs.sentCorrections[0].expected_group);
  });

  test('correction API error keeps picker open and surfaces toast', async ({ page }) => {
    const stubs = await installBackendStubs(page, { correctionError: true });
    await boot(page);
    await sendTurn(page);

    await page.click('.mark-btn');
    await page.click('.group-picker .gp-opt');
    await page.click('.group-picker .gp-save');

    await expect(page.locator('#toast')).toContainText('500');
    await expect(page.locator('.group-picker')).toHaveCount(1); // stays open
    await expect(page.locator('.group-picker .gp-save')).toBeEnabled(); // retry possible
    await expect(page.locator('.mark-btn.marked')).toHaveCount(0);
  });

  test('overwrite: an already marked button can re-open the picker and re-mark', async ({ page }) => {
    const stubs = await installBackendStubs(page);
    await boot(page);
    await sendTurn(page);

    await markOnce(page);
    await expect(page.locator('.mark-btn.marked')).toHaveCount(1);

    await page.click('.mark-btn'); // re-open after marked
    await expect(page.locator('.group-picker')).toHaveCount(1);
    await page.click('.group-picker .gp-opt');
    await page.click('.group-picker .gp-save');

    await expect(page.locator('.group-picker')).toHaveCount(0);
    expect(stubs.sentCorrections).toHaveLength(2);
    expect(stubs.sentCorrections[0].audit_id).toBe(stubs.sentCorrections[1].audit_id);
    await expect(page.locator('.mark-btn.marked')).toHaveCount(1);
  });

  test('401 from /tools/groups triggers the same api() re-prompt as the rest of the app', async ({ page }) => {
    await installBackendStubs(page);
    let calls = 0;
    await page.route('**/tools/groups', async route => {
      calls++;
      if (calls === 1) return route.fulfill({ status: 401, contentType: 'application/json', body: '{"detail":"no key"}' });
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ groups: GROUPS }) });
    });
    await boot(page);
    await sendTurn(page);

    let prompts = 0;
    page.on('dialog', async d => { prompts++; await d.accept('accepted-key'); });
    await page.click('.mark-btn');

    await expect(page.locator('.group-picker')).toHaveCount(1); // retry succeeded
    expect(prompts).toBe(1);
    expect(await page.evaluate(() => localStorage.getItem('ps_api_key'))).toBe('accepted-key');
  });

  test('keyboard: mark button reachable, Enter opens picker, option+save activate by keyboard', async ({ page }) => {
    await installBackendStubs(page);
    await boot(page);
    await sendTurn(page);

    await expect(page.locator('.mark-btn')).toHaveCount(1);
    for (let i = 0; i < 40; i++) {
      await page.keyboard.press('Tab');
      const active = await page.evaluate(() => document.activeElement && document.activeElement.className);
      if (String(active).includes('mark-btn')) break;
    }
    expect(await page.evaluate(() => document.activeElement && document.activeElement.className)).toContain('mark-btn');

    await page.keyboard.press('Enter');
    await expect(page.locator('.group-picker')).toHaveCount(1);

    // Tab into the first group option.
    await page.keyboard.press('Tab');
    await expect(page.locator('.group-picker .gp-opt').first()).toBeFocused();
    await page.keyboard.press('Enter'); // select
    await expect(page.locator('.group-picker .gp-save')).toBeEnabled();

    await page.locator('.group-picker .gp-cancel').focus();
    await page.keyboard.press('Enter'); // cancel via keyboard
    await expect(page.locator('.group-picker')).toHaveCount(0);

    // Cancel path done; now reopen and finish via save.
    await page.locator('.mark-btn').focus();
    await page.keyboard.press('Enter'); // re-open via keyboard
    await expect(page.locator('.group-picker')).toHaveCount(1);
    await page.locator('.group-picker .gp-opt').first().press('Enter');
    await page.locator('.group-picker .gp-save').press('Enter');
    await expect(page.locator('.group-picker')).toHaveCount(0);
    await expect(page.locator('.mark-btn.marked')).toHaveCount(1);
  });

  test('next send retains previous settled pills; new round adds its own pill', async ({ page }) => {
    await installBackendStubs(page, { streamDelayMs: 500 });
    await boot(page);
    await sendTurn(page, 'ilk');

    await expect(page.locator('.tool-status')).toHaveCount(1);
    await expect(page.locator('.tool-status .mark-btn')).toHaveCount(1);

    await sendTurn(page, 'ikinci');
    // clearToolPills() runs synchronously at the start of the second send;
    // because the first pill is settled (.done), it is retained (count stays 1).
    await expect(page.locator('.tool-status')).toHaveCount(1);

    // The second round completes, bringing the total count to 2.
    await expect(page.locator('.tool-status')).toHaveCount(2);
    await expect(page.locator('.tool-status .mark-btn')).toHaveCount(2);
  });
});