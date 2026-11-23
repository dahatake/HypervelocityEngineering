// FR-1094: the Product Manager's work steps at the top of the screen. Each step lists only the screens used for its
// decision (FR-1041's nine items each belong to at least one step); choosing a step opens its default screen.
import { t, onLang } from './i18n.js';
import { el, icon } from './ui.js';
import { store } from './store.js';

// key: a nav item (or 'release', the release judgment view of the implementation-status item); href: where it opens
export const STEPS = [
  { n: 1, main: 'dashboard', items: [{ key: 'dashboard' }] },
  { n: 2, main: 'tables', items: [{ key: 'tables', href: '#/tables?tab=reqs' }, { key: 'entities' }, { key: 'integrations' }] },
  { n: 3, main: 'source', items: [{ key: 'source', href: '#/floorplan' }, { key: 'map' }, { key: 'diagrams' }] },
  { n: 4, main: 'implstatus', items: [{ key: 'implstatus' }, { key: 'tables', href: '#/tables?tab=cases' }] },
  { n: 5, main: 'release', items: [{ key: 'release' }, { key: 'tables', href: '#/tables?tab=cases' }] },
  { n: 6, main: 'maintenance', items: [{ key: 'maintenance' }, { key: 'tables', href: '#/tables?tab=decisions' }] },
];
const RELEASE_ICON = { action: 'warning', ok: 'success', unknown: 'info' };

let current = 1;
const listeners = new Set();
export const currentStep = () => STEPS[current - 1];
export const onStep = (fn) => { listeners.add(fn); return () => listeners.delete(fn); };

// AC-515: a screen opened directly keeps the step when it belongs to it; otherwise the step whose default screen it is,
// else the lowest-numbered step that has it.
export function stepFor(key) {
  const cur = currentStep();
  if (cur.items.some((i) => i.key === key)) return cur.n;
  const main = STEPS.find((s) => s.main === key);
  if (main) return main.n;
  return (STEPS.find((s) => s.items.some((i) => i.key === key)) || STEPS[0]).n;
}

export function setStep(n, { open = false, target } = {}) {
  const changed = n !== current;
  current = n;
  if (changed) for (const fn of [...listeners]) fn(n);
  if (open) {
    const s = currentStep();
    const href = target(s.items.find((i) => i.key === s.main) || s.items[0]);
    if (location.hash !== href) location.hash = href;
    else if (changed) window.dispatchEvent(new HashChangeEvent('hashchange'));
  }
}

export function releaseBadge(release) {
  const state = release?.state || 'unknown';
  return el('span', { class: 'release-badge rb-' + state, 'data-testid': 'release-badge', 'data-state': state },
    icon(RELEASE_ICON[state] || 'info', { size: 16 }), el('span', {}, t('rel.state.' + state)));
}

// The bar: a list of numbered steps. Arrow keys move between them, Enter / Space opens one (roving tabindex).
export function renderStepBar(host, target) {
  const cur = currentStep().n;
  const buttons = STEPS.map((s) => {
    const on = s.n === cur;
    return el('button', {
      type: 'button', class: 'step' + (on ? ' on' : ''), 'data-step': String(s.n), 'data-testid': 'step',
      'aria-current': on ? 'step' : null, tabindex: on ? '0' : '-1', title: t(`step.${s.n}.judge`),
      onclick: () => setStep(s.n, { open: true, target }),
    },
    el('span', { class: 'step-num', 'aria-hidden': 'true' }, on ? icon('check', { size: 16 }) : String(s.n)),
    el('span', { class: 'step-name' }, el('span', { class: 'sr-only' }, t('step.label', { n: s.n }) + ' '), t(`step.${s.n}.name`)),
    on ? el('span', { class: 'step-here' }, t('step.here')) : null,
    s.n === 5 ? releaseBadge(store.model?.release) : null);
  });
  const list = el('ol', { class: 'steps-list' }, buttons.map((b) => el('li', {}, b)));
  list.addEventListener('keydown', (e) => {
    const i = buttons.indexOf(document.activeElement);
    if (i < 0) return;
    const next = e.key === 'ArrowRight' || e.key === 'ArrowDown' ? i + 1 : e.key === 'ArrowLeft' || e.key === 'ArrowUp' ? i - 1
      : e.key === 'Home' ? 0 : e.key === 'End' ? buttons.length - 1 : null;
    if (next === null) return;
    e.preventDefault();
    const b = buttons[(next + buttons.length) % buttons.length];
    buttons.forEach((x) => x.setAttribute('tabindex', x === b ? '0' : '-1'));
    b.focus();
  });
  host.setAttribute('aria-label', t('step.group'));
  const hadFocus = host.contains(document.activeElement);
  host.replaceChildren(list);
  if (hadFocus) buttons[cur - 1].focus();   // keyboard users stay on the bar after choosing a step
}

// AC-516: what to decide in this step, what this screen shows (the nav description) and the next step.
export function renderStepText(judgeEl, nextEl) {
  const s = currentStep();
  judgeEl.replaceChildren(el('b', {}, t('step.label', { n: s.n }) + ' ' + t(`step.${s.n}.name`) + ': '), t(`step.${s.n}.judge`));
  const nxt = STEPS[s.n] || null;
  nextEl.replaceChildren(nxt
    ? el('span', {}, t('step.next') + ' ', el('b', {}, t('step.label', { n: nxt.n }) + ' ' + t(`step.${nxt.n}.name`)))
    : el('span', {}, t('step.restart')));
}

export function stepCommands(target) {
  return STEPS.map((s) => ({ cmd: true, id: 'cmd:step:' + s.n, label: t('cmd.step') + t('step.label', { n: s.n }) + ' ' + t(`step.${s.n}.name`),
    key: t(`step.${s.n}.name`) + ' ' + t('step.label', { n: s.n }), run: () => setStep(s.n, { open: true, target }) }));
}

onLang(() => listeners.forEach((fn) => fn(current)));
