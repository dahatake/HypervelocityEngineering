// FR-1096..FR-1098, NFR-SEC-024, NFR-UX-019: the optional generative AI.
// Nothing here talks to the server's AI endpoints until the user opens the settings or asks; with AI off or unset no
// request reaches an AI provider, Azure Resource Manager or GitHub Copilot (AC-528).
// Only non-secret settings are kept in the browser (localStorage `eabk-studio.ai`); keys go to the server once, when the
// user saves them (OS vault) or uses them for this session (memory), and are never shown again (AC-521, AC-543).
import { t, onLang, lang } from './i18n.js';
import { store } from './store.js';
import { el, icon, toast } from './ui.js';
import { xrefLink } from './xref.js';
import { currentStep } from './steps.js';

const KEY = 'eabk-studio.ai';
const HDR = { 'Content-Type': 'application/json', 'X-EABK-Studio': '1' };
const AUTHS = { azure: ['key', 'entra'], copilot: ['gh', 'byok'] };
const MODELS = ['gpt-5', 'gpt-4.1', 'claude-sonnet-4.5'];
const ID_RE = /(?:[A-Za-z0-9_.-]+:)?[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*-\d{2,}/g;

let conn = { state: 'unset', detail: '' };   // 3.4: unset -> configured (unchecked) -> checked / failed (memory only)
let seenIntro = false;

export function loadConfig() {
  try {
    const c = JSON.parse(localStorage.getItem(KEY) || 'null');
    if (c && typeof c === 'object' && (c.provider === 'off' || AUTHS[c.provider])) return c;
  } catch { /* a broken entry is treated as unset */ }
  return { provider: 'off' };
}
function saveConfig(c) {
  const keep = ['provider', 'auth', 'endpoint', 'deployment', 'model', 'byokType', 'subscription', 'account'];
  const clean = Object.fromEntries(keep.filter((k) => c[k] != null && c[k] !== '').map((k) => [k, String(c[k])]));
  try { localStorage.setItem(KEY, JSON.stringify(clean)); } catch { /* the setting still applies to this page */ }
  window.dispatchEvent(new Event('eabk-ai-config'));
}
export const aiConfigured = () => { const c = loadConfig(); return c.provider !== 'off' && AUTHS[c.provider]?.includes(c.auth); };
const stateKey = () => (aiConfigured() ? (conn.state === 'unset' ? 'configured' : conn.state) : 'unset');

async function post(path, body, signal) {
  const res = await fetch(path, { method: 'POST', headers: HDR, body: JSON.stringify(body || {}), signal });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw Object.assign(new Error(data.detail || data.error || 'HTTP ' + res.status), { code: data.error, action: data.action });
  return data;
}
const errText = (e) => `${t('ai.err.' + (e.code || 'provider-error'))}${e.message ? ' — ' + e.message : ''}${e.action ? ' ' + t('ai.next', { a: e.action }) : ''}`;

// ---------------------------------------------------------------- settings (AC-520..AC-524, AC-543..AC-545)
let settingsOpen = null;
export function openSettings() {
  settingsOpen?.close();
  let cfg = loadConfig();
  const opener = document.activeElement;
  const live = el('p', { class: 'ai-live', role: 'status', 'aria-live': 'polite', 'data-testid': 'ai-conn-state' });
  const body = el('div', { class: 'ai-settings-body' });
  const card = el('div', { class: 'ai-dialog card', role: 'dialog', 'aria-modal': 'true', 'aria-labelledby': 'aiSetTitle', 'data-testid': 'ai-settings' });
  const root = el('div', { class: 'ai-overlay' }, card);
  const close = () => { root.remove(); window.removeEventListener('keydown', onKey, true); settingsOpen = null; opener?.focus?.(); offLang(); };
  const onKey = (e) => { if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); close(); } };
  const set = (patch) => { cfg = { ...cfg, ...patch }; saveConfig(cfg); conn = { state: 'unset', detail: '' }; draw(); };
  const showState = () => {
    const s = stateKey();
    live.replaceChildren(icon(s === 'checked' ? 'success' : s === 'failed' ? 'warning' : 'info', { size: 16 }), ' ', t('ai.state.' + s), conn.detail ? ' — ' + conn.detail : '');
    live.dataset.state = s;
  };

  const radio = (name, value, cur, label, onpick) => el('label', { class: 'ai-radio' },
    el('input', { type: 'radio', name, value, checked: cur === value || null, 'data-testid': `ai-${name}-${value}`, onchange: () => onpick(value) }), label);
  const field = (id, label, input, hint) => el('div', { class: 'ai-field', 'data-field': id }, el('label', { for: 'ai-f-' + id }, label), input, hint ? el('p', { class: 'mini' }, hint) : null);
  const text = (id, value, ph, onchange, list) => el('input', { id: 'ai-f-' + id, type: 'text', value: value || '', placeholder: ph || '', autocomplete: 'off', spellcheck: 'false', list: list || null, 'data-testid': 'ai-field-' + id, onchange: (e) => onchange(e.target.value.trim()) });

  // the key: never displayed; "saved" is shown instead of the value
  function keyField(provider) {
    const box = el('div', { class: 'ai-field', 'data-field': 'key' });
    const input = el('input', { id: 'ai-f-key', type: 'password', autocomplete: 'off', 'data-testid': 'ai-field-key', placeholder: t('ai.key.ph') });
    const status = el('p', { class: 'mini', 'data-testid': 'ai-key-status' }, t('ai.key.checking'));
    const saveBtn = el('button', { type: 'button', class: 'btn', 'data-testid': 'ai-key-save' }, t('ai.key.save'));
    const sessBtn = el('button', { type: 'button', class: 'btn ghost', 'data-testid': 'ai-key-session' }, t('ai.key.session'));
    const delBtn = el('button', { type: 'button', class: 'btn ghost', 'data-testid': 'ai-key-delete' }, t('ai.key.delete'));
    const refresh = async () => {
      if (!cfg.endpoint) { status.textContent = t('ai.key.needEndpoint'); saveBtn.disabled = sessBtn.disabled = delBtn.disabled = true; return; }
      try {
        const r = await fetch(`/api/ai/status?provider=${encodeURIComponent(provider)}&endpoint=${encodeURIComponent(cfg.endpoint)}`, { cache: 'no-store' }).then((x) => x.json());
        status.textContent = r.stored ? t('ai.key.stored') : r.session ? t('ai.key.inSession') : t('ai.key.notStored');
        status.dataset.stored = String(!!r.stored);
        saveBtn.disabled = !r.vault?.available;
        saveBtn.title = r.vault?.available ? '' : t('ai.key.noVault', { why: r.vault?.reason || '' });
        if (!r.vault?.available) status.append(' ', el('span', { 'data-testid': 'ai-vault-unavailable' }, t('ai.key.noVault', { why: r.vault?.reason || '' })));
        delBtn.disabled = !(r.stored || r.session);
        sessBtn.disabled = false;
      } catch (e) { status.textContent = errText(e); }
    };
    const put = async (persist) => {
      const key = input.value;
      if (!key) { status.textContent = t('ai.key.empty'); return; }
      try { await post('/api/ai/key', { config: cfg, key, persist }); input.value = ''; conn = { state: 'unset', detail: '' }; showState(); }
      catch (e) { status.textContent = errText(e); input.value = ''; return; }
      refresh();
    };
    saveBtn.onclick = () => put(true);
    sessBtn.onclick = () => put(false);
    delBtn.onclick = async () => { try { await post('/api/ai/key/delete', { config: cfg }); } catch (e) { status.textContent = errText(e); return; } refresh(); };
    box.append(el('label', { for: 'ai-f-key' }, t('ai.f.key')), input, el('div', { class: 'row' }, saveBtn, sessBtn, delBtn), status);
    refresh();
    return box;
  }

  function signinBox(provider) {
    const box = el('div', { class: 'ai-field', 'data-field': 'signin' }, el('span', {}, t('ai.f.signin')));
    const out = el('p', { 'data-testid': 'ai-signin' }, t('ai.signin.checking'));
    const again = el('button', { type: 'button', class: 'btn ghost', 'data-testid': 'ai-signin-retry' }, icon('retry', { size: 16 }), t('ai.retry'));
    const check = async () => {
      out.textContent = t('ai.signin.checking');
      try {
        const r = await post('/api/ai/signin', { provider });
        out.replaceChildren(t('ai.signin.ok', { account: r.account || '?' }));
        if (r.tokenSource === 'env') out.append(' ', el('span', { class: 'mini' }, t('ai.signin.envToken')));
        if (provider === 'azure') loadList('subscriptions');
      } catch (e) { out.textContent = errText(e); }
    };
    again.onclick = check;
    box.append(out, again);
    check();
    return box;
  }

  // FR-1097: subscription -> resource -> deployment, from what the signed-in identity can list
  const lists = el('div', { class: 'ai-lists' });
  async function loadList(level) {
    const holder = lists.querySelector(`[data-level="${level}"]`) || el('div', { 'data-level': level });
    if (!holder.isConnected) lists.append(holder);
    holder.replaceChildren(el('p', { class: 'mini' }, t('ai.list.loading')));
    try {
      const { items } = await post('/api/ai/resources', { level, subscription: cfg.subscription, account: cfg.account });
      const label = { subscriptions: (s) => s.name, accounts: (a) => `${a.name} · ${a.location}`, deployments: (d) => `${d.name} · ${d.model}${d.version ? ' ' + d.version : ''}` }[level];
      const value = { subscriptions: (s) => s.id, accounts: (a) => a.id, deployments: (d) => d.name }[level];
      const cur = { subscriptions: cfg.subscription, accounts: cfg.account, deployments: cfg.deployment }[level];
      const sel = el('select', { id: 'ai-f-' + level, 'data-testid': 'ai-list-' + level, onchange: (e) => {
        const v = e.target.value, item = items.find((x) => value(x) === v);
        if (level === 'subscriptions') { cfg = { ...cfg, subscription: v, account: '', deployment: '', endpoint: '' }; lists.querySelectorAll('[data-level=accounts],[data-level=deployments]').forEach((n) => n.remove()); saveConfig(cfg); if (v) loadList('accounts'); }
        else if (level === 'accounts') { cfg = { ...cfg, account: v, endpoint: item?.endpoint || '', deployment: '' }; lists.querySelector('[data-level=deployments]')?.remove(); saveConfig(cfg); if (v) loadList('deployments'); }
        else { cfg = { ...cfg, deployment: v }; saveConfig(cfg); }
        conn = { state: 'unset', detail: '' }; showState();
      } }, el('option', { value: '' }, t('ai.list.choose')), items.map((x) => el('option', { value: value(x), selected: value(x) === cur || null }, label(x))));
      holder.replaceChildren(el('label', { for: 'ai-f-' + level }, t('ai.list.' + level)), sel,
        el('button', { type: 'button', class: 'btn ghost', onclick: () => loadList(level) }, icon('retry', { size: 16 }), t('ai.list.reload')),
        items.length ? null : el('p', { class: 'mini', 'data-testid': 'ai-list-empty' }, t('ai.list.zero.' + level)));
      if (cur && items.some((x) => value(x) === cur)) { if (level === 'subscriptions') loadList('accounts'); else if (level === 'accounts') loadList('deployments'); }
    } catch (e) { holder.replaceChildren(el('p', { class: 'mini' }, errText(e))); }
  }

  function draw() {
    const p = cfg.provider || 'off';
    const parts = [el('fieldset', { class: 'ai-group' }, el('legend', {}, t('ai.f.provider')),
      ['off', 'azure', 'copilot'].map((v) => radio('provider', v, p, t('ai.provider.' + v), (val) => set({ provider: val, auth: AUTHS[val]?.[0] || undefined }))))];
    if (AUTHS[p]) {
      const auth = AUTHS[p].includes(cfg.auth) ? cfg.auth : AUTHS[p][0];
      if (auth !== cfg.auth) { cfg.auth = auth; saveConfig(cfg); }
      parts.push(el('fieldset', { class: 'ai-group' }, el('legend', {}, t('ai.f.auth')),
        AUTHS[p].map((v) => radio('auth', v, auth, t('ai.auth.' + v), (val) => set({ auth: val })))));
      lists.replaceChildren();
      if (p === 'azure' && auth === 'key') {
        parts.push(field('endpoint', t('ai.f.endpoint'), text('endpoint', cfg.endpoint, 'https://<resource>.openai.azure.com', (v) => set({ endpoint: v }))),
          field('deployment', t('ai.f.deployment'), text('deployment', cfg.deployment, '', (v) => set({ deployment: v }))), keyField('azure'));
      } else if (p === 'azure') {
        parts.push(signinBox('azure'), lists);
      } else if (auth === 'gh') {
        parts.push(signinBox('copilot'), field('model', t('ai.f.model'), text('model', cfg.model, MODELS[0], (v) => set({ model: v }), 'ai-models')));
      } else {
        parts.push(field('byokType', t('ai.f.byokType'), el('select', { id: 'ai-f-byokType', 'data-testid': 'ai-field-byokType', onchange: (e) => set({ byokType: e.target.value }) },
          ['openai', 'azure', 'anthropic'].map((v) => el('option', { value: v, selected: (cfg.byokType || 'openai') === v || null }, t('ai.byok.' + v))))),
        field('endpoint', t('ai.f.endpoint'), text('endpoint', cfg.endpoint, 'https://', (v) => set({ endpoint: v }))),
        keyField('copilot'), field('model', t('ai.f.model'), text('model', cfg.model, MODELS[0], (v) => set({ model: v }), 'ai-models')));
      }
      parts.push(el('div', { class: 'row' }, el('button', { type: 'button', class: 'btn', 'data-testid': 'ai-test', onclick: test }, t('ai.test'))), live);
    } else {
      parts.push(el('p', { class: 'mini' }, t('ai.off.d')));
    }
    body.replaceChildren(...parts, el('datalist', { id: 'ai-models' }, MODELS.map((m) => el('option', { value: m }))));
    showState();
  }
  async function test() {
    live.replaceChildren(t('ai.state.checking'));
    try { const r = await post('/api/ai/test', { config: cfg }); conn = { state: 'checked', detail: r.model || '' }; }
    catch (e) { conn = { state: 'failed', detail: errText(e) }; }
    showState();
  }

  card.append(el('div', { class: 'ai-dialog-head' }, icon('settings', { size: 20 }), el('h2', { id: 'aiSetTitle' }, t('ai.settings')),
    el('button', { type: 'button', class: 'btn ghost', 'aria-label': t('ai.close'), 'data-testid': 'ai-settings-close', onclick: close }, icon('close', { size: 16 }))),
  el('p', { class: 'mini' }, t('ai.settings.d')), body);
  document.body.append(root);
  window.addEventListener('keydown', onKey, true);
  const offLang = onLang(draw);
  draw();
  card.querySelector('input,button')?.focus();
  settingsOpen = { close };
}

// ---------------------------------------------------------------- asking (AC-525..AC-527, AC-530..AC-533)
let panel = null;
const consented = new Set();   // this session only (AC-530); the server checks again

function repos() {
  const list = store.model?.meta?.repos;
  return list && list.length ? list.filter((r) => r.status !== 'error') : [{ name: store.model?.meta?.name || '', path: store.model?.meta?.repo || '' }];
}

function resolveId(id) {
  if (store.nodes.has(id)) return id;
  const hits = [...store.nodes.keys()].filter((k) => k.endsWith(':' + id));
  return hits.length === 1 ? hits[0] : null;
}

function answerText(text) {
  const out = [];
  for (const line of text.split('\n')) {
    if (/^\s*RECOMMEND\s+Q-\d+/.test(line)) continue;   // shown as checked recommendations instead (AC-526)
    let last = 0;
    const p = el('p', {});
    for (const m of line.matchAll(ID_RE)) {
      p.append(line.slice(last, m.index));
      const node = resolveId(m[0]);
      p.append(node ? xrefLink(node, m[0]) : el('span', { class: 'ai-unknown-id', 'data-testid': 'ai-unknown-id', title: t('ai.unknownId') }, m[0], el('small', {}, ' (' + t('ai.unknownId') + ')')));
      last = m.index + m[0].length;
    }
    p.append(line.slice(last));
    out.push(p);
  }
  return out;
}

export function openAsk() {
  if (panel) { panel.focus(); return; }
  const opener = document.activeElement;
  const live = el('div', { class: 'sr-only', role: 'status', 'aria-live': 'polite', 'data-testid': 'ai-live' });
  const out = el('div', { class: 'ai-out' });
  const q = el('textarea', { id: 'aiQuestion', rows: 3, 'data-testid': 'ai-question', 'aria-label': t('ai.q.label'), placeholder: t('ai.q.ph') });
  const box = el('aside', { class: 'ai-panel card', role: 'region', 'aria-labelledby': 'aiAskTitle', tabindex: '-1', 'data-testid': 'ai-panel' });
  let ctrl = null, lastQuestion = '';
  const announce = (s) => { live.textContent = ''; setTimeout(() => { live.textContent = s; }, 30); };
  const close = () => { ctrl?.abort(); box.remove(); panel = null; window.removeEventListener('keydown', onKey); offLang(); opener?.focus?.(); };
  const onKey = (e) => {
    if (!box.contains(document.activeElement)) return;
    if (e.key === 'Escape') { e.preventDefault(); if (ctrl) cancel(); else close(); }
  };
  const cancel = () => { if (ctrl) { ctrl.abort(); ctrl = null; announce(t('ai.cancelled')); draw(); } };

  function intro(first) {
    return el('div', { class: 'ai-intro' + (first ? ' first' : ''), 'data-testid': 'ai-intro' },
      el('p', {}, el('b', {}, t('ai.can.h')), ' ', t('ai.can')),
      el('p', {}, el('b', {}, t('ai.cannot.h')), ' ', t('ai.cannot')),
      el('p', {}, el('b', {}, t('ai.wrong.h')), ' ', t('ai.wrong')));
  }

  function consentBox(onAgree) {
    const cfg = loadConfig();
    const pending = repos().filter((r) => !consented.has(r.path));
    const checks = pending.map((r) => el('label', { class: 'ai-radio' }, el('input', { type: 'checkbox', checked: true, value: r.path, 'data-testid': 'ai-consent-repo' }), r.name));
    return el('div', { class: 'ai-consent card', role: 'group', 'aria-labelledby': 'aiConsentH', 'data-testid': 'ai-consent' },
      el('h3', { id: 'aiConsentH' }, t('ai.consent.h')),
      el('p', {}, t('ai.consent.what')), el('p', {}, t('ai.consent.not')),
      el('p', {}, t('ai.consent.to', { to: `${t('ai.provider.' + cfg.provider)}${cfg.endpoint ? ' (' + cfg.endpoint + ')' : ''}` })),
      el('div', {}, checks),
      el('div', { class: 'row' },
        el('button', { type: 'button', class: 'btn', 'data-testid': 'ai-consent-agree', onclick: async () => {
          const picked = checks.map((c) => c.querySelector('input')).filter((i) => i.checked).map((i) => i.value);
          if (!picked.length) return;
          try { await post('/api/ai/consent', { repos: picked }); picked.forEach((p) => consented.add(p)); onAgree(); } catch (e) { out.replaceChildren(el('p', { class: 'warnbox' }, errText(e))); }
        } }, t('ai.consent.agree')),
        el('button', { type: 'button', class: 'btn ghost', onclick: () => draw() }, t('ai.consent.no'))));
  }

  async function send(question) {
    lastQuestion = question;
    const targets = repos().filter((r) => consented.has(r.path));
    if (!targets.length) { out.replaceChildren(consentBox(() => send(question))); return; }
    ctrl = new AbortController();
    const mine = ctrl;
    draw();
    announce(t('ai.generating'));
    try {
      const r = await post('/api/ai/ask', { config: loadConfig(), step: currentStep().n, question, lang: lang(), repos: targets.map((x) => x.path) }, mine.signal);
      if (ctrl !== mine) return;
      ctrl = null;
      showAnswer(r);
      announce(t('ai.done'));
    } catch (e) {
      if (mine.signal.aborted) return;
      ctrl = null;
      draw();
      out.replaceChildren(el('div', { class: 'warnbox', role: 'alert', 'data-testid': 'ai-error' }, errText(e)));
      announce(t('ai.failed'));
    }
  }

  function showAnswer(r) {
    draw();
    const evidence = el('details', { class: 'ai-evidence', 'data-testid': 'ai-evidence' }, el('summary', {}, t('ai.why')),
      el('p', {}, t('ai.why.step', { n: r.step, name: t(`step.${r.step}.name`) })),
      el('p', {}, t('ai.why.kinds', { kinds: r.sentKinds.map((k) => t('ai.kind.' + k)).join(t('ins.sep')) })),
      el('table', { class: 't' }, el('thead', {}, el('tr', {}, [t('col.id'), t('col.title'), t('col.status'), t('ai.col.known')].map((h) => el('th', {}, h)))),
        el('tbody', {}, r.ids.map((x) => {
          const node = resolveId(x.id), n = node && store.node(node);   // values from Studio's model, not from the AI text
          return el('tr', {}, el('td', { class: 'mono' }, node ? xrefLink(node, x.id) : x.id), el('td', {}, n?.title || ''), el('td', {}, n?.status || ''),
            el('td', {}, x.known && node ? t('ai.known') : t('ai.unknownId')));
        }))),
      el('details', {}, el('summary', {}, t('ai.sent')), el('pre', { class: 'ai-sent', 'data-testid': 'ai-sent' }, JSON.stringify(r.sent, null, 2))));
    const recs = r.recommendations.map((x) => el('p', { class: 'ai-rec', 'data-testid': 'ai-rec', 'data-valid': String(x.valid) },
      x.valid ? t('ai.rec', { q: x.question, o: x.option }) : t('ai.rec.none', { q: x.question })));
    const card = el('article', { class: 'ai-answer card', 'data-testid': 'ai-answer' },
      el('div', { class: 'ai-answer-head' }, el('span', { class: 'chip ai-derived', 'data-testid': 'ai-derived' }, icon('sparkle', { size: 16 }), t('ai.derived')),
        el('span', { class: 'mini', 'data-testid': 'ai-meta' }, t('ai.meta', { at: r.at, provider: t('ai.provider.' + r.provider), model: r.model }))),
      ...answerText(r.answer), ...recs, evidence,
      el('div', { class: 'row' },
        el('button', { type: 'button', class: 'btn ghost', 'data-testid': 'ai-copy', onclick: () => navigator.clipboard?.writeText(r.answer).then(() => toast(t('ai.copied'))) }, icon('copy', { size: 16 }), t('ai.copy')),
        el('button', { type: 'button', class: 'btn ghost', 'data-testid': 'ai-retry', onclick: () => send(lastQuestion) }, icon('retry', { size: 16 }), t('ai.again')),
        el('button', { type: 'button', class: 'btn ghost', 'data-testid': 'ai-dismiss', onclick: () => { out.replaceChildren(); q.focus(); } }, icon('close', { size: 16 }), t('ai.dismiss'))));
    out.replaceChildren(card);
  }

  function draw() {
    const s = currentStep().n;
    const head = el('div', { class: 'ai-dialog-head' }, icon('sparkle', { size: 20 }), el('h2', { id: 'aiAskTitle' }, t('ai.ask.title', { n: s, name: t(`step.${s}.name`) })),
      el('button', { type: 'button', class: 'btn ghost', 'data-testid': 'ai-settings-open', onclick: openSettings }, icon('settings', { size: 16 }), t('ai.settings')),
      el('button', { type: 'button', class: 'btn ghost', 'aria-label': t('ai.close'), 'data-testid': 'ai-close', onclick: close }, icon('close', { size: 16 })));
    if (!aiConfigured()) {
      box.replaceChildren(head, intro(false), el('p', { 'data-testid': 'ai-unset' }, t('ai.unset')),
        el('button', { type: 'button', class: 'btn', onclick: openSettings }, t('ai.settings.go')), live);
      return;
    }
    const busy = !!ctrl;
    const examples = el('div', { class: 'ai-examples', role: 'group', 'aria-label': t('ai.examples') },
      [1, 2, 3].map((i) => el('button', { type: 'button', class: 'chip', 'data-testid': 'ai-example', disabled: busy || null, onclick: () => { q.value = t(`ai.ex.${s}.${i}`); send(q.value); } }, t(`ai.ex.${s}.${i}`))));
    const actions = el('div', { class: 'row' },
      busy ? el('button', { type: 'button', class: 'btn', 'data-testid': 'ai-cancel', onclick: cancel }, t('ai.cancel'))
        : el('button', { type: 'button', class: 'btn', 'data-testid': 'ai-send', onclick: () => { if (q.value.trim()) send(q.value.trim()); } }, icon('sparkle', { size: 16 }), t('ai.send')),
      busy ? el('span', { class: 'mini', 'data-testid': 'ai-busy' }, el('span', { class: 'spin', 'aria-hidden': 'true' }), ' ', t('ai.generating')) : null);
    box.replaceChildren(head, intro(!seenIntro), examples, q, actions, out, live);
    seenIntro = true;
  }

  q.addEventListener('keydown', (e) => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); if (q.value.trim() && !ctrl) send(q.value.trim()); } });
  document.body.append(box);
  window.addEventListener('keydown', onKey);
  const onCfg = () => { if (!ctrl) draw(); };
  window.addEventListener('eabk-ai-config', onCfg);
  const offL = onLang(draw);
  const offLang = () => { offL(); window.removeEventListener('eabk-ai-config', onCfg); };
  draw();
  (aiConfigured() ? q : box).focus();
  panel = box;
}

export function aiCommands() {
  return [
    { cmd: true, id: 'cmd:ai:ask', label: t('cmd.ai.ask'), key: t('cmd.ai.ask') + ' AI', run: openAsk },
    { cmd: true, id: 'cmd:ai:settings', label: t('cmd.ai.settings'), key: t('cmd.ai.settings') + ' AI', run: openSettings },
  ];
}
