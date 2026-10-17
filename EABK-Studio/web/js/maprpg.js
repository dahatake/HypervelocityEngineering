// FR-1053 / FR-1054 / FR-1055 / NFR-UX-012: the map shown as an 8-bit style 2D role-playing field.
// Castles = business goals (G-ID), towns = entities. Walk with the keyboard, talk at an entrance to read the content.
// Everything (pixel art, sound) is generated here; nothing is fetched from outside (AC-291, AC-292, AC-299).
import { lang, onLang } from './i18n.js';
import { store } from './store.js';
import { el } from './ui.js';
import { xrefLink } from './xref.js';
import { runDim } from './dim.js';
import { view as zoomView, dataOf, thresholds, stateOf, isArch } from './semzoom.js';
import { buildWorld, stepOn, placeAt, DIRS, buttonOf } from './rpgworld.js';
import { createAudio } from './rpgaudio.js';
import { mount as mount2d } from './map2d.js';

const INITIAL_MUTED = true;     // PARAM-041: sound is off until the user turns it on
const MIN_FPS = 30;             // PARAM-040
const TILE = 32;
const STEP_MS = 130;            // walking pace; also the minimum interval between held-key steps (AC-296)
const TYPE_MS = 35;             // typewriter pace of the dialog

const TXT = {
  ja: {
    title: 'RPG 風マップ', area: 'RPG 風の地図。方向キーで歩き、城や街の入口で決定キーを押すと話せます。Tab で他の部分へ移れます。',
    castle: '城', town: '街', goal: '目的', entity: 'データ種別（エンティティ）', hero: '旅人', villager: '住人', guide: '案内役',
    sound: '音', on: 'オン', off: 'オフ（ミュート）', soundBtn: '音の入切', pos: '現在位置', field: '野外', at: '{k} {n} の入口',
    reqs: '関連する要求: {n} 件', repr: '代表: {ids}', noreq: '関連する要求はまだありません。', nodesc: '説明はまだありません。',
    start: 'スタート', select: 'セレクト', help: '操作の割り当て', close: '閉じる', to2d: '2D で表示', to3d: '3D で表示', toRpg: 'RPG 風で表示',
    keysTitle: '操作の割り当て', btn: 'ボタン', keys: 'キー', dpad: '十字キー', a: 'A（決定・話す・調べる）', b: 'B（取消・閉じる・戻る）',
    kDpad: '方向キー または W A S D', kA: 'Enter または Z', kB: 'Esc または X（Backspace も可）', kStart: 'Space（メニュー）', kSel: 'Shift だけを押す（音の入切・表示の切替）',
    legend: '十字=方向キー/WASD　A=Enter/Z　B=Esc/X　スタート=Space　セレクト=Shift　（Tab で他の部分へ）',
    alt: '同じ内容を表で見る', cols: '名前 / ID', kind: '種別', where: '位置', rel: '関連する要求', roads: '道（つながり）',
    fbNone: 'この管理データには、{what}がないため、RPG 風の地図を作れません。2D で表示しています。同じ内容は表でも確認できます。',
    fbGoal: '目的（城）', fbEnt: 'エンティティ（街）', fbCtx: 'この環境では RPG 風を描画できないため、2D で表示しています。同じ内容は表でも確認できます。',
    itemsStart: '', blockedMsg: '通れない', menuOpen: 'メニューを開きました', menuClosed: 'メニューを閉じました', talk: '{n} と話しています。',
    undef: '（名称未定義の目的）',
  },
  en: {
    title: 'RPG-style map', area: 'RPG-style map. Walk with the arrow keys and press the confirm key at a castle or town entrance to talk. Tab moves to other parts of the page.',
    castle: 'Castle', town: 'Town', goal: 'Goal', entity: 'Data kind (entity)', hero: 'Traveler', villager: 'Villager', guide: 'Guide',
    sound: 'Sound', on: 'On', off: 'Off (muted)', soundBtn: 'Toggle sound', pos: 'Position', field: 'Open field', at: 'At the entrance of {k} {n}',
    reqs: 'Related requirements: {n}', repr: 'e.g. {ids}', noreq: 'No related requirements yet.', nodesc: 'No description yet.',
    start: 'Start', select: 'Select', help: 'Controls', close: 'Close', to2d: 'Show in 2D', to3d: 'Show in 3D', toRpg: 'Show as RPG-style',
    keysTitle: 'Controls', btn: 'Button', keys: 'Keys', dpad: 'D-pad', a: 'A (confirm / talk / examine)', b: 'B (cancel / close / back)',
    kDpad: 'Arrow keys or W A S D', kA: 'Enter or Z', kB: 'Esc or X (Backspace also works)', kStart: 'Space (menu)', kSel: 'Press Shift alone (sound / view mode)',
    legend: 'D-pad = arrows/WASD  A = Enter/Z  B = Esc/X  Start = Space  Select = Shift  (Tab leaves the map)',
    alt: 'See the same content as a table', cols: 'Name / ID', kind: 'Kind', where: 'Position', rel: 'Related requirements', roads: 'Roads (links)',
    fbNone: 'This data has no {what}, so the RPG-style map cannot be built. 2D is shown. The table has the same content.',
    fbGoal: 'goals (castles)', fbEnt: 'entities (towns)', fbCtx: 'RPG-style cannot be drawn in this environment, so 2D is shown. The table has the same content.',
    itemsStart: '', blockedMsg: 'Blocked', menuOpen: 'Menu opened', menuClosed: 'Menu closed', talk: 'Talking at {n}.',
    undef: '(goal without a name)',
  },
};
const tr = (k, v) => { let s = (TXT[lang()] || TXT.ja)[k] ?? TXT.ja[k] ?? k; for (const [a, b] of Object.entries(v || {})) s = s.replace('{' + a + '}', b); return s; };

// ---------------------------------------------------------------- data (castles = goals, towns = entities)
export function collect(model) {
  const reqs = model.reqs || [];
  const goalIds = new Map((model.goals || []).map((g) => [g.id, g.title || '']));
  for (const r of reqs) if (r.goal && /^G-[A-Z0-9_-]+$/.test(r.goal) && !goalIds.has(r.goal)) goalIds.set(r.goal, '');   // referenced but not declared
  const castles = [...goalIds].map(([id, title]) => {
    const rs = reqs.filter((r) => r.goal === id).map((r) => r.id).sort();
    return { id, name: id, text: title, reqIds: rs };
  });
  const ents = model.entities?.entities || [];
  const towns = ents.map((e) => ({ id: 'ent:' + e.name, name: e.name, text: e.description || '', reqIds: reqs.filter((r) => (r.entities || []).includes(e.name)).map((r) => r.id).sort() }));
  const roads = [];
  const byEntity = new Set(ents.map((e) => e.name));
  for (const r of model.entities?.relations || []) if (r.scope === 'entity' && byEntity.has(r.from) && byEntity.has(r.to)) roads.push({ from: 'ent:' + r.from, to: 'ent:' + r.to, kind: r.kind });
  const seen = new Set();
  for (const r of reqs) for (const e of r.entities || []) {
    const k = r.goal + '>' + e;
    if (r.goal && byEntity.has(e) && goalIds.has(r.goal) && !seen.has(k)) { seen.add(k); roads.push({ from: r.goal, to: 'ent:' + e, kind: 'goal' }); }
  }
  return { castles, towns, roads };
}

// ---------------------------------------------------------------- pixel art (drawn with rectangles; no image files)
const PAL = { grass: '#3f9b46', grass2: '#368a3d', path: '#c9a36a', path2: '#b58d55', water: '#2f6fd6', water2: '#6fa4ff', stone: '#9aa3b5', stone2: '#6d7689', roof: '#c8483c', wall: '#f0e2c0', door: '#6b3f1d', ink: '#1b2440', skin: '#f4c9a0', flag: '#ffd23f' };
function r(ctx, c, x, y, w, h) { ctx.fillStyle = c; ctx.fillRect(Math.round(x), Math.round(y), Math.ceil(w), Math.ceil(h)); }
function drawGround(ctx, x, y, s, gx, gy, kind, frame) {
  const p = s / 8;
  if (kind === 'water') {
    r(ctx, PAL.water, x, y, s, s);
    const o = (frame + gx + gy) % 2 ? 0 : 2;
    r(ctx, PAL.water2, x + (1 + o) * p, y + 2 * p, 2 * p, p); r(ctx, PAL.water2, x + (4 - o) * p, y + 5 * p, 2 * p, p);
    return;
  }
  if (kind === 'path') { r(ctx, PAL.path, x, y, s, s); if ((gx * 7 + gy * 3) % 5 === 0) r(ctx, PAL.path2, x + 2 * p, y + 3 * p, p, p); return; }
  r(ctx, (gx + gy) % 2 ? PAL.grass : PAL.grass2, x, y, s, s);
  if ((gx * 5 + gy * 11) % 7 === 0) { r(ctx, '#6cc06c', x + 2 * p, y + 5 * p, p, p); r(ctx, '#6cc06c', x + 5 * p, y + 2 * p, p, p); }
}
function drawBridge(ctx, x, y, s) { const p = s / 8; r(ctx, '#8a5a2b', x, y, s, s); for (let i = 0; i < 4; i++) r(ctx, '#b07a3d', x + p, y + (i * 2 + 0.5) * p, 6 * p, p); }
function drawCastle(ctx, x, y, s) {       // x,y = left cell of the 3-cell body
  const p = s / 8, w = 3 * s;
  r(ctx, PAL.stone2, x, y + 3 * p, w, s - 3 * p);
  r(ctx, PAL.stone, x + p, y + 2 * p, w - 2 * p, s - 2 * p);
  for (let i = 0; i < 6; i++) r(ctx, PAL.stone, x + i * (w / 6), y + p, w / 12 + 1, p * 1.2);
  r(ctx, PAL.stone, x + s, y - 3 * p, s, 5 * p); r(ctx, PAL.stone2, x + s, y - 3 * p, s, p);
  r(ctx, PAL.ink, x + 1.25 * s, y - p, p, 2 * p); r(ctx, PAL.ink, x + 1.6 * s, y - p, p, 2 * p);
  r(ctx, PAL.ink, x + 1.5 * s, y - 6 * p, p / 2 + 1, 3 * p); r(ctx, PAL.flag, x + 1.5 * s + p / 2, y - 6 * p, 2 * p, p * 1.4);
  r(ctx, PAL.door, x + 1.25 * s, y + 4.5 * p, 0.5 * s, s - 4.5 * p);
}
function drawHouse(ctx, x, y, s) {
  const p = s / 8;
  r(ctx, PAL.wall, x + p, y + 3 * p, 6 * p, 5 * p);
  r(ctx, PAL.roof, x, y + p, s, 3 * p); r(ctx, '#8d2f27', x, y + 3 * p, s, p / 2 + 1);
  r(ctx, PAL.ink, x + 1.5 * p, y + 4.5 * p, 1.5 * p, 1.5 * p); r(ctx, PAL.ink, x + 5 * p, y + 4.5 * p, 1.5 * p, 1.5 * p);
}
function drawDoor(ctx, x, y, s, kind) {
  const p = s / 8;
  r(ctx, PAL.path2, x, y, s, s);
  r(ctx, kind === 'castle' ? '#e04b3a' : '#2c5fb3', x + 2 * p, y + 6 * p, 4 * p, p);                 // mat: castle = red, town = blue (also named in the label)
  r(ctx, PAL.door, x + 3 * p, y + 2 * p, 2 * p, 3 * p);
}
// characters: kind = hero | villager | guide; dir = up | down | left | right; frame = 0 | 1 (walk cycle)
const CHAR = { hero: { body: '#2f6fd6', hair: '#6b3f1d', extra: '#ffd23f' }, villager: { body: '#3fa65a', hair: '#d9a441', extra: '#fff' }, guide: { body: '#8a4fd0', hair: '#cfcfe6', extra: '#ffd23f' } };
export function drawChar(ctx, kind, dir, frame, x, y, s) {
  const c = CHAR[kind], p = s / 8, lift = frame ? -p / 2 : 0;
  r(ctx, 'rgba(0,0,0,.25)', x + 1.5 * p, y + 7 * p, 5 * p, p);
  const legOff = frame ? p : 0;
  r(ctx, PAL.ink, x + 2.5 * p, y + 6 * p + lift, 1.2 * p, 1.5 * p + (frame ? 0 : 0)); r(ctx, PAL.ink, x + 4.3 * p, y + 6 * p + lift + legOff * 0.5, 1.2 * p, 1.5 * p);
  r(ctx, c.body, x + 2 * p, y + 3.5 * p + lift, 4 * p, 3 * p);
  r(ctx, c.extra, x + 2 * p, y + 5 * p + lift, 4 * p, p / 2 + 1);
  r(ctx, PAL.skin, x + 2.5 * p, y + 0.5 * p + lift, 3 * p, 3 * p);
  if (dir === 'up') r(ctx, c.hair, x + 2.3 * p, y + 0.3 * p + lift, 3.4 * p, 3 * p);
  else {
    r(ctx, c.hair, x + 2.3 * p, y + 0.3 * p + lift, 3.4 * p, 1.2 * p);
    const ex = dir === 'left' ? -0.5 : dir === 'right' ? 0.5 : 0;
    if (dir === 'down' || dir === 'left') r(ctx, PAL.ink, x + (3.1 + ex) * p, y + 2 * p + lift, 0.6 * p, 0.8 * p);
    if (dir === 'down' || dir === 'right') r(ctx, PAL.ink, x + (4.5 + ex) * p, y + 2 * p + lift, 0.6 * p, 0.8 * p);
  }
  if (kind === 'guide') r(ctx, '#5b2fa0', x + 2 * p, y + lift - 0.4 * p, 4 * p, 1 * p);          // pointed hat
  if (kind === 'hero') r(ctx, PAL.skin, dir === 'left' ? x + 1 * p : x + 6 * p, y + 4 * p + lift, p, 1.5 * p);
}

// ---------------------------------------------------------------- mount
export function mount(host) {
  const model = store.model;
  const data = collect(model);
  const d = dataOf(model, isArch());
  const th = thresholds(model);
  const ctx2d = (() => { try { return document.createElement('canvas').getContext('2d'); } catch { return null; } })();
  const missing = !data.towns.length ? 'fbEnt' : !data.castles.length ? 'fbGoal' : null;
  if (!ctx2d || !d || missing) return mountFallback(host, data, missing ? tr('fbNone', { what: tr(missing) }) : tr('fbCtx'));

  const world = buildWorld(data.castles, data.towns);
  const placeById = new Map(world.places.map((p) => [p.id, p]));
  const reduce = () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
  const audio = createAudio({ initialMuted: INITIAL_MUTED });

  // start at the selected entity's town (NFR-UX-006: the selection survives the switch), else on the road below the castles
  const sel = zoomView.selected ? placeById.get('ent:' + zoomView.selected) : null;
  const player = sel ? { x: sel.x, y: sel.y, dir: 'down' } : { ...world.start, dir: 'down' };
  const npcs = world.places.map((p) => ({ kind: p.kind === 'castle' ? 'guide' : 'villager', x: p.x + 1, y: p.y, dir: 'left', place: p.id }));
  let anim = null, frame = 0, lastStep = 0, shiftPure = false;
  const ui = { dialog: null, menu: null, help: false, msg: '' };       // dialog: {place, full, shown, done} ; menu: {kind, items, idx}
  let dead = false, raf = 0, dirty = true, W = 0, H = 0, lastDraw = 0, fpsFrames = 0, fpsT = performance.now(), fps = 60, drawMs = 0, ambient = 0, typeT = 0;

  // ---- DOM
  const canvas = el('canvas', { class: 'rpg-canvas', 'aria-hidden': 'true' });
  const live = el('div', { class: 'sr-only', role: 'status', 'aria-live': 'polite', 'data-testid': 'rpg-live' });
  const posEl = el('span', { class: 'rpg-pos', 'data-testid': 'rpg-pos' });
  const soundBtn = el('button', { type: 'button', class: 'btn ghost rpg-sound', 'data-testid': 'rpg-sound', onclick: () => toggleSound() });
  const dialogEl = el('div', { class: 'rpg-dialog', 'data-testid': 'rpg-dialog', hidden: true });
  const menuEl = el('div', { class: 'rpg-menu', 'data-testid': 'rpg-menu', hidden: true });
  const selectEl = el('div', { class: 'rpg-menu rpg-select', 'data-testid': 'rpg-select', hidden: true });
  const legend = el('p', { class: 'rpg-legend', 'data-testid': 'rpg-legend' });
  const alt = el('details', { class: 'sz-alt rpg-alt', 'data-testid': 'rpg-alt' });
  const stage = el('div', { class: 'rpg-stage' }, canvas, dialogEl, menuEl, selectEl);
  const root = el('section', { class: 'rpg', tabindex: '0', role: 'group', 'aria-roledescription': 'RPG', 'data-testid': 'rpg-view', 'data-ready': 'false' },
    el('div', { class: 'rpg-bar' }, el('h1', { class: 'rpg-title' }, ''), posEl, soundBtn), stage, legend, alt, live);
  host.append(root);
  const heading = root.querySelector('h1');

  let altLang = null;
  const scene = () => { const p = placeAt(world, player.x, player.y); return p ? p.kind : 'field'; };
  const say = (s) => { live.textContent = ''; setTimeout(() => { if (!dead) live.textContent = s; }, 30); };

  function placeText(p) { return `${tr(p.kind)} ${p.name}（${p.kind === 'castle' ? tr('goal') : tr('entity')} ${p.id}）`; }
  function fullText(p) {
    const n = p.reqIds.length;
    return [placeText(p), p.text || tr('nodesc'), n ? tr('reqs', { n }) + '　' + tr('repr', { ids: p.reqIds.slice(0, 3).join('、') }) : tr('noreq')].join('\n');
  }

  // ---- text
  function renderStatic() {
    heading.textContent = tr('title');
    root.setAttribute('aria-label', tr('area'));
    const muted = audio.muted;
    soundBtn.textContent = `${muted ? '🔇' : '🔊'} ${tr('sound')}: ${muted ? tr('off') : tr('on')}`;
    soundBtn.setAttribute('aria-pressed', muted ? 'false' : 'true');
    soundBtn.title = tr('soundBtn');
    legend.textContent = tr('legend');
    const p = placeAt(world, player.x, player.y);
    posEl.textContent = `${tr('pos')}: ${p ? tr('at', { k: tr(p.kind), n: p.name }) : tr('field')} (${player.x}, ${player.y})`;
    if (altLang !== lang()) { altLang = lang(); alt.replaceChildren(el('summary', {}, tr('alt')), altTable()); }   // the table only changes with the language
  }
  function altTable() {
    return el('div', {},
      el('table', { class: 'tbl' }, el('thead', {}, el('tr', {}, [tr('cols'), tr('kind'), tr('where'), tr('rel')].map((x) => el('th', {}, x)))),
        el('tbody', {}, world.places.map((p) => el('tr', { 'data-place': p.id }, el('td', {}, `${p.name} / ${p.id.replace(/^ent:/, '')}`), el('td', {}, tr(p.kind)), el('td', {}, `${p.x}, ${p.y}`), el('td', {}, p.reqIds.length ? p.reqIds.join(', ') : '—'))))),
      el('p', { class: 'mini' }, `${tr('roads')}: ${data.roads.length}`),
      el('ul', { class: 'mini rpg-roads' }, data.roads.slice(0, 200).map((rd) => el('li', {}, `${rd.from.replace(/^ent:/, '')} → ${rd.to.replace(/^ent:/, '')}`))));
  }
  function renderDialog() {
    const dlg = ui.dialog;
    dialogEl.hidden = !dlg;
    if (!dlg) { dialogEl.replaceChildren(); return; }
    const p = dlg.place, links = el('div', { class: 'rpg-links' });
    if (dlg.done) for (const id of p.reqIds.slice(0, 3)) links.append(xrefLink(id), ' ');
    dialogEl.replaceChildren(el('div', { class: 'rpg-text', 'aria-hidden': 'true' }, dlg.full.slice(0, dlg.shown)), links,
      el('div', { class: 'rpg-more', 'aria-hidden': 'true' }, dlg.done ? '▼ A / Enter' : ''));
  }
  const menuItems = (kind) => {
    const sound = { id: 'sound', label: () => `${audio.muted ? '🔇' : '🔊'} ${tr('soundBtn')}: ${audio.muted ? tr('off') : tr('on')}` };
    const modes = [{ id: 'to2d', label: () => tr('to2d') }, { id: 'to3d', label: () => tr('to3d') }];
    return kind === 'start' ? [{ id: 'help', label: () => '❓ ' + tr('help') }, sound, ...modes, { id: 'close', label: () => tr('close') }] : [sound, ...modes];
  };
  function renderMenu() {
    for (const [kind, box] of [['start', menuEl], ['select', selectEl]]) {
      const m = ui.menu && ui.menu.kind === kind ? ui.menu : null;
      box.hidden = !m;
      if (!m) { box.replaceChildren(); continue; }
      const items = m.items.map((it, i) => el('li', { role: 'menuitem', class: 'rpg-item' + (i === m.idx ? ' on' : ''), 'aria-current': i === m.idx ? 'true' : null, onclick: () => { m.idx = i; activateMenu(); } }, (i === m.idx ? '▶ ' : '　') + it.label()));
      const kids = [el('div', { class: 'rpg-name' }, kind === 'start' ? tr('start') : tr('select')), el('ul', { role: 'menu', class: 'rpg-list' }, items)];
      if (kind === 'start' && ui.help) kids.push(keysTable());
      box.replaceChildren(...kids);
    }
  }
  function keysTable() {
    const row = (a, b) => el('tr', {}, el('th', { scope: 'row' }, a), el('td', {}, b));
    return el('table', { class: 'tbl rpg-keys', 'data-testid': 'rpg-keys' }, el('caption', {}, tr('keysTitle')),
      el('thead', {}, el('tr', {}, el('th', {}, tr('btn')), el('th', {}, tr('keys')))),
      el('tbody', {}, row(tr('dpad'), tr('kDpad')), row(tr('a'), tr('kA')), row(tr('b'), tr('kB')), row(tr('start'), tr('kStart')), row(tr('select'), tr('kSel'))));
  }
  const refresh = () => { renderStatic(); renderDialog(); renderMenu(); dirty = true; };

  // ---- actions
  function setScene() { audio.setScene(scene()); }
  function toggleSound() { audio.setMuted(!audio.muted); audio.play('confirm'); refresh(); say(`${tr('sound')}: ${audio.muted ? tr('off') : tr('on')}`); }
  function openDialog(p) {
    if (p.kind === 'town' && p.id.startsWith('ent:')) zoomView.selected = p.id.slice(4);        // the selection follows the talk (NFR-UX-006)
    const full = fullText(p);
    ui.dialog = { place: p, full, shown: reduce() ? full.length : 0, done: reduce() };
    audio.play('confirm'); refresh(); say(tr('talk', { n: p.name }) + ' ' + full.replace(/\n/g, ' '));
  }
  function closeDialog() { ui.dialog = null; audio.play('cancel'); refresh(); }
  function openMenu(kind) { ui.menu = { kind, items: menuItems(kind), idx: 0 }; ui.help = false; audio.play('menu'); refresh(); say(tr('menuOpen')); }
  function closeMenu() { ui.menu = null; ui.help = false; audio.play('cancel'); refresh(); say(tr('menuClosed')); }
  function activateMenu() {
    const m = ui.menu; if (!m) return;
    const it = m.items[m.idx];
    if (it.id === 'help') { ui.help = !ui.help; audio.play('confirm'); refresh(); }
    else if (it.id === 'sound') { toggleSound(); ui.menu = null; refresh(); }
    else if (it.id === 'close') closeMenu();
    else if (it.id === 'to2d' || it.id === 'to3d') { audio.play('confirm'); runDim(it.id === 'to2d' ? '2d' : '3d'); }
  }
  function walk(dir, now) {
    if (now - lastStep < STEP_MS) return;
    const from = { x: player.x, y: player.y };
    const res = stepOn(world, player, dir);
    player.dir = dir; lastStep = now;
    if (res.moved) {
      player.x = res.x; player.y = res.y; frame ^= 1;
      anim = reduce() ? null : { from, t0: now };
      audio.play('move'); setScene(); refresh();
      const p = placeAt(world, player.x, player.y);
      if (p) say(tr('at', { k: tr(p.kind), n: p.name }));
    } else { audio.play('blocked'); dirty = true; }
  }
  function pressA() {
    if (ui.menu) return activateMenu();
    const dlg = ui.dialog;
    if (dlg) {
      if (!dlg.done) { dlg.shown = dlg.full.length; dlg.done = true; audio.play('confirm'); refresh(); } else closeDialog();
      return;
    }
    const p = placeAt(world, player.x, player.y);
    if (p) openDialog(p);
    else {
      const near = npcs.find((n) => n.x === player.x + DIRS[player.dir][0] && n.y === player.y + DIRS[player.dir][1]);
      if (near) openDialog(placeById.get(near.place)); else audio.play('blocked');
    }
  }
  // B: close the dialog / menu, otherwise hand the focus to the rest of the page so the map is never a keyboard trap (AC-298).
  function pressB() {
    if (ui.dialog) return closeDialog();
    if (ui.menu) return closeMenu();
    leaveFocus();
  }
  function leaveFocus() {
    const target = document.querySelector('[data-testid="dim-toggle"] button.on') || document.getElementById('q');
    target?.focus();
  }

  function onKey(e) {
    const tag = e.target?.tagName || '';
    if (/INPUT|TEXTAREA|SELECT/.test(tag) || e.target?.isContentEditable) return;          // typing stays typing (AC-297)
    if (e.key === 'Shift') { if (!e.repeat) shiftPure = !e.ctrlKey && !e.metaKey && !e.altKey; return; }
    if (e.key === 'Tab') { shiftPure = false; return; }                                     // Tab / Shift+Tab move the focus as usual
    shiftPure = false;
    if (/^A$|BUTTON/.test(tag) && (e.key === 'Enter' || e.key === ' ')) return;              // a focused link / button keeps its own behaviour
    const b = buttonOf(e);
    if (!b) return;
    const now = performance.now();
    if (DIRS[b]) {
      e.preventDefault();
      if (ui.menu) { if (!e.repeat) { const n = ui.menu.items.length; ui.menu.idx = (ui.menu.idx + (b === 'down' || b === 'right' ? 1 : n - 1)) % n; audio.play('menu'); refresh(); } return; }
      if (ui.dialog) return;
      walk(b, now);
      return;
    }
    if (e.repeat) { e.preventDefault(); return; }                                            // holding a button never repeats it (AC-296)
    e.preventDefault();
    if (b === 'a') pressA();
    else if (b === 'b') { e.stopPropagation(); pressB(); }
    else if (b === 'start') { if (ui.menu?.kind === 'start') closeMenu(); else if (!ui.dialog) openMenu('start'); }
  }
  function onKeyUp(e) {
    if (e.key !== 'Shift') return;
    const pure = shiftPure; shiftPure = false;
    if (!pure || ui.dialog) return;
    if (ui.menu?.kind === 'select') closeMenu(); else openMenu('select');                    // Select = Shift alone
  }
  root.addEventListener('keydown', onKey);
  root.addEventListener('keyup', onKeyUp);
  root.addEventListener('blur', () => { shiftPure = false; }, true);

  // ---- drawing
  const ctx = canvas.getContext('2d');
  function resize() {
    const rc = stage.getBoundingClientRect();
    W = Math.max(200, Math.floor(rc.width)); H = Math.max(160, Math.floor(rc.height));
    canvas.width = W; canvas.height = H; dirty = true;
  }
  const ro = new ResizeObserver(resize); ro.observe(stage);
  const visualPos = (now) => {
    if (!anim) return { x: player.x, y: player.y };
    const k = Math.min(1, (now - anim.t0) / STEP_MS);
    if (k >= 1) { anim = null; return { x: player.x, y: player.y }; }
    return { x: anim.from.x + (player.x - anim.from.x) * k, y: anim.from.y + (player.y - anim.from.y) * k };
  };
  function groundKind(gx, gy) {
    if (world.blocked.has(world.key(gx, gy)) && gy === world.pondY) return 'water';
    if (gy === world.pondY) return 'bridge';
    return world.pathRows.has(gy) ? 'path' : 'grass';
  }
  function draw(now) {
    const t0 = performance.now();
    ctx.imageSmoothingEnabled = false;
    ctx.fillStyle = '#10182c'; ctx.fillRect(0, 0, W, H);
    const vp = visualPos(now);
    const camX = vp.x * TILE + TILE / 2 - W / 2, camY = vp.y * TILE + TILE / 2 - H / 2;
    const gx0 = Math.max(0, Math.floor(camX / TILE)), gx1 = Math.min(world.width - 1, Math.ceil((camX + W) / TILE));
    const gy0 = Math.max(0, Math.floor(camY / TILE)), gy1 = Math.min(world.height - 1, Math.ceil((camY + H) / TILE));
    const fr = reduce() ? 0 : ambient;
    for (let gy = gy0; gy <= gy1; gy++) for (let gx = gx0; gx <= gx1; gx++) {
      const k = groundKind(gx, gy), x = gx * TILE - camX, y = gy * TILE - camY;
      if (k === 'bridge') drawBridge(ctx, x, y, TILE); else drawGround(ctx, x, y, TILE, gx, gy, k, fr);
    }
    // roads: thin dotted lines between connected places (only those touching the view)
    ctx.save(); ctx.strokeStyle = 'rgba(255,255,255,.35)'; ctx.setLineDash([3, 5]); ctx.lineWidth = 1;
    let n = 0;
    for (const rd of data.roads) {
      const a = placeById.get(rd.from), b = placeById.get(rd.to);
      if (!a || !b) continue;
      const ax = a.x * TILE - camX + TILE / 2, ay = a.y * TILE - camY + TILE / 2, bx = b.x * TILE - camX + TILE / 2, by = b.y * TILE - camY + TILE / 2;
      if ((ax < -TILE || ax > W + TILE || ay < -TILE || ay > H + TILE) && (bx < -TILE || bx > W + TILE || by < -TILE || by > H + TILE)) continue;
      if (++n > 400) break;
      ctx.beginPath(); ctx.moveTo(ax, ay); ctx.lineTo(bx, by); ctx.stroke();
    }
    ctx.restore();
    ctx.font = 'bold 11px ui-monospace, Consolas, monospace'; ctx.textAlign = 'center';
    for (const p of world.places) {
      if (p.x < gx0 - 2 || p.x > gx1 + 2 || p.y < gy0 - 2 || p.y > gy1 + 2) continue;
      const x = p.x * TILE - camX, y = p.y * TILE - camY;
      if (p.kind === 'castle') drawCastle(ctx, x - TILE, y - TILE, TILE); else drawHouse(ctx, x, y - TILE, TILE);
      drawDoor(ctx, x, y, TILE, p.kind);
      const label = `${p.kind === 'castle' ? '🏰' : '⌂'} ${p.name}`;
      const w = ctx.measureText(label).width + 8;
      ctx.fillStyle = 'rgba(10,16,34,.8)'; ctx.fillRect(x + TILE / 2 - w / 2, y - TILE - 16, w, 14);
      ctx.fillStyle = '#fff'; ctx.fillText(label, x + TILE / 2, y - TILE - 5);
    }
    ctx.font = '10px ui-monospace, Consolas, monospace';
    for (const npc of npcs) {
      if (npc.x < gx0 - 1 || npc.x > gx1 + 1 || npc.y < gy0 - 1 || npc.y > gy1 + 1) continue;
      const x = npc.x * TILE - camX, y = npc.y * TILE - camY;
      drawChar(ctx, npc.kind, npc.dir, reduce() ? 0 : (ambient >> 1) & 1, x, y, TILE);
      ctx.fillStyle = 'rgba(10,16,34,.8)'; ctx.fillRect(x - 2, y - 11, TILE + 4, 11);
      ctx.fillStyle = '#fff'; ctx.fillText(tr(npc.kind), x + TILE / 2, y - 2);
    }
    drawChar(ctx, 'hero', player.dir, anim && !reduce() ? frame : 0, vp.x * TILE - camX, vp.y * TILE - camY, TILE);
    drawMs_set(performance.now() - t0);
  }
  const drawMs_set = (v) => { drawMs = drawMs * 0.8 + v * 0.2; };

  function loop(now) {
    if (dead) return;
    raf = requestAnimationFrame(loop);
    fpsFrames++;
    if (now - fpsT >= 1000) { fps = Math.round((fpsFrames * 1000) / (now - fpsT)); fpsFrames = 0; fpsT = now; }
    if (ui.dialog && !ui.dialog.done && now - typeT >= TYPE_MS) {
      typeT = now; ui.dialog.shown = Math.min(ui.dialog.full.length, ui.dialog.shown + 1);
      if (ui.dialog.shown % 3 === 0) audio.play('text');
      if (ui.dialog.shown >= ui.dialog.full.length) ui.dialog.done = true;
      renderDialog();
    }
    const amb = reduce() ? 0 : Math.floor(now / 450);
    if (amb !== ambient) { ambient = amb; dirty = true; }
    if (anim) dirty = true;
    if (dirty) { dirty = false; draw(now); lastDraw = now; }
  }

  const offLang = onLang(refresh);
  setScene(); resize(); refresh();
  raf = requestAnimationFrame(loop);
  root.setAttribute('data-ready', 'true');
  if (document.activeElement === document.body || document.activeElement?.closest?.('[data-testid="dim-toggle"]')) root.focus({ preventScroll: true });

  // published state (window.eabkView) for tests and assistive checks
  const getState = () => ({
    ...stateOf(d, th), dim: 'rpg', mode: 'rpg',
    rpg: {
      map: { width: world.width, height: world.height, blocked: [...world.blocked].map((k) => k.split(',').map(Number)) },
      player: { x: player.x, y: player.y, dir: player.dir },
      places: world.places.map((p) => ({ id: p.id, kind: p.kind, name: p.name, x: p.x, y: p.y })),
      roads: data.roads.map((x) => ({ ...x })),
      characters: [{ kind: 'hero', role: tr('hero'), x: player.x, y: player.y }, ...npcs.map((n) => ({ kind: n.kind, role: tr(n.kind), x: n.x, y: n.y }))],
      dialog: { open: !!ui.dialog, placeId: ui.dialog?.place.id ?? null, complete: !!ui.dialog?.done },
      menu: { open: ui.menu?.kind === 'start' }, select: { open: ui.menu?.kind === 'select' },
      muted: audio.muted, audio: { started: audio.started, scene: audio.scene, requested: { ...audio.stats.requested }, scenes: [...audio.stats.scenes] },
      reducedMotion: !!reduce(), perf: { fps, drawMs: Math.round(drawMs * 10) / 10, minFps: MIN_FPS },
    },
  });
  const viewApi = { mode: 'rpg', getState, setScale: (n) => { zoomView.scale = n; }, select: (n) => { zoomView.selected = n; } };
  window.eabkView = viewApi;

  return {
    destroy() {
      dead = true; cancelAnimationFrame(raf); ro.disconnect(); offLang(); audio.destroy();
      if (window.eabkView === viewApi) delete window.eabkView;
    },
  };
}

// AC-290: no goals / no entities / no 2D canvas -> show the 2D map with the reason and a table, never an error.
function mountFallback(host, data, reason) {
  const inner = mount2d(host);
  const rows = [...data.castles.map((c) => [c.name, tr('castle'), c.reqIds.length]), ...data.towns.map((c) => [c.name, tr('town'), c.reqIds.length])];
  const box = el('div', { class: 'warnbox', role: 'alert', 'data-testid': 'rpg-fallback', style: { position: 'absolute', left: '14px', top: '84px', right: '14px', zIndex: 9, maxHeight: '40%', overflow: 'auto' } },
    el('p', {}, reason),
    el('details', { class: 'sz-alt' }, el('summary', {}, tr('alt')),
      el('table', { class: 'tbl' }, el('thead', {}, el('tr', {}, [tr('cols'), tr('kind'), tr('rel')].map((x) => el('th', {}, x)))), el('tbody', {}, rows.map((r2) => el('tr', {}, r2.map((c) => el('td', {}, String(c)))))))));
  host.append(box);
  return { destroy() { box.remove(); inner?.destroy?.(); } };
}

