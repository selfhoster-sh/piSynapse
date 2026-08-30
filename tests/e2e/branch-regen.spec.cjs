// @ts-check
// Per-message branching & regenerate (C-12):
// Every assistant message features an action bar with copy, listen, and regenerate.
// Clicking regenerate on an OLDER assistant message truncates the conversation from
// that anchor onward (DOM + DB), re-running that exact prompt as a fresh branch.
// Older assistant action bars carry the `.not-last` class for dimmed opacity until hovered.
const { test, expect } = require('@playwright/test');
const { installBackendStubs, boot } = require('./stubs.cjs');

test.describe('per-message branch regenerate (C-12)', () => {
  test('all assistant messages have regen button and older bars carry .not-last', async ({ page }) => {
    const history = [
      { id: 10, role: 'user', content: 'ilk soru' },
      { id: 11, role: 'assistant', content: 'ilk cevap' },
      { id: 12, role: 'user', content: 'ikinci soru' },
      { id: 13, role: 'assistant', content: 'ikinci cevap' },
    ];
    await installBackendStubs(page, { history });
    await page.route('**/chat/sessions', route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ sessions: [{ session_id: 's12', name: 'Test', snippet: 'ikinci cevap' }] })
    }));
    await boot(page);
    await page.click('.sess-item[data-sid="s12"]');
    await expect(page.locator('.msg-group.assistant')).toHaveCount(2);

    // Both assistant groups have a regen button
    const regenBtns = page.locator('.msg-group.assistant .regen-btn');
    await expect(regenBtns).toHaveCount(2);

    // The first assistant bar has .not-last, the second (last) does NOT.
    // The copy/listen/regen bar merges into each message's settled feedback
    // row (.tool-status.done), which every assistant message now has.
    const asstGroups = page.locator('.msg-group.assistant');
    const bar1 = asstGroups.nth(0).locator('.tool-status.done');
    const bar2 = asstGroups.nth(1).locator('.tool-status.done');

    await expect(bar1).toHaveClass(/\bnot-last\b/);
    await expect(bar2).not.toHaveClass(/\bnot-last\b/);
  });

  test('clicking regenerate on an older message triggers branch DELETE and re-streams from that prompt', async ({ page }) => {
    const history = [
      { id: 101, role: 'user', content: 'birinci soru' },
      { id: 102, role: 'assistant', content: 'birinci cevap' },
      { id: 103, role: 'user', content: 'ikinci soru' },
      { id: 104, role: 'assistant', content: 'ikinci cevap' },
    ];
    let branchDeletePayload = null;
    await installBackendStubs(page, { history });
    await page.route('**/chat/sessions', route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ sessions: [{ session_id: 's12', name: 'Test', snippet: 'ikinci cevap' }] })
    }));
    await page.route('**/chat/messages/branch/**', async route => {
      branchDeletePayload = route.request().postDataJSON();
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true, removed: [102, 103, 104] }) });
    });

    await boot(page);
    await page.click('.sess-item[data-sid="s12"]');
    await expect(page.locator('.msg-group.assistant')).toHaveCount(2);

    // Click regenerate on the FIRST assistant message (id: 102)
    const firstAsst = page.locator('.msg-group.assistant').first();
    await firstAsst.locator('.regen-btn').click();

    // Verify branch DELETE request payload
    await expect.poll(() => branchDeletePayload).not.toBeNull();
    expect(branchDeletePayload.message_id).toBe(102);

    // DOM truncation: second user & assistant messages are removed, replaced by fresh stream
    // Remaining assistant count stays 1 (first assistant replaced by re-streamed reply "Yanıt geldi.")
    await expect(page.locator('.msg-group.assistant')).toHaveCount(1);
    await expect(page.locator('.msg-group.user')).toHaveCount(1);
    await expect(page.locator('.msg-group.user .bubble')).toHaveText('birinci soru');
    await expect(page.locator('.msg-group.assistant .bubble')).toContainText('Yanıt geldi.');
  });
});