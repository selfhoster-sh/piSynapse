// @ts-check
// C-9 TTS wait feedback: Piper takes a beat to render audio, so the listen
// button must light up the INSTANT it is clicked — otherwise the tap reads as
// dead until the sound arrives. The wait state (.tts-loading, accent tint +
// soft breathing ring, no text) is visually distinct from .tts-playing (icon
// pulse). A second click during the wait cancels the in-flight request
// (AbortController) so no orphan audio plays and no error toast appears.
const { test, expect } = require('@playwright/test');
const { installBackendStubs, boot } = require('./stubs.cjs');

test('listen button shows a wait state until audio plays, and cancels on second click', async ({ page }) => {
  const stream = () => [{ token: 'Merhaba dünya.' }, { done: true }];
  await installBackendStubs(page, { stream });
  // Hold /chat/tts open so the wait window is observable.
  await page.route('**/chat/tts', async route => {
    await new Promise(r => setTimeout(r, 3000));
    await route.fulfill({ status: 200, contentType: 'audio/wav', body: Buffer.alloc(100) });
  });
  await boot(page);
  await page.fill('#msg-input', 'Merhaba');
  await page.press('#msg-input', 'Enter');

  // The assistant bar: copy, listen, regen (all .tts-btn) — speaker is #2.
  const listen = page.locator('.msg-group.assistant .tts-btn').nth(1);
  await expect(listen).toHaveCount(1);

  // Clicking shows the wait state immediately, with an accent tint (not plain).
  await listen.click();
  await expect(listen).toHaveClass(/\btts-loading\b/);
  await expect(listen).not.toHaveClass(/\btts-playing\b/);
  const loadingBg = await listen.evaluate(el => getComputedStyle(el).backgroundColor);
  expect(loadingBg).not.toBe('rgba(0, 0, 0, 0)');

  // Second click during the wait aborts the request: no playing state, and the
  // late server response must not spawn orphan audio or an error toast.
  await listen.click();
  await expect(listen).not.toHaveClass(/\btts-loading\b/);
  await expect(listen).not.toHaveClass(/\btts-playing\b/);

  // Let the held request resolve past the old play-error window.
  await page.waitForTimeout(3200);
  await expect(page.locator('.toast')).toHaveCount(0);
});