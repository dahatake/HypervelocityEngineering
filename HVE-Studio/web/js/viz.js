// 動的な可視化の小部品（FR-1080 / NFR-UX-018）。d3 は同梱せず、外部通信もしない。
// 使い方: const v = region(page, 'dashboard', { items: '[data-viz-key]', keyOf }); 描画の前に v.snap()、描画の後に v.sync()。
//  - キー付きデータ結合: キーが同じ要素は DOM 要素を再利用（update）、新規は enter、消える要素は exit（フェードアウト後に除去）。
//  - 補間: 位置・大きさ・色・不透明度を {PARAM-058}ms 以内の Web Animations で補間する（最終状態は補間なしと同一）。
//  - 連続更新: snap() が進行中のアニメーションと exit の残りを即座に確定し、最新の状態へ向かう。
//  - ホバー・フォーカス: data-hover、ほかの減光（data-dim）、role=tooltip（離れる・Esc で消える）。
//  - prefers-reduced-motion: data-reduced-motion="true"、補間なし（即時切替。PARAM-037）。

export const MAX_MS = 600; // PARAM-058
const DUR = 360;
const TWEEN_PROPS = ['width', 'height', 'left', 'top', 'backgroundColor', 'color', 'opacity'];
const CAP = 300; // 補間を取る要素数の上限（それ以上は即時）

const mq = typeof matchMedia === 'function' ? matchMedia('(prefers-reduced-motion: reduce)') : null;
export const reduced = () => !!mq?.matches;
const regions = new Set();
mq?.addEventListener?.('change', () => regions.forEach((r) => { r.root.dataset.reducedMotion = String(reduced()); }));

/** 要素にイベントを登録し、再利用（adopt）時に付け替えられるよう記録する。 */
export function on(node, type, fn, opts) {
  node.addEventListener(type, fn, opts);
  (node._on ||= []).push([type, fn, opts]);
  return node;
}

function adopt(oldEl, newEl) {
  for (const [t, f, o] of oldEl._on || []) oldEl.removeEventListener(t, f, o);
  oldEl._on = [];
  for (const a of [...oldEl.attributes]) if (!a.name.startsWith('data-viz') && a.name !== 'data-hover' && a.name !== 'data-dim' && !newEl.hasAttribute(a.name)) oldEl.removeAttribute(a.name);
  for (const a of [...newEl.attributes]) if (!a.name.startsWith('data-viz') && oldEl.getAttribute(a.name) !== a.value) oldEl.setAttribute(a.name, a.value);
  for (const [t, f, o] of newEl._on || []) on(oldEl, t, f, o);
  for (const k of Object.keys(newEl)) if (k.startsWith('_') && k !== '_on') oldEl[k] = newEl[k];
  oldEl.replaceChildren(...newEl.childNodes);
}

const readStyle = (e) => { const cs = getComputedStyle(e); const o = {}; for (const p of TWEEN_PROPS) o[p] = cs[p]; return o; };

let tipEl = null;
function tip() {
  if (!tipEl) {
    tipEl = document.createElement('div');
    tipEl.setAttribute('role', 'tooltip');
    tipEl.className = 'viz-tooltip';
    tipEl.hidden = true;
    tipEl.id = 'viz-tooltip';
    document.body.append(tipEl);
  }
  return tipEl;
}
function hideAll() {
  if (tipEl) { tipEl.hidden = true; tipEl.textContent = ''; }   // 隠したツールチップに古い文言を残さない
  for (const r of regions) {
    r.root.querySelectorAll('[data-hover="true"]').forEach((n) => { n.removeAttribute('data-hover'); n.removeAttribute('aria-describedby'); });
    r.root.querySelectorAll('[data-dim="true"]').forEach((n) => n.removeAttribute('data-dim'));
    r.root.removeAttribute('data-hovering');
  }
}
if (typeof document !== 'undefined') document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && tipEl && !tipEl.hidden) hideAll(); });

/**
 * ホイールで拡大・縮小、ドラッグで移動（AC-442）。host が data-zoom / data-pan を公開する。
 * apply(z, x, y): 内容の変換を適用する（CSS transform など）。opt.skip: ドラッグを始めない要素のセレクター、opt.origin(): 内容の座標系の基準要素。
 * 状態 st（{z,x,y}）は呼び出し側が持つので、再描画をまたいで保たれる。
 */
export function zoomPan(host, apply, st = { z: 1, x: 0, y: 0 }, opt = {}) {
  const publish = () => {
    host.dataset.zoom = String(+st.z.toFixed(3));
    host.dataset.pan = `${Math.round(st.x)},${Math.round(st.y)}`;
    apply(st.z, st.x, st.y);
  };
  publish();
  on(host, 'wheel', (e) => {
    e.preventDefault();
    const b = (opt.origin ? opt.origin() : host).getBoundingClientRect();
    const mx = e.clientX - b.left, my = e.clientY - b.top; // 基準要素（変換されない外枠）の中での位置
    const z2 = Math.max(opt.min ?? 0.3, Math.min(opt.max ?? 5, st.z * Math.exp(-e.deltaY * 0.0015)));
    const k = z2 / st.z;
    st.x = mx - (mx - st.x) * k; st.y = my - (my - st.y) * k; // カーソルの下の点を保つ
    st.z = z2;
    publish();
  }, { passive: false });
  let drag = null;
  on(host, 'pointerdown', (e) => {
    if (e.button !== 0 || e.target.closest?.(opt.skip || '[data-viz-nodrag]')) return;
    drag = { x: e.clientX, y: e.clientY, sx: st.x, sy: st.y, id: e.pointerId };
  });
  on(host, 'pointermove', (e) => {
    if (!drag || e.pointerId !== drag.id) return;
    const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
    if (!drag.on && Math.hypot(dx, dy) < 3) return;
    if (!drag.on) { drag.on = true; try { host.setPointerCapture(e.pointerId); } catch { /* ignore */ } }
    st.x = drag.sx + dx; st.y = drag.sy + dy;
    publish();
  });
  const end = () => { drag = null; };
  on(host, 'pointerup', end);
  on(host, 'pointercancel', end);
  on(host, 'click', (e) => { if (drag?.on || host._justDragged) { e.stopPropagation(); e.preventDefault(); } }, true);
  on(host, 'pointerup', () => { if (drag?.on) { host._justDragged = true; setTimeout(() => { host._justDragged = false; }, 0); } }, true);
  return { st, publish, reset() { Object.assign(st, { z: 1, x: 0, y: 0 }); publish(); } };
}

export function nameOf(n) {
  return (n.getAttribute('aria-label') || n.getAttribute('title') || n.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 200);
}

/**
 * 可視化の領域（ルート要素）を作る。
 * @param root 領域のルート要素（data-viz などを公開する）
 * @param name 要素の名前（data-viz）
 * @param opt  { items: 項目のセレクター, keyOf(el): キー（既定は data-viz-key）, tooltip(el): ツールチップの文字列 }
 */
export function region(root, name, opt = {}) {
  const itemSel = opt.items || '[data-viz-key]';
  const keyOf = opt.keyOf || ((n) => n.getAttribute('data-viz-key'));
  const r = { root, name, pending: new Set(), ghosts: [], old: new Map(), epoch: 0 };
  regions.add(r);
  root.dataset.viz = name;
  root.dataset.vizState = 'idle';
  root.dataset.vizTransition = 'settled';
  root.dataset.reducedMotion = String(reduced());
  const count = () => { root.dataset.vizCount = String([...root.querySelectorAll(itemSel)].filter((n) => !n.hasAttribute('data-viz-ghost')).length); };
  count();

  const finish = (epoch) => {
    if (epoch !== r.epoch) return;
    root.querySelectorAll('[data-viz-state]').forEach((n) => { if (n !== root && n.getAttribute('data-viz-state') !== 'exit') n.setAttribute('data-viz-state', 'idle'); });
    for (const g of r.ghosts) g.remove();
    r.ghosts = [];
    root.dataset.vizState = 'idle';
    root.dataset.vizTransition = opt.hold?.() ? 'running' : 'settled'; // hold: force 風の動きが続いている間は running のまま
    count();
  };
  const settleNow = () => {
    r.epoch++;
    root.getAnimations?.({ subtree: true }).forEach((a) => { try { a.cancel(); } catch { /* ignore */ } });
    for (const g of r.ghosts) g.remove();
    r.ghosts = [];
    root.querySelectorAll('[data-viz-ghost]').forEach((g) => g.remove());
    root.querySelectorAll('[data-viz-state]').forEach((n) => { if (n !== root) n.setAttribute('data-viz-state', 'idle'); });
    root.dataset.vizState = 'idle';
    root.dataset.vizTransition = 'settled';
  };

  r.settle = settleNow; // 動きを確定して settled にする（force 風の動きの終了時）

  // 描画の前: 進行中の動きを確定し、現在の項目（要素・見た目・位置の隣）を記録する。
  r.snap = () => {
    settleNow();
    hideAll();
    const old = new Map();
    const els = [...root.querySelectorAll(itemSel)];
    els.forEach((n, i) => {
      const k = keyOf(n);
      if (k == null || old.has(k)) return;
      const prev = n.previousElementSibling, next = n.nextElementSibling;
      old.set(k, { el: n, style: i < CAP ? readStyle(n) : null, prevKey: prev && prev.matches?.(itemSel) ? keyOf(prev) : null, nextKey: next && next.matches?.(itemSel) ? keyOf(next) : null, parent: n.parentElement });
    });
    r.old = old;
  };

  // 描画の後: キーで突き合わせ、update（要素を再利用）・enter・exit を適用して補間する。
  r.sync = () => {
    const old = r.old;
    r.old = new Map();
    const red = reduced();
    root.dataset.reducedMotion = String(red);
    const items = [...root.querySelectorAll(itemSel)];
    const seen = new Set();
    const fresh = [];
    const updated = [];
    const entered = [];
    let idx = 0;
    for (const n of items) {
      const k = keyOf(n);
      if (k == null || seen.has(k)) continue;
      seen.add(k);
      const o = old.get(k);
      if (!o) { fresh.push(n); if (old.size) entered.push(n); continue; }
      let target = n;
      if (o.el !== n && !root.contains(o.el)) { // 古い要素を、新しい要素の場所へ移して中身を差し替える（DOM 要素の再利用）
        adopt(o.el, n);
        n.replaceWith(o.el);
        target = o.el;
      }
      updated.push({ n: target, from: idx < CAP ? o.style : null });
      idx++;
    }
    const exiting = [];
    if (old.size && !red) {
      for (const [k, o] of old) {
        if (seen.has(k) || exiting.length >= 100) continue;
        const ghost = o.el;
        if (root.contains(ghost)) continue;
        // 消える要素: 隣だった要素の近くに置き直し、フェードアウト後に取り除く。
        let anchor = null;
        for (const [kk, pos] of [[o.prevKey, 'after'], [o.nextKey, 'before']]) {
          if (kk == null) continue;
          const a = [...root.querySelectorAll(itemSel)].find((x) => keyOf(x) === kk);
          if (a) { anchor = [a, pos]; break; }
        }
        if (!anchor) continue;
        ghost.setAttribute('data-viz-ghost', 'true');
        ghost.setAttribute('aria-hidden', 'true');
        ghost.removeAttribute('data-testid');
        ghost.removeAttribute('tabindex');
        ghost.style.pointerEvents = 'none';
        ghost.setAttribute('data-viz-state', 'exit');
        anchor[0][anchor[1]](ghost);
        exiting.push(ghost);
      }
    }
    r.ghosts = exiting;
    count();
    if (!old.size || red) { // 初回の描画・動きの軽減: 補間なしで最終状態へ（即時切替）
      root.querySelectorAll('[data-viz-state]').forEach((n) => { if (n !== root) n.setAttribute('data-viz-state', 'idle'); });
      root.dataset.vizState = 'idle';
      root.dataset.vizTransition = 'settled';
      return;
    }
    // 状態の公開と補間
    const epoch = ++r.epoch;
    for (const n of entered) n.setAttribute('data-viz-state', 'enter');
    for (const u of updated) u.n.setAttribute('data-viz-state', 'update');
    root.dataset.vizState = exiting.length ? 'exit' : entered.length ? 'enter' : 'update';
    root.dataset.vizTransition = 'running';
    const anims = [];
    const dur = Math.min(DUR, MAX_MS);
    const opt2 = { duration: dur, easing: 'ease-out', fill: 'none' };
    const after = updated.map((u) => (u.from ? readStyle(u.n) : null)); // 一度にまとめて読む
    updated.forEach((u, i) => {
      if (!u.from || !after[i]) return;
      const a = {}, b = {};
      for (const p of TWEEN_PROPS) if (u.from[p] !== after[i][p]) { a[p] = u.from[p]; b[p] = after[i][p]; }
      if (Object.keys(a).length && u.n.animate) anims.push(u.n.animate([a, b], opt2));
    });
    for (const n of entered.slice(0, CAP)) if (n.animate) anims.push(n.animate([{ opacity: 0 }, { opacity: 1 }], opt2));
    for (const g of exiting) if (g.animate) anims.push(g.animate([{ opacity: 1 }, { opacity: 0 }], { ...opt2, fill: 'forwards' }));
    const timer = setTimeout(() => finish(epoch), dur + 40);
    if (!anims.length) { clearTimeout(timer); finish(epoch); return; }
    Promise.allSettled(anims.map((a) => a.finished)).then(() => { clearTimeout(timer); finish(epoch); });
  };

  // ホバー・フォーカス: 強調、ほかの減光、ツールチップ（名前と値）
  const show = (n) => {
    if (n.hasAttribute('data-viz-ghost')) return;
    hideAll();
    n.setAttribute('data-hover', 'true');
    root.setAttribute('data-hovering', 'true');
    if (opt.dim !== false) for (const o of root.querySelectorAll(itemSel)) if (o !== n && !n.contains(o) && !o.contains(n)) o.setAttribute('data-dim', 'true');
    const text = (opt.tooltip ? opt.tooltip(n) : nameOf(n));
    if (!text) return;
    const tp = tip();
    tp.textContent = text;
    tp.hidden = false;
    n.setAttribute('aria-describedby', tp.id);
    const b = n.getBoundingClientRect();
    tp.style.left = Math.max(4, Math.min(innerWidth - 8, b.left + b.width / 2)) + 'px';
    tp.style.top = Math.max(4, b.top - 6) + 'px';
  };
  const target = (e) => e.target?.closest?.(itemSel);
  on(root, 'mouseover', (e) => { const n = target(e); if (n && root.contains(n)) show(n); });
  on(root, 'mouseout', (e) => { const n = target(e); if (n && !n.contains(e.relatedTarget)) hideAll(); });
  on(root, 'focusin', (e) => { const n = target(e); if (n && root.contains(n)) show(n); });
  on(root, 'focusout', () => hideAll());
  r.takeFrom = (o) => { r.old = o.old; o.old = new Map(); };
  r.destroy = () => { regions.delete(r); hideAll(); };
  return r;
}
