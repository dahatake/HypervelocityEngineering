// FR-1070 / FR-1071 / NFR-UX-015: 3D カメラのプリセット（平易な名称・説明＋内部は 4 要素）。
// 表（CAMERA_PRESETS）は 1 か所。WebGL 版（map3d.js）と Canvas 版（sz3d.js）が同じ表・同じ操作部品を使う。
//   4 要素 = Shot Size × Camera Angle × Camera Movement × Motion Character（語彙は VOCAB。別名は ALIASES）
//   外部通信・外部アセットなし。選択は画面を開いている間だけ保つ（storage には書かない）。
import { el } from './ui.js';
import { t } from './i18n.js';

export const VOCAB = Object.freeze({
  shot: ['EWS', 'WS', 'FS', 'MS', 'MCU', 'CU', 'ECU', 'MW'],
  angle: ['Eye Level', 'Low', 'High', "Bird's Eye", "Worm's Eye", 'Dutch', 'Over-the-Shoulder', 'POV'],
  movement: ['Static', 'Pan', 'Tilt', 'Dolly In', 'Dolly Out', 'Truck', 'Pedestal', 'Orbit', 'Crane', 'Handheld', 'Gimbal', 'Whip Pan', 'Zoom', 'Dolly Zoom', 'Roll', 'FPV Fly-through'],
  motion: ['Locked', 'Slow', 'Smooth', 'Floating', 'Natural', 'Energetic', 'Snappy', 'Aggressive', 'Hyperdynamic', 'Impossible'],
});
// 別名表（要求 FR-1070 の適用方式）: 依頼の語 → 語彙の語。
export const ALIASES = Object.freeze({ 'Medium Wide': 'MW', Wide: 'WS', 'Close-Up': 'CU', 'Medium Shot': 'MS', 'Macro Close-Up': 'ECU',
  'Push In': 'Dolly In', 'Handheld Follow': 'Handheld', 'FPV Tracking': 'FPV Fly-through', 'Organic': 'Natural' });

// 動きの強さ。cumulative offset = f(秒)。yaw/pitch はラジアン、zoom は対数（exp で倍率）。
//   yawRate: 一定の回転、yaw/pitch/zoom: [振幅, 角周波数]、shake: 手ぶれ（振幅）
// 落ち着き → 派手の順（AC-381）。
export const CAMERA_PRESETS = Object.freeze([
  { id: 'corporate', icon: 'M4 18l8-12 8 12z', shot: 'MW', angle: 'Eye Level', movement: 'Dolly In', motion: 'Smooth', m: { zoom: [0.06, 0.21], yaw: [0.04, 0.21] } },
  { id: 'interview', icon: 'M5 6h14v12H5zM9 10h6', shot: 'MCU', angle: 'Over-the-Shoulder', movement: 'Pan', motion: 'Slow', m: { yaw: [0.2, 0.35] } },
  { id: 'documentary', icon: 'M4 8h16v10H4zM8 8l2-3h4l2 3', shot: 'MS', angle: 'Eye Level', movement: 'Handheld', motion: 'Natural', m: { yaw: [0.08, 0.3], shake: 0.015 } },
  { id: 'cinematic', icon: 'M3 7h18v10H3zM3 11h18', shot: 'MCU', angle: 'Eye Level', movement: 'Dolly In', motion: 'Natural', m: { zoom: [0.12, 0.3], yaw: [0.05, 0.3] } },
  { id: 'product', icon: 'M12 4a8 8 0 1 0 8 8M12 4l3-2M12 4l3 2', shot: 'CU', angle: 'Low', movement: 'Orbit', motion: 'Floating', m: { yawRate: 0.35, pitch: [0.03, 0.8] } },
  { id: 'commercial', icon: 'M4 12h12M12 7l5 5-5 5', shot: 'ECU', angle: 'Eye Level', movement: 'Dolly Out', motion: 'Smooth→Energetic', m: { zoom: [0.22, 0.6], yaw: [0.08, 0.6] } },
  { id: 'anime', icon: 'M12 3l2.5 6 6.5.5-5 4 1.5 6.5L12 17l-5.5 3 1.5-6.5-5-4 6.5-.5z', shot: 'ECU→EWS', angle: 'Dutch', movement: 'Orbit', motion: 'Hyperdynamic', m: { yawRate: 1.1, zoom: [0.3, 1.4], pitch: [0.1, 1.1] } },
  { id: 'musicvideo', icon: 'M9 18V6l10-2v12M9 18a2 2 0 1 1-4 0 2 2 0 0 1 4 0zM19 16a2 2 0 1 1-4 0 2 2 0 0 1 4 0z', shot: 'MCU', angle: 'Low', movement: 'Orbit', motion: 'Aggressive', m: { yawRate: 0.8, pitch: [0.08, 2.4], zoom: [0.06, 2.4] } },
  { id: 'game', icon: 'M3 12l9-8 9 8-9 8zM12 8v8', shot: 'WS', angle: 'Low', movement: 'FPV Fly-through', motion: 'Hyperdynamic', m: { yawRate: 0.6, zoom: [0.35, 1.0], pitch: [0.15, 0.9], shake: 0.02 } },
]);
export const DEFAULT_PRESET = 'corporate';
export const FPS_MIN = 30;   // PARAM-047
export const presetOf = (id) => CAMERA_PRESETS.find((p) => p.id === id) || null;
export const normPreset = (id) => (presetOf(id) ? id : DEFAULT_PRESET);
export const parts = (v) => String(v).split('→').map((s) => s.trim());

// 実際に使う Camera Movement（動きの軽減・性能縮退のときは Static。選んだプリセットの情報は変えない）
export const effectiveMovement = (p, { reduced = false, degraded = false } = {}) => (reduced || degraded ? 'Static' : p.movement);

// 秒 s の時点の累積オフセット（動きの軽減・性能縮退では呼ばない）
export function motionAt(p, s) {
  const m = p.m || {}, w = (a) => (a ? a[0] * Math.sin(a[1] * s) : 0);
  const sh = m.shake ? m.shake * (Math.sin(s * 7.1) + 0.6 * Math.sin(s * 11.3 + 1)) : 0;
  return { yaw: (m.yawRate || 0) * s + w(m.yaw) + sh, pitch: w(m.pitch) + sh * 0.6, zoom: w(m.zoom) };
}
// フレーム間隔（ms）の列が下限（fps）を下回っているか
export function belowFps(frameMs, minFps = FPS_MIN) {
  const xs = frameMs.filter((x) => x > 0 && x < 500);
  if (xs.length < 20) return false;
  return 1000 / (xs.reduce((a, b) => a + b, 0) / xs.length) < minFps;
}

// ---- 操作部品。applyDelta({yaw, pitch, zoom}) は増分（zoom は対数）。呼び出し側が選択・ズーム・絞り込みを保つ。
let activeRig = null;
export function cameraCommands() {
  if (!activeRig) return [];
  const r = activeRig;
  return [...CAMERA_PRESETS.map((p) => ({ cmd: true, id: 'cmd:camera:' + p.id, label: t('cam3d.cmd') + t(`cam3d.${p.id}.n`),   key: t('cam3d.keys') + ' ' + p.id, run: () => r.select(p.id) })),
      { cmd: true, id: 'cmd:camera:stop', label: t('cam3d.cmd') + t('cam3d.stop'), key: t('cam3d.keys') + ' stop ' + t('cam3d.keys.stop'), run: () => r.stop() }];
}
let sessionPreset = DEFAULT_PRESET;

export function createCameraRig({ applyDelta, interact, minFps = FPS_MIN }) {
  const mq = window.matchMedia ? matchMedia('(prefers-reduced-motion: reduce)') : null;
  const st = { preset: normPreset(sessionPreset), auto: false, reduced: !!mq?.matches, degraded: false };
  let raf = 0, t0 = 0, last = null, prevT = 0, win0 = 0, frames = [], lows = 0, dead = false;
  const root = el('div', { class: 'cam3d', 'data-testid': 'camera-presets', role: 'group', 'aria-label': t('cam3d.label') });
  const live = el('div', { class: 'sr-only cam-live', role: 'status', 'aria-live': 'polite' });
  const detail = el('div', { class: 'cam-detail', 'data-testid': 'camera-detail' });
  const note = el('div', { class: 'cam-note mini' });
  const stopBtn = el('button', { type: 'button', class: 'cam-stop', 'data-testid': 'camera-stop', onclick: () => api.stop() }, t('cam3d.stop'));
  const resumeBtn = el('button', { type: 'button', class: 'cam-resume', 'data-testid': 'camera-resume', onclick: () => api.select(st.preset) }, t('cam3d.resume'));
  const items = new Map();

  function build() {
    items.clear();
    const list = CAMERA_PRESETS.map((p) => {
      const b = el('button', { type: 'button', class: 'cam-item', 'data-preset': p.id, 'aria-pressed': 'false', onclick: () => api.select(p.id) },
        el('span', { class: 'cam-icon', 'data-icon': p.id, 'aria-hidden': 'true', html: `<svg class="icon" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"><path d="${p.icon}"/></svg>` }),
        el('span', { class: 'cam-name' }, t(`cam3d.${p.id}.n`)),
        el('span', { class: 'cam-desc' }, t(`cam3d.${p.id}.d`)),
        el('span', { class: 'cam-mark', 'aria-hidden': 'true' }, ''));
      items.set(p.id, b);
      return b;
    });
    // 矢印キーでプリセット間を移動（Enter / Space で選択）。地図の操作とは別なので、手動のカメラ操作とは数えない
    const grp = el('div', { class: 'cam-list', role: 'group', onkeydown: (e) => {
      const ids = CAMERA_PRESETS.map((p) => p.id), i = ids.indexOf(e.target.dataset?.preset);
      if (i < 0 || !/^Arrow(Left|Right|Up|Down)$/.test(e.key)) return;
      const n = (i + (/Left|Up/.test(e.key) ? -1 : 1) + ids.length) % ids.length;
      items.get(ids[n]).focus(); e.preventDefault(); e.stopPropagation();
    } }, ...list);
    root.replaceChildren(el('div', { class: 'cam-title' }, t('cam3d.label')), grp, detail, el('div', { class: 'cam-ctl' }, stopBtn, resumeBtn), note, live);
  }
  function paint(announce) {
    const p = presetOf(st.preset), mv = effectiveMovement(p, st);
    root.dataset.cameraPreset = p.id; root.dataset.cameraAuto = String(st.auto);
    root.dataset.reducedMotion = String(st.reduced); root.dataset.degraded = String(st.degraded);
    for (const [id, b] of items) { const on = id === p.id; b.classList.toggle('on', on); b.setAttribute('aria-pressed', String(on)); b.querySelector('.cam-mark').textContent = on ? '✓' : ''; }
    Object.assign(detail.dataset, { shot: p.shot, angle: p.angle, movement: mv, motion: p.motion });
    detail.replaceChildren(el('div', { class: 'cam-dt' }, `${t('cam3d.current')}: ${t(`cam3d.${p.id}.n`)}`),
      ...[['shot', p.shot], ['angle', p.angle], ['movement', mv], ['motion', p.motion]].map(([k, v]) => el('div', { class: 'cam-row' }, el('span', { class: 'cam-k' }, t('cam3d.' + k)), el('span', { class: 'cam-v' }, v))));
    stopBtn.disabled = !st.auto; resumeBtn.hidden = st.auto || st.reduced || st.degraded;
    note.textContent = st.reduced ? t('cam3d.reduced') : st.degraded ? t('cam3d.degraded') : st.auto ? '' : t('cam3d.idle');
    if (announce) live.textContent = `${t('cam3d.current')}: ${t(`cam3d.${p.id}.n`)}${st.auto ? '' : ' / ' + t('cam3d.auto.off')}`;
  }
  function loop(ts) {
    raf = 0; if (dead || !st.auto) return;
    const p = presetOf(st.preset), s = (ts - t0) / 1000, cur = motionAt(p, s);
    applyDelta({ yaw: cur.yaw - last.yaw, pitch: cur.pitch - last.pitch, zoom: cur.zoom - last.zoom });
    last = cur;
    if (prevT && !document.hidden) frames.push(ts - prevT);
    prevT = ts;
    if (!win0) win0 = ts;
    if (frames.length >= 20 && ts - win0 >= 1500) {     // NFR-UX-015 AC-389: 下限を 2 区間（各 1.5 秒以上）続けて下回ったら静止へ縮退（保存値は書かない）
      lows = belowFps(frames, minFps) ? lows + 1 : 0; frames = []; win0 = ts;
      if (lows >= 2) { st.degraded = true; st.auto = false; paint(true); return; }
    }
    raf = requestAnimationFrame(loop);
  }
  function start() {
    cancelAnimationFrame(raf);
    if (st.reduced || st.degraded) { st.auto = false; return; }
    st.auto = true; t0 = performance.now(); last = { yaw: 0, pitch: 0, zoom: 0 }; prevT = 0; win0 = 0; frames = []; lows = 0;
    raf = requestAnimationFrame(loop);
  }
  const api = {
    el: root,
    select(id) {
      if (!presetOf(id)) return false;
      st.preset = id; sessionPreset = id; st.degraded = false;
      start(); paint(true); return true;
    },
    stop() { if (!st.auto) return; st.auto = false; cancelAnimationFrame(raf); paint(true); },   // 手動操作・Esc・停止ボタン
    auto: () => st.auto,
    camera() { const p = presetOf(st.preset); return { preset: p.id, shot: p.shot, angle: p.angle, movement: effectiveMovement(p, st), motion: p.motion, auto: st.auto, reducedMotion: st.reduced, degraded: st.degraded }; },
    refresh() { build(); paint(false); },
    destroy() { dead = true; cancelAnimationFrame(raf); mq?.removeEventListener?.('change', onMq); interact?.removeEventListener('pointerdown', manual, true); interact?.removeEventListener('wheel', manual, true); interact?.removeEventListener('keydown', onKey, true); document.removeEventListener('keydown', onEsc, true); if (activeRig === api) activeRig = null; },
  };
  // 手動のカメラ操作（ドラッグ・ホイール・ピンチ・キー）が始まったら自動動作を止める。プリセットの操作部品の中の操作は数えない。
  const inUi = (e) => !!e.target?.closest?.('.cam3d, .style3d, .legend3d, button, a, input');
  function manual(e) { if (!inUi(e)) api.stop(); }
  const KEYS = /^(Arrow(Left|Right|Up|Down)|[-+=_]|PageUp|PageDown|[qerf0-3])$/;
  function onKey(e) { if (!inUi(e) && KEYS.test(e.key)) api.stop(); }
  function onEsc(e) { if (e.key === 'Escape' && st.auto) { api.stop(); e.stopPropagation(); } }   // 自動動作はいつでも Esc で止められる（選択は解除しない）
  function onMq() { st.reduced = !!mq.matches; if (st.reduced) api.stop(); paint(false); }
  interact?.addEventListener('pointerdown', manual, true);
  interact?.addEventListener('wheel', manual, { capture: true, passive: true });
  interact?.addEventListener('keydown', onKey, true);
  document.addEventListener('keydown', onEsc, true);
  mq?.addEventListener?.('change', onMq);
  activeRig = api;
  build(); paint(false);
  return api;
}
