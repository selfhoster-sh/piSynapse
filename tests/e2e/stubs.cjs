// Shared Playwright stubs: serve canned API responses so the marking flow can
// be exercised hermetically (no API key, no LLM). Only the app's API endpoints
// are intercepted; static assets pass through to the running server.

const GROUPS = ['calendar', 'email', 'memory', 'notes', 'tasks', 'weather'];

function sse(events) {
  return events.map(e => `data: ${JSON.stringify(e)}`).join('\n') + '\n';
}

function json(route, obj, status = 200) {
  return route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(obj) });
}

/**
 * @param {import('@playwright/test').Page} page
 * @param {{auditId?: number|null, correctionError?: boolean, confirmError?: boolean, history?: object[]}} opts
 */
async function installBackendStubs(page, opts = {}) {
  const auditId = opts.auditId === undefined ? 123 : opts.auditId;
  const sentCorrections = [];
  const sentConfirmations = [];

  const config = {
    username: 'testuser',
    default_city: '',
    model: '',
    stt_engine: 'whisper',
    tts_engine: 'piper',
    auto_send_on_voice: 'off',
    auto_tts_on_voice: 'off',
    llm_title_enrichment: 'off',
  };

  // Default stream: one finished audited tool call, then a reply, then done.
  const defaultStream = [
    { tool: { name: 'calendar', phase: 'start' } },
    { tool: { name: 'calendar', phase: 'end', ok: true, audit_id: auditId } },
    { token: 'Yanıt geldi.' },
    { done: true },
  ];

  await page.route('**/config', route => json(route, config));
  await page.route('**/config/settings', route => json(route, {}));
  await page.route('**/chat/sessions', route => json(route, { sessions: [] }));
  await page.route('**/chat/history**', route => json(route, { session_id: 'x', messages: opts.history || [] }));
  await page.route('**/chat/abort/**', route => json(route, {}));
  await page.route('**/widget/weather', route => json(route, { summary: 'Güneşli 22°C' }));
  await page.route('**/widget/calendar', route => json(route, { events: [] }));
  await page.route('**/health', route => json(route, { dependencies: {} }));

  await page.route('**/tools/groups', route => json(route, { groups: GROUPS }));

  await page.route('**/chat/tool-correction', async route => {
    sentCorrections.push(route.request().postDataJSON());
    if (opts.correctionError) {
      return json(route, { detail: 'boom' }, 500);
    }
    return json(route, {});
  });

  await page.route('**/chat/tool-confirm', async route => {
    sentConfirmations.push(route.request().postDataJSON());
    if (opts.confirmError) {
      return json(route, { detail: 'boom' }, 500);
    }
    return json(route, {});
  });

  await page.route('**/chat/stream', async route => {
    const events = opts.stream ? opts.stream() : defaultStream;
    if (opts.streamDelayMs) {
      await new Promise(r => setTimeout(r, opts.streamDelayMs));
    }
    await route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      body: sse(events),
    });
  });

  return { sentCorrections, sentConfirmations };
}

async function boot(page) {
  await page.goto('/');
  await page.waitForSelector('#messages .welcome', { timeout: 15_000 });
}

module.exports = { installBackendStubs, boot, sse, GROUPS };