// @ts-check
// Tool indicator lifecycle fix (C-11): while the tool runs the row shows its
// working label/spinner ("Notlarını listeliyorum…"), but the MOMENT the model
// starts replying (first token / reasoning) the label must disappear and the
// row flip to its quiet feedback state. Nothing may keep "bakıyorum" painted
// over a streaming answer, and multi-step tool use (tool → token → tool) must
// reuse the SAME row via revival — one pair per message, no duplicate rows.
//
// Playwright 1.40 cannot stream via route.fulfill, so this spec replaces the
// page's own fetch with one that returns a REAL web ReadableStream of SSE
// chunks on a timer — genuine mid-stream timing inside the browser.
const { test, expect } = require('@playwright/test');
const { installBackendStubs, boot } = require('./stubs.cjs');

async function interceptStream(page, chunks, gapMs) {
  await page.evaluate(([cs, gap]) => {
    const enc = new TextEncoder();
    const original = window.fetch.bind(window);
    window.fetch = (url, opts = {}) => {
      if (!String(url).endsWith('/chat/stream')) return original(url, opts);
      let i = 0;
      const body = new ReadableStream({
        start(controller) {
          const timer = setInterval(() => {
            if (i < cs.length) {
              controller.enqueue(enc.encode('data: ' + JSON.stringify(cs[i++]) + '\n\n'));
            } else {
              clearInterval(timer);
              controller.close();
            }
          }, gap);
        },
      });
      return Promise.resolve(new Response(body, {
        status: 200,
        headers: { 'Content-Type': 'text/event-stream' },
      }));
    };
  }, [chunks, gapMs]);
}

async function sendSimple(page, text = 'Notlarımı listele') {
  await page.fill('#msg-input', text);
  await page.press('#msg-input', 'Enter');
}

test.describe('tool indicator (C-11)', () => {
  test('tool label disappears the moment the model starts replying', async ({ page }) => {
    await installBackendStubs(page);
    await boot(page);
    await interceptStream(page, [
      { tool: { name: 'list_notes', phase: 'start' } },
      { tool: { name: 'list_notes', phase: 'end', ok: true, audit_id: 777 } },
      { token: 'Notlarınız:' },
      { token: ' hazır.' },
      { done: true },
    ], 400);
    await sendSimple(page);

    const row = page.locator('.tool-status');
    const tlab = row.locator('.tlab');
    // While the tool runs: working label, not yet settled.
    await expect(tlab).toHaveText(/not/i, { timeout: 2000 });
    await expect(row).not.toHaveClass(/\bdone\b/);

    // First reply token arrives → label gone, quiet feedback pair in place
    // (this is asserted BEFORE the stream's done chunk at ~1600ms).
    await expect(row.locator('.fb-up')).toHaveCount(1, { timeout: 2000 });
    await expect(tlab).toHaveCount(0);
    await expect(row).toHaveClass(/\bdone\b/);
    // No second row ever appears; answer streams under the settled row.
    await expect(page.locator('.tool-status')).toHaveCount(1);
    await expect(page.locator('.msg-group.assistant .bubble')).toContainText('hazır');
  });

  test('multi-step (tool → token → tool) stays ONE row with every audit', async ({ page }) => {
    await installBackendStubs(page);
    await boot(page);
    await interceptStream(page, [
      { tool: { name: 'search_tasks', phase: 'start' } },
      { tool: { name: 'search_tasks', phase: 'end', ok: true, audit_id: 111 } },
      { token: 'Ara araştırması: ' },
      { tool: { name: 'list_calendar_events', phase: 'start' } },
      { tool: { name: 'list_calendar_events', phase: 'end', ok: true, audit_id: 222 } },
      { token: 'takvim hazır.' },
      { done: true },
    ], 250);
    await sendSimple(page, 'planımı çıkar');

    const row = page.locator('.tool-status');
    await expect(row).toHaveCount(1, { timeout: 3000 });
    // The revive path re-used the settled row for the second tool, then the
    // final settle carries BOTH audits back under one pair.
    await expect(row).toHaveAttribute('data-audits', '111,222');
    await expect(row.locator('.fb-up')).toHaveCount(1);
    await expect(row.locator('.mark-btn')).toHaveCount(1);
    // Second tool's label ran during the round (revival worked), no second row.
    await expect(page.locator('.tool-status')).toHaveCount(1);
    await expect(page.locator('.msg-group.assistant .bubble')).toContainText('takvim hazır');
  });
});