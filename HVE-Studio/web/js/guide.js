// 「初めての方へ」: a wizard that highlights one part of the current screen at a time on a dimmed page and explains it in a card.
import { t, onLang } from './i18n.js';
import { el, icon } from './ui.js';

const GUIDED = ['dashboard', 'implstatus', 'map', 'diagrams', 'entities', 'integrations', 'source', 'tables', 'maintenance'];
const CONTROLS = '#view .toolbar, #view [role=tablist], #view .tabs, #view .controls, #view .seg';

const stepsFor = (key) => [
  { sel: '#nav', h: 'guide.nav.h', b: 'guide.nav.b' },
  { sel: '#view', h: `guide.${key}.1h`, b: `guide.${key}.1b` },
  { sel: CONTROLS, fallback: '#view', h: `guide.${key}.2h`, b: `guide.${key}.2b` },
  { sel: '.top .search', h: 'guide.search.h', b: 'guide.search.b' },
  { sel: '#lang', h: 'guide.end.h', b: 'guide.end.b' },
];

const visible = (n) => { const r = n.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
const find = (s) => [...document.querySelectorAll(s.sel)].find(visible) || (s.fallback && document.querySelector(s.fallback)) || null;

let active = null;

export function closeGuide() { active?.close(); }

export function startGuide(navKey) {
  closeGuide();
  const key = GUIDED.includes(navKey) ? navKey : 'dashboard';
  const steps = stepsFor(key);
  let i = 0;
  const opener = document.activeElement;
  const spot = el('div', { class: 'guide-spot', 'aria-hidden': 'true' });
  const card = el('div', { class: 'guide-card', role: 'dialog', 'aria-modal': 'true', 'aria-label': t('guide.dialog'), tabindex: '-1', 'data-testid': 'guide-card' });
  const root = el('div', { class: 'guide-root', 'data-testid': 'guide' }, el('div', { class: 'guide-shield' }), spot, card);

  const close = () => {
    window.removeEventListener('resize', place);
    window.removeEventListener('keydown', onKey, true);
    off();
    root.remove();
    active = null;
    if (opener && opener.focus) opener.focus();
  };
  const go = (d) => { const n = i + d; if (n < 0) return; if (n >= steps.length) return close(); i = n; draw(); };
  const onKey = (e) => {
    if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); close(); }
    else if (e.key === 'ArrowRight') { e.preventDefault(); go(1); }
    else if (e.key === 'ArrowLeft') { e.preventDefault(); go(-1); }
  };

  function place() {
    const target = find(steps[i]);
    const pad = 6, vw = innerWidth, vh = innerHeight;
    let r = target ? target.getBoundingClientRect() : { left: vw / 2, top: vh / 2, width: 0, height: 0 };
    const x = Math.max(0, r.left - pad), y = Math.max(0, r.top - pad);
    const w = Math.min(vw - x, r.width + pad * 2), h = Math.min(vh - y, r.height + pad * 2);
    Object.assign(spot.style, { left: x + 'px', top: y + 'px', width: w + 'px', height: h + 'px' });
    const cw = Math.min(card.offsetWidth || 340, vw - 16), ch = card.offsetHeight || 200;
    const big = h > vh * 0.6;       // a tall target (the whole screen): the card sits inside it, near the bottom
    let top = big ? y + h - ch - 24 : (y + h + 12 + ch <= vh ? y + h + 12 : Math.max(8, y - ch - 12));
    let left = big ? x + w - cw - 24 : Math.min(Math.max(8, x), vw - cw - 8);
    top = Math.min(Math.max(8, top), vh - ch - 8);
    left = Math.min(Math.max(8, left), vw - cw - 8);
    Object.assign(card.style, { left: left + 'px', top: top + 'px', width: cw + 'px' });
  }

  function draw() {
    const s = steps[i], last = i === steps.length - 1;
    find(s)?.scrollIntoView?.({ block: 'nearest', inline: 'nearest' });
    card.replaceChildren(
      el('div', { class: 'guide-head' }, icon('guide', { size: 20 }), el('strong', {}, t(s.h)), el('span', { class: 'guide-count' }, t('guide.step', { n: i + 1, m: steps.length }))),
      el('p', { class: 'guide-body' }, t(s.b)),
      el('p', { class: 'guide-hint' }, t('guide.hint')),
      el('div', { class: 'guide-actions' },
        el('button', { type: 'button', class: 'btn ghost', onclick: close, 'data-testid': 'guide-skip' }, t('guide.skip')),
        el('span', { class: 'guide-spacer' }),
        i > 0 ? el('button', { type: 'button', class: 'btn ghost', onclick: () => go(-1), 'data-testid': 'guide-prev' }, t('guide.prev')) : null,
        el('button', { type: 'button', class: 'btn', onclick: () => go(1), 'data-testid': 'guide-next' }, last ? t('guide.done') : t('guide.next'))));
    place();
    card.querySelector('[data-testid=guide-next]').focus({ preventScroll: true });
  }

  const off = onLang(draw);
  document.body.append(root);
  window.addEventListener('resize', place);
  window.addEventListener('keydown', onKey, true);
  active = { close };
  draw();
}
