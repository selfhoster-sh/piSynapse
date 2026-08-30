// @ts-check
// Universal thumbs: every assistant message — even one with no tool call —
// shows a single 👍/👎 pair. Marking persists via /chat/message-feedback and
// a 👎 accepts an optional free-text reason. Tool-less rounds are the data
// capture path for model drops / intent-gap replies (C-12 feedback).
const { test, expect } = require('@playwright/test');
const { installBackendStubs, boot } = require('./stubs.cjs');

const NO_TOOL_STREAM = () => [
  { token: 'Sadece sohbet.' },
  { done: true, message_id: 2002 },
];

async function sendTurn(page, text = 'Merhaba') {
  await page.fill('#msg-input', text);
  await page.press('#msg-input', 'Enter');
}

test.describe('universal message feedback', () => {
  test('tool-less round still shows a thumbs pair bound to the message id', async ({ page }) => {
    await installBackendStubs(page, { stream: NO_TOOL_STREAM });
    await boot(page);
    await sendTurn(page);

    await expect(page.locator('.tool-status')).toHaveCount(1);
    const pill = page.locator('.tool-status').first();
    await expect(pill.locator('.fb-up')).toHaveCount(1);
    await expect(pill.locator('.mark-btn')).toHaveCount(1);
    const group = pill.locator('xpath=..'); // .tool-status sits inside .msg-group
    await expect(group).toHaveAttribute('data-mid', '2002');
  });

  test('up marks and persists a message-level verdict', async ({ page }) => {
    const stubs = await installBackendStubs(page, { stream: NO_TOOL_STREAM });
    await boot(page);
    await sendTurn(page);

    await page.click('.fb-up');
    await expect(page.locator('.fb-up.active')).toHaveCount(1);
    expect(stubs.sentMessageFeedback).toHaveLength(1);
    expect(stubs.sentMessageFeedback[0].message_id).toBe(2002);
    expect(stubs.sentMessageFeedback[0].value).toBe('up');
    expect(stubs.sentMessageFeedback[0].note).toBeUndefined();
  });

  test('down opens the optional note editor and persists the reason', async ({ page }) => {
    const stubs = await installBackendStubs(page, { stream: NO_TOOL_STREAM });
    await boot(page);
    await sendTurn(page);

    await page.click('.mark-btn');
    await expect(page.locator('.msg-note-editor input')).toHaveCount(1);
    await page.fill('.msg-note-editor input', 'model gereksiz soru sordu');
    await page.keyboard.press('Enter');

    await expect(page.locator('.msg-note-editor')).toHaveCount(0);
    await expect(page.locator('.mark-btn.marked.msg-note')).toHaveCount(1);
    // First POST is the bare down; the Enter commit writes the note too.
    expect(stubs.sentMessageFeedback.at(-1)).toMatchObject({
      message_id: 2002, value: 'down', note: 'model gereksiz soru sordu',
    });
  });

  test('history restore: persisted verdict and note come back on session open', async ({ page }) => {
    const history = [
      { id: 2001, role: 'user', content: 'notları özetle', timestamp: '2026-08-30 10:00:00' },
      { id: 2002, role: 'assistant', content: 'Burada özet çıkar.', timestamp: '2026-08-30 10:00:05' },
      { id: 2003, role: 'user', content: 'teşekkürler', timestamp: '2026-08-30 10:00:10' },
      { id: 2004, role: 'assistant', content: 'Rica ederim!', timestamp: '2026-08-30 10:00:15', feedback: 'down', feedback_note: 'niyet algılanmadı' },
    ];
    await installBackendStubs(page, { history });
    await page.route('**/chat/sessions', route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ sessions: [{ session_id: 's1', name: 'Test', last_active: new Date().toISOString(), message_count: 4 }] }),
    }));
    await boot(page);
    await page.click('.sess-item[data-sid="s1"]');

    await expect(page.locator('#messages .msg-group.assistant')).toHaveCount(2);
    // First assistant message: clean pair, no restored verdict.
    const first = page.locator('#messages .msg-group.assistant').first();
    await expect(first.locator('.fb-up')).toHaveCount(1);
    await expect(first.locator('.fb-up.active')).toHaveCount(0);
    // Second assistant message: down verdict + note restored.
    const second = page.locator('#messages .msg-group.assistant').nth(1);
    await expect(second.locator('.mark-btn.marked.msg-note')).toHaveCount(1);
    await expect(second.locator('.mark-btn')).toHaveAttribute('data-note', 'niyet algılanmadı');
    await expect(second).toHaveAttribute('data-mid', '2004');
  });
});